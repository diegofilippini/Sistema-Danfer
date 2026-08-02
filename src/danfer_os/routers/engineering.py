from fastapi import APIRouter, HTTPException, Response
from xml.sax.saxutils import escape

from urllib.parse import quote

from danfer_os.models.engineering import (
    DxfAnalysis, DxfQuoteDraftRequest, DxfRegistration, DxfUpload, NestingBatchPlan, NestingPlan,
    PdfDrawingAnalysis, PdfDrawingConfirmation, PdfDrawingUpload,
    NestingRequest, NestingSheet,
)
from danfer_os.models.commercial import QuoteItemCreate
from danfer_os.models.technical_document import DocumentCategory, DocumentCreate, RoutingStep, TechnicalDocument
from danfer_os.services.engineering import DxfAnalysisError, EngineeringService
from danfer_os.services.technical_library import TechnicalLibrary
from danfer_os.services.commercial import CommercialService


def create_router(service: EngineeringService, library: TechnicalLibrary, commercial: CommercialService | None = None) -> APIRouter:
    router = APIRouter(prefix="/engineering", tags=["engenharia"])

    def resolved_nesting(data: NestingRequest) -> NestingRequest:
        if commercial is None:
            return NestingRequest(
                **data.model_dump(exclude_none=True),
                **({"sheets": [
                    NestingSheet(name="Padrão 1200 × 3000", width_mm=1200, length_mm=3000),
                    NestingSheet(name="Alternativa 1500 × 3000", width_mm=1500, length_mm=3000),
                ]} if data.sheets is None else {}),
                **({"gap_mm": 5} if data.gap_mm is None else {}),
                **({"edge_margin_mm": 10} if data.edge_margin_mm is None else {}),
                **({"alternative_minimum_gain_percent": 8} if data.alternative_minimum_gain_percent is None else {}),
            )
        settings = commercial.settings()
        updates = {
            "sheets": data.sheets or [
                NestingSheet(name="Padrão", width_mm=settings.default_sheet_width_mm, length_mm=settings.default_sheet_length_mm),
                NestingSheet(name="Alternativa", width_mm=settings.alternative_sheet_width_mm, length_mm=settings.alternative_sheet_length_mm),
            ],
            "gap_mm": data.gap_mm if data.gap_mm is not None else settings.default_nesting_gap_mm,
            "edge_margin_mm": data.edge_margin_mm if data.edge_margin_mm is not None else settings.sheet_edge_margin_mm,
            "alternative_minimum_gain_percent": data.alternative_minimum_gain_percent if data.alternative_minimum_gain_percent is not None else settings.alternative_minimum_gain_percent,
        }
        return data.model_copy(update=updates)

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

    @router.post("/pdf/analyze", response_model=PdfDrawingAnalysis)
    def analyze_pdf(upload: PdfDrawingUpload) -> PdfDrawingAnalysis:
        try:
            return service.analyze_pdf(upload)
        except DxfAnalysisError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @router.post("/pdf/confirm-quote-item", response_model=QuoteItemCreate)
    def confirm_pdf_item(data: PdfDrawingConfirmation) -> QuoteItemCreate:
        if not data.confirmed:
            raise HTTPException(status_code=422, detail="o orçamentista deve confirmar as medidas")
        perimeter = data.cut_length_mm or 2 * (data.width_mm + data.height_mm)
        return QuoteItemCreate(
            code=data.code, description=data.description, quantity=data.quantity,
            material=data.material, thickness_mm=data.thickness_mm,
            width_mm=data.width_mm, length_mm=data.height_mm,
            cut_length_mm=perimeter,
            notes=f"Medidas confirmadas manualmente a partir de {data.filename}.",
        )

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
        return service.nesting(resolved_nesting(data))

    @router.post("/nesting/batch-plan", response_model=NestingBatchPlan)
    def nesting_batch_plan(data: NestingRequest) -> NestingBatchPlan:
        return service.nesting_batch(resolved_nesting(data))

    @router.post("/nesting/preview.svg")
    def nesting_preview(data: NestingRequest) -> Response:
        plan = service.nesting(resolved_nesting(data))
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
