from pathlib import Path
from datetime import date, timedelta

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
    assert client.get("/api/v1/system/version").json() == {"version": "1.6.0", "data_schema": "3"}
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


def test_global_search_respects_configured_module_permissions(tmp_path: Path) -> None:
    admin = TestClient(create_app(data_dir=tmp_path, enforce_auth=True))
    admin.post("/api/v1/auth/login", json={"username": "admin", "password": "Danfer@2026"})
    admin.post("/api/v1/auth/change-password", json={
        "current_password": "Danfer@2026", "new_password": "AdminNova@2026",
    })
    admin.post("/api/v1/commercial/clients", json={"name": "Cliente Confidencial Busca"})
    created = admin.post("/api/v1/auth/users", json={
        "username": "engenheiro", "name": "Engenharia", "password": "Engenharia@2026",
        "role": "engenharia",
    }).json()
    admin.patch(f"/api/v1/auth/users/{created['id']}", json={
        "active": True, "permissions": ["engineering"],
    })

    engineering = TestClient(create_app(data_dir=tmp_path, enforce_auth=True))
    engineering.post("/api/v1/auth/login", json={
        "username": "engenheiro", "password": "Engenharia@2026",
    })
    engineering.post("/api/v1/auth/change-password", json={
        "current_password": "Engenharia@2026", "new_password": "EngenhariaNova@2026",
    })
    response = engineering.get("/api/v1/search", params={"q": "Cliente Confidencial"})
    assert response.status_code == 200
    assert response.json() == []


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


def test_admin_can_customize_modules_for_each_user(tmp_path: Path) -> None:
    admin = TestClient(create_app(data_dir=tmp_path, enforce_auth=True))
    admin.post("/api/v1/auth/login", json={"username": "admin", "password": "Danfer@2026"})
    admin.post("/api/v1/auth/change-password", json={
        "current_password": "Danfer@2026", "new_password": "AdminNova@2026",
    })
    created = admin.post("/api/v1/auth/users", json={
        "username": "orcamentista", "name": "Orçamentista", "password": "Orcamento@2026",
        "role": "comercial",
    }).json()
    updated = admin.patch(f"/api/v1/auth/users/{created['id']}", json={
        "active": True, "permissions": ["dashboard", "quotes"],
    })
    assert updated.status_code == 200
    assert updated.json()["permissions"] == ["dashboard", "quotes"]

    user = TestClient(create_app(data_dir=tmp_path, enforce_auth=True))
    user.post("/api/v1/auth/login", json={"username": "orcamentista", "password": "Orcamento@2026"})
    user.post("/api/v1/auth/change-password", json={
        "current_password": "Orcamento@2026", "new_password": "OrcamentoNova@2026",
    })
    assert user.get("/api/v1/commercial/quotes").status_code == 200
    assert user.get("/api/v1/catalogs/quote-materials").status_code == 200
    assert user.get("/api/v1/catalogs/quote-routing-templates").status_code == 200
    assert user.post("/api/v1/engineering/dxf/analyze-batch").status_code == 403


def test_commercial_user_cannot_decide_customer_proposal(tmp_path: Path) -> None:
    admin = TestClient(create_app(data_dir=tmp_path, enforce_auth=True))
    admin.post("/api/v1/auth/login", json={"username": "admin", "password": "Danfer@2026"})
    admin.post("/api/v1/auth/change-password", json={
        "current_password": "Danfer@2026", "new_password": "AdminNova@2026",
    })
    admin.post("/api/v1/auth/users", json={
        "username": "vendedor", "name": "Vendedor", "password": "Vendedor@2026",
        "role": "comercial",
    })
    customer = admin.post("/api/v1/commercial/clients", json={"name": "Cliente Proposta"}).json()
    quote = admin.post("/api/v1/commercial/quotes", json={
        "type": "servico", "client_id": customer["id"],
        "valid_until": str(date.today() + timedelta(days=10)),
        "items": [{"code": "P1", "description": "Peça", "quantity": 1,
                   "manual_unit_price": 3000}],
    }).json()
    admin.post(f"/api/v1/commercial/quotes/{quote['id']}/status", json={"status": "enviado"})
    pending = admin.post(f"/api/v1/commercial/quotes/{quote['id']}/customer-proposals", json={
        "proposed_total": 2700,
    }).json()
    proposal_id = pending["customer_proposals"][0]["id"]

    commercial = TestClient(create_app(data_dir=tmp_path, enforce_auth=True))
    commercial.post("/api/v1/auth/login", json={"username": "vendedor", "password": "Vendedor@2026"})
    commercial.post("/api/v1/auth/change-password", json={
        "current_password": "Vendedor@2026", "new_password": "VendedorNova@2026",
    })
    denied = commercial.post(
        f"/api/v1/commercial/quotes/{quote['id']}/customer-proposals/{proposal_id}/decision",
        json={"approved": True, "reason": "Tentativa sem alçada"},
    )
    assert denied.status_code == 403
    assert commercial.get(f"/api/v1/commercial/quotes/{quote['id']}").json()["status"] == "aguardando_aprovacao_administrativa"
