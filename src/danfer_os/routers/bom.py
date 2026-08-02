from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Response, status

from danfer_os.models.bom import (
    BillOfMaterials,
    BomCreate,
    BomUpdate,
    ExplodedComponent,
)
from danfer_os.services.bom import BomNotFoundError, BomService, BomValidationError


def create_router(service: BomService) -> APIRouter:
    router = APIRouter(prefix="/boms", tags=["estrutura de produto"])

    def not_found(error: Exception) -> HTTPException:
        return HTTPException(status_code=404, detail="BOM não encontrada")

    @router.post("", response_model=BillOfMaterials, status_code=status.HTTP_201_CREATED)
    def create(data: BomCreate) -> BillOfMaterials:
        try:
            return service.create(data)
        except BomValidationError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @router.get("", response_model=list[BillOfMaterials])
    def list_boms() -> list[BillOfMaterials]:
        return service.list()

    @router.get("/{bom_id}", response_model=BillOfMaterials)
    def get(bom_id: UUID) -> BillOfMaterials:
        try:
            return service.get(bom_id)
        except BomNotFoundError as error:
            raise not_found(error) from error

    @router.patch("/{bom_id}", response_model=BillOfMaterials)
    def update(bom_id: UUID, data: BomUpdate) -> BillOfMaterials:
        try:
            return service.update(bom_id, data)
        except BomNotFoundError as error:
            raise not_found(error) from error
        except BomValidationError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @router.delete("/{bom_id}", status_code=status.HTTP_204_NO_CONTENT)
    def delete(bom_id: UUID) -> Response:
        try:
            service.delete(bom_id)
        except BomNotFoundError as error:
            raise not_found(error) from error
        return Response(status_code=204)

    @router.get("/{bom_id}/explosion", response_model=list[ExplodedComponent])
    def explode(
        bom_id: UUID,
        quantity: float = Query(default=1, gt=0),
    ) -> list[ExplodedComponent]:
        try:
            return service.explode(bom_id, quantity)
        except BomNotFoundError as error:
            raise not_found(error) from error

    return router
