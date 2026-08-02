from datetime import datetime, timezone
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class OperationPricingMode(StrEnum):
    TIME = "tempo"
    WEIGHT = "peso"
    FIXED = "fixo"


class MaterialCreate(BaseModel):
    erp_code: str = Field(min_length=1, max_length=40)
    description: str = Field(min_length=2, max_length=120)
    specification: str = Field(default="", max_length=100)
    thickness_mm: float = Field(gt=0)
    price_per_kg: float = Field(ge=0)
    density_kg_m3: float = Field(default=7850, gt=0)
    laser_speed_mm_min: float = Field(default=0, ge=0)
    plasma_speed_mm_min: float = Field(default=0, ge=0)
    active: bool = True


class MaterialUpdate(BaseModel):
    description: str | None = Field(default=None, min_length=2, max_length=120)
    specification: str | None = Field(default=None, max_length=100)
    thickness_mm: float | None = Field(default=None, gt=0)
    price_per_kg: float | None = Field(default=None, ge=0)
    density_kg_m3: float | None = Field(default=None, gt=0)
    laser_speed_mm_min: float | None = Field(default=None, ge=0)
    plasma_speed_mm_min: float | None = Field(default=None, ge=0)
    active: bool | None = None


class Material(MaterialCreate):
    id: UUID = Field(default_factory=uuid4)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PriceTableMapping(BaseModel):
    erp_code_column: str
    price_column: str
    description_column: str = ""
    thickness_column: str = ""
    specification_column: str = ""
    density_column: str = ""
    create_missing: bool = True


class PriceTableChange(BaseModel):
    erp_code: str
    description: str
    action: str
    old_price: float | None = None
    new_price: float


class PriceTableImportResult(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    filename: str
    total_rows: int
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    invalid: int = 0
    changes: list[PriceTableChange] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    imported_by: str = ""
    imported_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class QuoteMaterialOption(BaseModel):
    """Projeção comercial sem preço, densidade ou outros dados de custo."""

    id: UUID
    erp_code: str
    description: str
    specification: str = ""
    thickness_mm: float


class OperationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=80)
    pricing_mode: OperationPricingMode | None = None
    hourly_rate: float | None = Field(default=None, ge=0)
    weight_rate: float | None = Field(default=None, ge=0)
    fixed_cost: float | None = Field(default=None, ge=0)
    active: bool | None = None


class Operation(BaseModel):
    erp_code: int = Field(gt=0)
    name: str = Field(min_length=2, max_length=80)
    pricing_mode: OperationPricingMode = OperationPricingMode.TIME
    hourly_rate: float = Field(default=0, ge=0)
    weight_rate: float = Field(default=0, ge=0)
    fixed_cost: float = Field(default=0, ge=0)
    active: bool = True
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class RoutingTemplateStep(BaseModel):
    operation_erp_code: int = Field(gt=0)
    process: str = Field(min_length=2, max_length=80)
    default_minutes: float = Field(default=0, ge=0)


class RoutingTemplateCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    description: str = Field(default="", max_length=240)
    steps: list[RoutingTemplateStep] = Field(min_length=1, max_length=20)
    active: bool = True


class RoutingTemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=100)
    description: str | None = Field(default=None, max_length=240)
    steps: list[RoutingTemplateStep] | None = Field(default=None, min_length=1, max_length=20)
    active: bool | None = None


class RoutingTemplate(RoutingTemplateCreate):
    id: UUID = Field(default_factory=uuid4)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
