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
