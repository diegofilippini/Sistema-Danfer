import base64
from decimal import Decimal, ROUND_HALF_UP
import io
import math
import re

import ezdxf
from ezdxf import bbox

from danfer_os.models.engineering import (
    DxfAnalysis, DxfQuoteDraftRequest, DxfUpload, NestingPart, NestingPlacement,
    NestingBatchPlan, NestingPlan, NestingRequest, NestingSheet, NestingSuggestion, SheetEvaluation,
)
from danfer_os.models.commercial import QuoteItemCreate, QuoteProcess


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

    @staticmethod
    def _arrange(parts: list[NestingPart], sheet: NestingSheet, gap: float, edge: float) -> tuple[list[NestingPlacement], list[str]]:
        expanded: list[tuple[str, int, float, float, bool]] = []
        for part in parts:
            expanded.extend((part.code, index, part.width_mm, part.height_mm, part.allow_rotation) for index in range(1, part.quantity + 1))
        expanded.sort(key=lambda item: (max(item[2], item[3]), item[2] * item[3]), reverse=True)
        max_x, max_y = sheet.width_mm - edge, sheet.length_mm - edge
        shelves: list[dict[str, float]] = []
        placements: list[NestingPlacement] = []
        unplaced: list[str] = []
        for code, sequence, original_w, original_h, allow_rotation in expanded:
            orientations = [(original_w, original_h, False)]
            if allow_rotation and original_w != original_h:
                orientations.append((original_h, original_w, True))
            candidate = None
            for shelf_index, shelf in enumerate(shelves):
                for width, height, rotated in orientations:
                    if height <= shelf["height"] and shelf["x"] + width <= max_x:
                        score = (shelf["height"] - height, shelf["x"])
                        if candidate is None or score < candidate[0]:
                            candidate = (score, shelf_index, width, height, rotated)
            if candidate is None:
                next_y = edge if not shelves else shelves[-1]["y"] + shelves[-1]["height"] + gap
                possible = [(w, h, r) for w, h, r in orientations if edge + w <= max_x and next_y + h <= max_y]
                if possible:
                    width, height, rotated = min(possible, key=lambda item: item[1])
                    shelves.append({"x": edge, "y": next_y, "height": height})
                    candidate = ((0, edge), len(shelves) - 1, width, height, rotated)
            if candidate is None:
                unplaced.append(f"{code} #{sequence}")
                continue
            _, shelf_index, width, height, rotated = candidate
            shelf = shelves[shelf_index]
            placements.append(NestingPlacement(
                code=code, sequence=sequence, x_mm=round(shelf["x"], 3), y_mm=round(shelf["y"], 3),
                width_mm=round(width, 3), height_mm=round(height, 3), rotated=rotated,
            ))
            shelf["x"] += width + gap
        return placements, unplaced

    @classmethod
    def nesting(cls, data: NestingRequest) -> NestingPlan:
        evaluations: list[tuple[NestingSheet, list[NestingPlacement], list[str], float]] = []
        for sheet in data.sheets:
            placements, unplaced = cls._arrange(data.parts, sheet, data.gap_mm, data.edge_margin_mm)
            used = sum(item.width_mm * item.height_mm for item in placements)
            utilization = used / (sheet.width_mm * sheet.length_mm) * 100
            evaluations.append((sheet, placements, unplaced, utilization))
        baseline = evaluations[0]
        selected = baseline
        reason = "chapa padrão selecionada"
        for option in evaluations[1:]:
            if len(option[2]) < len(selected[2]):
                selected = option
                reason = "alternativa acomoda mais peças"
            elif len(option[2]) == len(selected[2]) and option[3] >= selected[3] + data.alternative_minimum_gain_percent:
                selected = option
                reason = f"ganho mínimo de {data.alternative_minimum_gain_percent:g}% atingido"
        comparison = [SheetEvaluation(
            sheet=sheet, placed_count=len(placements), unplaced_count=len(unplaced),
            utilization_percent=round(utilization, 2), waste_percent=round(100 - utilization, 2),
        ) for sheet, placements, unplaced, utilization in evaluations]
        sheet, placements, unplaced, utilization = selected
        return NestingPlan(
            selected_sheet=sheet, placements=placements, unplaced=unplaced,
            utilization_percent=round(utilization, 2), waste_percent=round(100 - utilization, 2),
            comparison=comparison, selection_reason=reason,
        )

    @classmethod
    def nesting_batch(cls, data: NestingRequest) -> NestingBatchPlan:
        """Avalia todas as peças em quantas chapas forem necessárias."""
        evaluations = []
        total_requested = sum(part.quantity for part in data.parts)
        for sheet in data.sheets:
            remaining = {part.code: part.quantity for part in data.parts}
            definitions = {part.code: part for part in data.parts}
            sheet_count = placed_total = 0
            while sum(remaining.values()) and sheet_count < 1000:
                batch = [definitions[code].model_copy(update={"quantity": quantity})
                         for code, quantity in remaining.items() if quantity]
                placements, _ = cls._arrange(batch, sheet, data.gap_mm, data.edge_margin_mm)
                if not placements:
                    break
                sheet_count += 1
                placed_total += len(placements)
                for placement in placements:
                    remaining[placement.code] -= 1
            used_area = sum(
                part.width_mm * part.height_mm * (part.quantity - remaining[part.code])
                for part in data.parts
            )
            utilization = used_area / (sheet.width_mm * sheet.length_mm * sheet_count) * 100 if sheet_count else 0
            unplaced = [f"{code} × {quantity}" for code, quantity in remaining.items() if quantity]
            evaluations.append((sheet, sheet_count, placed_total, unplaced, utilization))
        selected = evaluations[0]
        reason = "chapa padrão selecionada para o lote completo"
        for option in evaluations[1:]:
            if len(option[3]) < len(selected[3]):
                selected = option
                reason = "alternativa acomoda mais peças no lote completo"
            elif len(option[3]) == len(selected[3]):
                fewer_sheets = option[1] < selected[1]
                gain = option[4] - selected[4]
                if fewer_sheets or gain >= data.alternative_minimum_gain_percent:
                    selected = option
                    reason = "alternativa reduz chapas ou atinge o ganho mínimo"
        sheet, sheet_count, placed_total, unplaced, utilization = selected
        return NestingBatchPlan(
            selected_sheet=sheet, sheet_count=max(sheet_count, 1),
            placed_count=placed_total, unplaced=unplaced,
            utilization_percent=round(utilization, 2),
            waste_percent=round(100 - utilization, 2),
            selection_reason=reason,
        )

    @classmethod
    def quote_drafts(cls, data: DxfQuoteDraftRequest) -> list[QuoteItemCreate]:
        drafts = []
        for upload in data.uploads:
            analysis = cls.analyze(upload)
            weight = analysis.net_area_mm2 * data.thickness_mm * data.density_kg_m3 / 1_000_000_000
            minutes = analysis.cut_length_mm / data.cutting_speed_mm_min + analysis.piercings * data.piercing_seconds / 60
            code = re.sub(r"[^A-Za-z0-9._-]+", "-", upload.filename.rsplit(".", 1)[0]).strip("-")[:60] or "DXF"
            drafts.append(QuoteItemCreate(
                code=code, description=analysis.description, quantity=analysis.suggested_quantity,
                material=data.material, thickness_mm=data.thickness_mm,
                width_mm=analysis.width_mm, length_mm=analysis.height_mm,
                net_weight_kg=float(Decimal(str(weight)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)), material_price_kg=data.material_price_kg,
                cut_length_mm=analysis.cut_length_mm, piercings=analysis.piercings,
                laser_estimated_minutes=round(minutes, 3),
                nesting_mode=analysis.nesting_suggestion.value,
                utilization_percent=max(round(analysis.fill_factor_percent, 2), 1),
                processes=[QuoteProcess(name="Corte Laser", minutes=round(minutes, 3), hourly_rate=data.laser_hourly_rate)],
                notes="; ".join(analysis.warnings),
            ))
        return drafts
