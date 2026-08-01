from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

from danfer_os.models.crm import (
    CrmActivity, CrmActivityCreate, CrmAlert, CrmAlertSettings,
    Opportunity, OpportunityCreate, OpportunityUpdate,
)


class CrmNotFoundError(LookupError):
    pass


class CrmService:
    def __init__(self, storage_path: Path | None = None) -> None:
        self._storage_path = storage_path
        self._items: dict[UUID, Opportunity] = {}
        self._sequence = 0
        self._settings = CrmAlertSettings()
        self._load()

    def _load(self) -> None:
        if not self._storage_path or not self._storage_path.exists():
            return
        payload = json.loads(self._storage_path.read_text(encoding="utf-8"))
        values = [Opportunity.model_validate(item) for item in payload.get("opportunities", [])]
        self._items = {item.id: item for item in values}
        self._sequence = int(payload.get("sequence", 0))
        self._settings = CrmAlertSettings.model_validate(payload.get("alert_settings", {}))

    def _save(self) -> None:
        if not self._storage_path:
            return
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._storage_path.write_text(json.dumps({
            "version": 2, "sequence": self._sequence,
            "alert_settings": self._settings.model_dump(mode="json"),
            "opportunities": [item.model_dump(mode="json") for item in self._items.values()],
        }, ensure_ascii=False, indent=2), encoding="utf-8")

    def create(self, data: OpportunityCreate) -> Opportunity:
        self._sequence += 1
        item = Opportunity(**data.model_dump(), number=f"NEG-{datetime.now():%Y}-{self._sequence:05d}")
        self._items[item.id] = item
        self._save()
        return item.model_copy(deep=True)

    def list(self, query: str = "", stage: str = "") -> list[Opportunity]:
        values = self._items.values()
        if query:
            term = query.casefold()
            values = (item for item in values if term in f"{item.number} {item.client_name} {item.owner} {item.notes}".casefold())
        if stage:
            values = (item for item in values if item.stage == stage)
        return [item.model_copy(deep=True) for item in sorted(values, key=lambda value: value.updated_at, reverse=True)]

    def update(self, item_id: UUID, data: OpportunityUpdate) -> Opportunity:
        current = self._items.get(item_id)
        if not current:
            raise CrmNotFoundError(item_id)
        updated = current.model_copy(update={**data.model_dump(exclude_unset=True), "updated_at": datetime.now(timezone.utc)})
        self._items[item_id] = updated
        self._save()
        return updated.model_copy(deep=True)

    def add_activity(self, item_id: UUID, data: CrmActivityCreate) -> Opportunity:
        current = self._items.get(item_id)
        if not current:
            raise CrmNotFoundError(item_id)
        activity = CrmActivity(**data.model_dump())
        changes = {"activities": [activity, *current.activities], "updated_at": datetime.now(timezone.utc)}
        if data.next_contact:
            changes["next_contact"] = data.next_contact
        updated = current.model_copy(update=changes)
        self._items[item_id] = updated
        self._save()
        return updated.model_copy(deep=True)

    def alert_settings(self) -> CrmAlertSettings:
        return self._settings.model_copy(deep=True)

    def set_alert_settings(self, data: CrmAlertSettings) -> CrmAlertSettings:
        self._settings = data.model_copy(deep=True)
        self._save()
        return self.alert_settings()

    def alerts(self, today: date | None = None) -> list[CrmAlert]:
        if not self._settings.enabled:
            return []
        today = today or date.today()
        alerts: list[CrmAlert] = []
        closed_stages = {"aprovada", "aprovado", "perdida", "perdido", "cancelada", "cancelado"}
        for item in self._items.values():
            if item.stage.casefold() in closed_stages:
                continue
            if item.next_contact:
                delta = (today - item.next_contact).days
                if delta > 0:
                    alerts.append(CrmAlert(
                        opportunity_id=item.id, opportunity_number=item.number,
                        client_name=item.client_name, quote_id=item.quote_id, owner=item.owner,
                        kind="contato_vencido", severity="alta",
                        message=f"Contato vencido há {delta} dia(s).",
                        due_date=item.next_contact, days_overdue=delta,
                    ))
                elif item.next_contact <= today + timedelta(days=self._settings.upcoming_contact_days):
                    alerts.append(CrmAlert(
                        opportunity_id=item.id, opportunity_number=item.number,
                        client_name=item.client_name, quote_id=item.quote_id, owner=item.owner,
                        kind="contato_proximo", severity="media",
                        message=f"Próximo contato previsto para {item.next_contact:%d/%m/%Y}.",
                        due_date=item.next_contact,
                    ))
            stale_days = (today - item.updated_at.date()).days
            if item.quote_id and stale_days >= self._settings.stale_quote_days:
                alerts.append(CrmAlert(
                    opportunity_id=item.id, opportunity_number=item.number,
                    client_name=item.client_name, quote_id=item.quote_id, owner=item.owner,
                    kind="orcamento_sem_interacao", severity="alta" if stale_days >= self._settings.stale_quote_days * 2 else "media",
                    message=f"Orçamento sem interação registrada há {stale_days} dia(s).",
                    days_overdue=stale_days - self._settings.stale_quote_days,
                ))
        rank = {"alta": 0, "media": 1, "baixa": 2}
        return sorted(alerts, key=lambda alert: (rank.get(alert.severity, 9), -alert.days_overdue, alert.client_name.casefold()))
