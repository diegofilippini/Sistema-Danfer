from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from danfer_os.models.importer import (
    FileUpload,
    ImportConfiguration,
    ImportHistory,
    ImportPreview,
    ImportProfile,
    ImportProfileCreate,
    ImportValidation,
)
from danfer_os.services.importer import ImporterError, ImporterService


def create_router(service: ImporterService) -> APIRouter:
    router = APIRouter(prefix="/imports", tags=["importador"])

    @router.post("/preview", response_model=ImportPreview, status_code=status.HTTP_201_CREATED)
    def preview(upload: FileUpload) -> ImportPreview:
        try:
            return service.preview(upload)
        except ImporterError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @router.post("/{session_id}/validate", response_model=ImportValidation)
    def validate(session_id: UUID, config: ImportConfiguration) -> ImportValidation:
        try:
            return service.validate(session_id, config)
        except LookupError as error:
            raise HTTPException(status_code=404, detail="sessão não encontrada") from error
        except ImporterError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @router.post("/profiles", response_model=ImportProfile, status_code=status.HTTP_201_CREATED)
    def create_profile(data: ImportProfileCreate) -> ImportProfile:
        return service.create_profile(data)

    @router.get("/profiles", response_model=list[ImportProfile])
    def profiles(customer: str | None = None) -> list[ImportProfile]:
        return service.list_profiles(customer)

    @router.get("/history", response_model=list[ImportHistory])
    def history() -> list[ImportHistory]:
        return service.history()

    @router.post("/{session_id}/finish", response_model=ImportHistory)
    def finish(
        session_id: UUID,
        validation: ImportValidation,
        customer: str = Query(default="", max_length=160),
        profile_id: UUID | None = None,
    ) -> ImportHistory:
        if validation.session_id != session_id:
            raise HTTPException(status_code=422, detail="sessão divergente")
        try:
            return service.finish(validation, customer, profile_id)
        except LookupError as error:
            raise HTTPException(status_code=404, detail="sessão não encontrada") from error

    return router
