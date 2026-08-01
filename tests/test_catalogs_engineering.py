import base64
import io
from pathlib import Path

import ezdxf
from fastapi.testclient import TestClient

from danfer_os.main import create_app
from danfer_os.services.technical_library import TechnicalLibrary


def test_material_catalog_persists_and_erp_operations_are_seeded(tmp_path: Path) -> None:
    client = TestClient(create_app(TechnicalLibrary(), data_dir=tmp_path))
    created = client.post("/api/v1/catalogs/materials", json={
        "erp_code": "MAT-AC-300-3",
        "description": "Aço carbono 3,00 mm",
        "specification": "SAE 1020",
        "thickness_mm": 3,
        "price_per_kg": 8.75,
    })
    assert created.status_code == 201
    assert client.post("/api/v1/catalogs/materials", json=created.json()).status_code == 409
    restarted = TestClient(create_app(TechnicalLibrary(), data_dir=tmp_path))
    assert restarted.get("/api/v1/catalogs/materials").json()[0]["price_per_kg"] == 8.75
    operations = restarted.get("/api/v1/catalogs/operations").json()
    assert [(item["erp_code"], item["name"]) for item in operations] == [
        (2, "Corte Laser"), (3, "Guilhotina"), (4, "Plasma"), (5, "Dobra"),
        (6, "Calandra"), (7, "Prensa"), (8, "Chanfro"), (9, "Solda"),
    ]


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
