from datetime import date, timedelta

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
