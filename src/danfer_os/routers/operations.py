from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from danfer_os.models.operations import (
    AuditEvent,
    MaintenanceOrder,
    MaintenanceOrderCreate,
    MaintenanceStatusChange,
    Notification,
    NotificationCreate,
    QualityOccurrence,
    QualityOccurrenceCreate,
)
from danfer_os.services.operations import OperationsNotFoundError, OperationsService
from danfer_os.models.pcp import WorkLogCreate, WorkLogType
from danfer_os.services.pcp import PcpService, ProductionOrderNotFoundError


def create_router(service: OperationsService, pcp: PcpService | None = None) -> APIRouter:
    router = APIRouter(tags=["operações"])

    @router.post("/quality", response_model=QualityOccurrence, status_code=201)
    def create_quality(data: QualityOccurrenceCreate) -> QualityOccurrence:
        order = None
        if data.production_order and pcp:
            try:
                order = pcp.find_by_number(data.production_order)
            except ProductionOrderNotFoundError as error:
                raise HTTPException(status_code=422, detail="ordem de produção não encontrada") from error
        occurrence = service.create_quality(data)
        if order and data.cost:
            pcp.add_log(order.id, WorkLogCreate(
                type=WorkLogType.QUALITY, amount=data.cost,
                notes=f"{data.type.value}: {data.description}",
            ))
        return occurrence

    @router.get("/quality", response_model=list[QualityOccurrence])
    def list_quality(resolved: bool | None = None) -> list[QualityOccurrence]:
        return service.list_quality(resolved)

    @router.post("/quality/{occurrence_id}/resolve", response_model=QualityOccurrence)
    def resolve_quality(occurrence_id: UUID) -> QualityOccurrence:
        try:
            return service.resolve_quality(occurrence_id)
        except OperationsNotFoundError as error:
            raise HTTPException(status_code=404, detail="ocorrência não encontrada") from error

    @router.post("/maintenance", response_model=MaintenanceOrder, status_code=201)
    def create_maintenance(data: MaintenanceOrderCreate) -> MaintenanceOrder:
        return service.create_maintenance(data)

    @router.get("/maintenance", response_model=list[MaintenanceOrder])
    def list_maintenance() -> list[MaintenanceOrder]:
        return service.list_maintenance()

    @router.post("/maintenance/{order_id}/status", response_model=MaintenanceOrder)
    def maintenance_status(
        order_id: UUID, data: MaintenanceStatusChange
    ) -> MaintenanceOrder:
        try:
            return service.change_maintenance(order_id, data.status, data.actual_cost)
        except OperationsNotFoundError as error:
            raise HTTPException(status_code=404, detail="manutenção não encontrada") from error

    @router.get("/audit", response_model=list[AuditEvent])
    def audit(module: str | None = None) -> list[AuditEvent]:
        return service.audits(module)

    @router.post("/notifications", response_model=Notification, status_code=201)
    def create_notification(data: NotificationCreate) -> Notification:
        return service.create_notification(data)

    @router.get("/notifications", response_model=list[Notification])
    def notifications(username: str = "", role: str = "") -> list[Notification]:
        return service.notifications(username, role)

    @router.post("/notifications/{notification_id}/read", response_model=Notification)
    def read_notification(notification_id: UUID) -> Notification:
        try:
            return service.read_notification(notification_id)
        except OperationsNotFoundError as error:
            raise HTTPException(status_code=404, detail="notificação não encontrada") from error

    return router
