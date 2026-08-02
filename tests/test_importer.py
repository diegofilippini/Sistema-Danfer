import base64
import io

from fastapi.testclient import TestClient

from danfer_os.main import create_app
from danfer_os.services.technical_library import TechnicalLibrary


def upload_csv(client: TestClient) -> dict:
    content = "Código;Descrição;Qtd;Material\nDF-1;Suporte;10;Aço\n;Inválido;0;Inox\n"
    response = client.post(
        "/api/v1/imports/preview",
        json={
            "filename": "pedido.csv",
            "content_base64": base64.b64encode(content.encode()).decode(),
        },
    )
    assert response.status_code == 201
    return response.json()


def test_csv_preview_mapping_validation_and_history() -> None:
    client = TestClient(create_app(TechnicalLibrary()))
    preview = upload_csv(client)
    assert preview["columns"] == ["Código", "Descrição", "Qtd", "Material"]
    assert preview["total_rows"] == 2

    configuration = {
        "mappings": [
            {"source_column": "Código", "target_field": "codigo_danfer"},
            {"source_column": "Descrição", "target_field": "descricao"},
            {"source_column": "Qtd", "target_field": "quantidade"},
            {"source_column": "Material", "target_field": "material"},
        ],
        "fixed_values": {"cliente": "Cliente ABC", "unidade": "un"},
    }
    validation = client.post(
        f"/api/v1/imports/{preview['session_id']}/validate",
        json=configuration,
    )
    assert validation.status_code == 200
    result = validation.json()
    assert result["valid_rows"] == 1
    assert result["invalid_rows"] == 1
    assert result["normalized_rows"][0]["quantidade"] == 10

    finished = client.post(
        f"/api/v1/imports/{preview['session_id']}/finish",
        params={"customer": "Cliente ABC"},
        json=result,
    )
    assert finished.status_code == 200
    assert finished.json()["total_rows"] == 2
    assert len(client.get("/api/v1/imports/history").json()) == 1


def test_import_profile_and_duplicate_mapping_validation() -> None:
    client = TestClient(create_app(TechnicalLibrary()))
    configuration = {
        "mappings": [{"source_column": "Item", "target_field": "codigo_cliente"}],
        "fixed_values": {"quantidade": 1},
    }
    created = client.post(
        "/api/v1/imports/profiles",
        json={
            "customer": "Cliente ABC",
            "name": "Tabela padrão",
            "configuration": configuration,
        },
    )
    assert created.status_code == 201
    assert len(client.get("/api/v1/imports/profiles", params={"customer": "Cliente ABC"}).json()) == 1

    preview = upload_csv(client)
    invalid = client.post(
        f"/api/v1/imports/{preview['session_id']}/validate",
        json={
            "mappings": [
                {"source_column": "Código", "target_field": "descricao"},
                {"source_column": "Material", "target_field": "descricao"},
            ]
        },
    )
    assert invalid.status_code == 422


def test_excel_xlsx_and_xls_preview() -> None:
    client = TestClient(create_app(TechnicalLibrary()))

    from openpyxl import Workbook
    xlsx = io.BytesIO()
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Pedido"
    sheet.append(["Código", "Qtd"])
    sheet.append(["DF-X", 3])
    workbook.save(xlsx)
    xlsx_response = client.post(
        "/api/v1/imports/preview",
        json={
            "filename": "pedido.xlsx",
            "sheet": "Pedido",
            "content_base64": base64.b64encode(xlsx.getvalue()).decode(),
        },
    )
    assert xlsx_response.status_code == 201
    assert xlsx_response.json()["sheets"] == ["Pedido"]
    assert xlsx_response.json()["rows"] == [["DF-X", "3"]]

    import xlwt
    xls = io.BytesIO()
    old_workbook = xlwt.Workbook()
    old_sheet = old_workbook.add_sheet("Itens")
    for column, value in enumerate(("Código", "Qtd")):
        old_sheet.write(0, column, value)
    old_sheet.write(1, 0, "DF-L")
    old_sheet.write(1, 1, 4)
    old_workbook.save(xls)
    xls_response = client.post(
        "/api/v1/imports/preview",
        json={
            "filename": "pedido.xls",
            "sheet": "Itens",
            "content_base64": base64.b64encode(xls.getvalue()).decode(),
        },
    )
    assert xls_response.status_code == 201
    assert xls_response.json()["sheets"] == ["Itens"]
    assert xls_response.json()["rows"][0][0] == "DF-L"
