from collections import Counter
from datetime import date

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
