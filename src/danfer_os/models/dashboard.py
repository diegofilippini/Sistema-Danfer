from datetime import datetime, timezone

from pydantic import BaseModel, Field

from danfer_os.models.pcp import MaterialGroup, ProductionOrder


class StatusIndicator(BaseModel):
    status: str
    total: int


class DashboardSummary(BaseModel):
    technical_parts: int
    active_boms: int
    production_orders: int
    overdue_orders: int
    integration_warnings: int
    pending_erp_events: int
    orders_by_status: list[StatusIndicator]
    next_orders: list[ProductionOrder] = Field(max_length=10)
    material_demand: list[MaterialGroup] = Field(max_length=10)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
