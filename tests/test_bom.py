from fastapi.testclient import TestClient

from danfer_os.main import create_app
from danfer_os.services.technical_library import TechnicalLibrary


def create_part(client: TestClient, code: str) -> str:
    response = client.post(
        "/api/v1/technical-library",
        json={
            "danfer_code": code,
            "title": f"Peça {code}",
            "category": "desenho",
            "file_url": f"https://docs.danfer.com/{code}.pdf",
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_multilevel_bom_explosion() -> None:
    client = TestClient(create_app(TechnicalLibrary()))
    product = create_part(client, "KIT-001")
    assembly = create_part(client, "CJ-001")
    raw = create_part(client, "MP-001")

    child = client.post(
        "/api/v1/boms",
        json={
            "product_id": assembly,
            "status": "ativa",
            "components": [{"part_id": raw, "quantity": 2, "scrap_percent": 10}],
        },
    )
    assert child.status_code == 201
    root = client.post(
        "/api/v1/boms",
        json={
            "product_id": product,
            "status": "ativa",
            "components": [{"part_id": assembly, "quantity": 3}],
        },
    )
    assert root.status_code == 201

    explosion = client.get(
        f"/api/v1/boms/{root.json()['id']}/explosion",
        params={"quantity": 2},
    )
    assert explosion.status_code == 200
    assert explosion.json()[0]["quantity"] == 6
    assert explosion.json()[1]["quantity"] == 13.2
    assert explosion.json()[1]["level"] == 2


def test_bom_rejects_self_reference_and_unknown_parts() -> None:
    client = TestClient(create_app(TechnicalLibrary()))
    product = create_part(client, "KIT-002")

    self_reference = client.post(
        "/api/v1/boms",
        json={"product_id": product, "components": [{"part_id": product, "quantity": 1}]},
    )
    assert self_reference.status_code == 422


def test_bom_is_persisted_between_application_restarts(tmp_path) -> None:
    first = TestClient(create_app(data_dir=tmp_path))
    product = create_part(first, "KIT-PERSIST")
    raw = create_part(first, "MP-PERSIST")
    created = first.post(
        "/api/v1/boms",
        json={"product_id": product, "status": "ativa", "components": [{"part_id": raw, "quantity": 4}]},
    )
    assert created.status_code == 201

    second = TestClient(create_app(data_dir=tmp_path))
    listed = second.get("/api/v1/boms")
    assert listed.status_code == 200
    assert listed.json()[0]["id"] == created.json()["id"]
    assert listed.json()[0]["components"][0]["quantity"] == 4
