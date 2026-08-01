from datetime import date, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from danfer_os.main import create_app
from danfer_os.services.technical_library import TechnicalLibrary


def commercial_client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(TechnicalLibrary(), data_dir=tmp_path))


def create_client(client: TestClient) -> dict:
    response = client.post(
        "/api/v1/commercial/clients",
        json={
            "name": "Metalúrgica Cliente",
            "document": "12.345.678/0001-90",
            "contact": "João",
            "payment_terms": "28/42 dias",
        },
    )
    assert response.status_code == 201
    return response.json()


def quote_payload(client_id: str) -> dict:
    return {
        "type": "venda",
        "client_id": client_id,
        "requester": "João",
        "valid_until": str(date.today() + timedelta(days=10)),
        "margin_percent": 25,
        "ipi_percent": 5,
        "cbs_percent": 0.9,
        "ibs_percent": 0.1,
        "prepared_by": "Diego Filippini",
        "items": [
            {
                "code": "DF-ORC-1",
                "description": "Suporte cortado e dobrado",
                "quantity": 2,
                "material": "Aço carbono",
                "thickness_mm": 3,
                "net_weight_kg": 10,
                "material_price_kg": 5,
                "utilization_percent": 80,
                "margin_percent": 30,
                "processes": [
                    {"name": "Corte laser", "minutes": 10, "hourly_rate": 180},
                    {"name": "Dobra", "minutes": 5, "hourly_rate": 120},
                ],
            }
        ],
    }


def test_quote_calculation_revision_status_and_pdf(tmp_path: Path) -> None:
    client = commercial_client(tmp_path)
    customer = create_client(client)
    created = client.post(
        "/api/v1/commercial/quotes", json=quote_payload(customer["id"])
    )
    assert created.status_code == 201
    quote = created.json()
    assert quote["number"].startswith("ORC-")
    assert quote["items"][0]["material_cost"] == 62.5
    assert quote["items"][0]["process_cost"] == 57.5
    assert quote["items"][0]["total_price"] == quote["items"][0]["unit_price"] * 2
    expected_ipi = round(quote["subtotal"] * 0.05, 2)
    assert quote["taxes"] == expected_ipi
    assert quote["total"] > quote["subtotal"]
    assert quote["gross_profit"] > 0

    updated = client.patch(
        f"/api/v1/commercial/quotes/{quote['id']}",
        json={"margin_percent": 30, "change_reason": "Negociação comercial"},
    )
    assert updated.status_code == 200
    assert updated.json()["revision"] == "B"
    assert len(
        client.get(f"/api/v1/commercial/quotes/{quote['id']}/revisions").json()
    ) == 1

    for next_status in ("enviado", "em_negociacao", "aprovado"):
        response = client.post(
            f"/api/v1/commercial/quotes/{quote['id']}/status",
            json={"status": next_status},
        )
        assert response.status_code == 200

    pdf = client.get(f"/api/v1/commercial/quotes/{quote['id']}/proposal.pdf")
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF")
    assert len(pdf.content) > 4000


def test_crm_search_and_duplicate_document(tmp_path: Path) -> None:
    client = commercial_client(tmp_path)
    create_client(client)
    assert len(client.get("/api/v1/commercial/clients", params={"q": "metal"}).json()) == 1
    duplicate = client.post(
        "/api/v1/commercial/clients",
        json={"name": "Outro", "document": "12.345.678/0001-90"},
    )
    assert duplicate.status_code == 409


def test_service_ignores_material_and_supports_weight_pricing_and_small_batch(tmp_path: Path) -> None:
    client = commercial_client(tmp_path)
    customer = create_client(client)
    payload = quote_payload(customer["id"])
    payload["type"] = "servico"
    payload["items"][0]["quantity"] = 2
    payload["items"][0]["processes"] = [
        {
            "name": "Calandra",
            "minutes": 0,
            "hourly_rate": 0,
            "pricing_mode": "peso",
            "weight_rate": 4.5,
        },
        {"name": "Dobra", "minutes": 10, "hourly_rate": 120},
    ]
    response = client.post("/api/v1/commercial/quotes", json=payload)
    assert response.status_code == 201
    item = response.json()["items"][0]
    assert item["material_cost"] == 0
    assert item["bend_estimated_minutes"] == 5
    assert item["process_cost"] == 72.5
    assert response.json()["taxes"] == 0
    assert response.json()["total"] == response.json()["subtotal"]


