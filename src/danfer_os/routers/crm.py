from uuid import UUID

from fastapi import APIRouter, HTTPException

from danfer_os.models.crm import (
    CrmActivityCreate, CrmAlert, CrmAlertSettings,
    Opportunity, OpportunityCreate, OpportunityUpdate,
)
from danfer_os.services.crm import CrmNotFoundError, CrmService


def create_router(service: CrmService) -> APIRouter:
    router = APIRouter(prefix="/crm", tags=["CRM"])

    @router.post("/opportunities", response_model=Opportunity, status_code=201)
    def create(data: OpportunityCreate) -> Opportunity:
        return service.create(data)

    @router.get("/opportunities", response_model=list[Opportunity])
    def list_items(q: str = "", stage: str = "") -> list[Opportunity]:
        return service.list(q, stage)

    @router.patch("/opportunities/{item_id}", response_model=Opportunity)
    def update(item_id: UUID, data: OpportunityUpdate) -> Opportunity:
        try:
            return service.update(item_id, data)
        except CrmNotFoundError as error:
            raise HTTPException(status_code=404, detail="oportunidade não encontrada") from error

    @router.post("/opportunities/{item_id}/activities", response_model=Opportunity)
    def activity(item_id: UUID, data: CrmActivityCreate) -> Opportunity:
        try:
            return service.add_activity(item_id, data)
        except CrmNotFoundError as error:
            raise HTTPException(status_code=404, detail="oportunidade não encontrada") from error

    @router.get("/alerts", response_model=list[CrmAlert])
    def alerts() -> list[CrmAlert]:
        return service.alerts()

    @router.get("/alert-settings", response_model=CrmAlertSettings)
    def alert_settings() -> CrmAlertSettings:
        return service.alert_settings()

    @router.put("/alert-settings", response_model=CrmAlertSettings)
    def set_alert_settings(data: CrmAlertSettings) -> CrmAlertSettings:
        return service.set_alert_settings(data)

    return router
