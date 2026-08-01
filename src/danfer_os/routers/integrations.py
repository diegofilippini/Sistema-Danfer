from uuid import UUID

from fastapi import APIRouter, Body, HTTPException, Query, status

from danfer_os.models.integrations import (
    ErpEvent,
    ErpEventStatus,
    ExternalOrderCreate,
    ImportedOrder,
)
from danfer_os.services.integrations import (
    DuplicateExternalOrderError,
    IntegrationService,
    IntegrationValidationError,
)


def create_router(service: IntegrationService) -> APIRouter:
    router = APIRouter(prefix="/integrations", tags=["integrações"])

    @router.post("/orders", response_model=ImportedOrder, status_code=status.HTTP_201_CREATED)
    def import_order(data: ExternalOrderCreate) -> ImportedOrder:
        try:
            return service.import_order(data)
        except DuplicateExternalOrderError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @router.post(
        "/orders/xml",
        response_model=ImportedOrder,
        status_code=status.HTTP_201_CREATED,
    )
    def import_xml(xml: str = Body(media_type="application/xml")) -> ImportedOrder:
        try:
            return service.import_xml(xml)
        except DuplicateExternalOrderError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except IntegrationValidationError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @router.get("/orders", response_model=list[ImportedOrder])
    def list_orders() -> list[ImportedOrder]:
        return service.list_orders()

    @router.get("/erp/events", response_model=list[ErpEvent])
    def list_events(
        event_status: ErpEventStatus | None = Query(default=None, alias="status"),
    ) -> list[ErpEvent]:
        return service.list_events(event_status)

    @router.post("/erp/events/{event_id}/ack", response_model=ErpEvent)
    def acknowledge(event_id: UUID, succeeded: bool = True, error: str = "") -> ErpEvent:
        try:
            return service.acknowledge_event(event_id, succeeded, error)
        except LookupError as error:
            raise HTTPException(status_code=404, detail="evento não encontrado") from error

    return router
