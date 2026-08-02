import base64
import io
from datetime import date, timedelta
from pathlib import Path

import ezdxf
import base64

from fastapi.testclient import TestClient

from danfer_os.main import create_app
from danfer_os.services.technical_library import TechnicalLibrary


def test_price_table_import_updates_creates_and_keeps_history(tmp_path) -> None:
    client = TestClient(create_app(data_dir=tmp_path))
    existing = client.post("/api/v1/catalogs/materials", json={
        "erp_code": "CH-001", "description": "Aço existente", "thickness_mm": 3,
        "price_per_kg": 8, "density_kg_m3": 7850,
    })
    assert existing.status_code == 201
    content = (
        "Codigo ERP;Descricao;Espessura;Preco kg;Densidade\n"
        "CH-001;Aço existente;3;9,50;7850\n"
        "CH-002;Inox 304;2;18,75;7930\n"
        ";Linha inválida;1;4,00;7850\n"
    ).encode("utf-8")
    preview = client.post("/api/v1/catalogs/materials/price-table/preview", json={
        "filename": "tabela-precos.csv", "content_base64": base64.b64encode(content).decode(),
        "header_row": 1,
    })
    assert preview.status_code == 201
    assert preview.json()["total_rows"] == 3
    session_id = preview.json()["session_id"]
    applied = client.post(f"/api/v1/catalogs/materials/price-table/{session_id}/apply", json={
        "erp_code_column": "Codigo ERP", "price_column": "Preco kg",
        "description_column": "Descricao", "thickness_column": "Espessura",
        "density_column": "Densidade", "create_missing": True,
    })
    assert applied.status_code == 200
    result = applied.json()
    assert result["updated"] == 1
    assert result["created"] == 1
    assert result["invalid"] == 1
    assert result["changes"][0]["old_price"] == 8
    materials = client.get("/api/v1/catalogs/materials").json()
    assert {item["erp_code"]: item["price_per_kg"] for item in materials} == {
        "CH-001": 9.5, "CH-002": 18.75,
    }
    restarted = TestClient(create_app(data_dir=tmp_path))
    history = restarted.get("/api/v1/catalogs/materials/price-table/history").json()
    assert history[0]["filename"] == "tabela-precos.csv"
    assert history[0]["created"] == 1


def test_material_catalog_persists_and_erp_operations_are_seeded(tmp_path: Path) -> None:
    client = TestClient(create_app(TechnicalLibrary(), data_dir=tmp_path))
    created = client.post("/api/v1/catalogs/materials", json={
        "erp_code": "MAT-AC-300-3",
        "description": "Aço carbono 3,00 mm",
        "specification": "SAE 1020",
        "thickness_mm": 3,
        "price_per_kg": 8.75,
        "laser_speed_mm_min": 1500,
        "plasma_speed_mm_min": 900,
    })
    assert created.status_code == 201
    assert client.post("/api/v1/catalogs/materials", json=created.json()).status_code == 409
    restarted = TestClient(create_app(TechnicalLibrary(), data_dir=tmp_path))
    assert restarted.get("/api/v1/catalogs/materials").json()[0]["price_per_kg"] == 8.75
    assert restarted.get("/api/v1/catalogs/materials").json()[0]["laser_speed_mm_min"] == 1500
    operations = restarted.get("/api/v1/catalogs/operations").json()
    assert [(item["erp_code"], item["name"]) for item in operations] == [
        (2, "Corte Laser"), (3, "Guilhotina"), (4, "Plasma"), (5, "Dobra"),
        (6, "Calandra"), (7, "Prensa"), (8, "Chanfro"), (9, "Solda"),
        (60, "Calandra por peso"),
    ]
    costs = {item["name"]: (item["pricing_mode"], item["hourly_rate"], item["weight_rate"])
             for item in operations}
    assert costs["Corte Laser"] == ("tempo", 360, 0)
    assert costs["Dobra"] == ("tempo", 260, 0)
    assert costs["Calandra"] == ("tempo", 240, 0)
    assert costs["Calandra por peso"] == ("peso", 0, 1.8)
    assert costs["Solda"] == ("tempo", 160, 0)
    assert costs["Guilhotina"] == ("tempo", 200, 0)
    templates = restarted.get("/api/v1/catalogs/routing-templates").json()
    assert any(item["name"] == "Corte + Dobra" for item in templates)
    created_template = restarted.post("/api/v1/catalogs/routing-templates", json={
        "name": "Roteiro de teste",
        "description": "Seleção rápida",
        "steps": [
            {"operation_erp_code": 2, "process": "Corte Laser", "default_minutes": 7},
            {"operation_erp_code": 9, "process": "Solda", "default_minutes": 12},
        ],
    })
    assert created_template.status_code == 201
    restarted_again = TestClient(create_app(TechnicalLibrary(), data_dir=tmp_path))
    assert any(item["name"] == "Roteiro de teste" for item in restarted_again.get(
        "/api/v1/catalogs/routing-templates"
    ).json())


