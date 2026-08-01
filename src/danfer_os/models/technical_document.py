from datetime import datetime, timezone
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


class DocumentCategory(StrEnum):
    DRAWING = "desenho"
    MANUAL = "manual"
    PROCEDURE = "procedimento"
    SPECIFICATION = "especificacao"
    STANDARD = "norma"
    OTHER = "outro"


class PartStatus(StrEnum):
    ACTIVE = "ativo"
    OBSOLETE = "obsoleto"


class RoutingStep(BaseModel):
    erp_code: int | None = Field(default=None, gt=0)
    process: str = Field(min_length=2, max_length=80)
    estimated_minutes: float = Field(ge=0)


class DocumentCreate(BaseModel):
    danfer_code: str = Field(min_length=1, max_length=50)
    customer_code: str = Field(default="", max_length=50)
    title: str = Field(min_length=3, max_length=160)
    customer: str = Field(default="", max_length=120)
    material: str = Field(default="", max_length=100)
    thickness_mm: float | None = Field(default=None, gt=0)
    weight_kg: float | None = Field(default=None, ge=0)
    width_mm: float | None = Field(default=None, gt=0)
    length_mm: float | None = Field(default=None, gt=0)
    cut_length_mm: float | None = Field(default=None, ge=0)
    piercings: int | None = Field(default=None, ge=0)
    fill_factor_percent: float | None = Field(default=None, ge=0, le=100)
    nesting_mode: str = Field(default="automatico", max_length=30)
    family: str = Field(default="", max_length=80)
    group: str = Field(default="", max_length=80)
    status: PartStatus = PartStatus.ACTIVE
    routing: list[RoutingStep] = Field(default_factory=list, max_length=30)
    category: DocumentCategory
    description: str = Field(default="", max_length=2000)
    tags: list[str] = Field(default_factory=list, max_length=20)
    revision: str = Field(default="A", min_length=1, max_length=20)
    file_url: HttpUrl

    @field_validator(
        "danfer_code", "customer_code", "title", "customer", "material",
        "family", "group", "description", "revision"
    )
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, tags: list[str]) -> list[str]:
        normalized = {tag.strip().lower() for tag in tags if tag.strip()}
        if any(len(tag) > 40 for tag in normalized):
            raise ValueError("cada tag deve ter no máximo 40 caracteres")
        return sorted(normalized)


class DocumentUpdate(BaseModel):
    danfer_code: str | None = Field(default=None, min_length=1, max_length=50)
    customer_code: str | None = Field(default=None, max_length=50)
    title: str | None = Field(default=None, min_length=3, max_length=160)
    customer: str | None = Field(default=None, max_length=120)
    material: str | None = Field(default=None, max_length=100)
    thickness_mm: float | None = Field(default=None, gt=0)
    weight_kg: float | None = Field(default=None, ge=0)
    width_mm: float | None = Field(default=None, gt=0)
    length_mm: float | None = Field(default=None, gt=0)
    cut_length_mm: float | None = Field(default=None, ge=0)
    piercings: int | None = Field(default=None, ge=0)
    fill_factor_percent: float | None = Field(default=None, ge=0, le=100)
    nesting_mode: str | None = Field(default=None, max_length=30)
    family: str | None = Field(default=None, max_length=80)
    group: str | None = Field(default=None, max_length=80)
    status: PartStatus | None = None
    routing: list[RoutingStep] | None = Field(default=None, max_length=30)
    category: DocumentCategory | None = None
    description: str | None = Field(default=None, max_length=2000)
    tags: list[str] | None = Field(default=None, max_length=20)
    revision: str | None = Field(default=None, min_length=1, max_length=20)
    file_url: HttpUrl | None = None

    _strip_text = field_validator(
        "danfer_code", "customer_code", "title", "customer", "material",
        "family", "group", "description", "revision"
    )(DocumentCreate.strip_text.__func__)
    _normalize_tags = field_validator("tags")(DocumentCreate.normalize_tags.__func__)


class TechnicalDocument(DocumentCreate):
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DocumentList(BaseModel):
    items: list[TechnicalDocument]
    total: int


class RevisionRecord(BaseModel):
    changed_at: datetime
    reason: str
    previous: TechnicalDocument
