from datetime import date, datetime, timezone
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class CrmActivityCreate(BaseModel):
    type: str = Field(min_length=2, max_length=80)
    description: str = Field(min_length=2, max_length=1000)
    performed_by: str = Field(default="", max_length=120)
    next_contact: date | None = None


class CrmActivity(CrmActivityCreate):
    id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class OpportunityCreate(BaseModel):
    client_id: UUID | None = None
    client_name: str = Field(min_length=2, max_length=160)
    quote_id: UUID | None = None
    stage: str = Field(default="em_elaboracao", max_length=60)
    value: float = Field(default=0, ge=0)
    probability_percent: float = Field(default=10, ge=0, le=100)
    owner: str = Field(default="", max_length=120)
    next_contact: date | None = None
    temperature: str = Field(default="morna", max_length=20)
    source: str = Field(default="", max_length=80)
    segment: str = Field(default="", max_length=80)
    notes: str = Field(default="", max_length=2000)


class Opportunity(OpportunityCreate):
    id: UUID = Field(default_factory=uuid4)
    number: str
    activities: list[CrmActivity] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class OpportunityUpdate(BaseModel):
    stage: str | None = None
    value: float | None = Field(default=None, ge=0)
    probability_percent: float | None = Field(default=None, ge=0, le=100)
    owner: str | None = None
    next_contact: date | None = None
    temperature: str | None = None
    source: str | None = None
    segment: str | None = None
    notes: str | None = None


class CrmAlertSettings(BaseModel):
    enabled: bool = True
    stale_quote_days: int = Field(default=3, ge=1, le=90)
    upcoming_contact_days: int = Field(default=1, ge=0, le=30)


class CrmAlert(BaseModel):
    opportunity_id: UUID
    opportunity_number: str
    client_name: str
    quote_id: UUID | None = None
    owner: str = ""
    kind: str
    severity: str
    message: str
    due_date: date | None = None
    days_overdue: int = 0
