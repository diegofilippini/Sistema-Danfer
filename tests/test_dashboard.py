from datetime import date, timedelta

from fastapi.testclient import TestClient

from danfer_os.main import create_app
from danfer_os.services.technical_library import TechnicalLibrary


def add_part(client: TestClient, code: str, material: str = "") -> dict:
    response = client.post(
        "/api/v1/technical-library",
        json={
            "danfer_code": code,
            "customer_code": f"C-{code}",
            "title": f"Peça {code}",
            "category": "desenho",
            "material": material,
            "file_url": f"https://docs.danfer.com/{code}.pdf",
        },
    )
    assert response.status_code == 201
    return response.json()


def test_industrial_dashboard_consolidates_modules() -> None:
    client = TestClient(create_app(TechnicalLibrary()))
    product = add_part(client, "PAINEL-1")
    component = add_part(client, "CHAPA-1", "Aço carbono")
    bom = client.post(
        "/api/v1/boms",
        json={
            "product_id": product["id"],
            "status": "ativa",
            "components": [{"part_id": component["id"], "quantity": 2}],
        },
    ).json()
    client.post(
        "/api/v1/pcp/orders",
        json={
            "product_id": product["id"],
            "bom_id": bom["id"],
            "quantity": 3,
            "due_date": str(date.today() - timedelta(days=1)),
            "priority": 1,
        },
    )
    client.post(
        "/api/v1/integrations/orders",
        json={
            "external_id": "EXT-1",
            "customer": "Cliente Teste",
            "items": [{"customer_code": "INEXISTENTE", "quantity": 1}],
        },
    )

    response = client.get("/api/v1/dashboard/industrial")

    assert response.status_code == 200
    dashboard = response.json()
    assert dashboard["technical_parts"] == 2
    assert dashboard["active_boms"] == 1
    assert dashboard["production_orders"] == 1
    assert dashboard["overdue_orders"] == 1
    assert dashboard["integration_warnings"] == 1
    assert dashboard["pending_erp_events"] == 1
    assert dashboard["orders_by_status"] == [{"status": "planejada", "total": 1}]
    assert dashboard["material_demand"][0]["total_quantity"] == 6


def test_empty_dashboard() -> None:
    client = TestClient(create_app(TechnicalLibrary()))

    dashboard = client.get("/api/v1/dashboard/industrial").json()

    assert dashboard["technical_parts"] == 0
    assert dashboard["orders_by_status"] == []
    assert dashboard["next_orders"] == []


def test_delivery_board_period_colors_and_top_ten_clients() -> None:
    client = TestClient(create_app(TechnicalLibrary()))
    product = add_part(client, "PAINEL-ENTREGA")
    component = add_part(client, "CHAPA-ENTREGA", "Aço carbono")
    bom = client.post("/api/v1/boms", json={
        "product_id": product["id"], "components": [{"part_id": component["id"], "quantity": 1}],
    }).json()

    def order(name: str, due_date: date) -> None:
        response = client.post("/api/v1/pcp/orders", json={
            "product_id": product["id"], "bom_id": bom["id"], "quantity": 1,
            "due_date": str(due_date), "client_name": name,
        })
        assert response.status_code == 201

    order("Cliente Atrasado", date.today() - timedelta(days=1))
    for index in range(11):
        order(f"Cliente Hoje {index:02d}", date.today())
    order("Cliente Futuro", date.today() + timedelta(days=2))

    response = client.get("/api/v1/dashboard/deliveries", params={"days": 14})
    assert response.status_code == 200
    board = response.json()
    assert len(board["columns"]) == 15
    assert board["columns"][0]["status"] == "red"
    assert board["columns"][0]["clients"][0]["client"] == "Cliente Atrasado"
    assert board["columns"][1]["status"] == "yellow"
    assert len(board["columns"][1]["clients"]) == 10
    assert board["columns"][3]["status"] == "green"
    assert board["columns"][3]["clients"][0]["client"] == "Cliente Futuro"
    assert client.get("/api/v1/dashboard/deliveries", params={"days": 8}).status_code == 422
