from datetime import date, datetime, timezone
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field
from danfer_os.models.coordination import CompanyUnit


class FreightType(StrEnum):
    FOB = "FOB"
    CIF = "CIF"
    PICKUP = "retira_danfer"


class FreightPayer(StrEnum):
    CUSTOMER = "cliente"
    DANFER = "danfer"


class ClientCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    erp_code: str = Field(default="", max_length=50)
    document: str = Field(default="", max_length=20)
    state_registration: str = Field(default="", max_length=30)
    contact: str = Field(default="", max_length=120)
    email: str = Field(default="", max_length=160)
    phone: str = Field(default="", max_length=30)
    address: str = Field(default="", max_length=300)
    address_number: str = Field(default="", max_length=30)
    address_complement: str = Field(default="", max_length=100)
    district: str = Field(default="", max_length=100)
    city: str = Field(default="", max_length=100)
    state: str = Field(default="", max_length=2)
    postal_code: str = Field(default="", max_length=12)
    country_code: str = Field(default="BR", max_length=3)
    municipal_registration: str = Field(default="", max_length=30)
    suframa_registration: str = Field(default="", max_length=30)
    tax_email: str = Field(default="", max_length=160)
    payment_terms: str = Field(default="28 dias", max_length=100)
    payment_condition_erp_code: str = Field(default="", max_length=50)
    credit_limit: float = Field(default=0, ge=0)
    freight_type: FreightType = FreightType.FOB
    freight_payer: FreightPayer = FreightPayer.CUSTOMER
    tax_regime: str = Field(default="normal", max_length=80)
    active: bool = True
    notes: str = Field(default="", max_length=2000)


class ClientUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    erp_code: str | None = Field(default=None, max_length=50)
    document: str | None = Field(default=None, max_length=20)
    state_registration: str | None = Field(default=None, max_length=30)
    contact: str | None = Field(default=None, max_length=120)
    email: str | None = Field(default=None, max_length=160)
    phone: str | None = Field(default=None, max_length=30)
    address: str | None = Field(default=None, max_length=300)
    address_number: str | None = Field(default=None, max_length=30)
    address_complement: str | None = Field(default=None, max_length=100)
    district: str | None = Field(default=None, max_length=100)
    city: str | None = Field(default=None, max_length=100)
    state: str | None = Field(default=None, max_length=2)
    postal_code: str | None = Field(default=None, max_length=12)
    country_code: str | None = Field(default=None, max_length=3)
    municipal_registration: str | None = Field(default=None, max_length=30)
    suframa_registration: str | None = Field(default=None, max_length=30)
    tax_email: str | None = Field(default=None, max_length=160)
    payment_terms: str | None = Field(default=None, max_length=100)
    payment_condition_erp_code: str | None = Field(default=None, max_length=50)
    credit_limit: float | None = Field(default=None, ge=0)
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


class CommercialOperation(StrEnum):
    SALE_INDUSTRIALIZATION = "venda_industrializacao"
    SALE_USE_CONSUMPTION = "venda_uso_consumo"
    INDUSTRIALIZATION = "industrializacao"
    THIRD_PARTY_MATERIAL = "industrializacao_material_terceiros"


class QuoteStatus(StrEnum):
    DRAFT = "em_elaboracao"
    SENT = "enviado"
    NEGOTIATION = "em_negociacao"
    PENDING_ADMIN_APPROVAL = "aguardando_aprovacao_administrativa"
    APPROVED = "aprovado"
    PARTIALLY_INVOICED = "faturamento_parcial"
    LOST = "perdido"
    CANCELLED = "cancelado"
    INVOICED = "faturado"


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


class AppliedNestingPlan(BaseModel):
    reference: str = Field(default="", max_length=100)
    sheet_width_mm: float = Field(gt=0)
    sheet_length_mm: float = Field(gt=0)
    sheet_count: int = Field(gt=0)
    utilization_percent: float = Field(gt=0, le=100)
    waste_percent: float = Field(ge=0, lt=100)