def test_cost_settings_keep_recovered_defaults(tmp_path: Path) -> None:
    client = commercial_client(tmp_path)
    settings = client.get("/api/v1/commercial/settings/costs").json()
    assert settings["default_margin_percent"] == 30
    assert settings["small_bend_batch_limit"] == 5
    assert settings["default_sheet_width_mm"] == 1200
    assert settings["default_sheet_length_mm"] == 3000
    assert settings["alternative_minimum_gain_percent"] == 8


def test_laser_uses_perimeter_piercings_and_preserves_additional_time(tmp_path: Path) -> None:
    client = commercial_client(tmp_path)
    customer = create_client(client)
    settings = client.get("/api/v1/commercial/settings/costs").json()
    settings.update({
        "default_laser_cutting_speed_mm_min": 1000,
        "default_laser_piercing_seconds": 2,
        "indirect_percent": 0,
    })
    assert client.put("/api/v1/commercial/settings/costs", json=settings).status_code == 200

    payload = quote_payload(customer["id"])
    payload["type"] = "servico"
    payload["items"][0].update({
        "cut_length_mm": 2000,
        "piercings": 30,
        "laser_additional_minutes": 1,
        "laser_additional_reason": "Furações pequenas e demoradas",
        "processes": [{"name": "Corte laser", "minutes": 99, "hourly_rate": 120}],
    })
    response = client.post("/api/v1/commercial/quotes", json=payload)
    assert response.status_code == 201
    item = response.json()["items"][0]
    assert item["laser_estimated_minutes"] == 3
    assert item["laser_additional_minutes"] == 1
    assert item["laser_additional_reason"] == "Furações pequenas e demoradas"
    assert item["process_cost"] == 8


def test_bend_time_table_and_additional_time_are_applied_per_piece(tmp_path: Path) -> None:
    client = commercial_client(tmp_path)
    customer = create_client(client)
    settings = client.get("/api/v1/commercial/settings/costs").json()
    settings.update({"indirect_percent": 0, "small_bend_batch_surcharge": 0})
    assert client.put("/api/v1/commercial/settings/costs", json=settings).status_code == 200
    assert client.get("/api/v1/commercial/quote-bend-times").json() == {
        "one": 10, "two": 5, "three": 4, "four_to_five": 3, "six_plus": 2.5,
    }

    for quantity, expected in ((1, 10), (2, 5), (3, 4), (5, 3), (6, 2.5)):
        payload = quote_payload(customer["id"])
        payload["type"] = "servico"
        payload["items"] = [{
            "code": f"DOB-{quantity}", "description": "Peça dobrada",
            "quantity": quantity, "bend_additional_minutes": 1,
            "bend_additional_reason": "Geometria com regulagem adicional",
            "processes": [{"name": "Dobra", "minutes": 99, "hourly_rate": 60}],
        }]
        response = client.post("/api/v1/commercial/quotes", json=payload)
        assert response.status_code == 201
        item = response.json()["items"][0]
        assert item["bend_estimated_minutes"] == expected
        assert item["bend_additional_minutes"] == 1
        assert item["process_cost"] == expected + 1

    payload = quote_payload(customer["id"])
    payload["type"] = "servico"
    payload["items"] = [{
        "code": "DOB-AJUSTE", "description": "Lote com ajuste manual", "quantity": 7,
        "bend_estimated_minutes": 2.8, "bend_additional_minutes": .7,
        "processes": [{"name": "Dobra", "minutes": 99, "hourly_rate": 60}],
    }]
    adjusted = client.post("/api/v1/commercial/quotes", json=payload).json()["items"][0]
    assert adjusted["bend_estimated_minutes"] == 2.8
    assert adjusted["process_cost"] == 3.5


