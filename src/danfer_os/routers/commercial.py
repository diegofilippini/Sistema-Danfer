from io import BytesIO
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from fastapi.responses import StreamingResponse

from danfer_os.models.commercial import (
    Client,
    ClientCreate,
    ClientUpdate,
    CostSettings,
    PriceAdjustment,
    PriceAdjustmentCreate,
    CustomerProposalCreate,
    CustomerProposalDecision,
    Quote,
    QuoteCreate,
    QuoteRevision,
    QuoteStatus,
    QuoteUpdate,
    StatusChange,
)
from danfer_os.services.commercial import (
    CommercialNotFoundError,
    CommercialService,
    CommercialValidationError,
)
from danfer_os.proposal import build_proposal_pdf


def create_router(service: CommercialService) -> APIRouter:
    router = APIRouter(prefix="/commercial", tags=["comercial"])

    @router.post("/clients", response_model=Client, status_code=status.HTTP_201_CREATED)
    def create_client(data: ClientCreate) -> Client:
        try:
            return service.create_client(data)
        except CommercialValidationError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @router.get("/clients", response_model=list[Client])
    def list_clients(q: str = Query(default="", max_length=100)) -> list[Client]:
        return service.list_clients(q)

    @router.get("/clients/{client_id}", response_model=Client)
    def get_client(client_id: UUID) -> Client:
        try:
            return service.get_client(client_id)
        except CommercialNotFoundError as error:
            raise HTTPException(status_code=404, detail="cliente não encontrado") from error

    @router.patch("/clients/{client_id}", response_model=Client)
    def update_client(client_id: UUID, data: ClientUpdate) -> Client:
        try:
            return service.update_client(client_id, data)
        except CommercialNotFoundError as error:
            raise HTTPException(status_code=404, detail="cliente não encontrado") from error

    @router.get("/settings/costs", response_model=CostSettings)
    def get_cost_settings() -> CostSettings:
        return service.settings()

    @router.put("/settings/costs", response_model=CostSettings)
    def update_cost_settings(data: CostSettings) -> CostSettings:
        return service.update_settings(data)

    @router.get("/quote-bend-times", response_model=dict[str, float])
    def quote_bend_times() -> dict[str, float]:
        return service.bend_time_settings()

    @router.get("/price-adjustments", response_model=list[PriceAdjustment])
    def price_adjustments() -> list[PriceAdjustment]:
        return service.price_adjustments()

    @router.post("/price-adjustments", response_model=PriceAdjustment, status_code=201)
    def create_price_adjustment(data: PriceAdjustmentCreate, request: Request) -> PriceAdjustment:
        user = getattr(request.state, "user", None)
        if user is not None and user.role.value != "administrador":
            raise HTTPException(403, "somente o administrador pode registrar reajustes")
        if user is not None and not data.adjusted_by:
            data = data.model_copy(update={"adjusted_by": user.name})
        try:
            return service.create_price_adjustment(data)
        except CommercialNotFoundError as error:
            raise HTTPException(404, "cliente não encontrado") from error

    @router.post("/quotes", response_model=Quote, status_code=status.HTTP_201_CREATED)
    def create_quote(data: QuoteCreate) -> Quote:
        try:
            return service.create_quote(data)
        except CommercialNotFoundError as error:
            raise HTTPException(status_code=422, detail="cliente não encontrado") from error

    @router.get("/quotes", response_model=list[Quote])
    def list_quotes(
        quote_status: QuoteStatus | None = Query(default=None, alias="status"),
        client_id: UUID | None = None,
    ) -> list[Quote]:
        return service.list_quotes(quote_status, client_id)

    @router.get("/quotes/{quote_id}", response_model=Quote)
    def get_quote(quote_id: UUID) -> Quote:
        try:
            return service.get_quote(quote_id)
        except CommercialNotFoundError as error:
            raise HTTPException(status_code=404, detail="orçamento não encontrado") from error

    @router.patch("/quotes/{quote_id}", response_model=Quote)
    def update_quote(quote_id: UUID, data: QuoteUpdate) -> Quote:
        try:
            return service.update_quote(quote_id, data)
        except CommercialNotFoundError as error:
            raise HTTPException(status_code=404, detail="orçamento não encontrado") from error
        except CommercialValidationError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @router.post("/quotes/{quote_id}/status", response_model=Quote)
    def change_status(quote_id: UUID, data: StatusChange) -> Quote:
        try:
            return service.change_status(quote_id, data.status, data.reason)
        except CommercialNotFoundError as error:
            raise HTTPException(status_code=404, detail="orçamento não encontrado") from error
        except CommercialValidationError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @router.get("/quotes/{quote_id}/revisions", response_model=list[QuoteRevision])
    def revisions(quote_id: UUID) -> list[QuoteRevision]:
        try:
            return service.revisions(quote_id)
        except CommercialNotFoundError as error:
            raise HTTPException(status_code=404, detail="orçamento não encontrado") from error

    @router.post("/quotes/{quote_id}/customer-proposals", response_model=Quote, status_code=201)
    def submit_customer_proposal(quote_id: UUID, data: CustomerProposalCreate, request: Request) -> Quote:
        user = getattr(request.state, "user", None)
        if user and not data.submitted_by:
            data = data.model_copy(update={"submitted_by": user.name})
        try:
            return service.submit_customer_proposal(quote_id, data)
        except CommercialNotFoundError as error:
            raise HTTPException(status_code=404, detail="orçamento não encontrado") from error
        except CommercialValidationError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @router.post("/quotes/{quote_id}/customer-proposals/{proposal_id}/decision", response_model=Quote)
    def decide_customer_proposal(
        quote_id: UUID, proposal_id: UUID, data: CustomerProposalDecision, request: Request
    ) -> Quote:
        user = getattr(request.state, "user", None)
        is_admin = user is None or user.role.value == "administrador"
        if user and not data.decided_by:
            data = data.model_copy(update={"decided_by": user.name})
        try:
            return service.decide_customer_proposal(quote_id, proposal_id, data, is_admin)
        except CommercialNotFoundError as error:
            raise HTTPException(status_code=404, detail="orçamento ou proposta não encontrada") from error
        except CommercialValidationError as error:
            raise HTTPException(status_code=403 if "administrador" in str(error) else 409, detail=str(error)) from error

    @router.get("/quotes/{quote_id}/proposal.pdf")
    def proposal_pdf(quote_id: UUID) -> StreamingResponse:
        try:
            quote = service.get_quote(quote_id)
            client = service.get_client(quote.client_id)
        except CommercialNotFoundError as error:
            raise HTTPException(status_code=404, detail="orçamento não encontrado") from error
        buffer = BytesIO(build_proposal_pdf(quote, client, service.settings()))
        return StreamingResponse(
            buffer,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{quote.number}.pdf"'},
        )

    return router
