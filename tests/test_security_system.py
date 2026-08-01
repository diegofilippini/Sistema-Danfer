from pathlib import Path

from fastapi.testclient import TestClient

from danfer_os.main import create_app


def test_auth_enforcement_roles_password_and_backup(tmp_path: Path) -> None:
    client = TestClient(create_app(data_dir=tmp_path, enforce_auth=True))
    assert client.get("/api/v1/commercial/clients").status_code == 401
    login = client.post("/api/v1/auth/login", json={"username": "admin", "password": "Danfer@2026"})
    assert login.status_code == 200
    assert client.get("/api/v1/system/version").json()["data_schema"] == "1"
    backup = client.get("/api/v1/system/backup")
    assert backup.status_code == 200
    assert backup.content.startswith(b"PK")
    changed = client.post("/api/v1/auth/change-password", json={"current_password": "Danfer@2026", "new_password": "NovaSenha@2026"})
    assert changed.status_code == 200
    assert changed.json()["must_change_password"] is False
