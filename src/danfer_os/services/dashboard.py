from collections import Counter
from datetime import date, timedelta

from danfer_os.models.bom import BomStatus
from danfer_os.models.dashboard import DashboardSummary, StatusIndicator
from danfer_os.models.integrations import ErpEventStatus, ImportStatus
from danfer_os.models.pcp import ProductionStatus
from danfer_os.services.bom import BomService
from danfer_os.services.integrations import IntegrationService
from danfer_os.services.pcp import PcpService
from danfer_os.services.technical_library import TechnicalLibrary


class DashboardService:
    def __init__(
        self,
        library: TechnicalLibrary,
        boms: BomService,
        pcp: PcpService,
        integrations: IntegrationService,
    ) -> None:
        self._library = library
        self._boms = boms
        self._pcp = pcp
        self._integrations = integrations

    def summary(self) -> DashboardSummary:
        orders = self._pcp.list()
        status_counts = Counter(order.status.value for order in orders)
        terminal = {ProductionStatus.COMPLETED, ProductionStatus.CANCELLED}
        overdue = sum(
            order.due_date < date.today() and order.status not in terminal
            for order in orders
        )
        warnings = sum(
            order.status == ImportStatus.WARNING
            for order in self._integrations.list_orders()
        )
        pending_events = len(
            self._integrations.list_events(ErpEventStatus.PENDING)
        )
        return DashboardSummary(
            technical_parts=len(self._library.list()),
            active_boms=sum(
                bom.status == BomStatus.ACTIVE for bom in self._boms.list()
            ),
            production_orders=len(orders),
            overdue_orders=overdue,
            integration_warnings=warnings,
            pending_erp_events=pending_events,
            orders_by_status=[
                StatusIndicator(status=status, total=total)
                for status, total in sorted(status_counts.items())
            ],
            next_orders=self._pcp.sequence()[:10],
            material_demand=self._pcp.material_groups()[:10],
        )

    def delivery_board(self, days: int) -> dict:
        if days not in {7, 14, 21, 30}:
            raise ValueError("período permitido: 7, 14, 21 ou 30 dias")
        today = date.today()
        terminal = {ProductionStatus.COMPLETED, ProductionStatus.CANCELLED}
        active = [item for item in self._pcp.list() if item.status not in terminal]

        def top_clients(orders: list) -> list[dict]:
            grouped: dict[str, list] = {}
            for order in orders:
                grouped.setdefault(order.client_name or "Cliente não informado", []).append(order)
            ranked = sorted(grouped.items(), key=lambda item: (-len(item[1]), item[0].casefold()))[:10]
            return [{"client": name, "total": len(values), "orders": [item.number for item in values]}
                    for name, values in ranked]

        columns = [{"date": "overdue", "label": "Atrasados", "weekday": "",
                    "status": "red", "clients": top_clients([item for item in active if item.due_date < today])}]
        weekdays = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
        for offset in range(days):
            day = today + timedelta(days=offset)
            columns.append({"date": day.isoformat(), "label": day.strftime("%d/%m"),
                            "weekday": weekdays[day.weekday()], "status": "yellow" if offset == 0 else "green",
                            "clients": top_clients([item for item in active if item.due_date == day])})
        return {"days": days, "generated_on": today.isoformat(), "columns": columns}
