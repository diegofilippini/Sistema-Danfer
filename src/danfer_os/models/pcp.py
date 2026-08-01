from datetime import date, datetime, timezone
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class ProductionStatus(StrEnum):
    PLANNED = "planejada"
    RELEASED = "liberada"
    IN_PROGRESS = "em_producao"
    PAUSED = "pausada"
    COMPLETED = "concluida"
    CANCELLED = "cancelada"


class ProductionOrderCreate(BaseModel):
    product_id: UUID
    bom_id: UUID
    quantity: float = Field(gt=0)
    due_date: date
    priority: int = Field(default=3, ge=1, le=5)
    estimated_material_cost: float = Field(default=0, ge=0)
    estimated_process_cost: float = Field(default=0, ge=0)
    notes: str = Field(default="", max_length=1000)


class ProductionOrderUpdate(BaseModel):
    due_date: date | None = None
    priority: int | None = Field(default=None, ge=1, le=5)
    status: ProductionStatus | None = None
    notes: str | None = Field(default=None, max_length=1000)


class MaterialRequirement(BaseModel):
    part_id: UUID
    danfer_code: str
    material: str
    thickness_mm: float | None
    quantity: float
    unit: str


class ProductionOrder(ProductionOrderCreate):
    id: UUID = Field(default_factory=uuid4)
    number: str
    status: ProductionStatus = ProductionStatus.PLANNED
    requirements: list[MaterialRequirement] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class MaterialGroup(BaseModel):
    material: str
    thickness_mm: float | None
    orders: list[UUID]
    total_quantity: float


class WorkCenter(BaseModel):
    operation_erp_code: int = Field(gt=0)
    name: str = Field(min_length=2, max_length=80)
    daily_capacity_minutes: float = Field(default=480, gt=0)
    hourly_rate: float = Field(default=0, ge=0)
    active: bool = True


class CalendarException(BaseModel):
    date: date
    available_minutes: float = Field(ge=0)
    reason: str = Field(default="", max_length=200)


class WorkLogType(StrEnum):
    OPERATION = "operacao"
    MATERIAL = "material"
    EXTERNAL = "terceiro"
    QUALITY = "qualidade"


class WorkLogCreate(BaseModel):
    type: WorkLogType
    operation_erp_code: int | None = Field(default=None, gt=0)
    employee: str = Field(default="", max_length=120)
    occurred_on: date = Field(default_factory=date.today)
    minutes: float = Field(default=0, ge=0)
    quantity: float = Field(default=0, ge=0)
    unit_cost: float = Field(default=0, ge=0)
    amount: float | None = Field(default=None, ge=0)
    notes: str = Field(default="", max_length=500)


class WorkLog(WorkLogCreate):
    id: UUID = Field(default_factory=uuid4)
    calculated_cost: float = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CostVariance(BaseModel):
    order_id: UUID
    order_number: str
    estimated_material_cost: float
    estimated_process_cost: float
    estimated_total_cost: float
    actual_material_cost: float
    actual_process_cost: float
    actual_external_cost: float
    actual_quality_cost: float
    actual_total_cost: float
    variance_value: float
    variance_percent: float | None


class DailyCapacity(BaseModel):
    date: date
    operation_erp_code: int
    operation: str
    available_minutes: float
    planned_minutes: float
    remaining_minutes: float
    utilization_percent: float
    overloaded: bool
    orders: list[str] = Field(default_factory=list)
