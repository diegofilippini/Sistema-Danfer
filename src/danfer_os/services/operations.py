from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from danfer_os.models.operations import (
    AuditEvent,
    MaintenanceOrder,
    MaintenanceOrderCreate,
    MaintenanceStatus,
    Notification,
    NotificationCreate,
    QualityOccurrence,
    QualityOccurrenceCreate,
)


class OperationsNotFoundError(LookupError):
    pass


class OperationsService:
    def __init__(self, storage_path: Path | None = None) -> None:
        self._storage_path = storage_path
        self._quality: dict[UUID, QualityOccurrence] = {}
        self._maintenance: dict[UUID, MaintenanceOrder] = {}
        self._audits: list[AuditEvent] = []
        self._notifications: dict[UUID, Notification] = {}
        self._maintenance_sequence = 0
        self._load()

    def _load(self) -> None:
        if self._storage_path is None or not self._storage_path.exists():
            return
        data = json.loads(self._storage_path.read_text(encoding="utf-8"))
        self._quality = {
            item.id: item for item in map(QualityOccurrence.model_validate, data.get("quality", []))
        }
        self._maintenance = {
            item.id: item for item in map(MaintenanceOrder.model_validate, data.get("maintenance", []))
        }
        self._audits = [AuditEvent.model_validate(item) for item in data.get("audits", [])]
        self._notifications = {
            item.id: item for item in map(Notification.model_validate, data.get("notifications", []))
        }
        self._maintenance_sequence = int(data.get("maintenance_sequence", 0))

    def _save(self) -> None:
        if self._storage_path is None:
            return
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "quality": [item.model_dump(mode="json") for item in self._quality.values()],
            "maintenance": [item.model_dump(mode="json") for item in self._maintenance.values()],
            "audits": [item.model_dump(mode="json") for item in self._audits[-1000:]],
            "notifications": [item.model_dump(mode="json") for item in self._notifications.values()],
            "maintenance_sequence": self._maintenance_sequence,
        }
        self._storage_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def audit(self, module: str, action: str, entity_id: str = "", details: str = "") -> None:
        self._audits.append(
            AuditEvent(module=module, action=action, entity_id=entity_id, details=details)
        )
        self._save()

    def audits(self, module: str | None = None) -> list[AuditEvent]:
        events = self._audits
        if module:
            events = [item for item in events if item.module == module]
        return [item.model_copy(deep=True) for item in reversed(events)]

    def create_quality(self, data: QualityOccurrenceCreate) -> QualityOccurrence:
        item = QualityOccurrence(**data.model_dump())
        self._quality[item.id] = item
        self.audit("qualidade", "criar", str(item.id), item.description)
        return item.model_copy(deep=True)

    def list_quality(self, resolved: bool | None = None) -> list[QualityOccurrence]:
        values = self._quality.values()
        if resolved is not None:
            values = (item for item in values if item.resolved == resolved)
        return [item.model_copy(deep=True) for item in values]

    def resolve_quality(self, occurrence_id: UUID) -> QualityOccurrence:
        current = self._quality.get(occurrence_id)
        if current is None:
            raise OperationsNotFoundError(occurrence_id)
        updated = current.model_copy(
            update={"resolved": True, "resolved_at": datetime.now(timezone.utc)}
        )
        self._quality[occurrence_id] = updated
        self.audit("qualidade", "resolver", str(occurrence_id))
        return updated.model_copy(deep=True)

    def create_maintenance(self, data: MaintenanceOrderCreate) -> MaintenanceOrder:
        self._maintenance_sequence += 1
        item = MaintenanceOrder(
            **data.model_dump(),
            number=f"MAN-{datetime.now():%Y}-{self._maintenance_sequence:05d}",
        )
        self._maintenance[item.id] = item
        self.audit("manutencao", "criar", str(item.id), item.equipment)
        return item.model_copy(deep=True)

    def list_maintenance(self) -> list[MaintenanceOrder]:
        return [item.model_copy(deep=True) for item in self._maintenance.values()]

    def change_maintenance(
        self, order_id: UUID, status: MaintenanceStatus, actual_cost: float | None
    ) -> MaintenanceOrder:
        current = self._maintenance.get(order_id)
        if current is None:
            raise OperationsNotFoundError(order_id)
        changes: dict[str, object] = {
            "status": status,
            "updated_at": datetime.now(timezone.utc),
        }
        if actual_cost is not None:
            changes["actual_cost"] = actual_cost
        updated = current.model_copy(update=changes)
        self._maintenance[order_id] = updated
        self.audit("manutencao", "status", str(order_id), status.value)
        return updated.model_copy(deep=True)

    def create_notification(self, data: NotificationCreate) -> Notification:
        item = Notification(**data.model_dump())
        self._notifications[item.id] = item
        self.audit("notificacoes", "criar", str(item.id), item.title)
        return item.model_copy(deep=True)

    def notifications(self, username: str = "", role: str = "") -> list[Notification]:
        values = reversed(self._notifications.values())
        if username or role:
            values = (item for item in values if (
                (not item.recipient_username and not item.recipient_role)
                or item.recipient_username.casefold() == username.casefold()
                or item.recipient_role.casefold() == role.casefold()
            ))
        return [item.model_copy(deep=True) for item in values]

    def read_notification(self, notification_id: UUID) -> Notification:
        current = self._notifications.get(notification_id)
        if current is None:
            raise OperationsNotFoundError(notification_id)
        updated = current.model_copy(update={"read": True})
        self._notifications[notification_id] = updated
        self._save()
        return updated.model_copy(deep=True)
