import base64
import io

import ezdxf
from fastapi.testclient import TestClient

from danfer_os.main import create_app
from danfer_os.services.technical_library import TechnicalLibrary


def dxf_payload(filename: str = "Suporte_QTD3.dxf") -> dict[str, str]:
    document = ezdxf.new()
    document.modelspace().add_lwpolyline([(0, 0), (100, 0), (100, 50), (0, 50)], close=True)
    stream = io.StringIO()
    document.write(stream)
    return {"filename": filename, "content_base64": base64.b64encode(stream.getvalue().encode()).decode()}


def test_nesting_compares_sheets_places_without_overlap_and_renders_svg() -> None:
    client = TestClient(create_app(TechnicalLibrary()))
    payload = {
        "parts": [
            {"code": "LARGO", "width_mm": 1300, "height_mm": 700, "quantity": 2, "allow_rotation": False},
            {"code": "PEQUENO", "width_mm": 100, "height_mm": 100, "quantity": 2},
        ],
        "gap_mm": 5,
        "edge_margin_mm": 10,
    }
    response = client.post("/api/v1/engineering/nesting/plan", json=payload)
    assert response.status_code == 200
    plan = response.json()
    assert plan["selected_sheet"]["width_mm"] == 1500
    assert plan["comparison"][0]["unplaced_count"] >= 2
    assert plan["comparison"][1]["unplaced_count"] == 0
    placements = plan["placements"]
    for index, first in enumerate(placements):
        for second in placements[index + 1:]:
            separated = (
                first["x_mm"] + first["width_mm"] <= second["x_mm"]
                or second["x_mm"] + second["width_mm"] <= first["x_mm"]
                or first["y_mm"] + first["height_mm"] <= second["y_mm"]
                or second["y_mm"] + second["height_mm"] <= first["y_mm"]
            )
            assert separated
    svg = client.post("/api/v1/engineering/nesting/preview.svg", json=payload)
    assert svg.status_code == 200
    assert svg.headers["content-type"].startswith("image/svg+xml")
    assert "LARGO" in svg.text
    assert "Ocupação" in svg.text


def test_batch_nesting_uses_multiple_sheets_and_reports_real_utilization() -> None:
    client = TestClient(create_app(TechnicalLibrary()))
    response = client.post("/api/v1/engineering/nesting/batch-plan", json={
        "parts": [
            {"code": "A", "width_mm": 700, "height_mm": 700, "quantity": 10},
            {"code": "B", "width_mm": 300, "height_mm": 400, "quantity": 12},
        ],
        "sheets": [{"name": "Chapa teste", "width_mm": 1500, "length_mm": 3000}],
        "gap_mm": 5, "edge_margin_mm": 10, "alternative_minimum_gain_percent": 8,
    })
    assert response.status_code == 200
    plan = response.json()
    assert plan["sheet_count"] > 1
    assert plan["placed_count"] == 22
    assert plan["unplaced"] == []
    assert 0 < plan["utilization_percent"] <= 100


def test_dxf_batch_becomes_priced_quote_item_drafts() -> None:
    client = TestClient(create_app(TechnicalLibrary()))
    response = client.post("/api/v1/engineering/dxf/quote-drafts", json={
        "uploads": [dxf_payload(), dxf_payload("Base_X2.dxf")],
        "material": "Aço carbono SAE 1020",
        "thickness_mm": 3,
        "material_price_kg": 8.75,
        "density_kg_m3": 7850,
        "cutting_speed_mm_min": 1500,
        "piercing_seconds": 1.2,
        "laser_hourly_rate": 180,
    })
    assert response.status_code == 200
    drafts = response.json()
    assert [item["quantity"] for item in drafts] == [3, 2]
    assert drafts[0]["net_weight_kg"] == 0.1178
    assert drafts[0]["cut_length_mm"] == 300
    assert drafts[0]["processes"][0]["name"] == "Corte Laser"
    assert drafts[0]["processes"][0]["minutes"] > 0


def test_nesting_uses_administrative_defaults_when_parameters_are_omitted(tmp_path) -> None:
    client = TestClient(create_app(TechnicalLibrary(), data_dir=tmp_path))
    settings = client.get("/api/v1/commercial/settings/costs").json()
    settings.update({
        "default_sheet_width_mm": 1000,
        "default_sheet_length_mm": 2000,
        "alternative_sheet_width_mm": 1400,
        "alternative_sheet_length_mm": 2500,
        "default_nesting_gap_mm": 7,
        "sheet_edge_margin_mm": 15,
        "alternative_minimum_gain_percent": 9,
    })
    client.put("/api/v1/commercial/settings/costs", json=settings)
    response = client.post("/api/v1/engineering/nesting/plan", json={
        "parts": [{"code": "P1", "width_mm": 100, "height_mm": 100}],
    })
    assert response.status_code == 200
    widths = [item["sheet"]["width_mm"] for item in response.json()["comparison"]]
    assert widths == [1000, 1400]
