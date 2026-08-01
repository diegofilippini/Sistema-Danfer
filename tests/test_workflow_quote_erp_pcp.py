from datetime import date, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from danfer_os.main import create_app
from danfer_os.services.technical_library import TechnicalLibrary


def test_approved_quote_queues_erp_and_carries_estimated_cost_to_pcp(tmp_path: Path) -> None:
    client = TestClient(create_app(TechnicalLibrary(), data_dir=tmp_path))
    customer = client.post("/api/v1/commercial/clients", json={
        "name": "Cliente Integrado", "document": "123", "payment_terms": "28 dias",
    }).json()
    product = client.post("/api/v1/technical-library", json={
        "danfer_code": "PROD-ERP", "title": "Produto integrado", "category": "desenho",
        "file_url": "https://docs.danfer.com/prod-erp.dxf",
    }).json()
    component = client.post("/api/v1/technical-library", json={
        "danfer_code": "COMP-ERP", "title": "Componente integrado", "category": "desenho",
        "file_url": "https://docs.danfer.com/comp-erp.dxf",
    }).json()
    client.post("/api/v1/boms", json={
        "product_id": product["id"], "components": [{"part_id": component["id"], "quantity": 1}],
    })
    quote = client.post("/api/v1/commercial/quotes", json={
        "type": "venda", "billing_unit": "df", "client_id": customer["id"],
        "valid_until": str(date.today() + timedelta(days=10)),
        "expected_delivery": str(date.today() + timedelta(days=15)), "margin_percent": 30,
        "items": [{
            "code": "PROD-ERP", "description": "Produto integrado", "quantity": 3,
            "material": "Aço carbono", "net_weight_kg": 5, "material_price_kg": 8,
            "processes": [{"name": "Corte Laser", "minutes": 10, "hourly_rate": 180}],
        }],
    }).json()
    for status in ("enviado", "aprovado"):
        assert client.post(f"/api/v1/commercial/quotes/{quote['id']}/status", json={"status": status}).status_code == 200

    erp = client.post(f"/api/v1/workflows/quotes/{quote['id']}/erp-order")
    assert erp.status_code == 200
    assert erp.json()["company_unit"] == "df"
    assert erp.json()["payload"]["items"][0]["code"] == "PROD-ERP"
    assert client.post(f"/api/v1/workflows/quotes/{quote['id']}/erp-order").json()["id"] == erp.json()["id"]

    orders = client.post(f"/api/v1/workflows/quotes/{quote['id']}/production-orders")
    assert orders.status_code == 200
    order = orders.json()[0]
    assert order["estimated_material_cost"] > 0
    assert order["estimated_process_cost"] > 0
    costs = client.get(f"/api/v1/pcp/orders/{order['id']}/costs").json()
    assert costs["estimated_total_cost"] == round(order["estimated_material_cost"] + order["estimated_process_cost"], 2)
    quality = client.post("/api/v1/quality", json={
        "type": "retrabalho", "production_order": order["number"],
        "description": "Correção de dobra", "cost": 40,
    })
    assert quality.status_code == 201
    costs_after_quality = client.get(f"/api/v1/pcp/orders/{order['id']}/costs").json()
    assert costs_after_quality["actual_quality_cost"] == 40
    assert client.post("/api/v1/quality", json={
        "type": "refugo", "production_order": "OP-INEXISTENTE",
        "description": "Registro inválido", "cost": 10,
    }).status_code == 422
