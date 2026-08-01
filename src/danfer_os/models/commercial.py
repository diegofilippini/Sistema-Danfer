from datetime import date, datetime, timezone
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class FreightType(StrEnum):
    FOB = "FOB"
    CIF = "CIF"
    PICKUP = "retira_danfer"


class FreightPayer(StrEnum):
    CUSTOMER = "cliente"
    DANFER = "danfer"


class ClientCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    document: str = Field(default="", max_length=20)
    state_registration: str = Field(default="", max_length=30)
    contact: str = Field(default="", max_length=120)
    email: str = Field(default="", max_length=160)
    phone: str = Field(default="", max_length=30)
    address: str = Field(default="", max_length=300)
    payment_terms: str = Field(default="28 dias", max_length=100)
    freight_type: FreightType = FreightType.FOB
    freight_payer: FreightPayer = FreightPayer.CUSTOMER
    tax_regime: str = Field(default="normal", max_length=80)
    active: bool = True
    notes: str = Field(default="", max_length=2000)


class ClientUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    document: str | None = Field(default=None, max_length=20)
    state_registration: str | None = Field(default=None, max_length=30)
    contact: str | None = Field(default=None, max_length=120)
    email: str | None = Field(default=None, max_length=160)
    phone: str | None = Field(default=None, max_length=30)
    address: str | None = Field(default=None, max_length=300)
    payment_terms: str | None = Field(default=None, max_length=100)
    freight_type: FreightType | None = None
    freight_payer: FreightPayer | None = None
    tax_regime: str | None = Field(default=None, max_length=80)
    active: bool | None = None
    notes: str | None = Field(default=None, max_length=2000)


class Client(ClientCreate):
    id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class QuoteType(StrEnum):
    SALE = "venda"
    SERVICE = "servico"


class QuoteStatus(StrEnum):
    DRAFT = "em_elaboracao"
    SENT = "enviado"
    NEGOTIATION = "em_negociacao"
    APPROVED = "aprovado"
    LOST = "perdido"
    CANCELLED = "cancelado"


class NestingMode(StrEnum):
    AUTOMATIC = "automatico"
    FORCE = "forcar_ncav"
    DISABLED = "desabilitado"


class ProcessPricingMode(StrEnum):
    TIME = "tempo"
    WEIGHT = "peso"
    FIXED = "fixo"