def test_quote_uses_admin_defaults_when_sensitive_fields_are_omitted(tmp_path: Path) -> None:
    client = commercial_client(tmp_path)
    customer = create_client(client)
    settings = client.get("/api/v1/commercial/settings/costs").json()
    settings.update({
        "default_margin_percent": 35,
        "default_item_utilization_percent": 76,
        "default_ipi_percent": 7,
        "default_cbs_percent": 1.2,
        "default_ibs_percent": 0.3,
    })
    assert client.put("/api/v1/commercial/settings/costs", json=settings).status_code == 200
    payload = quote_payload(customer["id"])
    for field in ("margin_percent", "ipi_percent", "cbs_percent", "ibs_percent"):
        payload.pop(field)
    payload["items"][0].pop("margin_percent")
    payload["items"][0].pop("utilization_percent")
    response = client.post("/api/v1/commercial/quotes", json=payload)
    assert response.status_code == 201
    quote = response.json()
    assert quote["margin_percent"] == 35
    assert quote["ipi_percent"] == 7
    assert quote["items"][0]["utilization_percent"] == 76
    assert quote["taxes"] == round(quote["subtotal"] * .07, 2)


def test_sheet_selection_strip_costing_gap_and_inox_warning(tmp_path: Path) -> None:
    client = commercial_client(tmp_path)
    customer = create_client(client)
    payload = quote_payload(customer["id"])
    payload["items"] = [
        {
            "code": "ALT", "description": "Peça para chapa alternativa", "quantity": 6,
            "material": "Aço carbono", "thickness_mm": 3, "width_mm": 700,
            "length_mm": 750, "net_weight_kg": 4, "material_price_kg": 8,
        },
        {
            "code": "FAIXA", "description": "Peça pequena em inox", "quantity": 1,
            "material": "Aço inox", "thickness_mm": 2, "width_mm": 100,
            "length_mm": 100, "net_weight_kg": 1, "material_price_kg": 20,
        },
    ]
    response = client.post("/api/v1/commercial/quotes", json=payload)
    assert response.status_code == 201
    alternative, strip = response.json()["items"]
    assert alternative["costing_method"] == "nesting_real"
    assert alternative["nesting_calculation_source"] == "nesting_geometrico"
    assert alternative["selected_sheet_count"] >= 1
    assert 0 < alternative["calculated_utilization_percent"] <= 100
    assert strip["costing_method"] == "nesting_real"
    assert strip["nesting_calculation_source"] == "nesting_geometrico"
    assert any("riscos superficiais" in warning for warning in strip["costing_warnings"])


def test_omitted_material_price_is_resolved_from_protected_catalog(tmp_path: Path) -> None:
    client = commercial_client(tmp_path)
    customer = create_client(client)
    client.post("/api/v1/catalogs/materials", json={
        "erp_code": "CH-3", "description": "Aço catálogo", "thickness_mm": 3,
        "price_per_kg": 10,
    })
    payload = quote_payload(customer["id"])
    payload["items"][0].update({"material": "Aço catálogo", "thickness_mm": 3})
    payload["items"][0].pop("material_price_kg")
    response = client.post("/api/v1/commercial/quotes", json=payload)
    assert response.status_code == 201
    assert response.json()["items"][0]["material_price_kg"] == 10


def test_large_quote_keeps_20_item_margins_ncav_routes_and_single_delivery(tmp_path: Path) -> None:
    client = commercial_client(tmp_path)
    customer = create_client(client)
    delivery = str(date.today() + timedelta(days=25))
    items = [{
        "code": f"ITEM-{index:02d}", "description": f"Peça industrial {index:02d}",
        "quantity": index, "material": "Aço carbono", "thickness_mm": 3,
        "width_mm": 100 + index, "length_mm": 200 + index,
        "net_weight_kg": 2, "material_price_kg": 8,
        "nesting_mode": "forcar_ncav" if index % 4 == 0 else "automatico",
        "utilization_percent": 75, "margin_percent": 20 + index / 2,
        "processes": [
            {"name": "Corte Laser", "minutes": 4 + index, "hourly_rate": 0},
            {"name": "Dobra", "minutes": 2 + index / 2, "hourly_rate": 0},
        ],
    } for index in range(1, 21)]
    payload = quote_payload(customer["id"])
    payload.update({"expected_delivery": delivery, "items": items})
    response = client.post("/api/v1/commercial/quotes", json=payload)
    assert response.status_code == 201
    quote = response.json()
    assert len(quote["items"]) == 20
    assert quote["expected_delivery"] == delivery
    assert quote["items"][19]["margin_percent"] == 30
    assert quote["items"][3]["nesting_mode"] == "forcar_ncav"
    assert [process["minutes"] for process in quote["items"][0]["processes"]] == [5, 2.5]


