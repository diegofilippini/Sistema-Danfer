from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
from uuid import UUID
from xml.etree import ElementTree

from danfer_os.models.integrations import (
    ErpEvent,
    ErpEventStatus,
    ErpConnectionSettings,
    InvoiceFinancialData,
    PaymentInstallment,
    PaymentMethod,
    ExternalOrderCreate,
    ExternalOrderItem,
    ImportedOrder,
    ImportStatus,
)
from danfer_os.services.technical_library import TechnicalLibrary
from danfer_os.models.commercial import Client, Quote
from danfer_os.models.commercial import CommercialOperation
from danfer_os.services.catalogs import CatalogService


class IntegrationValidationError(ValueError):
    pass


class DuplicateExternalOrderError(ValueError):
    pass


class IntegrationService:
    def __init__(self, library: TechnicalLibrary, storage_path: Path | None = None,
                 catalog: CatalogService | None = None) -> None:
        self._library = library
        self._orders: dict[UUID, ImportedOrder] = {}
        self._external_keys: set[tuple[str, str]] = set()
        self._erp_events: dict[UUID, ErpEvent] = {}
        self._settings = ErpConnectionSettings()
        self._catalog = catalog
        self._storage_path = storage_path
        self._load()

    def _load(self) -> None:
        if self._storage_path is None or not self._storage_path.exists():
            return
        payload = json.loads(self._storage_path.read_text(encoding="utf-8"))
        orders = [ImportedOrder.model_validate(item) for item in payload.get("orders", [])]
        self._orders = {item.id: item for item in orders}
        self._external_keys = {(item.source.casefold(), item.external_id.casefold()) for item in orders}
        events = [ErpEvent.model_validate(item) for item in payload.get("erp_events", [])]
        self._erp_events = {item.id: item for item in events}
        self._settings = ErpConnectionSettings.model_validate(payload.get("settings", {}))

    def _save(self) -> None:
        if self._storage_path is None:
            return
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._storage_path.write_text(json.dumps({
            "version": 2,
            "orders": [item.model_dump(mode="json") for item in self._orders.values()],
            "erp_events": [item.model_dump(mode="json") for item in self._erp_events.values()],
            "settings": self._settings.model_dump(mode="json"),
        }, ensure_ascii=False, indent=2), encoding="utf-8")

    def import_order(self, data: ExternalOrderCreate) -> ImportedOrder:
        key = (data.source.casefold(), data.external_id.casefold())
        if key in self._external_keys:
            raise DuplicateExternalOrderError("pedido externo já importado")
        warnings = []
        catalog = self._library.list()
        customer_codes = {part.customer_code.casefold() for part in catalog if part.customer_code}
        danfer_codes = {part.danfer_code.casefold() for part in catalog}
        for index, item in enumerate(data.items, start=1):
            code = item.customer_code.casefold()
            if code not in customer_codes and code not in danfer_codes:
                warnings.append(
                    f"item {index}: código {item.customer_code} não localizado na biblioteca"
                )
        order = ImportedOrder(
            **data.model_dump(),
            status=ImportStatus.WARNING if warnings else ImportStatus.IMPORTED,
            warnings=warnings,
        )
        self._orders[order.id] = order
        self._external_keys.add(key)
        event = ErpEvent(
            entity="pedido", entity_id=order.id, action="importar",
            company_unit=order.company_unit,
            payload={"external_id": order.external_id, "customer": order.customer,
                     "erp_customer_code": order.erp_customer_code,
                     "items": [item.model_dump(mode="json") for item in order.items]},
        )
        self._erp_events[event.id] = event
        self._save()
        return order.model_copy(deep=True)

    def import_xml(self, xml: str) -> ImportedOrder:
        try:
            root = ElementTree.fromstring(xml)
            external_id = self._text(root, "external_id")
            customer = self._text(root, "customer")
            source = root.attrib.get("source", "xml")
            items = [
                ExternalOrderItem(
                    customer_code=self._text(node, "code"),
                    quantity=float(self._text(node, "quantity")),
                    unit=node.findtext("unit", default="un"),
                )
                for node in root.findall("./items/item")
            ]
            return self.import_order(
                ExternalOrderCreate(
                    source=source,
                    external_id=external_id,
                    customer=customer,
                    items=items,
                    notes=root.findtext("notes", default=""),
                )
            )
        except (ElementTree.ParseError, ValueError, TypeError) as error:
            raise IntegrationValidationError("XML de pedido inválido") from error

    @staticmethod
    def _text(node: ElementTree.Element, name: str) -> str:
        value = node.findtext(name)
        if value is None or not value.strip():
            raise IntegrationValidationError(f"campo XML obrigatório: {name}")
        return value.strip()

    def list_orders(self) -> list[ImportedOrder]:
        return [item.model_copy(deep=True) for item in self._orders.values()]

    def list_events(self, status: ErpEventStatus | None = None) -> list[ErpEvent]:
        events = self._erp_events.values()
        if status:
            events = (event for event in events if event.status == status)
        return [event.model_copy(deep=True) for event in events]

    def settings(self, include_secret: bool = False) -> ErpConnectionSettings:
        current = self._settings.model_copy(deep=True)
        if not include_secret and current.api_token:
            current.api_token = "********"
        return current

    def update_settings(self, settings: ErpConnectionSettings) -> ErpConnectionSettings:
        if settings.api_token == "********":
            settings = settings.model_copy(update={"api_token": self._settings.api_token})
        self._settings = settings.model_copy(deep=True)
        self._save()
        return self.settings()

    def validate_event(self, event_id: UUID) -> dict[str, object]:
        event = self._erp_events.get(event_id)
        if event is None:
            raise LookupError(event_id)
        payload = event.payload
        blocking: list[str] = []
        warnings: list[str] = []
        if not payload.get("erp_customer_code"):
            blocking.append("cliente sem código ERP")
        if not payload.get("customer_document"):
            blocking.append("cliente sem CNPJ/CPF")
        if not payload.get("erp_company_code"):
            blocking.append("unidade de faturamento sem código de empresa no ERP")
        if not payload.get("nature_operation_erp_code"):
            warnings.append("natureza de operação sem código ERP")
        for index, item in enumerate(payload.get("items", []), 1):
            if not item.get("erp_product_code") and not item.get("code"):
                blocking.append(f"item {index} sem código de produto")
            if float(item.get("quantity", 0) or 0) <= 0:
                blocking.append(f"item {index} sem quantidade válida")
        for material in payload.get("raw_materials", []):
            if not material.get("erp_material_code"):
                blocking.append(f"matéria-prima {material.get('description', '')} sem código ERP")
            if not material.get("warehouse_erp_code"):
                blocking.append(f"matéria-prima {material.get('description', '')} sem depósito ERP")
        financial = payload.get("financial") or {}
        installments = financial.get("installments", []) if isinstance(financial, dict) else []
        if event.action == "faturar" and not installments:
            blocking.append("faturamento sem parcelas financeiras")
        for installment in installments:
            if installment.get("method") == "boleto":
                if not installment.get("bank_account_erp_code"):
                    blocking.append("boleto sem conta bancária ERP")
                if not installment.get("billing_portfolio_erp_code"):
                    blocking.append("boleto sem carteira de cobrança ERP")
        return {"event_id": str(event.id), "valid": not blocking,
                "blocking": sorted(set(blocking)), "warnings": sorted(set(warnings)),
                "checked_at": datetime.now(timezone.utc).isoformat()}

    def readiness(self) -> dict[str, object]:
        checks = {
            "provider": self._settings.provider != "generico",
            "base_url": bool(self._settings.base_url),
            "credentials": bool(self._settings.api_token),
            "warehouse": bool(self._settings.default_warehouse_erp_code),
            "bank_account": bool(self._settings.default_bank_account_erp_code),
            "billing_portfolio": bool(self._settings.default_billing_portfolio_erp_code),
            "cost_center": bool(self._settings.default_cost_center_erp_code),
            "financial_category": bool(self._settings.default_financial_category_erp_code),
            "company_codes": bool(self._settings.danfer_company_erp_code and self._settings.df_company_erp_code),
            "invoice_series": bool(self._settings.invoice_series),
        }
        return {"ready": all(checks.values()), "enabled": self._settings.enabled,
                "checks": checks, "pending": [key for key, value in checks.items() if not value]}

    @staticmethod
    def _customer_payload(client: Client) -> dict[str, object]:
        return {
            "erp_code": client.erp_code, "legal_name": client.name,
            "document": client.document, "state_registration": client.state_registration,
            "municipal_registration": client.municipal_registration,
            "suframa_registration": client.suframa_registration,
            "tax_regime": client.tax_regime, "contact": client.contact,
            "email": client.email, "tax_email": client.tax_email or client.email,
            "phone": client.phone,
            "address": {"street": client.address, "number": client.address_number,
                        "complement": client.address_complement, "district": client.district,
                        "city": client.city, "state": client.state,
                        "postal_code": client.postal_code, "country_code": client.country_code},
            "payment_condition_erp_code": client.payment_condition_erp_code,
            "credit_limit": client.credit_limit,
        }

    def _raw_materials(self, quote: Quote, quantities: dict[UUID, float] | None = None) -> list[dict[str, object]]:
        if quote.commercial_operation in {CommercialOperation.INDUSTRIALIZATION,
                                          CommercialOperation.THIRD_PARTY_MATERIAL}:
            return []
        materials = self._catalog.list_materials(active=True) if self._catalog else []
        grouped: dict[tuple[str, str], dict[str, object]] = {}
        for item in quote.items:
            quantity = quantities.get(item.id, item.quantity) if quantities is not None else item.quantity
            if quantity <= 0 or not item.material:
                continue
            match = next((material for material in materials
                          if material.description.casefold() == item.material.casefold()
                          and (item.thickness_mm is None or abs(material.thickness_mm - item.thickness_mm) < .001)), None)
            consumed_per_unit = (item.material_cost / item.material_price_kg
                                 if item.material_price_kg and item.material_price_kg > 0 else item.net_weight_kg)
            erp_code = match.erp_code if match else ""
            warehouse = (match.warehouse_erp_code if match else "") or self._settings.default_warehouse_erp_code
            key = (erp_code or item.material.casefold(), warehouse)
            row = grouped.setdefault(key, {
                "erp_material_code": erp_code, "description": item.material,
                "specification": match.specification if match else "",
                "thickness_mm": item.thickness_mm,
                "warehouse_erp_code": warehouse,
                "stock_unit": match.stock_unit if match else "kg",
                "required_quantity": 0.0, "movement": "saida_producao",
                "source": "custo_com_aproveitamento", "mapping_warning": not bool(match),
            })
            row["required_quantity"] = round(float(row["required_quantity"]) + consumed_per_unit * quantity, 4)
        return list(grouped.values())

    @staticmethod
    def _parse_due_days(payment_terms: str) -> list[int]:
        numbers = [int(value) for value in __import__("re").findall(r"\d+", payment_terms or "")]
        return sorted(set(numbers)) or [28]

    def financial_data(self, total: float, payment_terms: str,
                       supplied: InvoiceFinancialData | None = None) -> InvoiceFinancialData:
        if supplied and supplied.installments:
            difference = abs(sum(item.amount for item in supplied.installments) - total)
            if difference > .02:
                raise IntegrationValidationError("a soma das parcelas deve ser igual ao total faturado")
            return supplied
        days = self._parse_due_days(payment_terms)
        base = round(total / len(days), 2)
        amounts = [base] * len(days)
        amounts[-1] = round(total - sum(amounts[:-1]), 2)
        today = date.today()
        return InvoiceFinancialData(
            payment_condition_erp_code=supplied.payment_condition_erp_code if supplied else "",
            cost_center_erp_code=(supplied.cost_center_erp_code if supplied else "") or self._settings.default_cost_center_erp_code,
            financial_category_erp_code=(supplied.financial_category_erp_code if supplied else "") or self._settings.default_financial_category_erp_code,
            generate_bank_slips=supplied.generate_bank_slips if supplied else True,
            notes=supplied.notes if supplied else "",
            installments=[PaymentInstallment(
                sequence=index, due_date=today + timedelta(days=due), amount=amount,
                method=PaymentMethod.BANK_SLIP,
                bank_account_erp_code=self._settings.default_bank_account_erp_code,
                billing_portfolio_erp_code=self._settings.default_billing_portfolio_erp_code,
            ) for index, (due, amount) in enumerate(zip(days, amounts), 1)],
        )

    def queue_quote(self, quote: Quote, client: Client) -> ErpEvent:
        existing = next((event for event in self._erp_events.values()
                         if event.entity == "orcamento" and event.entity_id == quote.id and event.action == "criar_pedido"), None)
        if existing:
            return existing.model_copy(deep=True)
        event = ErpEvent(
            entity="orcamento", entity_id=quote.id, action="criar_pedido",
            company_unit=quote.billing_unit,
            payload={
                "erp_company_code": (self._settings.danfer_company_erp_code
                                     if quote.billing_unit.value == "danfer" else self._settings.df_company_erp_code),
                "quote_number": quote.number, "revision": quote.revision,
                "customer": client.name, "customer_document": client.document,
                "erp_customer_code": client.erp_code,
                "customer_data": self._customer_payload(client),
                "customer_purchase_order": quote.customer_purchase_order,
                "seller_erp_code": quote.seller_erp_code,
                "nature_operation": quote.nature_operation,
                "nature_operation_erp_code": quote.nature_operation_erp_code,
                "payment_terms": quote.payment_terms or client.payment_terms,
                "payment_condition_erp_code": client.payment_condition_erp_code,
                "freight_type": quote.freight_type.value,
                "freight_payer": quote.freight_payer.value,
                "carrier_erp_code": quote.carrier_erp_code,
                "expected_delivery": quote.expected_delivery.isoformat() if quote.expected_delivery else None,
                "subtotal": quote.subtotal, "taxes": quote.taxes,
                "freight_value": quote.freight_value, "discount_value": quote.discount_value,
                "total": quote.total,
                "taxes_detail": {"ipi_percent": quote.ipi_percent or 0,
                                 "cbs_percent": quote.cbs_percent or 0,
                                 "ibs_percent": quote.ibs_percent or 0,
                                 "tax_scenario": quote.tax_scenario, "cfop": quote.cfop,
                                 "cst_icms": quote.cst_icms, "cst_ipi": quote.cst_ipi,
                                 "cst_pis": quote.cst_pis, "cst_cofins": quote.cst_cofins},
                "items": [{
                    "code": item.code, "erp_product_code": item.erp_product_code or item.code,
                    "description": item.description,
                    "quantity": item.quantity, "unit": item.unit,
                    "unit_price": item.unit_price, "total_price": item.total_price,
                    "material": item.material, "thickness_mm": item.thickness_mm,
                    "gross_weight_kg": round(item.material_cost / item.material_price_kg, 4)
                    if item.material_price_kg else item.net_weight_kg,
                    "net_weight_kg": item.net_weight_kg, "ncm": item.ncm, "cest": item.cest,
                } for item in quote.items],
                "raw_materials": self._raw_materials(quote),
            },
        )
        self._erp_events[event.id] = event
        self._save()
        return event.model_copy(deep=True)

    def queue_invoice(self, quote: Quote, client: Client, quantities: dict[UUID, float],
                      supplied_financial: InvoiceFinancialData | None = None) -> ErpEvent:
        selected = [(item, quantities[item.id]) for item in quote.items if item.id in quantities]
        subtotal = round(sum(item.unit_price * quantity for item, quantity in selected), 2)
        total = round(quote.total * subtotal / quote.subtotal, 2) if quote.subtotal else subtotal
        financial = self.financial_data(total, quote.payment_terms or client.payment_terms,
                                        supplied_financial)
        if not financial.payment_condition_erp_code:
            financial.payment_condition_erp_code = client.payment_condition_erp_code
        event = ErpEvent(
            entity="orcamento", entity_id=quote.id, action="faturar",
            company_unit=quote.billing_unit,
            payload={
                "erp_company_code": (self._settings.danfer_company_erp_code
                                     if quote.billing_unit.value == "danfer" else self._settings.df_company_erp_code),
                "invoice_series": self._settings.invoice_series,
                "invoice_model": self._settings.invoice_model,
                "quote_number": quote.number, "revision": quote.revision,
                "customer": client.name, "erp_customer_code": client.erp_code,
                "customer_document": client.document,
                "customer_data": self._customer_payload(client),
                "customer_purchase_order": quote.customer_purchase_order,
                "seller_erp_code": quote.seller_erp_code,
                "nature_operation": quote.nature_operation,
                "nature_operation_erp_code": quote.nature_operation_erp_code,
                "freight_type": quote.freight_type.value, "freight_payer": quote.freight_payer.value,
                "carrier_erp_code": quote.carrier_erp_code,
                "subtotal": subtotal, "total": total,
                "invoice_sequence": quote.invoice_count + 1,
                "partial": any(quantity < item.quantity for item, quantity in selected) or len(selected) < len(quote.items),
                "items": [{"item_id": str(item.id), "code": item.code,
                           "erp_product_code": item.erp_product_code or item.code,
                           "ncm": item.ncm, "cest": item.cest, "quantity": quantity,
                           "unit_price": item.unit_price, "total_price": round(item.unit_price * quantity, 2)}
                          for item, quantity in selected],
                "financial": financial.model_dump(mode="json"),
                "raw_materials": self._raw_materials(quote, quantities),
                "stock_movement": {"type": "saida_producao", "automatic": True,
                                   "reference": f"{quote.number}/{quote.invoice_count + 1}"},
                "taxes_detail": {"ipi_percent": quote.ipi_percent or 0,
                                 "cbs_percent": quote.cbs_percent or 0,
                                 "ibs_percent": quote.ibs_percent or 0,
                                 "tax_scenario": quote.tax_scenario, "cfop": quote.cfop,
                                 "cst_icms": quote.cst_icms, "cst_ipi": quote.cst_ipi,
                                 "cst_pis": quote.cst_pis, "cst_cofins": quote.cst_cofins},
            },
        )
        self._erp_events[event.id] = event
        self._save()
        return event.model_copy(deep=True)

    def acknowledge_event(self, event_id: UUID, succeeded: bool, error: str = "") -> ErpEvent:
        current = self._erp_events.get(event_id)
        if current is None:
            raise LookupError(event_id)
        updated = current.model_copy(
            update={
                "status": ErpEventStatus.SENT if succeeded else ErpEventStatus.FAILED,
                "attempts": current.attempts + 1,
                "last_error": "" if succeeded else error,
                "updated_at": datetime.now(timezone.utc),
            }
        )
        self._erp_events[event_id] = updated
        self._save()
        return updated.model_copy(deep=True)
