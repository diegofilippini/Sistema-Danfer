from fastapi import APIRouter, HTTPException, Response
from xml.sax.saxutils import escape

from urllib.parse import quote

from danfer_os.models.engineering import (
    DxfAnalysis, DxfQuoteDraftRequest, DxfRegistration, DxfUpload, NestingPlan,
    NestingRequest,
)
from danfer_os.models.commercial import QuoteItemCreate
from danfer_os.models.technical_document import DocumentCategory, DocumentCreate, RoutingStep, TechnicalDocument
from danfer_os.services.engineering import DxfAnalysisError, EngineeringService
from danfer_os.services.technical_library import TechnicalLibrary


def create_router(service: EngineeringService, library: TechnicalLibrary) -> APIRouter:
    router = APIRouter(prefix="/engineering", tags=["engenharia"])

    @router.post("/dxf/analyze", response_model=DxfAnalysis)
    def analyze_dxf(upload: DxfUpload) -> DxfAnalysis:
        try:
            return service.analyze(upload)
        except DxfAnalysisError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @router.post("/dxf/analyze-batch", response_model=list[DxfAnalysis])
    def analyze_batch(uploads: list[DxfUpload]) -> list[DxfAnalysis]:
        if len(uploads) > 200:
            raise HTTPException(status_code=422, detail="máximo de 200 arquivos por lote")
        try:
            return [service.analyze(upload) for upload in uploads]
        except DxfAnalysisError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @router.post("/dxf/register", response_model=TechnicalDocument, status_code=201)
    def register_dxf(data: DxfRegistration) -> TechnicalDocument:
        try:
            analysis = service.analyze(DxfUpload(filename=data.filename, content_base64=data.content_base64))
            return library.create(DocumentCreate(
                danfer_code=data.danfer_code,
                customer_code=data.customer_code,
                title=analysis.description,
                customer=data.customer,
                material=data.material,
                thickness_mm=data.thickness_mm,
                width_mm=analysis.width_mm,
                length_mm=analysis.height_mm,
                cut_length_mm=analysis.cut_length_mm,
                piercings=analysis.piercings,
                fill_factor_percent=analysis.fill_factor_percent,
                nesting_mode=analysis.nesting_suggestion.value,
                routing=[RoutingStep(erp_code=2, process="Corte Laser", estimated_minutes=0)],
                category=DocumentCategory.DRAWING,
                description="; ".join(analysis.warnings),
                tags=["dxf", "engenharia"],
                revision=data.revision,
                file_url=f"https://engineering.danfer.local/dxf/{quote(data.filename)}",
            ))
        except DxfAnalysisError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @router.post("/nesting/plan", response_model=NestingPlan)
    def nesting_plan(data: NestingRequest) -> NestingPlan:
        return service.nesting(data)

    @router.post("/nesting/preview.svg")
    def nesting_preview(data: NestingRequest) -> Response:
        plan = service.nesting(data)
        sheet = plan.selected_sheet
        colors = ["#41b9f4", "#58c98d", "#f0ad4e", "#8d7bd8", "#e56b7f", "#56b4aa"]
        codes = {code: colors[index % len(colors)] for index, code in enumerate(sorted({item.code for item in plan.placements}))}
        shapes = []
        for item in plan.placements:
            shapes.append(
                f'<g><rect x="{item.x_mm}" y="{item.y_mm}" width="{item.width_mm}" height="{item.height_mm}" fill="{codes[item.code]}" fill-opacity="0.62" stroke="#071a2e" stroke-width="2"/>'
                f'<text x="{item.x_mm + 5}" y="{item.y_mm + 18}" font-size="14" fill="#071a2e">{escape(item.code)} #{item.sequence}{" ↻" if item.rotated else ""}</text></g>'
            )
        subtitle = f"Ocupação {plan.utilization_percent:.2f}% · Perda {plan.waste_percent:.2f}% · {escape(plan.selection_reason)}"
        unplaced = escape(", ".join(plan.unplaced) or "nenhuma")
        svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {sheet.width_mm} {sheet.length_mm + 100}" role="img">'
            f'<rect width="100%" height="100%" fill="#f2f5f8"/><rect x="1" y="1" width="{sheet.width_mm - 2}" height="{sheet.length_mm - 2}" fill="#fff" stroke="#071a2e" stroke-width="3"/>'
            + "".join(shapes)
            + f'<text x="10" y="{sheet.length_mm + 35}" font-size="22" font-family="Arial" font-weight="bold" fill="#071a2e">{escape(sheet.name)}</text>'
            f'<text x="10" y="{sheet.length_mm + 65}" font-size="17" font-family="Arial" fill="#52677a">{subtitle}</text>'
            f'<text x="10" y="{sheet.length_mm + 90}" font-size="14" font-family="Arial" fill="#cf4051">Não encaixadas: {unplaced}</text></svg>'
        )
        return Response(content=svg, media_type="image/svg+xml", headers={"Content-Disposition": "inline; filename=nesting.svg"})

    @router.post("/dxf/quote-drafts", response_model=list[QuoteItemCreate])
    def dxf_quote_drafts(data: DxfQuoteDraftRequest) -> list[QuoteItemCreate]:
        try:
            return service.quote_drafts(data)
        except DxfAnalysisError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    return router
