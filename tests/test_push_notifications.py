import sys
from types import SimpleNamespace

from fastapi.testclient import TestClient

from danfer_os.main import create_app
from danfer_os.models.push import PushSubscriptionCreate
from danfer_os.services.push import PushService


SUBSCRIPTION = {
    "username": "comercial1",
    "role": "comercial",
    "endpoint": "https://push.example.test/subscriptions/device-001",
    "keys": {"p256dh": "public-device-key-123456", "auth": "auth-key-123"},
}


def test_push_subscription_is_persistent_and_reports_configuration(tmp_path) -> None:
    client = TestClient(create_app(data_dir=tmp_path))
    status = client.get("/api/v1/push/status")
    assert status.status_code == 200
    assert status.json()["available"] is False

    created = client.post("/api/v1/push/subscriptions", json=SUBSCRIPTION)
    assert created.status_code == 201
    assert created.json()["username"] == "comercial1"
    restarted = TestClient(create_app(data_dir=tmp_path))
    assert restarted.get("/api/v1/push/status").json()["subscriptions"] == 1

    removed = restarted.delete(
        "/api/v1/push/subscriptions", params={"endpoint": SUBSCRIPTION["endpoint"]}
    )
    assert removed.json() == {"removed": True}


def test_push_dispatch_targets_username_or_role(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DANFER_VAPID_PUBLIC_KEY", "public-vapid-key")
    monkeypatch.setenv("DANFER_VAPID_PRIVATE_KEY", "private-vapid-key")
    calls = []

    def fake_webpush(**kwargs):
        calls.append(kwargs)

    monkeypatch.setitem(sys.modules, "pywebpush", SimpleNamespace(webpush=fake_webpush))
    service = PushService(tmp_path / "push.json")
    service.subscribe(PushSubscriptionCreate.model_validate(SUBSCRIPTION))
    assert service.send("Andamento", "Pedido atualizado", recipient_role="comercial") == 1
    assert len(calls) == 1
    assert "Pedido atualizado" in calls[0]["data"]
    assert service.send("PCP", "Outro aviso", recipient_role="pcp") == 0
