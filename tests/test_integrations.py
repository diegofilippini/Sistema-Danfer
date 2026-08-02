from fastapi.testclient import TestClient

from danfer_os.main import create_app
from danfer_os.services.technical_library import TechnicalLibrary


def client_with_part() -> TestClient:
    client = TestClient(create_app(TechnicalLibrary()))
    response = client.post(
        "/api/v1/technical-library",
        json={
            "danfer_code": "DF-100",
            "customer_code": "CLI-100",
            "title": "Suporte",
            "category": "desenho",
            "file_url": "https://docs.danfer.com/DF-100.pdf",
        },
    )
    assert response.status_code == 201
    return client


def test_api_order_import_is_idempotent_and_creates_erp_event() -> None:
    client = client_with_part()
    payload = {
        "source": "erp-teste",
        "external_id": "PED-42",
        "customer": "Cliente ABC",
        "items": [{"customer_code": "CLI-100", "quantity": 5}],
    }
    imported = client.post("/api/v1/integrations/orders", json=payload)
    assert imported.status_code == 201
    assert imported.json()["status"] == "importado"
    assert client.post("/api/v1/integrations/orders", json=payload).status_code == 409

    events = client.get("/api/v1/integrations/erp/events").json()
    assert len(events) == 1
    acknowledged = client.post(
        f"/api/v1/integrations/erp/events/{events[0]['id']}/ack"
    )
    assert acknowledged.json()["status"] == "enviado"
    assert acknowledged.json()["attempts"] == 1


def test_xml_import_reports_unknown_catalog_code() -> None:
    client = client_with_part()
    xml = """<order source="xml-cliente">
      <external_id>9001</external_id><customer>Cliente XYZ</customer>
      <items><item><code>DESCONHECIDO</code><quantity>2</quantity></item></items>
    </order>"""
    response = client.post(
        "/api/v1/integrations/orders/xml",
        content=xml,
        headers={"Content-Type": "application/xml"},
    )
    assert response.status_code == 201
    assert response.json()["status"] == "com_advertencias"
    assert len(response.json()["warnings"]) == 1


def test_invalid_xml_is_rejected() -> None:
    client = client_with_part()
    response = client.post(
        "/api/v1/integrations/orders/xml",
        content="<order>",
        headers={"Content-Type": "application/xml"},
    )
    assert response.status_code == 422
