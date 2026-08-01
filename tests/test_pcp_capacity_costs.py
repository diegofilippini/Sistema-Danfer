from datetime import date, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from danfer_os.main import create_app
from danfer_os.services.technical_library import TechnicalLibrary


def build_order(client: TestClient, due: date) -> dict[str, object]:
    product = client.post("/api/v1/technical-library", json={
        "danfer_code": "PROD-CAP", "title": "Produto capacidade", "category": "desenho",
        "file_url": "https://docs.danfer.com/prod-cap.dxf",
        "routing": [{"erp_code": 2, "process": "Corte Laser", "estimated_minutes": 12}],
    }).json()
    component = client.post("/api/v1/technical-library", json={
        "danfer_code": "COMP-CAP", "title": "Componente capacidade", "category": "desenho",
        "file_url": "https://docs.danfer.com/comp-cap.dxf",
    }).json()
    bom = client.post("/api/v1/boms", json={
        "product_id": product["id"], "components": [{"part_id": component["id"], "quantity": 1}],
    }).json()
    response = client.post("/api/v1/pcp/orders", json={
        "product_id": product["id"], "bom_id": bom["id"], "quantity": 10,
        "due_date": str(due), "estimated_material_cost": 500, "estimated_process_cost": 300,
    })
    assert response.status_code == 201
    return response.json()


def test_daily_capacity_calendar_and_real_cost_variance(tmp_path: Path) -> None:
    client = TestClient(create_app(TechnicalLibrary(), data_dir=tmp_path))
    due = date.today() + timedelta(days=(7 - date.today().weekday()) % 7 or 1)
    order = build_order(client, due)
    center = client.put("/api/v1/pcp/work-centers/2", json={
        "operation_erp_code": 2, "name": "Corte Laser", "daily_capacity_minutes": 100,
        "hourly_rate": 180,
    })
    assert center.status_code == 200
    capacity = client.get("/api/v1/pcp/capacity/daily", params={"start": str(due), "days": 1}).json()[0]
    assert capacity["planned_minutes"] == 120
    assert capacity["overloaded"] is True

    client.put(f"/api/v1/pcp/calendar/{due}", json={
        "date": str(due), "available_minutes": 150, "reason": "Hora extra",
    })
    adjusted = client.get("/api/v1/pcp/capacity/daily", params={"start": str(due), "days": 1}).json()[0]
    assert adjusted["overloaded"] is False

    for payload in (
        {"type": "material", "quantity": 50, "unit_cost": 11},
        {"type": "operacao", "operation_erp_code": 2, "minutes": 120},
        {"type": "qualidade", "amount": 40},
    ):
        assert client.post(f"/api/v1/pcp/orders/{order['id']}/logs", json=payload).status_code == 201
    costs = client.get(f"/api/v1/pcp/orders/{order['id']}/costs").json()
    assert costs["actual_total_cost"] == 950
    assert costs["variance_value"] == 150
    assert costs["variance_percent"] == 18.75

    restarted = TestClient(create_app(TechnicalLibrary(tmp_path / "technical-library.json"), data_dir=tmp_path))
    assert restarted.get("/api/v1/pcp/orders").json()[0]["number"] == order["number"]
    assert len(restarted.get(f"/api/v1/pcp/orders/{order['id']}/logs").json()) == 3
