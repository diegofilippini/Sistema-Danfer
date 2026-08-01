from datetime import date

from fastapi.testclient import TestClient

from danfer_os.main import create_app


def test_management_quality_and_monthly_analytics_use_persistent_data(tmp_path) -> None:
    client = TestClient(create_app(data_dir=tmp_path))
    occurrence = client.post("/api/v1/quality", json={
        "type": "retrabalho", "description": "Dobra fora da medida",
        "responsible": "Qualidade", "cost": 325.5,
    })
    assert occurrence.status_code == 201

    quality = client.get("/api/v1/analytics/quality").json()
    assert quality["total"] == 1
    assert quality["open"] == 1
    assert quality["total_cost"] == 325.5

    management = client.get("/api/v1/analytics/management").json()
    assert management["quality_cost"] == 325.5
    assert management["quotes"] == 0

    monthly = client.get("/api/v1/analytics/monthly", params={
        "start": str(date.today().replace(day=1)), "end": str(date.today()),
    })
    assert monthly.status_code == 200
    assert monthly.json()["orders"] == 0
