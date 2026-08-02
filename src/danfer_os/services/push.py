from __future__ import annotations

import json
import os
from pathlib import Path

from danfer_os.models.push import PushStatus, PushSubscription, PushSubscriptionCreate


class PushService:
    def __init__(self, storage_path: Path | None = None) -> None:
        self._storage_path = storage_path
        self._items: dict[str, PushSubscription] = {}
        self._public_key = os.getenv("DANFER_VAPID_PUBLIC_KEY", "")
        self._private_key = os.getenv("DANFER_VAPID_PRIVATE_KEY", "")
        self._subject = os.getenv("DANFER_VAPID_SUBJECT", "mailto:ti@danfer.com.br")
        self._load()

    def _load(self) -> None:
        if not self._storage_path or not self._storage_path.exists():
            return
        payload = json.loads(self._storage_path.read_text(encoding="utf-8"))
        values = [PushSubscription.model_validate(item) for item in payload.get("subscriptions", [])]
        self._items = {item.endpoint: item for item in values}

    def _save(self) -> None:
        if not self._storage_path:
            return
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._storage_path.write_text(json.dumps({
            "version": 1,
            "subscriptions": [item.model_dump(mode="json") for item in self._items.values()],
        }, ensure_ascii=False, indent=2), encoding="utf-8")

    def status(self) -> PushStatus:
        configured = bool(self._public_key and self._private_key)
        return PushStatus(
            available=configured,
            public_key=self._public_key,
            subscriptions=len(self._items),
            detail="Push configurado." if configured else "Informe as chaves VAPID no servidor.",
        )

    def subscribe(self, data: PushSubscriptionCreate) -> PushSubscription:
        current = self._items.get(data.endpoint)
        item = PushSubscription(**data.model_dump(), **({"id": current.id, "created_at": current.created_at} if current else {}))
        self._items[item.endpoint] = item
        self._save()
        return item.model_copy(deep=True)

    def unsubscribe(self, endpoint: str) -> bool:
        removed = self._items.pop(endpoint, None) is not None
        if removed:
            self._save()
        return removed

    def send(self, title: str, message: str, recipient_username: str = "", recipient_role: str = "") -> int:
        if not self.status().available:
            return 0
        try:
            from pywebpush import webpush
        except ImportError:
            return 0
        targets = [item for item in self._items.values() if (
            (not recipient_username and not recipient_role)
            or item.username.casefold() == recipient_username.casefold()
            or item.role.casefold() == recipient_role.casefold()
        )]
        sent = 0
        for item in targets:
            try:
                webpush(
                    subscription_info={"endpoint": item.endpoint, "keys": item.keys.model_dump()},
                    data=json.dumps({"title": title, "body": message, "url": "/"}, ensure_ascii=False),
                    vapid_private_key=self._private_key,
                    vapid_claims={"sub": self._subject},
                )
                sent += 1
            except Exception:
                # A notificação interna permanece registrada mesmo se o dispositivo
                # estiver temporariamente indisponível.
                continue
        return sent
