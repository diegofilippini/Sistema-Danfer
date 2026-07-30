from pathlib import Path

from fastapi.testclient import TestClient

from danfer_os.main import create_app
from danfer_os.services.technical_library import TechnicalLibrary


def test_auth_quality_maintenance_and_audit(tmp_path: Path) -> None:
    client = TestClient(create_app(TechnicalLibrary(), data_dir=tmp_path))
    login = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "Danfer@2026"},
    )
    assert login.status_code == 200
    assert login.json()["user"]["role"] == "administrador"
    assert client.get("/api/v1/auth/me").status_code == 200

    quality = client.post(
        "/api/v1/quality",
        json={
            "type": "retrabalho",
            "description": "Dobra fora da tolerância",
            "responsible": "Produção",
            "cost": 150,
        },
    )
    assert quality.status_code == 201
    resolved = client.post(f"/api/v1/quality/{quality.json()['id']}/resolve")
    assert resolved.json()["resolved"] is True

    maintenance = client.post(
        "/api/v1/maintenance",
        json={
            "equipment": "Laser 01",
            "type": "preventiva",
            "description": "Revisão dos filtros",
        },
    )
    assert maintenance.status_code == 201
    assert maintenance.json()["number"].startswith("MAN-")
    completed = client.post(
        f"/api/v1/maintenance/{maintenance.json()['id']}/status",
        json={"status": "concluida", "actual_cost": 320},
    )
    assert completed.json()["actual_cost"] == 320
    assert len(client.get("/api/v1/audit").json()) >= 4
