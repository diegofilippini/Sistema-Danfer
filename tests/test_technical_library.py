from fastapi.testclient import TestClient

from danfer_os.main import create_app
from danfer_os.services.technical_library import TechnicalLibrary


def payload(**changes: object) -> dict[str, object]:
    data: dict[str, object] = {
        "danfer_code": "DF-001",
        "title": "Manual da dobradeira",
        "category": "manual",
        "description": "Operação e manutenção preventiva",
        "tags": ["Máquina", " manutenção ", "máquina"],
        "revision": "B",
        "file_url": "https://docs.danfer.com/dobradeira.pdf",
    }
    data.update(changes)
    return data


def test_document_lifecycle() -> None:
    client = TestClient(create_app(TechnicalLibrary()))
    created = client.post("/api/v1/technical-library", json=payload())

    assert created.status_code == 201
    document = created.json()
    assert document["tags"] == ["manutenção", "máquina"]

    fetched = client.get(f"/api/v1/technical-library/{document['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["title"] == "Manual da dobradeira"

    updated = client.patch(
        f"/api/v1/technical-library/{document['id']}",
        json={"revision": "C", "title": "Manual revisado da dobradeira"},
    )
    assert updated.status_code == 200
    assert updated.json()["revision"] == "C"

    deleted = client.delete(f"/api/v1/technical-library/{document['id']}")
    assert deleted.status_code == 204
    assert client.get(f"/api/v1/technical-library/{document['id']}").status_code == 404


def test_search_and_filters() -> None:
    client = TestClient(create_app(TechnicalLibrary()))
    client.post("/api/v1/technical-library", json=payload())
    client.post(
        "/api/v1/technical-library",
        json=payload(
            danfer_code="DF-002",
            title="Norma de soldagem",
            category="norma",
            description="Parâmetros MIG",
            tags=["solda"],
        ),
    )

    search = client.get("/api/v1/technical-library", params={"q": "MIG"})
    assert search.status_code == 200
    assert search.json()["total"] == 1
    assert search.json()["items"][0]["title"] == "Norma de soldagem"

    filtered = client.get(
        "/api/v1/technical-library",
        params={"category": "manual", "tag": "máquina"},
    )
    assert filtered.status_code == 200
    assert filtered.json()["total"] == 1


def test_validation_and_missing_document() -> None:
    client = TestClient(create_app(TechnicalLibrary()))

    assert client.post(
        "/api/v1/technical-library", json=payload(title="x")
    ).status_code == 422
    assert client.get(
        "/api/v1/technical-library/00000000-0000-0000-0000-000000000000"
    ).status_code == 404
