from pathlib import Path

from fastapi.testclient import TestClient

from danfer_os.main import create_app


def test_auth_enforcement_roles_password_and_backup(tmp_path: Path) -> None:
    client = TestClient(create_app(data_dir=tmp_path, enforce_auth=True))
    assert client.get("/api/v1/commercial/clients").status_code == 401
    login = client.post("/api/v1/auth/login", json={"username": "admin", "password": "Danfer@2026"})
    assert login.status_code == 200
    assert client.get("/api/v1/system/version").status_code == 428
    changed = client.post("/api/v1/auth/change-password", json={"current_password": "Danfer@2026", "new_password": "NovaSenha@2026"})
    assert changed.status_code == 200
    assert changed.json()["must_change_password"] is False
    assert client.get("/api/v1/system/version").json() == {"version": "1.4.0", "data_schema": "2"}
    backup = client.get("/api/v1/system/backup")
    assert backup.status_code == 200
    assert backup.content.startswith(b"PK")
    restored = client.post(
        "/api/v1/system/restore",
        content=backup.content,
        headers={"Content-Type": "application/zip"},
    )
    assert restored.status_code == 200
    assert restored.json()["restart_required"] is True
    assert (tmp_path.parent / "data-backups" / restored.json()["pre_restore_backup"]).exists()


def test_commercial_role_cannot_access_pcp_or_system_administration(tmp_path: Path) -> None:
    admin = TestClient(create_app(data_dir=tmp_path, enforce_auth=True))
    admin.post("/api/v1/auth/login", json={"username": "admin", "password": "Danfer@2026"})
    admin.post("/api/v1/auth/change-password", json={
        "current_password": "Danfer@2026", "new_password": "AdminNova@2026",
    })
    created = admin.post("/api/v1/auth/users", json={
        "username": "vendas", "name": "Equipe Comercial", "password": "Comercial@2026",
        "role": "comercial",
    })
    assert created.status_code == 201
    assert admin.post("/api/v1/catalogs/materials", json={
        "erp_code": "CH-TESTE", "description": "Aço teste", "thickness_mm": 3,
        "price_per_kg": 9.75,
    }).status_code == 201
    commercial = TestClient(create_app(data_dir=tmp_path, enforce_auth=True))
    assert commercial.post("/api/v1/auth/login", json={
        "username": "vendas", "password": "Comercial@2026",
    }).status_code == 200
    assert commercial.get("/api/v1/commercial/clients").status_code == 428
    assert commercial.post("/api/v1/auth/change-password", json={
        "current_password": "Comercial@2026", "new_password": "ComercialNova@2026",
    }).status_code == 200
    assert commercial.get("/api/v1/commercial/clients").status_code == 200
    assert commercial.get("/api/v1/commercial/settings/costs").status_code == 403
    assert commercial.put("/api/v1/commercial/settings/costs", json={}).status_code == 403
    assert commercial.get("/api/v1/catalogs/materials").status_code == 403
    assert commercial.get("/api/v1/catalogs/operations").status_code == 403
    assert commercial.get("/api/v1/catalogs/routing-templates").status_code == 403
    quick_routes = commercial.get("/api/v1/catalogs/quote-routing-templates")
    assert quick_routes.status_code == 200
    assert quick_routes.json()[0]["steps"][0]["default_minutes"] >= 0
    assert "hourly_rate" not in quick_routes.text
    assert commercial.post("/api/v1/engineering/nesting/plan", json={
        "parts": [{"code": "P1", "width_mm": 10, "height_mm": 10}],
    }).status_code == 403
    options = commercial.get("/api/v1/catalogs/quote-materials")
    assert options.status_code == 200
    assert options.json()[0]["description"] == "Aço teste"
    assert "price_per_kg" not in options.json()[0]
    assert commercial.get("/api/v1/pcp/orders").status_code == 403
    assert commercial.get("/api/v1/system/version").status_code == 403


def test_only_admin_can_manage_cost_settings(tmp_path: Path) -> None:
    client = TestClient(create_app(data_dir=tmp_path, enforce_auth=True))
    client.post("/api/v1/auth/login", json={"username": "admin", "password": "Danfer@2026"})
    client.post("/api/v1/auth/change-password", json={
        "current_password": "Danfer@2026", "new_password": "AdminNova@2026",
    })
    response = client.put("/api/v1/commercial/settings/costs", json={
        "default_margin_percent": 32,
        "default_item_utilization_percent": 76,
        "default_ipi_percent": 5,
        "default_cut_hourly_rate": 210,
    })
    assert response.status_code == 200
    assert response.json()["default_margin_percent"] == 32
    assert response.json()["default_cut_hourly_rate"] == 210