def test_nesting_cost_precedence_is_engineering_plan_then_ncav_then_geometry(tmp_path: Path) -> None:
    client = commercial_client(tmp_path)
    customer = create_client(client)
    payload = quote_payload(customer["id"])
    common = {"quantity": 4, "thickness_mm": 3, "width_mm": 300,
              "length_mm": 400, "net_weight_kg": 10, "material_price_kg": 8}
    payload["items"] = [
        {**common, "code": "REAL", "description": "Plano aprovado", "material": "Aço A",
         "nesting_plan": {"reference": "ENG-PLANO-001", "sheet_width_mm": 1500,
                          "sheet_length_mm": 3000, "sheet_count": 2,
                          "utilization_percent": 92, "waste_percent": 8}},
        {**common, "code": "NCAV", "description": "NcAv manual", "material": "Aço B",
         "nesting_mode": "forcar_ncav", "utilization_percent": 65},
        {**common, "code": "AUTO", "description": "Nesting automático", "material": "Aço C",
         "nesting_mode": "automatico"},
    ]
    response = client.post("/api/v1/commercial/quotes", json=payload)
    assert response.status_code == 201
    real, ncav, automatic = response.json()["items"]
    assert real["nesting_calculation_source"] == "plano_engenharia"
    assert real["nesting_plan_reference"] == "ENG-PLANO-001"
    assert real["selected_sheet_count"] == 2
    assert real["calculated_utilization_percent"] == 92
    assert ncav["nesting_calculation_source"] == "ncav"
    assert ncav["calculated_utilization_percent"] == 65
    assert automatic["nesting_calculation_source"] == "nesting_geometrico"
    assert automatic["selected_sheet_count"] >= 1
    assert real["material_cost"] < ncav["material_cost"]


def test_customer_proposal_recalculates_margin_and_requires_admin_decision(tmp_path: Path) -> None:
    client = commercial_client(tmp_path)
    customer = create_client(client)
    settings = client.get("/api/v1/commercial/settings/costs").json()
    settings.update({"indirect_percent": 0, "minimum_effective_margin_percent": 45})
    assert client.put("/api/v1/commercial/settings/costs", json=settings).status_code == 200
    payload = quote_payload(customer["id"])
    payload.update({"type": "servico", "ipi_percent": 0})
    payload["items"] = [{
        "code": "NEG-1", "description": "Pedido negociado", "quantity": 1,
        "manual_unit_price": 3000,
        "processes": [{"name": "Terceiro", "minutes": 0, "hourly_rate": 0,
                       "pricing_mode": "fixo", "fixed_cost": 1500}],
    }]
    quote = client.post("/api/v1/commercial/quotes", json=payload).json()
    assert quote["total"] == 3000
    client.post(f"/api/v1/commercial/quotes/{quote['id']}/status", json={"status": "enviado"})

    submitted = client.post(f"/api/v1/commercial/quotes/{quote['id']}/customer-proposals", json={
        "proposed_total": 2700, "submitted_by": "Orçamentista",
        "notes": "Contraproposta recebida por telefone",
    })
    assert submitted.status_code == 201
    pending = submitted.json()
    proposal = pending["customer_proposals"][0]
    assert pending["status"] == "aguardando_aprovacao_administrativa"
    assert proposal["discount_value"] == 300
    assert proposal["discount_percent"] == 10
    assert proposal["effective_margin_percent"] == 44.44
    assert proposal["minimum_margin_percent"] == 45
    bypass = client.post(f"/api/v1/commercial/quotes/{quote['id']}/status", json={"status": "aprovado"})
    assert bypass.status_code == 409

    approved = client.post(
        f"/api/v1/commercial/quotes/{quote['id']}/customer-proposals/{proposal['id']}/decision",
        json={"approved": True, "decided_by": "Administrador", "reason": "Volume estratégico"},
    )
    assert approved.status_code == 200
    result = approved.json()
    assert result["status"] == "aprovado"
    assert result["total"] == 2700
    assert result["effective_margin_percent"] == 44.44
    assert result["customer_proposals"][0]["status"] == "aprovada"
    notifications = client.get("/api/v1/notifications", params={"role": "administrador"}).json()
    assert any("Margem efetiva: 44.44%" in item["message"] for item in notifications)
