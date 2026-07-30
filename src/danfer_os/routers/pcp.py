from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from danfer_os.models.pcp import (
    MaterialGroup,
    ProductionOrder,
    ProductionOrderCreate,
    ProductionOrderUpdate,
    ProductionStatus,
)
from danfer_os.services.pcp import (
    PcpService,
    PcpValidationError,
    ProductionOrderNotFoundError,
)


def create_router(service: PcpService) -> APIRouter:
    router = APIRouter(prefix="/pcp", tags=["PCP"])

    @router.post("/orders", response_model=ProductionOrder, status_code=status.HTTP_201_CREATED)
    def create(data: ProductionOrderCreate) -> ProductionOrder:
        try:
            return service.create(data)
        except PcpValidationError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @router.get("/orders", response_model=list[ProductionOrder])
    def list_orders(status_filter: ProductionStatus | None = None) -> list[ProductionOrder]:
        return service.list(status_filter)

    @router.get("/sequence", response_model=list[ProductionOrder])
    def sequence() -> list[ProductionOrder]:
        return service.sequence()

    @router.get("/material-groups", response_model=list[MaterialGroup])
    def material_groups() -> list[MaterialGroup]:
        return service.material_groups()

    @router.get("/orders/{order_id}", response_model=ProductionOrder)
    def get(order_id: UUID) -> ProductionOrder:
        try:
            return service.get(order_id)
        except ProductionOrderNotFoundError as error:
            raise HTTPException(status_code=404, detail="ordem não encontrada") from error

    @router.patch("/orders/{order_id}", response_model=ProductionOrder)
    def update(order_id: UUID, data: ProductionOrderUpdate) -> ProductionOrder:
        try:
            return service.update(order_id, data)
        except ProductionOrderNotFoundError as error:
            raise HTTPException(status_code=404, detail="ordem não encontrada") from error
        except PcpValidationError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    return router
