from pathlib import Path

from fastapi.testclient import TestClient

from danfer_os.main import create_app
from danfer_os.models.technical_document import DocumentCreate
from danfer_os.services.technical_library import TechnicalLibrary


def test_billing_requests_and_whatsapp_draft_are_persistent(tmp_path: Path) -> None:
    client = TestClient(create_app(TechnicalLibrary(), data_dir=tmp_path))
    profiles = client.get("/api/v1/billing/profiles").json()
    assert {item["unit"] for item in profiles} == {"danfer", "df"}
    updated = client.put("/api/v1/billing/profiles/df", json={
        "unit": "df", "legal_name": "DF Soluções Industriais", "erp_company_code": "02",
    })
    assert updated.status_code == 200

    request = client.post("/api/v1/requests", json={
        "company_unit": "df", "requester": "Comercial", "source_department": "Vendas",
        "target_department": "Engenharia", "category": "desenho", "priority": "alta",
        "subject": "Revisar desenho", "description": "Validar revisão antes da produção",
    })
    assert request.status_code == 201
    assert request.json()["number"].startswith("SOL-")
    moved = client.post(f"/api/v1/requests/{request.json()['id']}/status", json={
        "status": "em_atendimento", "assigned_to": "Engenharia",
        "promised_date": "2026-08-15",
        "comment": {"author": "Diego", "message": "Análise iniciada"},
    })
    assert moved.json()["comments"][0]["message"] == "Análise iniciada"
    assert moved.json()["promised_date"] == "2026-08-15"

    engineering_notifications = client.get(
        "/api/v1/notifications", params={"username": "Engenharia", "role": "engenharia"}
    ).json()
    assert any(item["title"].startswith("Nova solicitação") for item in engineering_notifications)
    assert any(item["title"].startswith("Solicitação atribuída") for item in engineering_notifications)
    requester_notifications = client.get(
        "/api/v1/notifications", params={"username": "Comercial", "role": "comercial"}
    ).json()
    progress = next(item for item in requester_notifications if item["title"].startswith("Andamento"))
    assert "Análise iniciada" in progress["message"]
    marked = client.post(f"/api/v1/notifications/{progress['id']}/read")
    assert marked.status_code == 200
    assert marked.json()["read"] is True

    message = client.post("/api/v1/communications/messages", json={
        "company_unit": "df", "channel": "whatsapp", "recipient": "+55 (11) 99999-1234",
        "body": "Sua solicitação está em atendimento.", "linked_entity": "solicitacao",
        "linked_entity_id": request.json()["id"],
    })
    assert message.status_code == 201
    assert message.json()["action_url"].startswith("https://wa.me/5511999991234")
    assert message.json()["status"] == "pronta"

    restarted = TestClient(create_app(TechnicalLibrary(), data_dir=tmp_path))
    assert restarted.get("/api/v1/requests").json()[0]["assigned_to"] == "Engenharia"
    assert restarted.get("/api/v1/communications/messages").json()[0]["status"] == "pronta"
    restored_notifications = restarted.get(
        "/api/v1/notifications", params={"username": "Comercial", "role": "comercial"}
    ).json()
    assert next(item for item in restored_notifications if item["id"] == progress["id"])["read"] is True


def test_erp_event_carries_company_codes_failure_and_survives_restart(tmp_path: Path) -> None:
    library = TechnicalLibrary(tmp_path / "technical-library.json")
    library.create(DocumentCreate(
        danfer_code="DF-ERP-1", customer_code="CLI-ERP-1", title="Peça ERP",
        category="desenho", file_url="https://docs.danfer.com/erp-1.dxf",
    ))
    client = TestClient(create_app(library, data_dir=tmp_path))
    imported = client.post("/api/v1/integrations/orders", json={
        "company_unit": "df", "source": "erp", "external_id": "PED-ERP-1",
        "customer": "Cliente ERP", "erp_customer_code": "C00042",
        "items": [{"customer_code": "CLI-ERP-1", "erp_product_code": "P0099", "quantity": 2}],
    })
    assert imported.status_code == 201
    event = client.get("/api/v1/integrations/erp/events").json()[0]
    assert event["company_unit"] == "df"
    assert event["payload"]["erp_customer_code"] == "C00042"
    failed = client.post(f"/api/v1/integrations/erp/events/{event['id']}/ack", params={
        "succeeded": "false", "error": "ERP indisponível",
    }).json()
    assert failed["status"] == "falhou"
    assert failed["last_error"] == "ERP indisponível"
    restarted = TestClient(create_app(TechnicalLibrary(tmp_path / "technical-library.json"), data_dir=tmp_path))
    assert restarted.get("/api/v1/integrations/erp/events").json()[0]["attempts"] == 1
