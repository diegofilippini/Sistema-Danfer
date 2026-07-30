from fastapi.testclient import TestClient

from danfer_os.main import create_app


def test_health() -> None:
    response = TestClient(create_app()).get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_web_interface() -> None:
    response = TestClient(create_app()).get("/")

    assert response.status_code == 200
    assert "Danfer Industrial OS" in response.text
