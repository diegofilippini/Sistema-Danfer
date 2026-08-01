from datetime import date, datetime, timedelta, timezone
import json
from uuid import uuid4

from fastapi.testclient import TestClient

from danfer_os.main import create_app


def test_crm_activities_and_global_search_are_persistent(tmp_path) -> None:
    client = TestClient(create_app(data_dir=tmp_path))
    customer = client.post("/api/v1/commercial/clients", json={
        "name": "Metalúrgica Busca Ltda.", "document": "11.222.333/0001-44",
    }).json()
    opportunity = client.post("/api/v1/crm/opportunities", json={
        "client_id": customer["id"], "client_name": customer["name"],
        "value": 25000, "owner": "Diego", "next_contact": str(date.today()),
    })
    assert opportunity.status_code == 201
    item_id = opportunity.json()["id"]
    activity = client.post(f"/api/v1/crm/opportunities/{item_id}/activities", json={
        "type": "ligação", "description": "Cliente solicitou revisão",
        "performed_by": "Diego", "next_contact": str(date.today() + timedelta(days=2)),
    })
    assert activity.status_code == 200
    assert activity.json()["activities"][0]["description"] == "Cliente solicitou revisão"

    search = client.get("/api/v1/search", params={"q": "Metalúrgica Busca"})
    assert search.status_code == 200
    assert any(item["type"] == "cliente" for item in search.json())

    restarted = TestClient(create_app(data_dir=tmp_path))
    restored = restarted.get("/api/v1/crm/opportunities").json()
    assert restored[0]["value"] == 25000
    assert len(restored[0]["activities"]) == 1


def test_crm_generates_configurable_contact_and_stale_quote_alerts(tmp_path) -> None:
    client = TestClient(create_app(data_dir=tmp_path))
    opportunity = client.post("/api/v1/crm/opportunities", json={
        "client_name": "Cliente sem retorno", "quote_id": str(uuid4()),
        "owner": "Comercial", "next_contact": str(date.today() - timedelta(days=2)),
    })
    assert opportunity.status_code == 201
    settings = client.put("/api/v1/crm/alert-settings", json={
        "enabled": True, "stale_quote_days": 3, "upcoming_contact_days": 1,
    })
    assert settings.status_code == 200

    storage = tmp_path / "crm.json"
    payload = json.loads(storage.read_text(encoding="utf-8"))
    payload["opportunities"][0]["updated_at"] = (
        datetime.now(timezone.utc) - timedelta(days=5)
    ).isoformat()
    storage.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    restarted = TestClient(create_app(data_dir=tmp_path))
    alerts = restarted.get("/api/v1/crm/alerts").json()
    assert {item["kind"] for item in alerts} == {"contato_vencido", "orcamento_sem_interacao"}
    assert alerts[0]["client_name"] == "Cliente sem retorno"
    assert restarted.get("/api/v1/crm/alert-settings").json()["stale_quote_days"] == 3

    disabled = restarted.put("/api/v1/crm/alert-settings", json={
        "enabled": False, "stale_quote_days": 3, "upcoming_contact_days": 1,
    })
    assert disabled.status_code == 200
    assert restarted.get("/api/v1/crm/alerts").json() == []


def test_crm_does_not_alert_closed_opportunities(tmp_path) -> None:
    client = TestClient(create_app(data_dir=tmp_path))
    created = client.post("/api/v1/crm/opportunities", json={
        "client_name": "Negociação concluída", "stage": "aprovada",
        "next_contact": str(date.today() - timedelta(days=10)),
    })
    assert created.status_code == 201
    assert client.get("/api/v1/crm/alerts").json() == []
