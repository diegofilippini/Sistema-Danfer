from io import BytesIO
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Response, status
from fastapi.responses import StreamingResponse
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from danfer_os.models.commercial import (
    Client,
    ClientCreate,
    ClientUpdate,
    CostSettings,
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

    @router.get("/quotes/{quote_id}/proposal.pdf")
    def proposal_pdf(quote_id: UUID) -> StreamingResponse:
        try:
            quote = service.get_quote(quote_id)
            client = service.get_client(quote.client_id)
        except CommercialNotFoundError as error:
            raise HTTPException(status_code=404, detail="orçamento não encontrado") from error
        buffer = BytesIO()
        document = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=15 * mm,
            leftMargin=15 * mm,
            topMargin=15 * mm,
            bottomMargin=15 * mm,
        )
        styles = getSampleStyleSheet()
        right = ParagraphStyle("right", parent=styles["Normal"], alignment=TA_RIGHT)
        story = [
            Paragraph("<b>DANFER</b> — Transformando aço em soluções", styles["Title"]),
            Paragraph(
                f"<b>ORÇAMENTO {quote.number} · REV. {quote.revision}</b>",
                right,
            ),
            Spacer(1, 8 * mm),
            Paragraph(f"<b>Cliente:</b> {client.name}", styles["Normal"]),
            Paragraph(f"<b>Solicitante:</b> {quote.requester or client.contact}", styles["Normal"]),
            Paragraph(f"<b>Validade:</b> {quote.valid_until:%d/%m/%Y}", styles["Normal"]),
            Paragraph(
                f"<b>Frete:</b> {quote.freight_type.value} — por conta de {quote.freight_payer.value}",
                styles["Normal"],
            ),
            Spacer(1, 6 * mm),
        ]
        rows = [["Código", "Descrição", "Qtd.", "Unitário", "Total"]]
        rows.extend(
            [
                item.code,
                item.description,
                f"{item.quantity:g} {item.unit}",
                f"R$ {item.unit_price:,.2f}",
                f"R$ {item.total_price:,.2f}",
            ]
            for item in quote.items
        )
        table = Table(rows, colWidths=[28 * mm, 72 * mm, 24 * mm, 27 * mm, 27 * mm])
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0A4775")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#B8C4CE")),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("ALIGN", (2, 1), (-1, -1), "RIGHT"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F1F5F8")]),
                ]
            )
        )
        story.extend(
            [
                table,
                Spacer(1, 6 * mm),
                Paragraph(f"<b>Subtotal:</b> R$ {quote.subtotal:,.2f}", right),
                Paragraph(f"<b>Tributos:</b> R$ {quote.taxes:,.2f}", right),
                Paragraph(f"<b>TOTAL:</b> R$ {quote.total:,.2f}", right),
                Spacer(1, 8 * mm),
                Paragraph(f"<b>Observações:</b> {quote.observations or '—'}", styles["Normal"]),
            ]
        )
        if any("inox" in item.material.casefold() for item in quote.items):
            settings = service.settings()
            if settings.inox_warning_enabled:
                story.extend([Spacer(1, 4 * mm), Paragraph(settings.inox_warning, styles["Normal"])])
        document.build(story)
        buffer.seek(0)
        return StreamingResponse(
            buffer,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{quote.number}.pdf"'},
        )

    return router
