import base64
import io
from pathlib import Path

import ezdxf
from fastapi.testclient import TestClient
from reportlab.pdfgen import canvas

from danfer_os.main import create_app
from danfer_os.services.technical_library import TechnicalLibrary


def test_dxf_analysis_dimensions_quantity_and_nesting(tmp_path: Path) -> None:
    document = ezdxf.new()
    modelspace = document.modelspace()
    modelspace.add_lwpolyline(
        [(0, 0), (100, 0), (100, 40), (40, 40), (40, 100), (0, 100)],
        close=True,
    )
    stream = io.StringIO()
    document.write(stream)
    client = TestClient(create_app(TechnicalLibrary(), data_dir=tmp_path))
    response = client.post(
        "/api/v1/engineering/dxf/analyze",
        json={
            "filename": "Suporte_QTD10.dxf",
            "content_base64": base64.b64encode(stream.getvalue().encode()).decode(),
        },
    )
    assert response.status_code == 200
    analysis = response.json()
    assert analysis["suggested_quantity"] == 10
    assert analysis["width_mm"] == 100
    assert analysis["height_mm"] == 100
    assert analysis["fill_factor_percent"] == 64
    assert analysis["nesting_suggestion"] == "forcar_ncav"


def test_pdf_dimensions_require_budgeter_confirmation(tmp_path: Path) -> None:
    stream = io.BytesIO()
    document = canvas.Canvas(stream)
    document.drawString(80, 760, "PECA SUPORTE - MEDIDAS 120 x 350 mm - ESP. 3 mm")
    document.save()
    client = TestClient(create_app(TechnicalLibrary(), data_dir=tmp_path))
    analysis = client.post("/api/v1/engineering/pdf/analyze", json={
        "filename": "suporte.pdf",
        "content_base64": base64.b64encode(stream.getvalue()).decode(),
    })
    assert analysis.status_code == 200
    assert analysis.json()["width_mm"] == 120
    assert analysis.json()["height_mm"] == 350
    assert analysis.json()["requires_confirmation"] is True
    payload = {"filename": "suporte.pdf", "code": "PDF-1", "description": "Suporte",
               "quantity": 2, "material": "Aço carbono", "thickness_mm": 3,
               "width_mm": 120, "height_mm": 350, "confirmed": False}
    assert client.post("/api/v1/engineering/pdf/confirm-quote-item", json=payload).status_code == 422
    payload["confirmed"] = True
    item = client.post("/api/v1/engineering/pdf/confirm-quote-item", json=payload)
    assert item.status_code == 200
    assert item.json()["cut_length_mm"] == 940
    assert "confirmadas manualmente" in item.json()["notes"]
