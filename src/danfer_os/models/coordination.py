from datetime import date, datetime, timezone
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class CompanyUnit(StrEnum):
    DANFER = "danfer"
    DF = "df"


class BillingProfile(BaseModel):
    unit: CompanyUnit
    legal_name: str = Field(min_length=2, max_length=160)
    document: str = Field(default="", max_length=20)
    state_registration: str = Field(default="", max_length=30)
    address: str = Field(default="", max_length=300)
    erp_company_code: str = Field(default="", max_length=30)
    active: bool = True


class RequestPriority(StrEnum):
    LOW = "baixa"
    NORMAL = "normal"
    HIGH = "alta"
    URGENT = "urgente"


class RequestStatus(StrEnum):
    OPEN = "aberta"
    TRIAGE = "em_triagem"
    IN_PROGRESS = "em_atendimento"
    WAITING = "aguardando"
    COMPLETED = "concluida"
    CANCELLED = "cancelada"


class ServiceRequestCreate(BaseModel):
    company_unit: CompanyUnit = CompanyUnit.DANFER
    requester: str = Field(min_length=2, max_length=120)
    source_department: str = Field(default="", max_length=80)
    target_department: str = Field(min_length=2, max_length=80)
    category: str = Field(min_length=2, max_length=80)
    priority: RequestPriority = RequestPriority.NORMAL
    subject: str = Field(min_length=3, max_length=160)
    description: str = Field(min_length=3, max_length=2000)
    due_date: date | None = None
    linked_entity: str = Field(default="", max_length=80)
    linked_entity_id: str = Field(default="", max_length=80)


class RequestComment(BaseModel):
    author: str = Field(min_length=2, max_length=120)
    message: str = Field(min_length=2, max_length=1000)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ServiceRequest(ServiceRequestCreate):
    id: UUID = Field(default_factory=uuid4)
    number: str
    status: RequestStatus = RequestStatus.OPEN
    assigned_to: str = ""
    comments: list[RequestComment] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class RequestStatusChange(BaseModel):
    status: RequestStatus
    assigned_to: str | None = Field(default=None, max_length=120)
    comment: RequestComment | None = None


class MessageChannel(StrEnum):
    WHATSAPP = "whatsapp"
    EMAIL = "email"
    INTERNAL = "interno"


class MessageStatus(StrEnum):
    DRAFT = "rascunho"
    READY = "pronta"
    SENT = "enviada"
    FAILED = "falhou"


class OutboundMessageCreate(BaseModel):
    company_unit: CompanyUnit = CompanyUnit.DANFER
    channel: MessageChannel
    recipient: str = Field(min_length=2, max_length=160)
    subject: str = Field(default="", max_length=160)
    body: str = Field(min_length=2, max_length=3000)
    linked_entity: str = Field(default="", max_length=80)
    linked_entity_id: str = Field(default="", max_length=80)


class OutboundMessage(OutboundMessageCreate):
    id: UUID = Field(default_factory=uuid4)
    status: MessageStatus = MessageStatus.READY
    action_url: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    sent_at: datetime | None = None
