from datetime import date, datetime, timezone
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class QualityType(StrEnum):
    REWORK = "retrabalho"
    SCRAP = "refugo"
    CUSTOMER_COMPLAINT = "reclamacao_cliente"
    INTERNAL = "nao_conformidade"


class QualityOccurrenceCreate(BaseModel):
    type: QualityType
    production_order: str = Field(default="", max_length=60)
    description: str = Field(min_length=3, max_length=1000)
    reason: str = Field(default="", max_length=500)
    responsible: str = Field(default="", max_length=120)
    quantity: float = Field(default=1, gt=0)
    cost: float = Field(default=0, ge=0)
    corrective_action: str = Field(default="", max_length=1000)


class QualityOccurrence(QualityOccurrenceCreate):
    id: UUID = Field(default_factory=uuid4)
    resolved: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    resolved_at: datetime | None = None


class MaintenanceType(StrEnum):
    PREVENTIVE = "preventiva"
    CORRECTIVE = "corretiva"
    INSPECTION = "inspecao"


class MaintenanceStatus(StrEnum):
    OPEN = "aberta"
    SCHEDULED = "agendada"
    IN_PROGRESS = "em_execucao"
    COMPLETED = "concluida"
    CANCELLED = "cancelada"


class MaintenanceOrderCreate(BaseModel):
    equipment: str = Field(min_length=2, max_length=120)
    type: MaintenanceType
    description: str = Field(min_length=3, max_length=1000)
    scheduled_date: date | None = None
    responsible: str = Field(default="", max_length=120)
    estimated_cost: float = Field(default=0, ge=0)


class MaintenanceOrder(MaintenanceOrderCreate):
    id: UUID = Field(default_factory=uuid4)
    number: str
    status: MaintenanceStatus = MaintenanceStatus.OPEN
    actual_cost: float = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class MaintenanceStatusChange(BaseModel):
    status: MaintenanceStatus
    actual_cost: float | None = Field(default=None, ge=0)


class AuditEvent(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    module: str
    action: str
    entity_id: str = ""
    user: str = "sistema"
    details: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class NotificationCreate(BaseModel):
    title: str = Field(min_length=2, max_length=160)
    message: str = Field(min_length=2, max_length=1000)
    audience: str = Field(default="todos", max_length=80)
    recipient_username: str = Field(default="", max_length=50)
    recipient_role: str = Field(default="", max_length=40)


class Notification(NotificationCreate):
    id: UUID = Field(default_factory=uuid4)
    read: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
