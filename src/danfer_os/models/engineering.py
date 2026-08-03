from enum import StrEnum

from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class DxfUpload(BaseModel):
    filename: str = Field(min_length=5, max_length=255)
    content_base64: str = Field(min_length=1)


class PdfDrawingUpload(DxfUpload):
    reference_dimension_mm: float | None = Field(default=None, gt=0)


class PdfDimensionCandidate(BaseModel):
    label: str
    value_mm: float = Field(gt=0)
    kind: str
    confidence_percent: int = Field(ge=0, le=100)


class PdfDrawingAnalysis(BaseModel):
    filename: str
    page_count: int = Field(gt=0)
    source_type: str
    width_mm: float | None = Field(default=None, gt=0)
    height_mm: float | None = Field(default=None, gt=0)
    dimensions: list[PdfDimensionCandidate] = Field(default_factory=list)
    extracted_text: str = ""
    requires_confirmation: bool = True
    warnings: list[str] = Field(default_factory=list)


class PdfDrawingConfirmation(BaseModel):
    filename: str = Field(min_length=5, max_length=255)
    code: str = Field(min_length=1, max_length=60)
    description: str = Field(min_length=2, max_length=160)
    quantity: int = Field(default=1, gt=0, le=500)
    material: str = Field(default="", max_length=100)
    thickness_mm: float = Field(gt=0)
    width_mm: float = Field(gt=0)
    height_mm: float = Field(gt=0)
    cut_length_mm: float | None = Field(default=None, gt=0)
    confirmed: bool


class NestingSuggestion(StrEnum):
    AUTOMATIC = "automatico"
    FORCE = "forcar_ncav"


class DxfAnalysis(BaseModel):
    filename: str
    description: str
    suggested_quantity: int
    width_mm: float
    height_mm: float
    cut_length_mm: float
    net_area_mm2: float
    piercings: int
    fill_factor_percent: float
    nesting_suggestion: NestingSuggestion
    warnings: list[str] = Field(default_factory=list)


class DxfRegistration(DxfUpload):
    danfer_code: str = Field(min_length=1, max_length=50)
    customer_code: str = Field(default="", max_length=50)
    customer: str = Field(default="", max_length=120)
    material: str = Field(default="", max_length=100)
    thickness_mm: float | None = Field(default=None, gt=0)
    revision: str = Field(default="A", min_length=1, max_length=20)


class NestingPart(BaseModel):
    code: str = Field(min_length=1, max_length=60)
    width_mm: float = Field(gt=0)
    height_mm: float = Field(gt=0)
    quantity: int = Field(default=1, gt=0, le=500)
    allow_rotation: bool = True


class NestingSheet(BaseModel):
    name: str = Field(min_length=2, max_length=60)
    width_mm: float = Field(gt=0)
    length_mm: float = Field(gt=0)


class NestingRequest(BaseModel):
    parts: list[NestingPart] = Field(min_length=1, max_length=200)
    sheets: list[NestingSheet] | None = Field(default=None, max_length=10)
    gap_mm: float | None = Field(default=None, ge=0, le=100)
    edge_margin_mm: float | None = Field(default=None, ge=0, le=200)
    alternative_minimum_gain_percent: float | None = Field(default=None, ge=0, le=100)

    @model_validator(mode="after")
    def limit_expanded_parts(self) -> "NestingRequest":
        if sum(item.quantity for item in self.parts) > 1000:
            raise ValueError("máximo de 1000 peças por plano")
        return self


class NestingPlacement(BaseModel):
    code: str
    sequence: int
    x_mm: float
    y_mm: float
    width_mm: float
    height_mm: float
    rotated: bool


class SheetEvaluation(BaseModel):
    sheet: NestingSheet
    placed_count: int
    unplaced_count: int
    utilization_percent: float
    waste_percent: float


class NestingPlan(BaseModel):
    selected_sheet: NestingSheet
    placements: list[NestingPlacement]
    unplaced: list[str]
    utilization_percent: float
    waste_percent: float
    comparison: list[SheetEvaluation]
    selection_reason: str


class NestingBatchPlan(BaseModel):
    selected_sheet: NestingSheet
    sheet_count: int = Field(gt=0)
    placed_count: int = Field(ge=0)
    unplaced: list[str] = Field(default_factory=list)
    utilization_percent: float = Field(ge=0, le=100)
    waste_percent: float = Field(ge=0, le=100)
    selection_reason: str


class DxfQuoteDraftRequest(BaseModel):
    uploads: list[DxfUpload] = Field(min_length=1, max_length=200)
    material_id: UUID | None = None
    material: str = Field(default="", max_length=100)
    thickness_mm: float = Field(gt=0)
    material_price_kg: float = Field(default=0, ge=0)
    density_kg_m3: float = Field(default=7850, gt=0)
    cutting_speed_mm_min: float = Field(default=2000, gt=0)
    piercing_seconds: float = Field(default=1, ge=0)
    laser_hourly_rate: float = Field(default=180, ge=0)