def test_catalog_process_values_are_applied_to_quote_costing(tmp_path: Path) -> None:
    client = TestClient(create_app(TechnicalLibrary(), data_dir=tmp_path))
    customer = client.post("/api/v1/commercial/clients", json={"name": "Cliente Custeio"}).json()
    quote = client.post("/api/v1/commercial/quotes", json={
        "type": "servico", "client_id": customer["id"], "valid_until": str(date.today() + timedelta(days=10)),
        "items": [{"code": "CAL-PESO", "description": "Calandragem por peso", "quantity": 1,
                   "net_weight_kg": 10, "processes": [{"name": "Calandra por peso", "minutes": 0,
                   "hourly_rate": 0}]}],
    })
    assert quote.status_code == 201
    assert quote.json()["items"][0]["process_cost"] == 18


def test_material_cut_speed_is_editable_applied_and_material_can_be_deleted(tmp_path: Path) -> None:
    client = TestClient(create_app(TechnicalLibrary(), data_dir=tmp_path))
    material = client.post("/api/v1/catalogs/materials", json={
        "erp_code": "AC-3", "description": "Aço carbono", "specification": "SAE 1020",
        "thickness_mm": 3, "price_per_kg": 8, "density_kg_m3": 7850,
        "laser_speed_mm_min": 1000, "plasma_speed_mm_min": 750,
    }).json()
    updated = client.patch(f"/api/v1/catalogs/materials/{material['id']}", json={
        "laser_speed_mm_min": 2000, "price_per_kg": 9,
    })
    assert updated.status_code == 200
    assert updated.json()["laser_speed_mm_min"] == 2000
    customer = client.post("/api/v1/commercial/clients", json={"name": "Cliente Velocidade"}).json()
    quote = client.post("/api/v1/commercial/quotes", json={
        "type": "servico", "client_id": customer["id"],
        "valid_until": str(date.today() + timedelta(days=10)),
        "items": [{"code": "LAS-1", "description": "Corte por velocidade", "quantity": 1,
                   "material": "Aço carbono", "thickness_mm": 3, "cut_length_mm": 2000,
                   "processes": [{"name": "Corte Laser", "minutes": 0, "hourly_rate": 0}]}],
    })
    assert quote.status_code == 201
    assert quote.json()["items"][0]["laser_estimated_minutes"] == 1
    assert quote.json()["items"][0]["process_cost"] == 6
    projected = client.get("/api/v1/catalogs/quote-materials").json()[0]
    assert "laser_speed_mm_min" not in projected
    assert client.delete(f"/api/v1/catalogs/materials/{material['id']}").status_code == 204
    assert client.get("/api/v1/catalogs/materials").json() == []


def test_dxf_registration_creates_searchable_technical_record(tmp_path: Path) -> None:
    document = ezdxf.new()
    document.modelspace().add_lwpolyline([(0, 0), (80, 0), (80, 40), (0, 40)], close=True)
    stream = io.StringIO()
    document.write(stream)
    client = TestClient(create_app(TechnicalLibrary(), data_dir=tmp_path))
    response = client.post("/api/v1/engineering/dxf/register", json={
        "filename": "Base_QTD4.dxf",
        "content_base64": base64.b64encode(stream.getvalue().encode()).decode(),
        "danfer_code": "DF-DXF-001",
        "material": "Aço carbono",
        "thickness_mm": 3,
    })
    assert response.status_code == 201
    item = response.json()
    assert item["width_mm"] == 80
    assert item["cut_length_mm"] == 240
    assert item["routing"][0]["erp_code"] == 2
    assert client.get("/api/v1/technical-library", params={"q": "DF-DXF-001"}).json()["total"] == 1
