from fastapi import APIRouter, HTTPException

from urllib.parse import quote

from danfer_os.models.engineering import DxfAnalysis, DxfRegistration, DxfUpload
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

    return router
