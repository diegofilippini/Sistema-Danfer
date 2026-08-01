from enum import StrEnum

from pydantic import BaseModel, Field


class DxfUpload(BaseModel):
    filename: str = Field(min_length=5, max_length=255)
    content_base64: str = Field(min_length=1)


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