class QuoteItemCreate(BaseModel):
    code: str = Field(min_length=1, max_length=60)
    erp_product_code: str = Field(default="", max_length=60)
    description: str = Field(min_length=2, max_length=200)
    quantity: float = Field(gt=0)
    unit: str = Field(default="un", min_length=1, max_length=20)
    material: str = Field(default="", max_length=100)
    ncm: str = Field(default="", max_length=10)
    cest: str = Field(default="", max_length=10)
    thickness_mm: float | None = Field(default=None, gt=0)
    width_mm: float | None = Field(default=None, gt=0)
    length_mm: float | None = Field(default=None, gt=0)
    net_weight_kg: float = Field(default=0, ge=0)
    material_price_kg: float | None = Field(default=None, ge=0)
    cut_length_mm: float = Field(default=0, ge=0)
    piercings: int = Field(default=0, ge=0)
    laser_estimated_minutes: float = Field(default=0, ge=0)
    laser_additional_minutes: float = Field(default=0, ge=0)
    laser_additional_reason: str = Field(default="", max_length=500)
    bend_estimated_minutes: float = Field(default=0, ge=0)
    bend_additional_minutes: float = Field(default=0, ge=0)
    bend_additional_reason: str = Field(default="", max_length=500)
    nesting_mode: NestingMode = NestingMode.AUTOMATIC
    utilization_percent: float | None = Field(default=None, gt=0, le=100)
    nesting_plan: AppliedNestingPlan | None = None
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
    costing_method: str = "aproveitamento_informado"
    selected_sheet_width_mm: float | None = None
    selected_sheet_length_mm: float | None = None
    calculated_utilization_percent: float | None = None
    applied_gap_mm: float = 0
    selected_sheet_count: int | None = None
    calculated_waste_percent: float | None = None
    nesting_calculation_source: str = "administrativo"
    nesting_plan_reference: str = ""
    costing_warnings: list[str] = Field(default_factory=list)


class QuoteCreate(BaseModel):
    type: QuoteType
    commercial_operation: CommercialOperation = CommercialOperation.SALE_INDUSTRIALIZATION
    billing_unit: CompanyUnit = CompanyUnit.DANFER
    client_id: UUID
    requester: str = Field(default="", max_length=120)
    customer_purchase_order: str = Field(default="", max_length=100)
    seller_erp_code: str = Field(default="", max_length=50)
    prepared_by: str = Field(default="Equipe Comercial Danfer", max_length=120)
    valid_until: date
    expected_delivery: date | None = None
    payment_terms: str = Field(default="", max_length=100)
    freight_type: FreightType = FreightType.FOB
    freight_payer: FreightPayer = FreightPayer.CUSTOMER
    nature_operation: str = Field(default="Venda de produção", max_length=120)
    nature_operation_erp_code: str = Field(default="", max_length=50)
    cfop: str = Field(default="", max_length=10)
    cst_icms: str = Field(default="", max_length=5)
    cst_ipi: str = Field(default="", max_length=5)
    cst_pis: str = Field(default="", max_length=5)
    cst_cofins: str = Field(default="", max_length=5)
    carrier_erp_code: str = Field(default="", max_length=50)
    tax_scenario: str = Field(default="padrao", max_length=80)
    margin_percent: float | None = Field(default=None, ge=0, lt=100)
    ipi_percent: float | None = Field(default=None, ge=0, le=100)
    cbs_percent: float | None = Field(default=None, ge=0, le=100)
    ibs_percent: float | None = Field(default=None, ge=0, le=100)
    freight_value: float = Field(default=0, ge=0)
    discount_value: float = Field(default=0, ge=0)
    items: list[QuoteItemCreate] = Field(min_length=1)
    observations: str = Field(default="", max_length=3000)
    internal_notes: str = Field(default="", max_length=3000)


