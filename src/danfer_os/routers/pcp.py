from datetime import date
from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from danfer_os.models.pcp import (
    MaterialGroup,
    ProductionOrder,
    ProductionOrderCreate,
    ProductionOrderUpdate,
    ProductionStatus,
    CalendarException,
    CostVariance,
    DailyCapacity,
    WorkCenter,
    WorkLog,
    WorkLogCreate,
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

    @router.put("/work-centers/{erp_code}", response_model=WorkCenter)
    def set_work_center(erp_code: int, data: WorkCenter) -> WorkCenter:
        if erp_code != data.operation_erp_code:
            raise HTTPException(status_code=422, detail="código ERP divergente")
        return service.set_work_center(data)

    @router.get("/work-centers", response_model=list[WorkCenter])
    def work_centers() -> list[WorkCenter]:
        return service.work_centers()

    @router.put("/calendar/{day}", response_model=CalendarException)
    def set_calendar(day: date, data: CalendarException) -> CalendarException:
        if day != data.date:
            raise HTTPException(status_code=422, detail="data divergente")
        return service.set_calendar_exception(data)

    @router.get("/calendar", response_model=list[CalendarException])
    def calendar(start: date, end: date) -> list[CalendarException]:
        try:
            return service.calendar(start, end)
        except PcpValidationError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @router.get("/capacity/daily", response_model=list[DailyCapacity])
    def daily_capacity(start: date, days: int = 7) -> list[DailyCapacity]:
        try:
            return service.daily_capacity(start, days)
        except PcpValidationError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @router.get("/orders/{order_id}", response_model=ProductionOrder)
    def get(order_id: UUID) -> ProductionOrder:
        try:
            return service.get(order_id)
        except ProductionOrderNotFoundError as error:
            raise HTTPException(status_code=404, detail="ordem não encontrada") from error

    @router.post("/orders/{order_id}/logs", response_model=WorkLog, status_code=201)
    def add_log(order_id: UUID, data: WorkLogCreate) -> WorkLog:
        try:
            return service.add_log(order_id, data)
        except ProductionOrderNotFoundError as error:
            raise HTTPException(status_code=404, detail="ordem não encontrada") from error

    @router.get("/orders/{order_id}/logs", response_model=list[WorkLog])
    def logs(order_id: UUID) -> list[WorkLog]:
        try:
            return service.logs(order_id)
        except ProductionOrderNotFoundError as error:
            raise HTTPException(status_code=404, detail="ordem não encontrada") from error

    @router.get("/orders/{order_id}/costs", response_model=CostVariance)
    def costs(order_id: UUID) -> CostVariance:
        try:
            return service.costs(order_id)
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
