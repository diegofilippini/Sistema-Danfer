from datetime import datetime, timezone
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator


class ImportField(StrEnum):
    CUSTOMER_CODE = "codigo_cliente"
    DANFER_CODE = "codigo_danfer"
    INTERNAL_CODE = "codigo_interno"
    DESCRIPTION = "descricao"
    QUANTITY = "quantidade"
    UNIT = "unidade"
    MATERIAL = "material"
    THICKNESS = "espessura"
    WIDTH = "largura"
    LENGTH = "comprimento"
    WEIGHT = "peso"
    UNIT_PRICE = "preco_unitario"
    REQUESTED_DATE = "data_solicitada"
    REVISION = "revisao"
    NOTES = "observacoes"
    IGNORE = "ignorar"


class FileUpload(BaseModel):
    filename: str = Field(min_length=3, max_length=255)
    content_base64: str = Field(min_length=1)
    header_row: int = Field(default=1, ge=1)
    sheet: str | None = None
    delimiter: str | None = Field(default=None, min_length=1, max_length=1)


class ImportPreview(BaseModel):
    session_id: UUID
    filename: str
    columns: list[str]
    rows: list[list[str]]
    total_rows: int
    sheets: list[str] = Field(default_factory=list)


class ColumnMapping(BaseModel):
    source_column: str
    target_field: ImportField


class ImportConfiguration(BaseModel):
    mappings: list[ColumnMapping]
    fixed_values: dict[str, str | float] = Field(default_factory=dict)

    @model_validator(mode="after")
    def unique_targets(self) -> "ImportConfiguration":
        targets = [
            item.target_field for item in self.mappings
            if item.target_field != ImportField.IGNORE
        ]
        if len(targets) != len(set(targets)):
            raise ValueError("cada campo de destino pode ser mapeado apenas uma vez")
        return self


class ValidationIssue(BaseModel):
    row: int
    field: str
    message: str
    critical: bool


class ImportValidation(BaseModel):
    session_id: UUID
    normalized_rows: list[dict[str, str | float]]
    issues: list[ValidationIssue]
    valid_rows: int
    invalid_rows: int


class ImportProfileCreate(BaseModel):
    customer: str = Field(min_length=2, max_length=160)
    name: str = Field(min_length=2, max_length=160)
    configuration: ImportConfiguration


class ImportProfile(ImportProfileCreate):
    id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ImportHistory(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    session_id: UUID
    filename: str
    customer: str = ""
    profile_id: UUID | None = None
    total_rows: int
    valid_rows: int
    invalid_rows: int
    imported_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
