from uuid import UUID

from fastapi import APIRouter, HTTPException

from danfer_os.models.coordination import (
    BillingProfile, OutboundMessage, OutboundMessageCreate, RequestStatusChange,
    ServiceRequest, ServiceRequestCreate,
)
from danfer_os.services.coordination import CoordinationNotFoundError, CoordinationService


def create_router(service: CoordinationService) -> APIRouter:
    router = APIRouter(tags=["coordenação"])

    @router.get("/billing/profiles", response_model=list[BillingProfile])
    def profiles() -> list[BillingProfile]:
        return service.profiles()

    @router.put("/billing/profiles/{unit}", response_model=BillingProfile)
    def set_profile(unit: str, data: BillingProfile) -> BillingProfile:
        if unit != data.unit.value:
            raise HTTPException(status_code=422, detail="empresa divergente")
        return service.set_profile(data)

    @router.post("/requests", response_model=ServiceRequest, status_code=201)
    def create_request(data: ServiceRequestCreate) -> ServiceRequest:
        return service.create_request(data)

    @router.get("/requests", response_model=list[ServiceRequest])
    def requests(status: str | None = None) -> list[ServiceRequest]:
        return service.requests(status)

    @router.post("/requests/{request_id}/status", response_model=ServiceRequest)
    def change_request(request_id: UUID, data: RequestStatusChange) -> ServiceRequest:
        try:
            return service.change_request(request_id, data)
        except CoordinationNotFoundError as error:
            raise HTTPException(status_code=404, detail="solicitação não encontrada") from error

    @router.post("/communications/messages", response_model=OutboundMessage, status_code=201)
    def create_message(data: OutboundMessageCreate) -> OutboundMessage:
        try:
            return service.create_message(data)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @router.get("/communications/messages", response_model=list[OutboundMessage])
    def messages() -> list[OutboundMessage]:
        return service.messages()

    @router.post("/communications/messages/{message_id}/sent", response_model=OutboundMessage)
    def mark_sent(message_id: UUID, succeeded: bool = True) -> OutboundMessage:
        try:
            return service.mark_message(message_id, succeeded)
        except CoordinationNotFoundError as error:
            raise HTTPException(status_code=404, detail="mensagem não encontrada") from error

    return router
