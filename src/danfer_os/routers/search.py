from fastapi import APIRouter, Query

from danfer_os.services.commercial import CommercialService
from danfer_os.services.coordination import CoordinationService
from danfer_os.services.pcp import PcpService


def create_router(commercial: CommercialService, pcp: PcpService, coordination: CoordinationService) -> APIRouter:
    router = APIRouter(prefix="/search", tags=["busca global"])

    @router.get("")
    def search(q: str = Query(min_length=2, max_length=100)) -> list[dict[str, str]]:
        term = q.casefold()
        result: list[dict[str, str]] = []
        for client in commercial.list_clients(q):
            result.append({"type": "cliente", "id": str(client.id), "title": client.name, "subtitle": client.document})
        for quote in commercial.list_quotes():
            if term in f"{quote.number} {quote.requester} {quote.status.value}".casefold():
                result.append({"type": "orçamento", "id": str(quote.id), "title": quote.number, "subtitle": quote.status.value})
        for order in pcp.list():
            if term in f"{order.number} {order.status.value} {order.notes}".casefold():
                result.append({"type": "OP", "id": str(order.id), "title": order.number, "subtitle": order.status.value})
        for item in pcp.direct_requests():
            if term in f"{item.number} {item.client} {item.description}".casefold():
                result.append({"type": "SP", "id": str(item.id), "title": item.number, "subtitle": item.client})
        for item in coordination.requests():
            if term in f"{item.number} {item.subject} {item.requester}".casefold():
                result.append({"type": "solicitação", "id": str(item.id), "title": item.number, "subtitle": item.subject})
        return result[:30]

    return router
