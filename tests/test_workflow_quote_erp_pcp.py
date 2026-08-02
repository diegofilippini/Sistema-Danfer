from datetime import date, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from danfer_os.main import create_app
from danfer_os.services.technical_library import TechnicalLibrary


def test_approved_quote_queues_erp_and_carries_estimated_cost_to_pcp(tmp_path: Path) -> None:
    client = TestClient(create_app(TechnicalLibrary(), data_dir=tmp_path))
    customer = client.post("/api/v1/commercial/clients", json={
        "name": "Cliente Integrado", "erp_code": "CLI-0042",
        "document": "123", "payment_terms": "28 dias",
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
    quote_response = client.post("/api/v1/commercial/quotes", json={
        "type": "venda", "billing_unit": "df", "client_id": customer["id"],
        "valid_until": str(date.today() + timedelta(days=10)),
        "expected_delivery": str(date.today() + timedelta(days=15)), "margin_percent": 30,
        "items": [{
            "code": "PROD-ERP", "description": "Produto integrado", "quantity": 3,
            "material": "Aço carbono", "net_weight_kg": 5, "material_price_kg": 8,
            "processes": [{"name": "Corte Laser", "minutes": 10, "hourly_rate": 180}],
        }],
    })
    assert quote_response.status_code == 201, quote_response.text
    quote = quote_response.json()
    for status in ("enviado", "aprovado"):
        assert client.post(f"/api/v1/commercial/quotes/{quote['id']}/status", json={"status": status}).status_code == 200

    erp = client.post(f"/api/v1/workflows/quotes/{quote['id']}/erp-order")
    assert erp.status_code == 200
    assert erp.json()["company_unit"] == "df"
    assert erp.json()["payload"]["erp_customer_code"] == "CLI-0042"
    assert erp.json()["payload"]["items"][0]["code"] == "PROD-ERP"
    assert client.post(f"/api/v1/workflows/quotes/{quote['id']}/erp-order").json()["id"] == erp.json()["id"]

    orders = client.post(f"/api/v1/workflows/quotes/{quote['id']}/production-orders")
    assert orders.status_code == 200
    order = orders.json()[0]
    assert client.post(f"/api/v1/workflows/quotes/{quote['id']}/invoice").status_code == 409
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
    for status in ("liberada", "em_producao", "concluida"):
        assert client.patch(f"/api/v1/pcp/orders/{order['id']}", json={"status": status}).status_code == 200
    ready = client.get("/api/v1/workflows/invoice-ready").json()
    assert ready[0]["ready"] is True
    assert ready[0]["erp_customer_code"] == "CLI-0042"
    partial = client.post(f"/api/v1/workflows/quotes/{quote['id']}/invoice", json={
        "items": [{"item_id": quote["items"][0]["id"], "quantity": 1}],
    })
    assert partial.status_code == 200, partial.text
    assert partial.json()["action"] == "faturar"
    assert partial.json()["payload"]["partial"] is True
    assert partial.json()["payload"]["items"][0]["quantity"] == 1
    partially_invoiced = client.get(f"/api/v1/commercial/quotes/{quote['id']}").json()
    assert partially_invoiced["status"] == "faturamento_parcial"
    assert partially_invoiced["invoiced_quantities"][quote["items"][0]["id"]] == 1
    invoiced = client.post(f"/api/v1/workflows/quotes/{quote['id']}/invoice", json={
        "items": [{"item_id": quote["items"][0]["id"], "quantity": 2}],
    })
    assert invoiced.status_code == 200, invoiced.text
    assert invoiced.json()["payload"]["erp_customer_code"] == "CLI-0042"
    assert client.get(f"/api/v1/commercial/quotes/{quote['id']}").json()["status"] == "faturado"
    assert client.post(f"/api/v1/workflows/quotes/{quote['id']}/invoice").status_code == 409
    invoice_events = [event for event in client.get("/api/v1/integrations/erp/events").json()
                      if event["action"] == "faturar"]
    assert len(invoice_events) == 2
    history = client.get("/api/v1/workflows/invoiced-cost-history", params={
        "item_code": "PROD-ERP",
    })
    assert history.status_code == 200, history.text
    history_data = history.json()
    assert history_data["sample_count"] == 2
    assert history_data["total_invoiced_quantity"] == 3
    assert history_data["standard_margin_percent"] == 30
    assert history_data["suggested_unit_price"] > 0
    assert {row["quantity"] for row in history_data["history"]} == {1, 2}
    batch_ids = []
    for quantity in (2, 4):
        batch_quote = client.post("/api/v1/commercial/quotes", json={
            "type": "venda", "client_id": customer["id"],
            "valid_until": str(date.today() + timedelta(days=10)),
            "items": [{"code": "PROD-ERP", "description": "Produto integrado",
                       "quantity": quantity, "material": "Aço", "manual_unit_price": 100}],
        }).json()
        for status in ("enviado", "aprovado"):
            client.post(f"/api/v1/commercial/quotes/{batch_quote['id']}/status", json={"status": status})
        batch_order = client.post(
            f"/api/v1/workflows/quotes/{batch_quote['id']}/production-orders"
        ).json()[0]
        for status in ("liberada", "em_producao", "concluida"):
            client.patch(f"/api/v1/pcp/orders/{batch_order['id']}", json={"status": status})
        batch_ids.append(batch_quote["id"])
    batch = client.post("/api/v1/workflows/invoice-batch", json={"quote_ids": batch_ids})
    assert batch.status_code == 200, batch.text
    assert len(batch.json()) == 2
    assert all(event["action"] == "faturar" for event in batch.json())
    assert client.post("/api/v1/workflows/invoice-batch", json={"quote_ids": batch_ids}).status_code == 409


def test_quote_items_are_grouped_by_thickness_and_exact_route(tmp_path: Path) -> None:
    client = TestClient(create_app(TechnicalLibrary(), data_dir=tmp_path))
    customer = client.post("/api/v1/commercial/clients", json={"name": "Cliente Agrupamento"}).json()
    component = client.post("/api/v1/technical-library", json={
        "danfer_code": "MAT-GRP", "title": "Matéria prima", "category": "desenho",
        "file_url": "https://docs.danfer.com/mat.dxf",
    }).json()
    for code in ("P-A", "P-B", "P-C", "P-D"):
        product = client.post("/api/v1/technical-library", json={
            "danfer_code": code, "title": code, "category": "desenho",
            "file_url": f"https://docs.danfer.com/{code}.dxf",
        }).json()
        client.post("/api/v1/boms", json={
            "product_id": product["id"], "components": [{"part_id": component["id"], "quantity": 1}],
        })
    laser_bend = [{"name": "Laser", "minutes": 2, "hourly_rate": 180}, {"name": "Dobra", "minutes": 3, "hourly_rate": 120}]
    grouped_quote_response = client.post("/api/v1/commercial/quotes", json={
        "type": "venda", "client_id": customer["id"],
        "valid_until": str(date.today() + timedelta(days=10)),
        "items": [
            {"code": "P-A", "description": "Peça A", "quantity": 1, "material": "Aço", "thickness_mm": 3, "manual_unit_price": 100, "processes": laser_bend},
            {"code": "P-B", "description": "Peça B", "quantity": 2, "material": "Aço", "thickness_mm": 3, "manual_unit_price": 100, "processes": laser_bend},
            {"code": "P-C", "description": "Peça C", "quantity": 1, "material": "Aço", "thickness_mm": 4.75, "manual_unit_price": 100, "processes": laser_bend},
            {"code": "P-D", "description": "Peça D", "quantity": 1, "material": "Aço", "thickness_mm": 3, "manual_unit_price": 100, "processes": [{"name": "Laser", "minutes": 2, "hourly_rate": 180}]},
        ],
    })
    assert grouped_quote_response.status_code == 201, grouped_quote_response.text
    quote = grouped_quote_response.json()
    client.post(f"/api/v1/commercial/quotes/{quote['id']}/status", json={"status": "enviado"})
    client.post(f"/api/v1/commercial/quotes/{quote['id']}/status", json={"status": "aprovado"})
    orders = client.post(f"/api/v1/workflows/quotes/{quote['id']}/production-orders").json()
    assert [item["number"] for item in orders] == [f"1-{date.today():%y}-1", f"1-{date.today():%y}-2", f"1-{date.today():%y}-3"]
    assert len(orders[0]["production_items"]) == 2
    assert orders[0]["thickness_mm"] == 3
    assert orders[0]["routing_steps"] == ["Laser", "Dobra"]
    assert client.post(f"/api/v1/workflows/quotes/{quote['id']}/production-orders").json() == orders
    client.patch(f"/api/v1/pcp/orders/{orders[0]['id']}", json={"status": "liberada"})
    client.patch(f"/api/v1/pcp/orders/{orders[0]['id']}", json={"status": "em_producao"})
    client.patch(f"/api/v1/pcp/orders/{orders[0]['id']}", json={"status": "concluida"})
    progress = client.get("/api/v1/workflows/production-progress").json()[0]
    assert progress == {"client": "Cliente Agrupamento", "total": 3, "completed": 1, "percent": 33}


def test_service_history_uses_only_completed_orders_with_real_time(tmp_path: Path) -> None:
    client = TestClient(create_app(TechnicalLibrary(), data_dir=tmp_path))
    customer = client.post("/api/v1/commercial/clients", json={"name": "Cliente Serviço"}).json()
    component = client.post("/api/v1/technical-library", json={
        "danfer_code": "MP-SRV", "title": "Insumo", "category": "desenho",
        "file_url": "https://docs.danfer.com/mp-srv.dxf",
    }).json()
    product = client.post("/api/v1/technical-library", json={
        "danfer_code": "SRV-1", "title": "Serviço dobrado", "category": "desenho",
        "file_url": "https://docs.danfer.com/srv-1.dxf",
    }).json()
    client.post("/api/v1/boms", json={
        "product_id": product["id"], "components": [{"part_id": component["id"], "quantity": 1}],
    })
    quote = client.post("/api/v1/commercial/quotes", json={
        "type": "servico", "commercial_operation": "industrializacao_material_terceiros",
        "client_id": customer["id"], "valid_until": str(date.today() + timedelta(days=10)),
        "items": [{"code": "SRV-1", "description": "Serviço dobrado", "quantity": 5,
                   "material": "Aço carbono", "net_weight_kg": 2, "manual_unit_price": 200,
                   "processes": [{"name": "Dobra", "minutes": 10, "hourly_rate": 260}]}],
    }).json()
    for status in ("enviado", "aprovado"):
        client.post(f"/api/v1/commercial/quotes/{quote['id']}/status", json={"status": status})
    order = client.post(f"/api/v1/workflows/quotes/{quote['id']}/production-orders").json()[0]
    empty = client.post("/api/v1/workflows/service-price-suggestion", json={
        "commercial_operation": "industrializacao_material_terceiros", "quantity": 5,
        "total_weight_kg": 10, "routing_steps": ["Dobra"],
    }).json()
    assert empty["sample_count"] == 0
    client.post(f"/api/v1/pcp/orders/{order['id']}/logs", json={
        "type": "operacao", "operation_erp_code": 5, "minutes": 70,
    })
    for status in ("liberada", "em_producao", "concluida"):
        client.patch(f"/api/v1/pcp/orders/{order['id']}", json={"status": status})
    suggestion = client.post("/api/v1/workflows/service-price-suggestion", json={
        "commercial_operation": "industrializacao_material_terceiros", "quantity": 5,
        "total_weight_kg": 10, "routing_steps": ["Dobra"],
    }).json()
    assert suggestion["sample_count"] == 1
    assert suggestion["suggested_minutes"] == 70
    assert suggestion["suggested_value"] == 1000
    sale = client.post("/api/v1/workflows/service-price-suggestion", json={
        "commercial_operation": "venda_industrializacao", "quantity": 5,
        "total_weight_kg": 10, "routing_steps": ["Dobra"],
    }).json()
    assert sale["eligible"] is False
    reviews = client.get("/api/v1/workflows/price-reviews", params={
        "client_id": customer["id"], "type": "servico",
        "start": str(date.today() - timedelta(days=1)), "end": str(date.today()),
    }).json()
    assert len(reviews) == 1
    assert reviews[0]["validity_days"] == 180
    assert reviews[0]["historical_unit_price"] == 200
    adjustment = client.post("/api/v1/commercial/price-adjustments", json={
        "client_id": customer["id"], "item_code": "SRV-1",
        "commercial_operation": "industrializacao_material_terceiros",
        "previous_unit_price": 200, "new_unit_price": 225,
        "reason": "Revisão de custos", "effective_date": str(date.today()),
    })
    assert adjustment.status_code == 201
    revised = client.get("/api/v1/workflows/price-reviews", params={"client_id": customer["id"]}).json()
    assert revised[0]["historical_unit_price"] == 200
    assert revised[0]["current_reference_price"] == 225
