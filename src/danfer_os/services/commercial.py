from __future__ import annotations

import json
from decimal import Decimal, ROUND_HALF_UP
import math
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from uuid import UUID

from danfer_os.models.commercial import (
    Client,
    ClientCreate,
    ClientUpdate,
    CostSettings,
    CustomerProposal,
    CustomerProposalCreate,
    CustomerProposalDecision,
    CustomerProposalStatus,
    Quote,
    QuoteCreate,
    QuoteItem,
    QuoteItemCreate,
    NestingMode,
    PriceAdjustment,
    PriceAdjustmentCreate,
    QuoteRevision,
    QuoteStatus,
    QuoteUpdate,
)
from danfer_os.models.engineering import NestingBatchPlan, NestingPart, NestingRequest, NestingSheet
from danfer_os.services.catalogs import CatalogService
from danfer_os.services.engineering import EngineeringService
from danfer_os.models.operations import NotificationCreate
from danfer_os.services.operations import OperationsService


class CommercialNotFoundError(LookupError):
    pass


class CommercialValidationError(ValueError):
    pass


class CommercialService:
    _status_transitions = {
        QuoteStatus.DRAFT: {QuoteStatus.SENT, QuoteStatus.CANCELLED},
        QuoteStatus.SENT: {QuoteStatus.NEGOTIATION, QuoteStatus.APPROVED, QuoteStatus.LOST},
        QuoteStatus.NEGOTIATION: {QuoteStatus.SENT, QuoteStatus.APPROVED, QuoteStatus.LOST},
        QuoteStatus.PENDING_ADMIN_APPROVAL: {QuoteStatus.NEGOTIATION, QuoteStatus.APPROVED},
        QuoteStatus.APPROVED: {QuoteStatus.PARTIALLY_INVOICED, QuoteStatus.INVOICED},
        QuoteStatus.PARTIALLY_INVOICED: {QuoteStatus.INVOICED},
        QuoteStatus.LOST: {QuoteStatus.DRAFT},
        QuoteStatus.CANCELLED: {QuoteStatus.DRAFT},
        QuoteStatus.INVOICED: set(),
    }

    @staticmethod
    def _money(value: float) -> float:
        return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

    def __init__(self, storage_path: Path | None = None, catalog_service: CatalogService | None = None, notifications: OperationsService | None = None) -> None:
        self._storage_path = storage_path
        self._catalog_service = catalog_service
        self._notifications = notifications
        self._clients: dict[UUID, Client] = {}
        self._quotes: dict[UUID, Quote] = {}
        self._revisions: dict[UUID, list[QuoteRevision]] = {}
        self._price_adjustments: list[PriceAdjustment] = []
        self._settings = CostSettings()
        self._quote_sequence = 0
        self._lock = RLock()
        self._load()

    def _load(self) -> None:
        if self._storage_path is None or not self._storage_path.exists():
            return
        payload = json.loads(self._storage_path.read_text(encoding="utf-8"))
        self._clients = {
            item.id: item
            for item in (Client.model_validate(value) for value in payload.get("clients", []))
        }
        self._quotes = {
            item.id: item
            for item in (Quote.model_validate(value) for value in payload.get("quotes", []))
        }
        self._revisions = {
            UUID(key): [QuoteRevision.model_validate(item) for item in values]
            for key, values in payload.get("revisions", {}).items()
        }
        self._settings = CostSettings.model_validate(payload.get("settings", {}))
        self._price_adjustments = [PriceAdjustment.model_validate(item) for item in payload.get("price_adjustments", [])]
        self._quote_sequence = int(payload.get("quote_sequence", 0))

    def _save(self) -> None:
        if self._storage_path is None:
            return
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "clients": [item.model_dump(mode="json") for item in self._clients.values()],
            "quotes": [item.model_dump(mode="json") for item in self._quotes.values()],
            "revisions": {
                str(key): [item.model_dump(mode="json") for item in values]
                for key, values in self._revisions.items()
            },
            "settings": self._settings.model_dump(mode="json"),
            "price_adjustments": [item.model_dump(mode="json") for item in self._price_adjustments],
            "quote_sequence": self._quote_sequence,
        }
        self._storage_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def create_client(self, data: ClientCreate) -> Client:
        if data.document and any(
            item.document == data.document for item in self._clients.values()
        ):
            raise CommercialValidationError("CNPJ/CPF já cadastrado")
        client = Client(**data.model_dump())
        with self._lock:
            self._clients[client.id] = client
            self._save()
        return client.model_copy(deep=True)

    def list_clients(self, query: str = "") -> list[Client]:
        needle = query.strip().casefold()
        clients = self._clients.values()
        if needle:
            clients = (
                item for item in clients
                if needle in item.name.casefold()
                or needle in item.document.casefold()
                or needle in item.contact.casefold()
            )
        return [
            item.model_copy(deep=True)
            for item in sorted(clients, key=lambda value: value.name.casefold())
        ]

    def get_client(self, client_id: UUID) -> Client:
        client = self._clients.get(client_id)
        if client is None:
            raise CommercialNotFoundError(client_id)
        return client.model_copy(deep=True)

    def update_client(self, client_id: UUID, data: ClientUpdate) -> Client:
        current = self.get_client(client_id)
        updated = current.model_copy(
            update={
                **data.model_dump(exclude_unset=True),
                "updated_at": datetime.now(timezone.utc),
            }
        )
        with self._lock:
            self._clients[client_id] = updated
            self._save()
        return updated.model_copy(deep=True)

    def settings(self) -> CostSettings:
        return self._settings.model_copy(deep=True)

    def update_settings(self, data: CostSettings) -> CostSettings:
        self._settings = data.model_copy(deep=True)
        self._save()
        return self.settings()

    def bend_time_settings(self) -> dict[str, float]:
        return {
            "one": self._settings.bend_time_1_piece_minutes,
            "two": self._settings.bend_time_2_pieces_minutes,
            "three": self._settings.bend_time_3_pieces_minutes,
            "four_to_five": self._settings.bend_time_4_to_5_pieces_minutes,
            "six_plus": self._settings.bend_time_6_plus_pieces_minutes,
        }

    def create_price_adjustment(self, data: PriceAdjustmentCreate) -> PriceAdjustment:
        self.get_client(data.client_id)
        adjustment = PriceAdjustment(**data.model_dump())
        with self._lock:
            self._price_adjustments.append(adjustment)
            self._save()
        return adjustment.model_copy(deep=True)

    def price_adjustments(self) -> list[PriceAdjustment]:
        return [item.model_copy(deep=True) for item in reversed(self._price_adjustments)]

    def _calculate_item(
        self,
        data: QuoteItemCreate,
        margin_percent: float,
        quote_type: str,
        compatible_item_count: int,
        batch_plan: NestingBatchPlan | None = None,
    ) -> QuoteItem:
        selected = None
        if self._catalog_service is not None:
            candidates = self._catalog_service.list_materials(data.material, True)
            selected = next((item for item in candidates if (
                item.description.casefold() == data.material.casefold()
                and (data.thickness_mm is None or item.thickness_mm == data.thickness_mm)
            )), None)
        automatic_updates = {}
        if selected and not data.thickness_mm:
            automatic_updates["thickness_mm"] = selected.thickness_mm
        effective_thickness = data.thickness_mm or (selected.thickness_mm if selected else None)
        if not data.net_weight_kg and data.width_mm and data.length_mm and effective_thickness and selected:
            automatic_updates["net_weight_kg"] = (
                data.width_mm * data.length_mm * effective_thickness
                * selected.density_kg_m3 / 1_000_000_000
            )
        if not data.cut_length_mm and data.width_mm and data.length_mm:
            automatic_updates["cut_length_mm"] = 2 * (data.width_mm + data.length_mm)
        if automatic_updates:
            data = data.model_copy(update=automatic_updates)
        utilization = max(
            data.utilization_percent
            if data.utilization_percent is not None
            else self._settings.default_item_utilization_percent,
            1,
        )
        selected_width = selected_length = None
        selected_sheet_count = None
        calculated_waste = None
        plan_reference = ""
        applied_gap = 0.0
        costing_method = "aproveitamento_informado"
        calculation_source = "administrativo"
        warnings: list[str] = []
        material_consumption = data.net_weight_kg / (utilization / 100)
        applied_plan = data.nesting_plan
        if applied_plan is not None:
            utilization = applied_plan.utilization_percent
            selected_width = applied_plan.sheet_width_mm
            selected_length = applied_plan.sheet_length_mm
            selected_sheet_count = applied_plan.sheet_count
            calculated_utilization = utilization
            calculated_waste = applied_plan.waste_percent
            plan_reference = applied_plan.reference
            costing_method = "nesting_real"
            calculation_source = "plano_engenharia"
        elif data.nesting_mode == NestingMode.FORCE and data.utilization_percent is not None:
            calculated_utilization = utilization
            calculated_waste = 100 - utilization
            costing_method = "ncav_informado"
            calculation_source = "ncav"
        elif batch_plan is not None:
            utilization = max(batch_plan.utilization_percent, 1)
            selected_width = batch_plan.selected_sheet.width_mm
            selected_length = batch_plan.selected_sheet.length_mm
            selected_sheet_count = batch_plan.sheet_count
            calculated_utilization = utilization
            calculated_waste = batch_plan.waste_percent
            costing_method = "nesting_real"
            calculation_source = "nesting_geometrico"
            warnings.append(batch_plan.selection_reason)
        if (
            not (applied_plan or batch_plan)
            and data.nesting_mode == NestingMode.AUTOMATIC
            and data.width_mm and data.length_mm and data.thickness_mm
        ):
            applied_gap = next((gap for limit, gap in self._settings.gap_rules if data.thickness_mm <= limit), self._settings.gap_rules[-1][1])

            def sheet_metrics(width: float, length: float) -> tuple[int, float]:
                usable_w = max(width - 2 * self._settings.sheet_edge_margin_mm, 0)
                usable_l = max(length - 2 * self._settings.sheet_edge_margin_mm, 0)
                orientations = [(data.width_mm, data.length_mm), (data.length_mm, data.width_mm)]
                capacity = max(
                    int(usable_w // (part_w + applied_gap)) * int(usable_l // (part_l + applied_gap))
                    for part_w, part_l in orientations
                )
                if capacity <= 0:
                    return 0, 0
                sheets = math.ceil(data.quantity / capacity)
                occupied = data.width_mm * data.length_mm * data.quantity
                return capacity, occupied / (width * length * sheets) * 100

            standard = (
                self._settings.default_sheet_width_mm,
                self._settings.default_sheet_length_mm,
                *sheet_metrics(self._settings.default_sheet_width_mm, self._settings.default_sheet_length_mm),
            )
            alternative = (
                self._settings.alternative_sheet_width_mm,
                self._settings.alternative_sheet_length_mm,
                *sheet_metrics(self._settings.alternative_sheet_width_mm, self._settings.alternative_sheet_length_mm),
            )
            chosen = standard
            gain = ((alternative[3] - standard[3]) / standard[3] * 100) if standard[3] else (100 if alternative[2] else 0)
            if (not standard[2] and alternative[2]) or gain >= self._settings.alternative_minimum_gain_percent:
                chosen = alternative
                warnings.append(f"chapa alternativa selecionada; ganho calculado {gain:.1f}%")
            selected_width, selected_length, _, calculated_utilization = chosen
            if calculated_utilization:
                utilization = calculated_utilization
                costing_method = "nesting_retangular"
                calculation_source = "estimativa_retangular"

            if utilization < self._settings.strip_costing_threshold_percent and chosen[2]:
                usable_length = selected_length - 2 * self._settings.sheet_edge_margin_mm
                strip_options = []
                for cross, along in ((data.width_mm, data.length_mm), (data.length_mm, data.width_mm)):
                    per_strip = int(usable_length // (along + applied_gap))
                    if per_strip:
                        strips = math.ceil(data.quantity / per_strip)
                        strip_options.append(strips * (cross + applied_gap) * usable_length / data.quantity)
                if strip_options:
                    billable_area_unit = min(strip_options)
                    part_area = data.width_mm * data.length_mm
                    material_consumption = data.net_weight_kg * max(billable_area_unit / part_area, 1)
                    costing_method = "faixa_de_chapa"
                else:
                    material_consumption = data.net_weight_kg / (utilization / 100)
            else:
                material_consumption = data.net_weight_kg / (utilization / 100)
        elif not (applied_plan or batch_plan or data.nesting_mode == NestingMode.FORCE):
            calculated_utilization = None
        if self._settings.inox_warning_enabled and "inox" in data.material.casefold():
            warnings.append(self._settings.inox_warning)
        large_part_loss = (
            data.quantity == 1
            and utilization > self._settings.large_part_threshold_percent
            and compatible_item_count == 1
            and quote_type == "venda"
        )
        if large_part_loss and calculation_source in {"administrativo", "estimativa_retangular"}:
            material_consumption *= 1 + self._settings.large_part_loss_percent / 100
        material_price = data.material_price_kg
        if material_price is None:
            material_price = selected.price_per_kg if selected else 0
        material_price = material_price or 0
        material_cost = (
            0
            if quote_type == "servico"
            else material_consumption * material_price
        )
        process_cost = 0.0
        laser_estimated_minutes = data.laser_estimated_minutes
        laser_additional_applied = False
        bend_estimated_minutes = data.bend_estimated_minutes
        bend_additional_applied = False
        for process in data.processes:
            hourly_rate = process.hourly_rate
            pricing_mode = process.pricing_mode
            weight_rate = process.weight_rate
            fixed_cost = process.fixed_cost
            process_name = process.name.casefold()
            catalog_operation = next((item for item in (self._catalog_service.list_operations(True) if self._catalog_service else []) if item.name.casefold() == process_name), None)
            if catalog_operation and not (hourly_rate or weight_rate or fixed_cost):
                pricing_mode = catalog_operation.pricing_mode
                hourly_rate = hourly_rate or catalog_operation.hourly_rate
                weight_rate = weight_rate or catalog_operation.weight_rate
                fixed_cost = fixed_cost or catalog_operation.fixed_cost
            if not hourly_rate:
                if "corte" in process_name or "laser" in process_name:
                    hourly_rate = self._settings.default_cut_hourly_rate
                elif "dobra" in process_name:
                    hourly_rate = self._settings.default_bend_hourly_rate
                elif "calandra" in process_name:
                    hourly_rate = self._settings.default_roll_hourly_rate
            if pricing_mode.value == "peso":
                cost = data.net_weight_kg * weight_rate
            elif pricing_mode.value == "fixo":
                cost = fixed_cost
            else:
                minutes = process.minutes
                if "laser" in process_name or "corte laser" in process_name:
                    if not laser_estimated_minutes and data.cut_length_mm:
                        laser_speed = selected.laser_speed_mm_min if selected and selected.laser_speed_mm_min else self._settings.default_laser_cutting_speed_mm_min
                        laser_estimated_minutes = (
                            data.cut_length_mm / laser_speed
                            + data.piercings * self._settings.default_laser_piercing_seconds / 60
                        )
                    if laser_estimated_minutes:
                        minutes = laser_estimated_minutes
                    if not laser_additional_applied:
                        minutes += data.laser_additional_minutes
                        laser_additional_applied = True
                if "dobra" in process_name:
                    if not bend_estimated_minutes:
                        if data.quantity <= 1:
                            bend_estimated_minutes = self._settings.bend_time_1_piece_minutes
                        elif data.quantity <= 2:
                            bend_estimated_minutes = self._settings.bend_time_2_pieces_minutes
                        elif data.quantity <= 3:
                            bend_estimated_minutes = self._settings.bend_time_3_pieces_minutes
                        elif data.quantity <= 5:
                            bend_estimated_minutes = self._settings.bend_time_4_to_5_pieces_minutes
                        else:
                            bend_estimated_minutes = self._settings.bend_time_6_plus_pieces_minutes
                    minutes = bend_estimated_minutes
                    if not bend_additional_applied:
                        minutes += data.bend_additional_minutes
                        bend_additional_applied = True
                cost = minutes / 60 * hourly_rate
            cost += process.external_cost
            if (
                "dobra" in process.name.casefold()
                and data.quantity <= self._settings.small_bend_batch_limit
            ):
                cost += self._settings.small_bend_batch_surcharge / data.quantity
            process_cost += cost
        base_cost = material_cost + process_cost
        indirect = base_cost * self._settings.indirect_percent / 100
        total_cost = base_cost + indirect
        effective_margin = (
            data.margin_percent if data.margin_percent is not None else margin_percent
        )
        calculated_price = total_cost / (1 - effective_margin / 100)
        unit_price = (
            data.manual_unit_price
            if data.manual_unit_price is not None
            else calculated_price
        )
        rounded_unit_price = self._money(unit_price)
        return QuoteItem(
            **data.model_dump(exclude={"utilization_percent", "material_price_kg", "laser_estimated_minutes", "bend_estimated_minutes"}),
            utilization_percent=utilization,
            material_price_kg=material_price,
            laser_estimated_minutes=round(laser_estimated_minutes, 3),
            bend_estimated_minutes=round(bend_estimated_minutes, 3),
            material_cost=self._money(material_cost),
            process_cost=self._money(process_cost),
            indirect_cost=self._money(indirect),
            total_cost=self._money(total_cost),
            unit_price=rounded_unit_price,
            total_price=self._money(rounded_unit_price * data.quantity),
            costing_method=costing_method,
            selected_sheet_width_mm=selected_width,
            selected_sheet_length_mm=selected_length,
            calculated_utilization_percent=self._money(calculated_utilization) if calculated_utilization is not None else None,
            applied_gap_mm=applied_gap,
            selected_sheet_count=selected_sheet_count,
            calculated_waste_percent=self._money(calculated_waste) if calculated_waste is not None else None,
            nesting_calculation_source=calculation_source,
            nesting_plan_reference=plan_reference,
            costing_warnings=warnings,
        )

    def _calculate_quote(self, data: QuoteCreate, number: str) -> Quote:
        groups: dict[tuple[str, float | None], int] = {}
        for item in data.items:
            key = (item.material.casefold(), item.thickness_mm)
            groups[key] = groups.get(key, 0) + 1
        batch_plans: dict[tuple[str, float | None], NestingBatchPlan] = {}
        for key in groups:
            candidates = [
                (index, item) for index, item in enumerate(data.items)
                if (item.material.casefold(), item.thickness_mm) == key
                and item.nesting_mode == NestingMode.AUTOMATIC
                and item.nesting_plan is None
                and item.width_mm and item.length_mm
            ]
            if not candidates:
                continue
            thickness = key[1]
            gap = next(
                (value for limit, value in self._settings.gap_rules if thickness is not None and thickness <= limit),
                self._settings.default_nesting_gap_mm,
            )
            request = NestingRequest(
                parts=[NestingPart(
                    code=f"{index}:{item.code}", width_mm=item.width_mm,
                    height_mm=item.length_mm, quantity=max(int(math.ceil(item.quantity)), 1),
                    allow_rotation=True,
                ) for index, item in candidates],
                sheets=[
                    NestingSheet(name="Padrão", width_mm=self._settings.default_sheet_width_mm, length_mm=self._settings.default_sheet_length_mm),
                    NestingSheet(name="Alternativa", width_mm=self._settings.alternative_sheet_width_mm, length_mm=self._settings.alternative_sheet_length_mm),
                ],
                gap_mm=gap,
                edge_margin_mm=self._settings.sheet_edge_margin_mm,
                alternative_minimum_gain_percent=self._settings.alternative_minimum_gain_percent,
            )
            plan = EngineeringService.nesting_batch(request)
            if not plan.unplaced:
                batch_plans[key] = plan
        items = [
            self._calculate_item(
                item,
                data.margin_percent,
                data.type.value,
                groups[(item.material.casefold(), item.thickness_mm)],
                batch_plans.get((item.material.casefold(), item.thickness_mm)),
            )
            for item in data.items
        ]
        subtotal = sum(item.total_price for item in items)
        taxable = max(subtotal + data.freight_value - data.discount_value, 0)
        applied_tax_percent = data.ipi_percent if data.type.value == "venda" else 0
        taxes = taxable * applied_tax_percent / 100
        total_cost = sum(item.total_cost * item.quantity for item in items)
        total = taxable + taxes
        net_revenue = max(total - taxes, 0)
        effective_margin = ((net_revenue - total_cost) / net_revenue * 100) if net_revenue else -100
        return Quote(
            **data.model_dump(exclude={"items"}),
            items=items,
            number=number,
            subtotal=self._money(subtotal),
            taxes=self._money(taxes),
            total=self._money(total),
            total_cost=self._money(total_cost),
            gross_profit=self._money(total - taxes - total_cost),
            effective_margin_percent=self._money(effective_margin),
        )

    def create_quote(self, data: QuoteCreate) -> Quote:
        self.get_client(data.client_id)
        # Valores zero/default enviados por clientes antigos continuam válidos.
        # A interface simplificada envia os campos administrativos como nulos e
        # eles são resolvidos aqui, sem expor a configuração ao orçamentista.
        updates = {}
        if data.margin_percent is None:
            updates["margin_percent"] = self._settings.default_margin_percent
        if data.ipi_percent is None:
            updates["ipi_percent"] = self._settings.default_ipi_percent
        if data.cbs_percent is None:
            updates["cbs_percent"] = self._settings.default_cbs_percent
        if data.ibs_percent is None:
            updates["ibs_percent"] = self._settings.default_ibs_percent
        if updates:
            data = data.model_copy(update=updates)
        self._quote_sequence += 1
        number = f"ORC-{datetime.now():%Y}-{self._quote_sequence:05d}"
        quote = self._calculate_quote(data, number)
        with self._lock:
            self._quotes[quote.id] = quote
            self._revisions[quote.id] = []
            self._save()
        return quote.model_copy(deep=True)

    def preview_quote(self, data: QuoteCreate) -> Quote:
        """Calcula a proposta com as regras reais sem gravar ou consumir numeração."""
        self.get_client(data.client_id)
        updates = {}
        if data.margin_percent is None:
            updates["margin_percent"] = self._settings.default_margin_percent
        if data.ipi_percent is None:
            updates["ipi_percent"] = self._settings.default_ipi_percent
        if data.cbs_percent is None:
            updates["cbs_percent"] = self._settings.default_cbs_percent
        if data.ibs_percent is None:
            updates["ibs_percent"] = self._settings.default_ibs_percent
        if updates:
            data = data.model_copy(update=updates)
        return self._calculate_quote(data, "PRÉVIA")

    def list_quotes(
        self,
        status: QuoteStatus | None = None,
        client_id: UUID | None = None,
    ) -> list[Quote]:
        quotes = self._quotes.values()
        if status:
            quotes = (item for item in quotes if item.status == status)
        if client_id:
            quotes = (item for item in quotes if item.client_id == client_id)
        return [
            item.model_copy(deep=True)
            for item in sorted(quotes, key=lambda value: value.created_at, reverse=True)
        ]

    def get_quote(self, quote_id: UUID) -> Quote:
        quote = self._quotes.get(quote_id)
        if quote is None:
            raise CommercialNotFoundError(quote_id)
        return quote.model_copy(deep=True)

    def update_quote(self, quote_id: UUID, data: QuoteUpdate) -> Quote:
        current = self.get_quote(quote_id)
        if current.status == QuoteStatus.APPROVED:
            raise CommercialValidationError("orçamento aprovado não pode ser alterado")
        snapshot = current.model_dump(mode="json")
        values = current.model_dump(
            exclude={
                "id", "number", "revision", "status", "subtotal", "taxes",
                "total", "total_cost", "gross_profit", "effective_margin_percent",
                "customer_proposals", "created_at", "updated_at"
            }
        )
        changes = data.model_dump(exclude_unset=True, exclude={"change_reason"})
        values.update(changes)
        recalculated = self._calculate_quote(
            QuoteCreate.model_validate(values), current.number
        )
        revision_index = ord(current.revision[-1]) - ord("A") + 1
        updated = recalculated.model_copy(
            update={
                "id": current.id,
                "revision": chr(ord("A") + revision_index),
                "status": current.status,
                "created_at": current.created_at,
                "updated_at": datetime.now(timezone.utc),
                "customer_proposals": current.customer_proposals,
            }
        )
        record = QuoteRevision(
            quote_id=quote_id,
            revision=current.revision,
            reason=data.change_reason,
            snapshot=snapshot,
        )
        with self._lock:
            self._quotes[quote_id] = updated
            self._revisions.setdefault(quote_id, []).append(record)
            self._save()
        return updated.model_copy(deep=True)

    def change_status(
        self, quote_id: UUID, status: QuoteStatus, reason: str = ""
    ) -> Quote:
        current = self.get_quote(quote_id)
        if current.status == QuoteStatus.PENDING_ADMIN_APPROVAL:
            raise CommercialValidationError("a proposta do cliente deve ser decidida pelo fluxo de aprovação administrativa")
        if status != current.status and status not in self._status_transitions[current.status]:
            raise CommercialValidationError(
                f"transição inválida: {current.status.value} → {status.value}"
            )
        updated = current.model_copy(
            update={"status": status, "updated_at": datetime.now(timezone.utc)}
        )
        with self._lock:
            self._quotes[quote_id] = updated
            self._revisions.setdefault(quote_id, []).append(
                QuoteRevision(
                    quote_id=quote_id,
                    revision=current.revision,
                    reason=reason or f"Status alterado para {status.value}",
                    snapshot=current.model_dump(mode="json"),
                )
            )
            self._save()
        return updated.model_copy(deep=True)

    def revisions(self, quote_id: UUID) -> list[QuoteRevision]:
        self.get_quote(quote_id)
        return [item.model_copy(deep=True) for item in self._revisions.get(quote_id, [])]

    def register_invoice(self, quote_id: UUID, quantities: dict[UUID, float]) -> Quote:
        current = self.get_quote(quote_id)
        if current.status not in {QuoteStatus.APPROVED, QuoteStatus.PARTIALLY_INVOICED}:
            raise CommercialValidationError("o orçamento não possui saldo disponível para faturamento")
        accumulated = dict(current.invoiced_quantities)
        for item_id, quantity in quantities.items():
            item = next((row for row in current.items if row.id == item_id), None)
            if item is None:
                raise CommercialValidationError(f"item {item_id} não pertence ao orçamento")
            previous = accumulated.get(str(item_id), 0)
            if quantity <= 0 or previous + quantity > item.quantity + 1e-6:
                raise CommercialValidationError(f"quantidade inválida para o item {item.code}")
            accumulated[str(item_id)] = round(previous + quantity, 6)
        complete = all(accumulated.get(str(item.id), 0) >= item.quantity - 1e-6 for item in current.items)
        status = QuoteStatus.INVOICED if complete else QuoteStatus.PARTIALLY_INVOICED
        updated = current.model_copy(update={
            "invoiced_quantities": accumulated, "invoice_count": current.invoice_count + 1,
            "status": status, "updated_at": datetime.now(timezone.utc),
        })
        with self._lock:
            self._quotes[quote_id] = updated
            self._revisions.setdefault(quote_id, []).append(QuoteRevision(
                quote_id=quote_id, revision=current.revision,
                reason=f"Faturamento {'total' if complete else 'parcial'} #{updated.invoice_count}",
                snapshot=current.model_dump(mode="json"),
            ))
            self._save()
        return updated.model_copy(deep=True)

    def submit_customer_proposal(self, quote_id: UUID, data: CustomerProposalCreate) -> Quote:
        current = self.get_quote(quote_id)
        if current.status not in {QuoteStatus.SENT, QuoteStatus.NEGOTIATION}:
            raise CommercialValidationError("a proposta do cliente exige orçamento enviado ou em negociação")
        if data.proposed_total >= current.total:
            raise CommercialValidationError("a proposta do cliente deve ser menor que o total atual")
        tax_rate = current.ipi_percent if current.type.value == "venda" else 0
        proposed_net = data.proposed_total / (1 + tax_rate / 100)
        available_before_discount = current.subtotal + current.freight_value
        discount = max(available_before_discount - proposed_net, 0)
        margin = ((proposed_net - current.total_cost) / proposed_net * 100) if proposed_net else -100
        proposal = CustomerProposal(
            quoted_total=current.total,
            proposed_total=self._money(data.proposed_total),
            discount_value=self._money(discount),
            discount_percent=self._money((current.total - data.proposed_total) / current.total * 100),
            effective_margin_percent=self._money(margin),
            minimum_margin_percent=self._settings.minimum_effective_margin_percent,
            submitted_by=data.submitted_by,
            notes=data.notes,
        )
        updated = current.model_copy(update={
            "status": QuoteStatus.PENDING_ADMIN_APPROVAL,
            "customer_proposals": [*current.customer_proposals, proposal],
            "updated_at": datetime.now(timezone.utc),
        })
        with self._lock:
            self._quotes[quote_id] = updated
            self._revisions.setdefault(quote_id, []).append(QuoteRevision(
                quote_id=quote_id, revision=current.revision,
                reason=f"Proposta do cliente: {proposal.proposed_total:.2f}",
                snapshot=current.model_dump(mode="json"),
            ))
            self._save()
        if self._notifications:
            level = "ABAIXO da margem mínima" if margin < self._settings.minimum_effective_margin_percent else "dentro da margem mínima"
            self._notifications.create_notification(NotificationCreate(
                title=f"Autorização comercial: {current.number}",
                message=f"Cliente propôs R$ {proposal.proposed_total:.2f} sobre R$ {current.total:.2f}. Margem efetiva: {proposal.effective_margin_percent:.2f}% ({level}).",
                audience="administradores", recipient_role="administrador",
            ))
        return updated.model_copy(deep=True)

    def decide_customer_proposal(
        self, quote_id: UUID, proposal_id: UUID, data: CustomerProposalDecision, is_admin: bool
    ) -> Quote:
        if not is_admin:
            raise CommercialValidationError("somente o administrador pode decidir a proposta do cliente")
        current = self.get_quote(quote_id)
        proposal = next((item for item in current.customer_proposals if item.id == proposal_id), None)
        if proposal is None:
            raise CommercialNotFoundError(proposal_id)
        if proposal.status != CustomerProposalStatus.PENDING:
            raise CommercialValidationError("esta proposta já foi decidida")
        decided = proposal.model_copy(update={
            "status": CustomerProposalStatus.APPROVED if data.approved else CustomerProposalStatus.REJECTED,
            "decided_by": data.decided_by, "decision_reason": data.reason,
            "decided_at": datetime.now(timezone.utc),
        })
        proposals = [decided if item.id == proposal_id else item for item in current.customer_proposals]
        if data.approved:
            values = current.model_dump(exclude={
                "id", "number", "revision", "status", "items", "subtotal", "taxes", "total",
                "total_cost", "gross_profit", "effective_margin_percent", "customer_proposals",
                "created_at", "updated_at",
            })
            values["items"] = [item.model_dump(exclude={
                "id", "material_cost", "process_cost", "indirect_cost", "total_cost", "unit_price",
                "total_price", "costing_method", "selected_sheet_width_mm", "selected_sheet_length_mm",
                "calculated_utilization_percent", "applied_gap_mm", "selected_sheet_count",
                "calculated_waste_percent", "nesting_calculation_source", "nesting_plan_reference", "costing_warnings",
            }) for item in current.items]
            values["discount_value"] = proposal.discount_value
            recalculated = self._calculate_quote(QuoteCreate.model_validate(values), current.number)
            updated = recalculated.model_copy(update={
                "id": current.id, "revision": current.revision, "status": QuoteStatus.APPROVED,
                "customer_proposals": proposals, "created_at": current.created_at,
                "updated_at": datetime.now(timezone.utc),
            })
        else:
            updated = current.model_copy(update={
                "status": QuoteStatus.NEGOTIATION, "customer_proposals": proposals,
                "updated_at": datetime.now(timezone.utc),
            })
        with self._lock:
            self._quotes[quote_id] = updated
            self._revisions.setdefault(quote_id, []).append(QuoteRevision(
                quote_id=quote_id, revision=current.revision,
                reason=f"Proposta do cliente {'aprovada' if data.approved else 'recusada'} por {data.decided_by}: {data.reason}",
                snapshot=current.model_dump(mode="json"),
            ))
            self._save()
        if self._notifications:
            self._notifications.create_notification(NotificationCreate(
                title=f"Proposta {updated.number} {'aprovada' if data.approved else 'recusada'}",
                message=f"Decisão de {data.decided_by}: {data.reason}",
                audience="comercial", recipient_role="comercial",
            ))
        return updated.model_copy(deep=True)
