from datetime import date, datetime, timedelta, timezone
import re
import math
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from danfer_os.models.commercial import CommercialOperation, QuoteStatus, QuoteType
from danfer_os.models.pcp import ProductionOrder, ProductionOrderCreate, ProductionOrderItem, ProductionStatus, WorkLogType
from danfer_os.services.bom import BomNotFoundError, BomService
from danfer_os.services.commercial import CommercialNotFoundError, CommercialService, CommercialValidationError
from danfer_os.services.pcp import PcpService
from danfer_os.services.technical_library import TechnicalLibrary
from danfer_os.models.integrations import ErpEvent
from danfer_os.services.integrations import IntegrationService

BUSINESS_TZ = timezone(timedelta(hours=-3))


class ServiceHistoryQuery(BaseModel):
    commercial_operation: CommercialOperation
    quantity: float = Field(gt=0)
    total_weight_kg: float = Field(default=0, ge=0)
    routing_steps: list[str] = Field(min_length=1)


class ServiceHistorySample(BaseModel):
    order_number: str
    quote_number: str
    quantity: float
    total_weight_kg: float
    actual_minutes: float
    charged_value: float
    similarity_percent: int


class ServicePriceSuggestion(BaseModel):
    eligible: bool
    reason: str
    sample_count: int = 0
    confidence_percent: int = 0
    suggested_minutes: float | None = None
    suggested_value: float | None = None
    minimum_value: float | None = None
    maximum_value: float | None = None
    samples: list[ServiceHistorySample] = Field(default_factory=list)


class InvoiceBatchRequest(BaseModel):
    quote_ids: list[UUID] = Field(min_length=1, max_length=200)


class InvoiceItemRequest(BaseModel):
    item_id: UUID
    quantity: float = Field(gt=0)


class InvoiceRequest(BaseModel):
    items: list[InvoiceItemRequest] = Field(min_length=1, max_length=500)