class QuoteUpdate(BaseModel):
    commercial_operation: CommercialOperation | None = None
    billing_unit: CompanyUnit | None = None
    requester: str | None = Field(default=None, max_length=120)
    customer_purchase_order: str | None = Field(default=None, max_length=100)
    seller_erp_code: str | None = Field(default=None, max_length=50)
    prepared_by: str | None = Field(default=None, max_length=120)
    valid_until: date | None = None
    expected_delivery: date | None = None
    payment_terms: str | None = Field(default=None, max_length=100)
    freight_type: FreightType | None = None
    freight_payer: FreightPayer | None = None
    nature_operation: str | None = Field(default=None, max_length=120)
    nature_operation_erp_code: str | None = Field(default=None, max_length=50)
    cfop: str | None = Field(default=None, max_length=10)
    cst_icms: str | None = Field(default=None, max_length=5)
    cst_ipi: str | None = Field(default=None, max_length=5)
    cst_pis: str | None = Field(default=None, max_length=5)
    cst_cofins: str | None = Field(default=None, max_length=5)
    carrier_erp_code: str | None = Field(default=None, max_length=50)
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
    effective_margin_percent: float = 0
    customer_proposals: list["CustomerProposal"] = Field(default_factory=list)
    invoiced_quantities: dict[str, float] = Field(default_factory=dict)
    invoice_count: int = 0
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


class CustomerProposalStatus(StrEnum):
    PENDING = "pendente"
    APPROVED = "aprovada"
    REJECTED = "recusada"


class CustomerProposalCreate(BaseModel):
    proposed_total: float = Field(gt=0)
    submitted_by: str = Field(default="", max_length=120)
    notes: str = Field(default="", max_length=1000)


class CustomerProposalDecision(BaseModel):
    approved: bool
    decided_by: str = Field(default="", max_length=120)
    reason: str = Field(min_length=3, max_length=1000)


class CustomerProposal(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    quoted_total: float
    proposed_total: float
    discount_value: float
    discount_percent: float
    effective_margin_percent: float
    minimum_margin_percent: float
    status: CustomerProposalStatus = CustomerProposalStatus.PENDING
    submitted_by: str = ""
    notes: str = ""
    submitted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    decided_by: str = ""
    decision_reason: str = ""
    decided_at: datetime | None = None


class CostSettings(BaseModel):
    attach_institutional_page: bool = True
    institutional_page_minimum: float = Field(default=10000, ge=0)
    default_margin_percent: float = Field(default=30, ge=0, lt=100)
    minimum_effective_margin_percent: float = Field(default=20, ge=0, lt=100)
    sale_industrialization_price_review_days: int = Field(default=30, ge=1, le=3650)
    sale_consumption_price_review_days: int = Field(default=30, ge=1, le=3650)
    industrialization_price_review_days: int = Field(default=180, ge=1, le=3650)
    third_party_material_price_review_days: int = Field(default=180, ge=1, le=3650)
    default_item_utilization_percent: float = Field(default=80, gt=0, le=100)
    default_ipi_percent: float = Field(default=0, ge=0, le=100)
    default_cbs_percent: float = Field(default=0, ge=0, le=100)
    default_ibs_percent: float = Field(default=0, ge=0, le=100)
    default_cut_hourly_rate: float = Field(default=360, ge=0)
    default_laser_cutting_speed_mm_min: float = Field(default=2000, gt=0)
    default_laser_piercing_seconds: float = Field(default=1, ge=0)
    default_bend_hourly_rate: float = Field(default=260, ge=0)
    bend_time_1_piece_minutes: float = Field(default=10, ge=0)
    bend_time_2_pieces_minutes: float = Field(default=5, ge=0)
    bend_time_3_pieces_minutes: float = Field(default=4, ge=0)
    bend_time_4_to_5_pieces_minutes: float = Field(default=3, ge=0)
    bend_time_6_plus_pieces_minutes: float = Field(default=2.5, ge=0)
    default_roll_hourly_rate: float = Field(default=240, ge=0)
    default_nesting_gap_mm: float = Field(default=5, ge=0, le=100)
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


class PriceAdjustmentCreate(BaseModel):
    client_id: UUID
    item_code: str = Field(min_length=1, max_length=60)
    commercial_operation: CommercialOperation
    previous_unit_price: float = Field(ge=0)
    new_unit_price: float = Field(gt=0)
    reason: str = Field(min_length=3, max_length=500)
    effective_date: date = Field(default_factory=date.today)
    adjusted_by: str = Field(default="", max_length=120)


class PriceAdjustment(PriceAdjustmentCreate):
    id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
