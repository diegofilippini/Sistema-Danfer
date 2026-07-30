from fastapi import APIRouter, HTTPException

from danfer_os.models.engineering import DxfAnalysis, DxfUpload
from danfer_os.services.engineering import DxfAnalysisError, EngineeringService


def create_router(service: EngineeringService) -> APIRouter:
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

    return router
