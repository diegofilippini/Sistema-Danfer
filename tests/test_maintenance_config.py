from fastapi.testclient import TestClient

from danfer_os.main import create_app


def test_v051_maintenance_catalogs_are_recovered_editable_and_persistent(tmp_path) -> None:
    client = TestClient(create_app(data_dir=tmp_path))
    categories = client.get("/api/v1/maintenance-config/categories").json()
    assert categories["materials"] == 61
    assert categories["models"] == 103
    assert categories["taxScenarios"] == 4
    materials = client.get("/api/v1/maintenance-config/materials").json()
    corrected = next(item for item in materials if item["material"] == "aço carbono" and item["espessura"] == 1.06)
    assert corrected["densidade"] == 7850
    assert client.get("/api/v1/maintenance-config/standardSheets").json() == [
        {"codigo": "CH1200", "largura": 1200.0, "comprimento": 3000.0},
        {"codigo": "CH1500", "largura": 1500.0, "comprimento": 3000.0},
    ]
    rules = client.get("/api/v1/maintenance-config/largePieceLossRules").json()
    rules[0]["percentualPerda"] = 18
    assert client.put("/api/v1/maintenance-config/largePieceLossRules", json=rules).status_code == 200
    restarted = TestClient(create_app(data_dir=tmp_path))
    assert restarted.get("/api/v1/maintenance-config/largePieceLossRules").json()[0]["percentualPerda"] == 18


def test_v051_models_are_available_as_quick_routing_templates(tmp_path) -> None:
    client = TestClient(create_app(data_dir=tmp_path))
    templates = client.get("/api/v1/catalogs/routing-templates").json()
    names = {item["name"] for item in templates}
    assert "Corte + Dobra" in names
    assert "LD · Corte laser + Dobra" in names
