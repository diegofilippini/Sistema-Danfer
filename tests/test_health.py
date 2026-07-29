from fastapi.testclient import TestClient

from danfer_os.main import create_app


def test_health_endpoint() -> None:
    response = TestClient(create_app()).get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "danfer-industrial-os",
    }

