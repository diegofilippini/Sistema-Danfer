from fastapi.testclient import TestClient

from danfer_os.main import create_app


def test_health() -> None:
    response = TestClient(create_app()).get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_web_interface() -> None:
    client = TestClient(create_app())
    response = client.get("/")

    assert response.status_code == 200
    assert "Danfer Industrial OS" in response.text
    assert "danfer-theme" in response.text
    script = client.get("/app.js").text
    styles = client.get("/styles-extra.css").text
    assert 'order=["auto","light","dark"]' in script
    assert 'data-theme="dark"' in styles
    assert "prefers-color-scheme: dark" in response.text
    assert "print-current-view" in script
    assert "showDirectoryPicker" in script
    assert "saveQuotePdf" in script
    assert "openGlobalSearchResult" in script
    assert "printProductionOrders" in script
    assert "print-selected-ops" in script
    assert "productionProgressChart" in script
    assert 'item.percent<=20?"red":item.percent<70?"yellow":"green"' in script
    assert "loadDeliveryBoard" in script
    assert "push-delivery-board" in response.text
    assert "print-delivery-board" in response.text
    assert "renderOperationCostSettings" in script
    assert "operation-cost-settings-card" in script
    assert "renderMaterialCostSettings" in script
    assert "material-cost-settings-card" in script
    assert "@media print" in styles
