from datetime import date, timedelta
import re

from fastapi.testclient import TestClient

from danfer_os.main import create_app
from danfer_os.services.technical_library import TechnicalLibrary


def part(client: TestClient, code: str, material: str = "", thickness: float | None = None) -> str:
    payload = {
        "danfer_code": code,
        "title": f"Peça {code}",
        "category": "desenho",
        "file_url": f"https://docs.danfer.com/{code}.pdf",
        "material": material,
    }
    if thickness is not None:
        payload["thickness_mm"] = thickness
    response = client.post("/api/v1/technical-library", json=payload)
    assert response.status_code == 201
    return response.json()["id"]


def test_pcp_order_material_group_and_kanban_flow() -> None:
    client = TestClient(create_app(TechnicalLibrary()))
    product = part(client, "PROD-1")
    component = part(client, "COMP-1", "Aço SAE 1020", 3)
    bom = client.post(
        "/api/v1/boms",
        json={
            "product_id": product,
            "status": "ativa",
            "components": [{"part_id": component, "quantity": 2}],
        },
    ).json()
    order_response = client.post(
        "/api/v1/pcp/orders",
        json={
            "product_id": product,
            "bom_id": bom["id"],
            "quantity": 5,
            "due_date": str(date.today() + timedelta(days=2)),
            "priority": 1,
        },
    )
    assert order_response.status_code == 201
    order = order_response.json()
    assert order["requirements"][0]["quantity"] == 10
    assert order["number"].startswith("OP-")

    single_pdf = client.get("/api/v1/pcp/orders-print.pdf", params={"ids": order["id"]})
    assert single_pdf.status_code == 200
    assert single_pdf.headers["content-type"] == "application/pdf"
    assert single_pdf.content.startswith(b"%PDF")
    single_box = re.search(rb"/MediaBox\s*\[\s*0\s+0\s+([\d.]+)\s+([\d.]+)", single_pdf.content)
    assert single_box and float(single_box.group(1)) > float(single_box.group(2))
    batch_pdf = client.get("/api/v1/pcp/orders-print.pdf", params=[
        ("ids", order["id"]), ("ids", order["id"]),
    ])
    assert batch_pdf.status_code == 200
    assert "OPs-2.pdf" in batch_pdf.headers["content-disposition"]
    assert len(batch_pdf.content) > len(single_pdf.content)
    batch_box = re.search(rb"/MediaBox\s*\[\s*0\s+0\s+([\d.]+)\s+([\d.]+)", batch_pdf.content)
    assert batch_box and float(batch_box.group(1)) < float(batch_box.group(2))

    groups = client.get("/api/v1/pcp/material-groups").json()
    assert groups[0]["material"] == "Aço SAE 1020"
    assert groups[0]["total_quantity"] == 10

    for next_status in ("liberada", "em_producao", "concluida"):
        moved = client.patch(
            f"/api/v1/pcp/orders/{order['id']}",
            json={"status": next_status},
        )
        assert moved.status_code == 200
    assert client.get("/api/v1/pcp/sequence").json() == []


def test_pcp_rejects_invalid_status_transition() -> None:
    client = TestClient(create_app(TechnicalLibrary()))
    product = part(client, "PROD-2")
    component = part(client, "COMP-2")
    bom = client.post(
        "/api/v1/boms",
        json={
            "product_id": product,
            "components": [{"part_id": component, "quantity": 1}],
        },
    ).json()
    order = client.post(
        "/api/v1/pcp/orders",
        json={
            "product_id": product,
            "bom_id": bom["id"],
            "quantity": 1,
            "due_date": str(date.today()),
        },
    ).json()
    response = client.patch(
        f"/api/v1/pcp/orders/{order['id']}",
        json={"status": "concluida"},
    )
    assert response.status_code == 409


def test_cost_analyst_can_register_manual_order_without_quote() -> None:
    client = TestClient(create_app(TechnicalLibrary()))
    quotes_before = client.get("/api/v1/commercial/quotes").json()
    response = client.post("/api/v1/pcp/direct-requests", json={
        "origin": "pedido_manual_sem_orcamento",
        "client": "Cliente Pedido Direto", "customer_erp_code": "CLI-0099",
        "contact": "Compras", "customer_order_number": "PC-7788",
        "description": "Lote informado diretamente pelo analista de custos",
        "processes": ["Corte Laser", "Dobra"], "material": "Aço carbono",
        "due_date": str(date.today() + timedelta(days=5)), "priority": 2,
        "reason": "Pedido recorrente autorizado",
        "items": [
            {"code": "MAN-01", "description": "Suporte", "quantity": 10,
             "unit": "un", "material": "Aço carbono", "thickness_mm": 3,
             "unit_price": 125.50},
            {"code": "MAN-02", "description": "Tampa", "quantity": 4,
             "unit": "un", "material": "Aço carbono", "thickness_mm": 2,
             "unit_price": 80},
        ],
    })
    assert response.status_code == 201, response.text
    order = response.json()
    assert order["number"].startswith("SP-")
    assert order["origin"] == "pedido_manual_sem_orcamento"
    assert order["customer_erp_code"] == "CLI-0099"
    assert len(order["items"]) == 2
    assert order["total_value"] == 1575
    assert client.get("/api/v1/commercial/quotes").json() == quotes_before
