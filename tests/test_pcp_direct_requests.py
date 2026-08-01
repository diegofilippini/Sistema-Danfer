from datetime import date, timedelta

from fastapi.testclient import TestClient

from danfer_os.main import create_app


def test_direct_production_request_is_persistent_and_trackable(tmp_path) -> None:
    client = TestClient(create_app(data_dir=tmp_path))
    payload = {
        "client": "Cliente Industrial",
        "contact": "Comprador",
        "description": "Corte e dobra de suportes",
        "processes": ["Corte Laser", "Dobra"],
        "material": "SAE 1020 3 mm",
        "due_date": str(date.today() + timedelta(days=7)),
        "priority": 2,
    }
    created = client.post("/api/v1/pcp/direct-requests", json=payload)
    assert created.status_code == 201
    assert created.json()["number"].startswith("SP-")
    request_id = created.json()["id"]

    updated = client.patch(f"/api/v1/pcp/direct-requests/{request_id}", json={
        "status": "em_producao", "progress_percent": 40,
    })
    assert updated.status_code == 200
    assert updated.json()["progress_percent"] == 40

    restarted = TestClient(create_app(data_dir=tmp_path))
    restored = restarted.get("/api/v1/pcp/direct-requests").json()
    assert restored[0]["status"] == "em_producao"
    assert restored[0]["client"] == "Cliente Industrial"
