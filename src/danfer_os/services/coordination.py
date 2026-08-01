from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
from urllib.parse import quote
from uuid import UUID

from danfer_os.models.coordination import (
    BillingProfile, CompanyUnit, MessageChannel, MessageStatus, OutboundMessage,
    OutboundMessageCreate, RequestStatusChange, ServiceRequest, ServiceRequestCreate,
)


class CoordinationNotFoundError(LookupError):
    pass


class CoordinationService:
    def __init__(self, storage_path: Path | None = None) -> None:
        self._storage_path = storage_path
        self._profiles = {
            CompanyUnit.DANFER: BillingProfile(unit="danfer", legal_name="Danfer Industrial"),
            CompanyUnit.DF: BillingProfile(unit="df", legal_name="DF"),
        }
        self._requests: dict[UUID, ServiceRequest] = {}
        self._messages: dict[UUID, OutboundMessage] = {}
        self._request_sequence = 0
        self._load()

    def _load(self) -> None:
        if self._storage_path is None or not self._storage_path.exists():
            return
        payload = json.loads(self._storage_path.read_text(encoding="utf-8"))
        for raw in payload.get("profiles", []):
            profile = BillingProfile.model_validate(raw)
            self._profiles[profile.unit] = profile
        requests = [ServiceRequest.model_validate(item) for item in payload.get("requests", [])]
        self._requests = {item.id: item for item in requests}
        messages = [OutboundMessage.model_validate(item) for item in payload.get("messages", [])]
        self._messages = {item.id: item for item in messages}
        self._request_sequence = int(payload.get("request_sequence", 0))

    def _save(self) -> None:
        if self._storage_path is None:
            return
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._storage_path.write_text(json.dumps({
            "version": 1, "request_sequence": self._request_sequence,
            "profiles": [item.model_dump(mode="json") for item in self._profiles.values()],
            "requests": [item.model_dump(mode="json") for item in self._requests.values()],
            "messages": [item.model_dump(mode="json") for item in self._messages.values()],
        }, ensure_ascii=False, indent=2), encoding="utf-8")

    def profiles(self) -> list[BillingProfile]:
        return [item.model_copy(deep=True) for item in self._profiles.values()]

    def set_profile(self, profile: BillingProfile) -> BillingProfile:
        self._profiles[profile.unit] = profile
        self._save()
        return profile.model_copy(deep=True)

    def create_request(self, data: ServiceRequestCreate) -> ServiceRequest:
        self._request_sequence += 1
        item = ServiceRequest(**data.model_dump(), number=f"SOL-{datetime.now():%Y}-{self._request_sequence:05d}")
        self._requests[item.id] = item
        self._save()
        return item.model_copy(deep=True)

    def requests(self, status: str | None = None) -> list[ServiceRequest]:
        items = self._requests.values()
        if status:
            items = (item for item in items if item.status.value == status)
        return [item.model_copy(deep=True) for item in sorted(items, key=lambda item: item.created_at, reverse=True)]

    def change_request(self, request_id: UUID, data: RequestStatusChange) -> ServiceRequest:
        current = self._requests.get(request_id)
        if current is None:
            raise CoordinationNotFoundError(request_id)
        comments = [*current.comments, *([data.comment] if data.comment else [])]
        updated = current.model_copy(update={
            "status": data.status,
            "assigned_to": data.assigned_to if data.assigned_to is not None else current.assigned_to,
            "comments": comments, "updated_at": datetime.now(timezone.utc),
        })
        self._requests[request_id] = updated
        self._save()
        return updated.model_copy(deep=True)

    def create_message(self, data: OutboundMessageCreate) -> OutboundMessage:
        action_url = ""
        if data.channel == MessageChannel.WHATSAPP:
            phone = re.sub(r"\D", "", data.recipient)
            if not phone:
                raise ValueError("telefone do WhatsApp inválido")
            action_url = f"https://wa.me/{phone}?text={quote(data.body)}"
        elif data.channel == MessageChannel.EMAIL:
            action_url = f"mailto:{data.recipient}?subject={quote(data.subject)}&body={quote(data.body)}"
        item = OutboundMessage(**data.model_dump(), action_url=action_url)
        self._messages[item.id] = item
        self._save()
        return item.model_copy(deep=True)

    def messages(self) -> list[OutboundMessage]:
        return [item.model_copy(deep=True) for item in sorted(self._messages.values(), key=lambda item: item.created_at, reverse=True)]

    def mark_message(self, message_id: UUID, succeeded: bool) -> OutboundMessage:
        current = self._messages.get(message_id)
        if current is None:
            raise CoordinationNotFoundError(message_id)
        updated = current.model_copy(update={
            "status": MessageStatus.SENT if succeeded else MessageStatus.FAILED,
            "sent_at": datetime.now(timezone.utc) if succeeded else None,
        })
        self._messages[message_id] = updated
        self._save()
        return updated.model_copy(deep=True)
