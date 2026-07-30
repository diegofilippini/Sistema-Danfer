from datetime import datetime, timezone
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class BomStatus(StrEnum):
    DRAFT = "rascunho"
    ACTIVE = "ativa"
    OBSOLETE = "obsoleta"


class BomComponent(BaseModel):
    part_id: UUID
    quantity: float = Field(gt=0)
    unit: str = Field(default="un", min_length=1, max_length=20)
    scrap_percent: float = Field(default=0, ge=0, le=100)


class BomCreate(BaseModel):
    product_id: UUID
    revision: str = Field(default="A", min_length=1, max_length=20)
    status: BomStatus = BomStatus.DRAFT
    components: list[BomComponent] = Field(min_length=1)


class BomUpdate(BaseModel):
    revision: str | None = Field(default=None, min_length=1, max_length=20)
    status: BomStatus | None = None
    components: list[BomComponent] | None = Field(default=None, min_length=1)


class BillOfMaterials(BomCreate):
    id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ExplodedComponent(BaseModel):
    part_id: UUID
    quantity: float
    unit: str
    level: int
