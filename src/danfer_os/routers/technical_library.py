from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Response, status

from danfer_os.models.technical_document import (
    DocumentCategory,
    DocumentCreate,
    DocumentList,
    DocumentUpdate,
    TechnicalDocument,
    RevisionRecord,
)
from danfer_os.services.technical_library import (
    DocumentNotFoundError,
    TechnicalLibrary,
)


def create_router(library: TechnicalLibrary) -> APIRouter:
    router = APIRouter(prefix="/technical-library", tags=["biblioteca técnica"])

    @router.post("", response_model=TechnicalDocument, status_code=status.HTTP_201_CREATED)
    def create_document(data: DocumentCreate) -> TechnicalDocument:
        try:
            return library.create(data)
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @router.get("", response_model=DocumentList)
    def list_documents(
        q: str | None = Query(default=None, max_length=100),
        category: DocumentCategory | None = None,
        tag: str | None = Query(default=None, max_length=40),
    ) -> DocumentList:
        items = library.list(query=q, category=category, tag=tag)
        return DocumentList(items=items, total=len(items))

    @router.get("/admin/backup")
    def backup() -> dict[str, object]:
        return library.backup()

    @router.post("/admin/restore", status_code=status.HTTP_204_NO_CONTENT)
    def restore(payload: dict[str, object]) -> Response:
        try:
            library.restore(payload)
        except (ValueError, TypeError) as error:
            raise HTTPException(status_code=422, detail="backup inválido") from error
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @router.get("/{document_id}", response_model=TechnicalDocument)
    def get_document(document_id: UUID) -> TechnicalDocument:
        try:
            return library.get(document_id)
        except DocumentNotFoundError as error:
            raise HTTPException(status_code=404, detail="documento não encontrado") from error

    @router.patch("/{document_id}", response_model=TechnicalDocument)
    def update_document(document_id: UUID, data: DocumentUpdate) -> TechnicalDocument:
        try:
            return library.update(document_id, data)
        except DocumentNotFoundError as error:
            raise HTTPException(status_code=404, detail="documento não encontrado") from error

    @router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
    def delete_document(document_id: UUID) -> Response:
        try:
            library.delete(document_id)
        except DocumentNotFoundError as error:
            raise HTTPException(status_code=404, detail="documento não encontrado") from error
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @router.get("/{document_id}/history", response_model=list[RevisionRecord])
    def document_history(document_id: UUID) -> list[RevisionRecord]:
        try:
            return library.history(document_id)
        except DocumentNotFoundError as error:
            raise HTTPException(status_code=404, detail="documento não encontrado") from error

    return router