def create_router(
    commercial: CommercialService,
    library: TechnicalLibrary,
    boms: BomService,
    pcp: PcpService,
    integrations: IntegrationService,
) -> APIRouter:
    router = APIRouter(prefix="/workflows", tags=["fluxos integrados"])

    @router.post(
        "/quotes/{quote_id}/production-orders",
        response_model=list[ProductionOrder],
    )
    def quote_to_production(quote_id: UUID) -> list[ProductionOrder]:
        try:
            quote = commercial.get_quote(quote_id)
        except CommercialNotFoundError as error:
            raise HTTPException(status_code=404, detail="orçamento não encontrado") from error
        if quote.status != QuoteStatus.APPROVED:
            raise HTTPException(status_code=409, detail="o orçamento precisa estar aprovado")
        existing = [item for item in pcp.list() if item.source_quote_id == quote.id]
        if existing:
            return existing
        delivery = quote.expected_delivery or date.today()
        created = []
        missing = []
        parts = {item.danfer_code.casefold(): item for item in library.list()}
        groups: dict[tuple[float | None, tuple[str, ...]], list] = {}
        for item in quote.items:
            route = tuple(process.name.strip() for process in item.processes)
            groups.setdefault((item.thickness_mm, route), []).append(item)
        match = re.fullmatch(r"ORC-(\d{4})-(\d+)", quote.number)
        base_number = f"{int(match.group(2))}-{match.group(1)[-2:]}" if match else quote.number
        client = commercial.get_client(quote.client_id)
        for sequence, ((thickness, route), group_items) in enumerate(groups.items(), 1):
            resolved = []
            for item in group_items:
                part = parts.get(item.code.casefold())
                if part is None:
                    missing.append(f"{item.code}: peça não cadastrada")
                    continue
                try:
                    bom = boms.for_product(part.id)
                except BomNotFoundError:
                    missing.append(f"{item.code}: BOM ativa não encontrada")
                    continue
                resolved.append((item, part, bom))
            if not resolved:
                continue
            first_item, part, bom = resolved[0]
            material_names = sorted({item.material for item, _, _ in resolved if item.material})
            created.append(
                pcp.create(
                    ProductionOrderCreate(
                        product_id=part.id,
                        bom_id=bom.id,
                        quantity=sum(item.quantity for item, _, _ in resolved),
                        due_date=delivery,
                        priority=3,
                        estimated_material_cost=sum(item.material_cost * item.quantity for item, _, _ in resolved),
                        estimated_process_cost=sum((item.process_cost + item.indirect_cost) * item.quantity for item, _, _ in resolved),
                        notes=f"Gerada pelo orçamento {quote.number}", source_quote_id=quote.id,
                        source_quote_number=quote.number, client_name=client.name,
                        material=" / ".join(material_names), thickness_mm=thickness,
                        routing_steps=list(route), number_override=f"{base_number}-{sequence}",
                        production_items=[ProductionOrderItem(
                            code=item.code, description=item.description, quantity=item.quantity,
                            unit_weight_kg=item.net_weight_kg,
                        ) for item, _, _ in resolved],
                    )
                )
            )
        if missing and not created:
            raise HTTPException(status_code=422, detail="; ".join(missing))
        return created

    @router.post("/service-price-suggestion", response_model=ServicePriceSuggestion)
    def service_price_suggestion(data: ServiceHistoryQuery) -> ServicePriceSuggestion:
        if data.commercial_operation in {
            CommercialOperation.SALE_INDUSTRIALIZATION,
            CommercialOperation.SALE_USE_CONSUMPTION,
        }:
            return ServicePriceSuggestion(
                eligible=False,
                reason="Consultas históricas são usadas somente em industrializações/serviços.",
            )
        target_route = {step.strip().casefold() for step in data.routing_steps if step.strip()}
        candidates: list[tuple[float, ServiceHistorySample]] = []
        for order in pcp.list(ProductionStatus.COMPLETED):
            if not order.source_quote_id:
                continue
            try:
                quote = commercial.get_quote(order.source_quote_id)
            except CommercialNotFoundError:
                continue
            # Somente vendas efetivamente confirmadas e convertidas em OP podem aprender.
            if quote.status not in {QuoteStatus.APPROVED, QuoteStatus.PARTIALLY_INVOICED, QuoteStatus.INVOICED} or quote.type != QuoteType.SERVICE:
                continue
            if quote.commercial_operation != data.commercial_operation:
                continue
            operation_logs = [log for log in pcp.logs(order.id) if log.type == WorkLogType.OPERATION and log.minutes > 0]
            if not operation_logs:
                continue
            actual_minutes = sum(log.minutes for log in operation_logs)
            quantity = sum(item.quantity for item in order.production_items) or order.quantity
            weight = sum(item.quantity * item.unit_weight_kg for item in order.production_items)
            codes = {item.code.casefold() for item in order.production_items}
            charged = sum(item.total_price for item in quote.items if item.code.casefold() in codes)
            if charged <= 0:
                continue
            route = {step.strip().casefold() for step in order.routing_steps if step.strip()}
            route_score = len(target_route & route) / len(target_route | route) if target_route | route else 0
            quantity_score = math.exp(-abs(math.log(max(quantity, .001) / data.quantity)))
            weight_score = 1.0 if not data.total_weight_kg or not weight else math.exp(-abs(math.log(weight / data.total_weight_kg)))
            score = .55 * route_score + .25 * quantity_score + .20 * weight_score
            if route_score < .5 or score < .45:
                continue
            candidates.append((score, ServiceHistorySample(
                order_number=order.number, quote_number=quote.number, quantity=quantity,
                total_weight_kg=round(weight, 3), actual_minutes=round(actual_minutes, 2),
                charged_value=round(charged, 2), similarity_percent=round(score * 100),
            )))
        candidates.sort(key=lambda item: item[0], reverse=True)
        selected = candidates[:20]
        if not selected:
            return ServicePriceSuggestion(
                eligible=True,
                reason="Ainda não existem OPs concluídas semelhantes com tempo real apontado.",
            )
        total_weight = sum(score for score, _ in selected)
        suggested_minutes = sum(score * sample.actual_minutes for score, sample in selected) / total_weight
        suggested_value = sum(score * sample.charged_value for score, sample in selected) / total_weight
        values = [sample.charged_value for _, sample in selected]
        confidence = min(95, round((sum(score for score, _ in selected) / len(selected)) * 70 + min(len(selected), 10) * 3))
        return ServicePriceSuggestion(
            eligible=True,
            reason="Sugestão consultiva baseada exclusivamente em OPs concluídas e apontamentos reais.",
            sample_count=len(selected), confidence_percent=confidence,
            suggested_minutes=round(suggested_minutes, 2), suggested_value=round(suggested_value, 2),
            minimum_value=round(min(values), 2), maximum_value=round(max(values), 2),
            samples=[sample for _, sample in selected],
        )

    @router.get("/production-progress")
    def production_progress() -> list[dict]:
        grouped: dict[str, dict] = {}
        for order in pcp.list():
            if not order.source_quote_id:
                continue
            row = grouped.setdefault(order.client_name or "Cliente não informado", {
                "client": order.client_name or "Cliente não informado", "total": 0, "completed": 0,
            })
            row["total"] += 1
            row["completed"] += int(order.status.value == "concluida")
        for row in grouped.values():
            row["percent"] = round(row["completed"] / row["total"] * 100) if row["total"] else 0
        return sorted(grouped.values(), key=lambda item: item["client"].casefold())

    @router.get("/price-reviews")
    def price_reviews(
        client_id: UUID | None = None,
        quote_type: QuoteType | None = Query(default=None, alias="type"),
        start: date | None = None,
        end: date | None = None,
        expired_only: bool = False,
    ) -> list[dict]:
        settings = commercial.settings()
        validity = {
            CommercialOperation.SALE_INDUSTRIALIZATION: settings.sale_industrialization_price_review_days,
            CommercialOperation.SALE_USE_CONSUMPTION: settings.sale_consumption_price_review_days,
            CommercialOperation.INDUSTRIALIZATION: settings.industrialization_price_review_days,
            CommercialOperation.THIRD_PARTY_MATERIAL: settings.third_party_material_price_review_days,
        }
        adjustments = commercial.price_adjustments()
        rows = []
        for order in pcp.list(ProductionStatus.COMPLETED):
            if not order.source_quote_id:
                continue
            try:
                quote = commercial.get_quote(order.source_quote_id)
                client = commercial.get_client(quote.client_id)
            except CommercialNotFoundError:
                continue
            if quote.status not in {QuoteStatus.APPROVED, QuoteStatus.PARTIALLY_INVOICED, QuoteStatus.INVOICED} or (client_id and quote.client_id != client_id) or (quote_type and quote.type != quote_type):
                continue
            produced_on = order.updated_at.astimezone(BUSINESS_TZ).date()
            if (start and produced_on < start) or (end and produced_on > end):
                continue
            days = validity[quote.commercial_operation]
            expires_on = produced_on + timedelta(days=days)
            expired = datetime.now(BUSINESS_TZ).date() > expires_on
            if expired_only and not expired:
                continue
            for produced in order.production_items:
                quote_item = next((item for item in quote.items if item.code.casefold() == produced.code.casefold()), None)
                if quote_item is None:
                    continue
                adjustment = next((item for item in adjustments if item.client_id == quote.client_id and item.item_code.casefold() == produced.code.casefold() and item.commercial_operation == quote.commercial_operation), None)
                rows.append({
                    "client_id": str(quote.client_id), "client": client.name,
                    "quote_type": quote.type.value, "commercial_operation": quote.commercial_operation.value,
                    "quote_number": quote.number, "order_number": order.number,
                    "item_code": produced.code, "description": produced.description,
                    "quantity": produced.quantity, "total_weight_kg": round(produced.quantity * produced.unit_weight_kg, 3),
                    "produced_on": produced_on.isoformat(), "validity_days": days,
                    "expires_on": expires_on.isoformat(), "expired": expired,
                    "historical_unit_price": quote_item.unit_price,
                    "current_reference_price": adjustment.new_unit_price if adjustment else quote_item.unit_price,
                    "last_adjustment_date": adjustment.effective_date.isoformat() if adjustment else None,
                })
        return sorted(rows, key=lambda item: (item["client"].casefold(), item["item_code"], item["produced_on"]), reverse=True)

    @router.post("/quotes/{quote_id}/erp-order", response_model=ErpEvent)
    def quote_to_erp(quote_id: UUID) -> ErpEvent:
        try:
            quote = commercial.get_quote(quote_id)
            client = commercial.get_client(quote.client_id)
        except CommercialNotFoundError as error:
            raise HTTPException(status_code=404, detail="orçamento ou cliente não encontrado") from error
        if quote.status != QuoteStatus.APPROVED:
            raise HTTPException(status_code=409, detail="o orçamento precisa estar aprovado")
        return integrations.queue_quote(quote, client)

    def invoice_context(quote_id: UUID):
        try:
            quote = commercial.get_quote(quote_id)
            client = commercial.get_client(quote.client_id)
        except CommercialNotFoundError as error:
            raise HTTPException(status_code=404, detail="orçamento ou cliente não encontrado") from error
        if quote.status == QuoteStatus.INVOICED:
            raise HTTPException(status_code=409, detail=f"{quote.number} já está faturado")
        if quote.status not in {QuoteStatus.APPROVED, QuoteStatus.PARTIALLY_INVOICED}:
            raise HTTPException(status_code=409, detail=f"{quote.number} não possui saldo para faturamento")
        orders = [item for item in pcp.list() if item.source_quote_id == quote.id]
        if not orders:
            raise HTTPException(status_code=409, detail=f"{quote.number} não possui OP vinculada")
        return quote, client, orders

    def invoice_availability(quote, orders) -> list[dict]:
        completed_by_code: dict[str, float] = {}
        for order in orders:
            if order.status != ProductionStatus.COMPLETED:
                continue
            for produced in order.production_items:
                key = produced.code.casefold()
                completed_by_code[key] = completed_by_code.get(key, 0) + produced.quantity
        already_by_code: dict[str, float] = {}
        for item in quote.items:
            key = item.code.casefold()
            already_by_code[key] = already_by_code.get(key, 0) + quote.invoiced_quantities.get(str(item.id), 0)
        available_by_code = {key: max(quantity - already_by_code.get(key, 0), 0)
                             for key, quantity in completed_by_code.items()}
        rows = []
        for item in quote.items:
            invoiced = quote.invoiced_quantities.get(str(item.id), 0)
            remaining = max(item.quantity - invoiced, 0)
            key = item.code.casefold()
            eligible = min(remaining, available_by_code.get(key, 0))
            available_by_code[key] = max(available_by_code.get(key, 0) - eligible, 0)
            rows.append({"item_id": str(item.id), "code": item.code, "description": item.description,
                         "quantity": item.quantity, "invoiced_quantity": invoiced,
                         "remaining_quantity": remaining, "eligible_quantity": eligible,
                         "unit": item.unit, "unit_price": item.unit_price})
        return rows

    def selected_quantities(quote, orders, data: InvoiceRequest | None) -> dict[UUID, float]:
        availability = invoice_availability(quote, orders)
        eligible = {UUID(row["item_id"]): row["eligible_quantity"] for row in availability}
        requested = ({row.item_id: row.quantity for row in data.items} if data else
                     {item_id: quantity for item_id, quantity in eligible.items() if quantity > 1e-6})
        if not requested:
            raise HTTPException(status_code=409, detail=f"{quote.number} não possui itens produzidos com saldo")
        for item_id, quantity in requested.items():
            if item_id not in eligible:
                raise HTTPException(status_code=422, detail=f"item {item_id} não pertence ao orçamento")
            if quantity > eligible[item_id] + 1e-6:
                raise HTTPException(status_code=409, detail="quantidade solicitada supera o saldo produzido disponível")
        return requested

    @router.get("/invoice-ready")
    def invoice_ready() -> list[dict]:
        rows = []
        for quote in commercial.list_quotes():
            if quote.status not in {QuoteStatus.APPROVED, QuoteStatus.PARTIALLY_INVOICED, QuoteStatus.INVOICED}:
                continue
            orders = [item for item in pcp.list() if item.source_quote_id == quote.id]
            if not orders:
                continue
            completed = sum(item.status == ProductionStatus.COMPLETED for item in orders)
            client = commercial.get_client(quote.client_id)
            items = invoice_availability(quote, orders)
            invoiced_subtotal = sum(item.unit_price * quote.invoiced_quantities.get(str(item.id), 0)
                                     for item in quote.items)
            invoiced_total = (round(quote.total * invoiced_subtotal / quote.subtotal, 2)
                              if quote.subtotal else round(invoiced_subtotal, 2))
            rows.append({"quote_id": str(quote.id), "quote_number": quote.number,
                         "client": client.name, "erp_customer_code": client.erp_code,
                         "total": quote.total, "orders": len(orders), "completed": completed,
                         "ready": any(item["eligible_quantity"] > 1e-6 for item in items)
                                  and quote.status != QuoteStatus.INVOICED,
                         "invoiced_total": invoiced_total, "remaining_total": round(quote.total - invoiced_total, 2),
                         "items": items, "status": quote.status.value})
        return rows

    @router.post("/quotes/{quote_id}/invoice", response_model=ErpEvent)
    def invoice_quote(quote_id: UUID, data: InvoiceRequest | None = None) -> ErpEvent:
        quote, client, orders = invoice_context(quote_id)
        quantities = selected_quantities(quote, orders, data)
        event = integrations.queue_invoice(quote, client, quantities)
        try:
            commercial.register_invoice(quote.id, quantities)
        except CommercialValidationError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        return event

    @router.post("/invoice-batch", response_model=list[ErpEvent])
    def invoice_batch(data: InvoiceBatchRequest) -> list[ErpEvent]:
        contexts = [invoice_context(quote_id) for quote_id in dict.fromkeys(data.quote_ids)]
        prepared = [(quote, client, selected_quantities(quote, orders, None))
                    for quote, client, orders in contexts]
        events = []
        for quote, client, quantities in prepared:
            events.append(integrations.queue_invoice(quote, client, quantities))
            commercial.register_invoice(quote.id, quantities)
        return events

    @router.get("/invoiced-cost-history")
    def invoiced_cost_history(item_code: str = Query(min_length=1), client_id: UUID | None = None) -> dict:
        normalized = item_code.strip().casefold()
        rows = []
        for event in integrations.list_events():
            if event.action != "faturar":
                continue
            try:
                quote = commercial.get_quote(event.entity_id)
                client = commercial.get_client(quote.client_id)
            except CommercialNotFoundError:
                continue
            if client_id and quote.client_id != client_id:
                continue
            for billed in event.payload.get("items", []):
                if str(billed.get("code", "")).strip().casefold() != normalized:
                    continue
                item_id = str(billed.get("item_id", ""))
                quote_item = next((item for item in quote.items if str(item.id) == item_id), None)
                if quote_item is None:
                    quote_item = next((item for item in quote.items if item.code.casefold() == normalized), None)
                if quote_item is None:
                    continue
                produced_orders = [order for order in pcp.list(ProductionStatus.COMPLETED)
                                   if order.source_quote_id == quote.id
                                   and any(part.code.casefold() == normalized for part in order.production_items)]
                actual_cost_total = 0.0
                actual_quantity = 0.0
                for order in produced_orders:
                    matching_quantity = sum(part.quantity for part in order.production_items
                                            if part.code.casefold() == normalized)
                    if matching_quantity <= 0:
                        continue
                    costs = pcp.costs(order.id)
                    order_quantity = sum(part.quantity for part in order.production_items) or order.quantity
                    share = matching_quantity / order_quantity if order_quantity else 0
                    actual_cost_total += costs.actual_total_cost * share
                    actual_quantity += matching_quantity
                actual_unit_cost = (actual_cost_total / actual_quantity
                                    if actual_quantity and actual_cost_total > 0 else quote_item.total_cost)
                unit_price = float(billed.get("unit_price", quote_item.unit_price))
                margin = ((unit_price - actual_unit_cost) / unit_price * 100) if unit_price else 0
                rows.append({
                    "invoice_event_id": str(event.id), "invoice_sequence": event.payload.get("invoice_sequence", 1),
                    "invoiced_at": event.created_at.isoformat(), "quote_number": quote.number,
                    "client": client.name, "erp_customer_code": client.erp_code,
                    "item_code": quote_item.code, "description": quote_item.description,
                    "quantity": float(billed.get("quantity", 0)), "unit": quote_item.unit,
                    "estimated_unit_cost": round(quote_item.total_cost, 2),
                    "actual_unit_cost": round(actual_unit_cost, 2), "unit_price": round(unit_price, 2),
                    "effective_margin_percent": round(margin, 2),
                })
        rows.sort(key=lambda row: row["invoiced_at"], reverse=True)
        total_quantity = sum(row["quantity"] for row in rows)
        weighted_cost = (sum(row["actual_unit_cost"] * row["quantity"] for row in rows) / total_quantity
                         if total_quantity else 0)
        standard_margin = commercial.settings().default_margin_percent
        suggested = weighted_cost / (1 - standard_margin / 100) if weighted_cost and standard_margin < 100 else 0
        return {"item_code": item_code.strip(), "sample_count": len(rows),
                "total_invoiced_quantity": round(total_quantity, 3),
                "standard_margin_percent": standard_margin,
                "weighted_unit_cost": round(weighted_cost, 2),
                "suggested_unit_price": round(suggested, 2), "history": rows}

    return router
