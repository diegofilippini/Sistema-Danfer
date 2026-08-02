from datetime import date

from fastapi import APIRouter

from danfer_os.services.commercial import CommercialService
from danfer_os.services.operations import OperationsService
from danfer_os.services.pcp import PcpService


def create_router(commercial: CommercialService, pcp: PcpService, operations: OperationsService) -> APIRouter:
    router = APIRouter(prefix="/analytics", tags=["indicadores e gestão"])

    @router.get("/quality")
    def quality_summary() -> dict[str, object]:
        occurrences = operations.list_quality()
        by_type: dict[str, int] = {}
        for item in occurrences:
            by_type[item.type.value] = by_type.get(item.type.value, 0) + 1
        return {
            "total": len(occurrences),
            "open": sum(not item.resolved for item in occurrences),
            "resolved": sum(item.resolved for item in occurrences),
            "total_cost": round(sum(item.cost for item in occurrences), 2),
            "by_type": [{"type": key, "total": value} for key, value in sorted(by_type.items())],
        }

    @router.get("/deviations")
    def deviations() -> list[dict[str, object]]:
        result = []
        for order in pcp.list():
            cost = pcp.costs(order.id)
            result.append({
                **cost.model_dump(mode="json"),
                "due_date": order.due_date,
                "priority": order.priority,
                "status": order.status.value,
                "reason": "custo realizado acima do previsto" if cost.variance_value > 0 else "dentro ou abaixo do previsto",
            })
        return result

    @router.get("/management")
    def management() -> dict[str, object]:
        quotes = commercial.list_quotes()
        orders = pcp.list()
        occurrences = operations.list_quality()
        approved = [item for item in quotes if item.status.value == "aprovado"]
        return {
            "quotes": len(quotes),
            "approved_quotes": len(approved),
            "conversion_percent": round(len(approved) / len(quotes) * 100, 2) if quotes else 0,
            "projected_revenue": round(sum(item.total for item in approved), 2),
            "production_orders": len(orders),
            "active_orders": sum(item.status.value not in {"concluida", "cancelada"} for item in orders),
            "late_orders": sum(item.due_date < date.today() and item.status.value not in {"concluida", "cancelada"} for item in orders),
            "quality_cost": round(sum(item.cost for item in occurrences), 2),
        }

    @router.get("/monthly")
    def monthly(start: date, end: date) -> dict[str, object]:
        orders = [item for item in pcp.list() if start <= item.created_at.date() <= end]
        rows = []
        for order in orders:
            cost = pcp.costs(order.id)
            rows.append({
                "order": order.number, "date": order.created_at.date(), "status": order.status.value,
                "estimated": cost.estimated_total_cost, "actual": cost.actual_total_cost,
                "variance": cost.variance_value, "variance_percent": cost.variance_percent,
            })
        return {
            "start": start, "end": end, "orders": len(rows),
            "estimated": round(sum(item["estimated"] for item in rows), 2),
            "actual": round(sum(item["actual"] for item in rows), 2),
            "variance": round(sum(item["variance"] for item in rows), 2),
            "rows": rows,
        }

    return router
