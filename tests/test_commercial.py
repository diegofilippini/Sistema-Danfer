from datetime import date, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from danfer_os.main import create_app
from danfer_os.services.technical_library import TechnicalLibrary


def commercial_client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(TechnicalLibrary(), data_dir=tmp_path))


def create_client(client: TestClient) -> dict:
    response = client.post(
        "/api/v1/commercial/clients",
        json={
            "name": "Metalúrgica Cliente",
            "document": "12.345.678/0001-90",
            "contact": "João",
            "payment_terms": "28/42 dias",
        },
    )
    assert response.status_code == 201
    return response.json()


def quote_payload(client_id: str) -> dict:
    return {
        "type": "venda",
        "client_id": client_id,
        "requester": "João",
        "valid_until": str(date.today() + timedelta(days=10)),
        "margin_percent": 25,
        "ipi_percent": 5,
        "cbs_percent": 0.9,
        "ibs_percent": 0.1,
        "prepared_by": "Diego Filippini",
        "items": [
            {
                "code": "DF-ORC-1",
                "description": "Suporte cortado e dobrado",
                "quantity": 2,
                "material": "Aço carbono",
                "thickness_mm": 3,
                "net_weight_kg": 10,
                "material_price_kg": 5,
                "utilization_percent": 80,
                "margin_percent": 30,
                "processes": [
                    {"name": "Corte laser", "minutes": 10, "hourly_rate": 180},
                    {"name": "Dobra", "minutes": 5, "hourly_rate": 120},
                ],
            }
        ],
    }


def test_quote_calculation_revision_status_and_pdf(tmp_path: Path) -> None:
    client = commercial_client(tmp_path)
    customer = create_client(client)
    created = client.post(
        "/api/v1/commercial/quotes", json=quote_payload(customer["id"])
    )
    assert created.status_code == 201
    quote = created.json()
    assert quote["number"].startswith("ORC-")
    assert quote["items"][0]["material_cost"] == 62.5
    assert quote["items"][0]["process_cost"] == 57.5
    expected_ipi = round(quote["subtotal"] * 0.05, 2)
    assert quote["taxes"] == expected_ipi
    assert quote["total"] > quote["subtotal"]
    assert quote["gross_profit"] > 0

    updated = client.patch(
        f"/api/v1/commercial/quotes/{quote['id']}",
        json={"margin_percent": 30, "change_reason": "Negociação comercial"},
    )
    assert updated.status_code == 200
    assert updated.json()["revision"] == "B"
    assert len(
        client.get(f"/api/v1/commercial/quotes/{quote['id']}/revisions").json()
    ) == 1

    for next_status in ("enviado", "em_negociacao", "aprovado"):
        response = client.post(
            f"/api/v1/commercial/quotes/{quote['id']}/status",
            json={"status": next_status},
        )
        assert response.status_code == 200

    pdf = client.get(f"/api/v1/commercial/quotes/{quote['id']}/proposal.pdf")
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF")
    assert len(pdf.content) > 4000


def test_crm_search_and_duplicate_document(tmp_path: Path) -> None:
    client = commercial_client(tmp_path)
    create_client(client)
    assert len(client.get("/api/v1/commercial/clients", params={"q": "metal"}).json()) == 1
    duplicate = client.post(
        "/api/v1/commercial/clients",
        json={"name": "Outro", "document": "12.345.678/0001-90"},
    )
    assert duplicate.status_code == 409


def test_service_ignores_material_and_supports_weight_pricing_and_small_batch(tmp_path: Path) -> None:
    client = commercial_client(tmp_path)
    customer = create_client(client)
    payload = quote_payload(customer["id"])
    payload["type"] = "servico"
    payload["items"][0]["quantity"] = 2
    payload["items"][0]["processes"] = [
        {
            "name": "Calandra",
            "minutes": 0,
            "hourly_rate": 0,
            "pricing_mode": "peso",
            "weight_rate": 4.5,
        },
        {"name": "Dobra", "minutes": 10, "hourly_rate": 120},
    ]
    response = client.post("/api/v1/commercial/quotes", json=payload)
    assert response.status_code == 201
    item = response.json()["items"][0]
    assert item["material_cost"] == 0
    assert item["process_cost"] == 82.5
    assert response.json()["taxes"] == 0
    assert response.json()["total"] == response.json()["subtotal"]


def test_cost_settings_keep_recovered_defaults(tmp_path: Path) -> None:
    client = commercial_client(tmp_path)
    settings = client.get("/api/v1/commercial/settings/costs").json()
    assert settings["default_margin_percent"] == 30
    assert settings["small_bend_batch_limit"] == 5
    assert settings["default_sheet_width_mm"] == 1200
    assert settings["default_sheet_length_mm"] == 3000
    assert settings["alternative_minimum_gain_percent"] == 8
