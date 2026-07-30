from datetime import datetime, timezone
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class ImportStatus(StrEnum):
    IMPORTED = "importado"
    WARNING = "com_advertencias"
    REJECTED = "rejeitado"


class ExternalOrderItem(BaseModel):
    customer_code: str = Field(min_length=1, max_length=50)
    quantity: float = Field(gt=0)
    unit: str = Field(default="un", min_length=1, max_length=20)


class ExternalOrderCreate(BaseModel):
    source: str = Field(default="api", min_length=2, max_length=40)
    external_id: str = Field(min_length=1, max_length=100)
    customer: str = Field(min_length=2, max_length=160)
    items: list[ExternalOrderItem] = Field(min_length=1)
    notes: str = Field(default="", max_length=1000)


class ImportedOrder(ExternalOrderCreate):
    id: UUID = Field(default_factory=uuid4)
    status: ImportStatus
    warnings: list[str] = Field(default_factory=list)
    imported_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ErpEventStatus(StrEnum):
    PENDING = "pendente"
    SENT = "enviado"
    FAILED = "falhou"


class ErpEvent(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    entity: str
    entity_id: UUID
    action: str
    status: ErpEventStatus = ErpEventStatus.PENDING
    attempts: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
