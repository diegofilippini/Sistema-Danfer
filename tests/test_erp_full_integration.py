from datetime import date, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from danfer_os.main import create_app


def test_erp_settings_are_persistent_and_secrets_are_masked(tmp_path: Path) -> None:
    client = TestClient(create_app(data_dir=tmp_path))
    payload = {
        "provider": "erp-homologacao", "base_url": "https://erp.example/api",
        "api_token": "segredo", "enabled": True,
        "default_warehouse_erp_code": "EST-01",
        "default_bank_account_erp_code": "BANCO-01",
        "default_billing_portfolio_erp_code": "CARTEIRA-01",
        "default_cost_center_erp_code": "CC-IND",
        "default_financial_category_erp_code": "REC-VENDAS",
        "danfer_company_erp_code": "01", "df_company_erp_code": "02",
        "invoice_series": "1",
    }
    updated = client.put("/api/v1/integrations/erp/settings", json=payload)
    assert updated.status_code == 200, updated.text
    assert updated.json()["api_token"] == "********"
    assert client.get("/api/v1/integrations/erp/readiness").json()["ready"] is True
    restarted = TestClient(create_app(data_dir=tmp_path))
    assert restarted.get("/api/v1/integrations/erp/settings").json()["provider"] == "erp-homologacao"


def test_invoice_generates_installments_bank_slips_and_raw_material_stock(tmp_path: Path) -> None:
    client = TestClient(create_app(data_dir=tmp_path))
    client.put("/api/v1/integrations/erp/settings", json={
        "provider": "teste", "base_url": "https://erp.example/api", "api_token": "x",
        "default_warehouse_erp_code": "EST-01", "default_bank_account_erp_code": "BCO-1",
        "default_billing_portfolio_erp_code": "BOL-1", "default_cost_center_erp_code": "CC-1",
        "default_financial_category_erp_code": "REC-1",
    })
    material = client.post("/api/v1/catalogs/materials", json={
        "erp_code": "MP-AC-300", "description": "Aço carbono", "thickness_mm": 3,
        "price_per_kg": 10, "warehouse_erp_code": "EST-CHAPAS", "ncm": "72085100",
    })
    assert material.status_code == 201, material.text
    customer = client.post("/api/v1/commercial/clients", json={
        "name": "Cliente Fiscal", "erp_code": "CLI-10", "document": "12345678000190",
        "state_registration": "123", "city": "Caxias do Sul", "state": "RS",
        "payment_terms": "28/35/42 DDL", "payment_condition_erp_code": "PC-283542",
    }).json()
    quote = client.post("/api/v1/commercial/quotes", json={
        "type": "venda", "client_id": customer["id"],
        "valid_until": str(date.today() + timedelta(days=10)),
        "payment_terms": "28/35/42 DDL", "customer_purchase_order": "OC-900",
        "items": [{"code": "P-1", "description": "Peça", "quantity": 2,
                   "material": "Aço carbono", "thickness_mm": 3,
                   "net_weight_kg": 5, "material_price_kg": 10,
                   "manual_unit_price": 300}],
    }).json()
    for status in ("enviado", "aprovado"):
        client.post(f"/api/v1/commercial/quotes/{quote['id']}/status", json={"status": status})
    order_event = client.post(f"/api/v1/workflows/quotes/{quote['id']}/erp-order").json()
    assert order_event["payload"]["customer_data"]["address"]["state"] == "RS"
    assert order_event["payload"]["raw_materials"][0]["erp_material_code"] == "MP-AC-300"

    # Este teste focaliza o contrato financeiro diretamente; o fluxo de liberação
    # para faturamento por OP concluída já é coberto na suíte de workflows.
    from danfer_os.services.integrations import IntegrationService
    from danfer_os.services.technical_library import TechnicalLibrary
    service = IntegrationService(TechnicalLibrary())
    financial = service.financial_data(600, "28/35/42 DDL")
    assert [item.amount for item in financial.installments] == [200, 200, 200]
    assert [item.due_date for item in financial.installments] == [
        date.today() + timedelta(days=28),
        date.today() + timedelta(days=35),
        date.today() + timedelta(days=42),
    ]
    assert all(item.method == "boleto" for item in financial.installments)
    assert order_event["payload"]["payment_condition_erp_code"] == "PC-283542"
