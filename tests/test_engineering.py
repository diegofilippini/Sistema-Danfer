import base64
import io
from pathlib import Path

import ezdxf
from fastapi.testclient import TestClient

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
