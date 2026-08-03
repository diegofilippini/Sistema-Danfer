from datetime import date, datetime, timezone
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field
from danfer_os.models.coordination import CompanyUnit


class ImportStatus(StrEnum):
    IMPORTED = "importado"
    WARNING = "com_advertencias"
    REJECTED = "rejeitado"


class ExternalOrderItem(BaseModel):
    customer_code: str = Field(min_length=1, max_length=50)
    erp_product_code: str = Field(default="", max_length=50)
    quantity: float = Field(gt=0)
    unit: str = Field(default="un", min_length=1, max_length=20)


class ExternalOrderCreate(BaseModel):
    company_unit: CompanyUnit = CompanyUnit.DANFER
    source: str = Field(default="api", min_length=2, max_length=40)
    external_id: str = Field(min_length=1, max_length=100)
    customer: str = Field(min_length=2, max_length=160)
    erp_customer_code: str = Field(default="", max_length=50)
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


class PaymentMethod(StrEnum):
    BANK_SLIP = "boleto"
    PIX = "pix"
    BANK_TRANSFER = "transferencia"
    CREDIT_CARD = "cartao_credito"
    CASH = "dinheiro"
    OTHER = "outro"


class PaymentInstallment(BaseModel):
    sequence: int = Field(gt=0)
    due_date: date
    amount: float = Field(gt=0)
    method: PaymentMethod = PaymentMethod.BANK_SLIP
    bank_account_erp_code: str = Field(default="", max_length=50)
    billing_portfolio_erp_code: str = Field(default="", max_length=50)
    instructions: str = Field(default="", max_length=500)


class InvoiceFinancialData(BaseModel):
    installments: list[PaymentInstallment] = Field(default_factory=list, max_length=120)
    generate_bank_slips: bool = True
    payment_condition_erp_code: str = Field(default="", max_length=50)
    cost_center_erp_code: str = Field(default="", max_length=50)
    financial_category_erp_code: str = Field(default="", max_length=50)
    notes: str = Field(default="", max_length=1000)


class ErpConnectionSettings(BaseModel):
    provider: str = Field(default="generico", min_length=2, max_length=80)
    base_url: str = Field(default="", max_length=500)
    authentication_type: str = Field(default="bearer", max_length=30)
    api_token: str = Field(default="", max_length=1000)
    order_endpoint: str = Field(default="/orders", max_length=200)
    invoice_endpoint: str = Field(default="/invoices", max_length=200)
    stock_endpoint: str = Field(default="/stock-movements", max_length=200)
    customer_endpoint: str = Field(default="/customers", max_length=200)
    timeout_seconds: int = Field(default=30, ge=1, le=300)
    enabled: bool = False
    default_warehouse_erp_code: str = Field(default="", max_length=50)
    default_bank_account_erp_code: str = Field(default="", max_length=50)
    default_billing_portfolio_erp_code: str = Field(default="", max_length=50)
    default_cost_center_erp_code: str = Field(default="", max_length=50)
    default_financial_category_erp_code: str = Field(default="", max_length=50)
    danfer_company_erp_code: str = Field(default="", max_length=30)
    df_company_erp_code: str = Field(default="", max_length=30)
    invoice_series: str = Field(default="", max_length=20)
    invoice_model: str = Field(default="55", max_length=5)


class ErpEvent(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    entity: str
    entity_id: UUID
    action: str
    company_unit: CompanyUnit = CompanyUnit.DANFER
    payload: dict[str, object] = Field(default_factory=dict)
    status: ErpEventStatus = ErpEventStatus.PENDING
    attempts: int = 0
    last_error: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
