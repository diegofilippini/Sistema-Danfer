from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from uuid import UUID

from danfer_os.models.commercial import (
    Client,
    ClientCreate,
    ClientUpdate,
    CostSettings,
    Quote,
    QuoteCreate,
    QuoteItem,
    QuoteItemCreate,
    QuoteRevision,
    QuoteStatus,
    QuoteUpdate,
)


class CommercialNotFoundError(LookupError):
    pass


class CommercialValidationError(ValueError):
    pass


class CommercialService:
    _status_transitions = {
        QuoteStatus.DRAFT: {QuoteStatus.SENT, QuoteStatus.CANCELLED},
        QuoteStatus.SENT: {QuoteStatus.NEGOTIATION, QuoteStatus.APPROVED, QuoteStatus.LOST},
        QuoteStatus.NEGOTIATION: {QuoteStatus.SENT, QuoteStatus.APPROVED, QuoteStatus.LOST},
        QuoteStatus.APPROVED: set(),
        QuoteStatus.LOST: {QuoteStatus.DRAFT},
        QuoteStatus.CANCELLED: {QuoteStatus.DRAFT},
    }

    def __init__(self, storage_path: Path | None = None) -> None:
        self._storage_path = storage_path
        self._clients: dict[UUID, Client] = {}
        self._quotes: dict[UUID, Quote] = {}
        self._revisions: dict[UUID, list[QuoteRevision]] = {}
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

    def _calculate_item(
        self,
        data: QuoteItemCreate,
        margin_percent: float,
        quote_type: str,
        compatible_item_count: int,
    ) -> QuoteItem:
        utilization = max(data.utilization_percent, 1)
        material_consumption = data.net_weight_kg / (utilization / 100)
        large_part_loss = (
            data.quantity == 1
            and data.utilization_percent > self._settings.large_part_threshold_percent
            and compatible_item_count == 1
            and quote_type == "venda"
        )
        if large_part_loss:
            material_consumption *= 1 + self._settings.large_part_loss_percent / 100
        material_cost = material_consumption * data.material_price_kg
        process_cost = sum(
            process.minutes / 60 * process.hourly_rate + process.external_cost
            for process in data.processes
        )
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
        return QuoteItem(
            **data.model_dump(),
            material_cost=round(material_cost, 2),
            process_cost=round(process_cost, 2),
            indirect_cost=round(indirect, 2),
            total_cost=round(total_cost, 2),
            unit_price=round(unit_price, 2),
            total_price=round(unit_price * data.quantity, 2),
        )

    def _calculate_quote(self, data: QuoteCreate, number: str) -> Quote:
        groups: dict[tuple[str, float | None], int] = {}
        for item in data.items:
            key = (item.material.casefold(), item.thickness_mm)
            groups[key] = groups.get(key, 0) + 1
        items = [
            self._calculate_item(
                item,
                data.margin_percent,
                data.type.value,
                groups[(item.material.casefold(), item.thickness_mm)],
            )
            for item in data.items
        ]
        subtotal = sum(item.total_price for item in items)
        taxable = max(subtotal + data.freight_value - data.discount_value, 0)
        taxes = taxable * (
            data.ipi_percent + data.cbs_percent + data.ibs_percent
        ) / 100
        total_cost = sum(item.total_cost * item.quantity for item in items)
        total = taxable + taxes
        return Quote(
            **data.model_dump(exclude={"items"}),
            items=items,
            number=number,
            subtotal=round(subtotal, 2),
            taxes=round(taxes, 2),
            total=round(total, 2),
            total_cost=round(total_cost, 2),
            gross_profit=round(total - taxes - total_cost, 2),
        )

    def create_quote(self, data: QuoteCreate) -> Quote:
        self.get_client(data.client_id)
        self._quote_sequence += 1
        number = f"ORC-{datetime.now():%Y}-{self._quote_sequence:05d}"
        quote = self._calculate_quote(data, number)
        with self._lock:
            self._quotes[quote.id] = quote
            self._revisions[quote.id] = []
            self._save()
        return quote.model_copy(deep=True)

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
                "total", "total_cost", "gross_profit", "created_at", "updated_at"
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
