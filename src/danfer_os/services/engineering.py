import base64
import io
import math
import re

import ezdxf
from ezdxf import bbox

from danfer_os.models.engineering import DxfAnalysis, DxfUpload, NestingSuggestion


class DxfAnalysisError(ValueError):
    pass


class EngineeringService:
    _quantity_patterns = [
        re.compile(r"(?:QTD|QTDE)[-_ ]?(\d+)", re.IGNORECASE),
        re.compile(r"(?:^|[-_ ])X(\d+)(?:$|[-_ .])", re.IGNORECASE),
        re.compile(r"\[(\d+)\]"),
    ]

    @classmethod
    def analyze(cls, upload: DxfUpload) -> DxfAnalysis:
        try:
            content = base64.b64decode(upload.content_base64, validate=True)
            document = ezdxf.read(io.StringIO(content.decode("utf-8", errors="ignore")))
        except Exception as error:
            raise DxfAnalysisError("arquivo DXF inválido ou não suportado") from error
        modelspace = document.modelspace()
        entities = list(modelspace)
        if not entities:
            raise DxfAnalysisError("DXF sem geometria")
        try:
            bounds = bbox.extents(entities, fast=True)
            width = max(bounds.extmax.x - bounds.extmin.x, 0)
            height = max(bounds.extmax.y - bounds.extmin.y, 0)
        except Exception as error:
            raise DxfAnalysisError("não foi possível calcular as dimensões") from error
        cut_length = 0.0
        area = 0.0
        piercings = 0
        warnings = []
        for entity in entities:
            kind = entity.dxftype()
            try:
                if kind == "LINE":
                    cut_length += entity.dxf.start.distance(entity.dxf.end)
                elif kind == "CIRCLE":
                    radius = entity.dxf.radius
                    cut_length += 2 * math.pi * radius
                    area += math.pi * radius**2
                    piercings += 1
                elif kind == "ARC":
                    angle = math.radians((entity.dxf.end_angle - entity.dxf.start_angle) % 360)
                    cut_length += entity.dxf.radius * angle
                elif kind == "LWPOLYLINE":
                    points = [(point[0], point[1]) for point in entity.get_points()]
                    for first, second in zip(points, points[1:]):
                        cut_length += math.dist(first, second)
                    if entity.closed and len(points) > 2:
                        cut_length += math.dist(points[-1], points[0])
                        polygon_area = abs(sum(
                            points[index][0] * points[(index + 1) % len(points)][1]
                            - points[(index + 1) % len(points)][0] * points[index][1]
                            for index in range(len(points))
                        )) / 2
                        area += polygon_area
                        piercings += 1
                elif kind in {"SPLINE", "ELLIPSE"}:
                    warnings.append(f"{kind}: comprimento aproximado não calculado")
            except Exception:
                warnings.append(f"{kind}: geometria ignorada parcialmente")
        envelope_area = width * height
        if area <= 0:
            area = envelope_area
            warnings.append("área estimada pelo envelope externo")
        fill_factor = min(area / envelope_area * 100, 100) if envelope_area else 0
        suggestion = (
            NestingSuggestion.FORCE
            if fill_factor < 80 or len(warnings) > 1
            else NestingSuggestion.AUTOMATIC
        )
        stem = upload.filename.rsplit(".", 1)[0]
        quantity = 1
        for pattern in cls._quantity_patterns:
            match = pattern.search(stem)
            if match:
                quantity = int(match.group(1))
                break
        description = re.sub(
            r"(?:QTD|QTDE)[-_ ]?\d+|(?:^|[-_ ])X\d+|\[\d+\]",
            "",
            stem,
            flags=re.IGNORECASE,
        ).replace("_", " ").strip(" -")
        return DxfAnalysis(
            filename=upload.filename,
            description=description or stem,
            suggested_quantity=quantity,
            width_mm=round(width, 3),
            height_mm=round(height, 3),
            cut_length_mm=round(cut_length, 3),
            net_area_mm2=round(area, 3),
            piercings=piercings,
            fill_factor_percent=round(fill_factor, 2),
            nesting_suggestion=suggestion,
            warnings=sorted(set(warnings)),
        )
