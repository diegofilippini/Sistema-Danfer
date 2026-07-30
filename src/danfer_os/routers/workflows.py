from datetime import date
from uuid import UUID

from fastapi import APIRouter, HTTPException

from danfer_os.models.commercial import QuoteStatus
from danfer_os.models.pcp import ProductionOrder, ProductionOrderCreate
from danfer_os.services.bom import BomNotFoundError, BomService
from danfer_os.services.commercial import CommercialNotFoundError, CommercialService
from danfer_os.services.pcp import PcpService
from danfer_os.services.technical_library import TechnicalLibrary


def create_router(
    commercial: CommercialService,
    library: TechnicalLibrary,
    boms: BomService,
    pcp: PcpService,
) -> APIRouter:
    router = APIRouter(prefix="/workflows", tags=["fluxos integrados"])

    @router.post(
        "/quotes/{quote_id}/production-orders",
        response_model=list[ProductionOrder],
    )
    def quote_to_production(quote_id: UUID) -> list[ProductionOrder]:
        try:
            quote = commercial.get_quote(quote_id)
        except CommercialNotFoundError as error:
            raise HTTPException(status_code=404, detail="orçamento não encontrado") from error
        if quote.status != QuoteStatus.APPROVED:
            raise HTTPException(status_code=409, detail="o orçamento precisa estar aprovado")
        delivery = quote.expected_delivery or date.today()
        created = []
        missing = []
        parts = {item.danfer_code.casefold(): item for item in library.list()}
        for item in quote.items:
            part = parts.get(item.code.casefold())
            if part is None:
                missing.append(f"{item.code}: peça não cadastrada")
                continue
            try:
                bom = boms.for_product(part.id)
            except BomNotFoundError:
                missing.append(f"{item.code}: BOM ativa não encontrada")
                continue
            created.append(
                pcp.create(
                    ProductionOrderCreate(
                        product_id=part.id,
                        bom_id=bom.id,
                        quantity=item.quantity,
                        due_date=delivery,
                        priority=3,
                        notes=f"Gerada pelo orçamento {quote.number}",
                    )
                )
            )
        if missing and not created:
            raise HTTPException(status_code=422, detail="; ".join(missing))
        return created

    return router