class QuoteProcess(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    minutes: float = Field(ge=0)
    hourly_rate: float = Field(ge=0)
    external_cost: float = Field(default=0, ge=0)
    pricing_mode: ProcessPricingMode = ProcessPricingMode.TIME
    weight_rate: float = Field(default=0, ge=0)
    fixed_cost: float = Field(default=0, ge=0)


class QuoteItemCreate(BaseModel):
    code: str = Field(min_length=1, max_length=60)
    description: str = Field(min_length=2, max_length=200)
    quantity: float = Field(gt=0)
    unit: str = Field(default="un", min_length=1, max_length=20)
    material: str = Field(default="", max_length=100)
    thickness_mm: float | None = Field(default=None, gt=0)
    width_mm: float | None = Field(default=None, gt=0)
    length_mm: float | None = Field(default=None, gt=0)
    net_weight_kg: float = Field(default=0, ge=0)
    material_price_kg: float = Field(default=0, ge=0)
    cut_length_mm: float = Field(default=0, ge=0)
    piercings: int = Field(default=0, ge=0)
    nesting_mode: NestingMode = NestingMode.AUTOMATIC
    utilization_percent: float = Field(default=80, gt=0, le=100)
    processes: list[QuoteProcess] = Field(default_factory=list)
    manual_unit_price: float | None = Field(default=None, ge=0)
    margin_percent: float | None = Field(default=None, ge=0, lt=100)
    notes: str = Field(default="", max_length=1000)


class QuoteItem(QuoteItemCreate):
    id: UUID = Field(default_factory=uuid4)
    material_cost: float = 0
    process_cost: float = 0
    indirect_cost: float = 0
    total_cost: float = 0
    unit_price: float = 0
    total_price: float = 0


class QuoteCreate(BaseModel):
    type: QuoteType
    client_id: UUID
    requester: str = Field(default="", max_length=120)
    prepared_by: str = Field(default="Equipe Comercial Danfer", max_length=120)
    valid_until: date
    expected_delivery: date | None = None
    payment_terms: str = Field(default="", max_length=100)
    freight_type: FreightType = FreightType.FOB
    freight_payer: FreightPayer = FreightPayer.CUSTOMER
    nature_operation: str = Field(default="Venda de produção", max_length=120)
    tax_scenario: str = Field(default="padrao", max_length=80)
    margin_percent: float = Field(default=30, ge=0, lt=100)
    ipi_percent: float = Field(default=0, ge=0, le=100)
    cbs_percent: float = Field(default=0, ge=0, le=100)
    ibs_percent: float = Field(default=0, ge=0, le=100)
    freight_value: float = Field(default=0, ge=0)
    discount_value: float = Field(default=0, ge=0)
    items: list[QuoteItemCreate] = Field(min_length=1)
    observations: str = Field(default="", max_length=3000)
    internal_notes: str = Field(default="", max_length=3000)


class QuoteUpdate(BaseModel):
    requester: str | None = Field(default=None, max_length=120)
    prepared_by: str | None = Field(default=None, max_length=120)
    valid_until: date | None = None
    expected_delivery: date | None = None
    payment_terms: str | None = Field(default=None, max_length=100)
    freight_type: FreightType | None = None
    freight_payer: FreightPayer | None = None
    nature_operation: str | None = Field(default=None, max_length=120)
    tax_scenario: str | None = Field(default=None, max_length=80)
    margin_percent: float | None = Field(default=None, ge=0, lt=100)
    ipi_percent: float | None = Field(default=None, ge=0, le=100)
    cbs_percent: float | None = Field(default=None, ge=0, le=100)
    ibs_percent: float | None = Field(default=None, ge=0, le=100)
    freight_value: float | None = Field(default=None, ge=0)
    discount_value: float | None = Field(default=None, ge=0)
    items: list[QuoteItemCreate] | None = Field(default=None, min_length=1)
    observations: str | None = Field(default=None, max_length=3000)
    internal_notes: str | None = Field(default=None, max_length=3000)
    change_reason: str = Field(default="Atualização do orçamento", min_length=3, max_length=300)


class Quote(QuoteCreate):
    id: UUID = Field(default_factory=uuid4)
    number: str
    revision: str = "A"
    status: QuoteStatus = QuoteStatus.DRAFT
    items: list[QuoteItem]
    subtotal: float = 0
    taxes: float = 0
    total: float = 0
    total_cost: float = 0
    gross_profit: float = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class QuoteRevision(BaseModel):
    quote_id: UUID
    revision: str
    reason: str
    changed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    snapshot: dict[str, object]


class StatusChange(BaseModel):
    status: QuoteStatus
    reason: str = Field(default="", max_length=500)


class CostSettings(BaseModel):
    default_margin_percent: float = Field(default=30, ge=0, lt=100)
    indirect_percent: float = Field(default=12, ge=0, le=100)
    small_bend_batch_limit: int = Field(default=5, ge=0)
    small_bend_batch_surcharge: float = Field(default=35, ge=0)
    strip_costing_threshold_percent: float = Field(default=30, ge=0, le=100)
    large_part_threshold_percent: float = Field(default=60, gt=0, le=100)
    large_part_loss_percent: float = Field(default=15, ge=0, le=100)
    default_sheet_width_mm: float = Field(default=1200, gt=0)
    default_sheet_length_mm: float = Field(default=3000, gt=0)
    alternative_sheet_width_mm: float = Field(default=1500, gt=0)
    alternative_sheet_length_mm: float = Field(default=3000, gt=0)
    alternative_minimum_gain_percent: float = Field(default=8, ge=0, le=100)
    sheet_edge_margin_mm: float = Field(default=10, ge=0)
    inox_warning_enabled: bool = True
    inox_warning: str = (
        "Peças em aço inox podem apresentar riscos superficiais e pequenas "
        "marcas de manuseio. Exigências estéticas especiais devem constar no orçamento."
    )
    gap_rules: list[tuple[float, float]] = Field(
        default_factory=lambda: [(3.0, 3), (6.35, 5), (12.7, 8), (19.05, 10), (999, 12)]
    )
