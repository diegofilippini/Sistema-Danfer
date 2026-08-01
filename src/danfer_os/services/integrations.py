from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from uuid import UUID
from xml.etree import ElementTree

from danfer_os.models.integrations import (
    ErpEvent,
    ErpEventStatus,
    ExternalOrderCreate,
    ExternalOrderItem,
    ImportedOrder,
    ImportStatus,
)
from danfer_os.services.technical_library import TechnicalLibrary


class IntegrationValidationError(ValueError):
    pass


class DuplicateExternalOrderError(ValueError):
    pass


class IntegrationService:
    def __init__(self, library: TechnicalLibrary, storage_path: Path | None = None) -> None:
        self._library = library
        self._orders: dict[UUID, ImportedOrder] = {}
        self._external_keys: set[tuple[str, str]] = set()
        self._erp_events: dict[UUID, ErpEvent] = {}
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

    def _save(self) -> None:
        if self._storage_path is None:
            return
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._storage_path.write_text(json.dumps({
            "version": 1,
            "orders": [item.model_dump(mode="json") for item in self._orders.values()],
            "erp_events": [item.model_dump(mode="json") for item in self._erp_events.values()],
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
