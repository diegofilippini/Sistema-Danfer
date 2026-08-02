"""Gera uma base isolada com 20 orçamentos aprovados e rastreabilidade de custos."""

from __future__ import annotations

import argparse
import csv
import json
import shutil
from datetime import date, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from danfer_os.main import create_app


def checked(response):
    if not response.is_success:
        raise RuntimeError(f"{response.request.method} {response.request.url}: {response.status_code} {response.text}")
    return response.json()


def generate(destination: Path) -> dict[str, object]:
    if destination.exists():
        shutil.rmtree(destination)
    data_dir = destination / "data"
    data_dir.mkdir(parents=True)
    client = TestClient(create_app(data_dir=data_dir))
    rows: list[dict[str, object]] = []
    materials = ["Aço carbono", "Aço inox 304", "Alumínio 5052", "Aço carbono", "Aço inox 430"]

    for index in range(1, 21):
        code = f"HOM-{index:03d}"
        customer = checked(client.post("/api/v1/commercial/clients", json={
            "name": f"Cliente Homologação {index:02d}", "document": f"99000000000{index:02d}",
            "contact": f"Comprador {index:02d}", "email": f"cliente{index:02d}@example.test",
            "payment_terms": ["28 dias", "28/56 dias", "à vista"][index % 3],
        }))
        product = checked(client.post("/api/v1/technical-library", json={
            "danfer_code": code, "title": f"Conjunto industrial {index:02d}", "category": "desenho",
            "file_url": f"https://example.test/desenhos/{code}.dxf",
        }))
        component = checked(client.post("/api/v1/technical-library", json={
            "danfer_code": f"{code}-C", "title": f"Componente {index:02d}", "category": "desenho",
            "file_url": f"https://example.test/desenhos/{code}-C.dxf", "material": materials[index % len(materials)],
            "thickness_mm": [1.5, 3.0, 6.35, 9.5, 12.7][index % 5],
        }))
        checked(client.post("/api/v1/boms", json={
            "product_id": product["id"], "components": [{"part_id": component["id"], "quantity": 1 + index % 3}],
        }))
        quote_type = "servico" if index % 5 == 0 else "venda"
        quantity = 1 + index % 8
        quote = checked(client.post("/api/v1/commercial/quotes", json={
            "type": quote_type, "billing_unit": "df" if index % 2 else "danfer",
            "client_id": customer["id"], "requester": f"Comprador {index:02d}",
            "valid_until": str(date.today() + timedelta(days=10)),
            "expected_delivery": str(date.today() + timedelta(days=12 + index)),
            "margin_percent": 25 + index % 11, "ipi_percent": 5 if quote_type == "venda" else 0,
            "cbs_percent": 0.9, "ibs_percent": 0.1, "freight_value": 25 * (index % 4),
            "items": [{
                "code": code, "description": f"Conjunto industrial homologação {index:02d}",
                "quantity": quantity, "material": materials[index % len(materials)],
                "thickness_mm": [1.5, 3.0, 6.35, 9.5, 12.7][index % 5],
                "width_mm": 180 + 37 * index, "length_mm": 260 + 61 * index,
                "net_weight_kg": 1.8 + index * 0.72, "material_price_kg": 7.2 + (index % 5) * 4.1,
                "cut_length_mm": 850 + index * 190, "piercings": 4 + index,
                "utilization_percent": 22 + (index * 7) % 69,
                "processes": [
                    {"name": "Corte Laser", "minutes": 4 + index * 0.8, "hourly_rate": 180},
                    {"name": "Dobra", "minutes": 3 + index * 0.45, "hourly_rate": 135},
                ],
            }], "observations": "Cenário sintético de homologação; não representa pedido real.",
        }))
        for status in ("enviado", "aprovado"):
            quote = checked(client.post(f"/api/v1/commercial/quotes/{quote['id']}/status", json={"status": status}))
        erp = checked(client.post(f"/api/v1/workflows/quotes/{quote['id']}/erp-order"))
        order = checked(client.post(f"/api/v1/workflows/quotes/{quote['id']}/production-orders"))[0]
        factor = 0.88 + (index % 7) * 0.04
        checked(client.post(f"/api/v1/pcp/orders/{order['id']}/logs", json={
            "type": "material", "quantity": 1, "unit_cost": round(order["estimated_material_cost"] * factor, 2),
            "employee": "Homologação", "notes": "Consumo sintético controlado",
        }))
        checked(client.post(f"/api/v1/pcp/orders/{order['id']}/logs", json={
            "type": "operacao", "amount": round(order["estimated_process_cost"] * factor, 2),
            "employee": "Homologação", "notes": "Apontamento sintético controlado",
        }))
        if index % 4 == 0:
            checked(client.post("/api/v1/quality", json={
                "type": "retrabalho", "production_order": order["number"],
                "description": "Ajuste dimensional de homologação", "cost": 12.5 * index,
            }))
        costs = checked(client.get(f"/api/v1/pcp/orders/{order['id']}/costs"))
        rows.append({
            "cenario": index, "orcamento": quote["number"], "status": quote["status"], "tipo": quote["type"],
            "unidade": quote["billing_unit"], "cliente": customer["name"], "material": quote["items"][0]["material"],
            "metodo_custeio": quote["items"][0]["costing_method"], "quantidade": quantity,
            "preco_total": quote["total"], "custo_orcado": quote["total_cost"],
            "custo_pcp_estimado": costs["estimated_total_cost"], "custo_real": costs["actual_total_cost"],
            "variacao_valor": costs["variance_value"], "variacao_percentual": costs["variance_percent"],
            "evento_erp": erp["id"], "ordem_producao": order["number"],
            "alertas_custeio": " | ".join(quote["items"][0]["costing_warnings"]),
        })

    with (destination / "relatorio_20_orcamentos.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    summary = {
        "generated_on": str(date.today()), "approved_quotes": len(rows), "erp_events": len(rows),
        "production_orders": len(rows), "total_sales_value": round(sum(float(row["preco_total"]) for row in rows), 2),
        "total_estimated_cost": round(sum(float(row["custo_pcp_estimado"]) for row in rows), 2),
        "total_actual_cost": round(sum(float(row["custo_real"]) for row in rows), 2),
        "dataset": "sintético e isolado; não usar como dado fiscal ou pedido real",
    }
    (destination / "resumo.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    assert all(row["status"] == "aprovado" for row in rows)
    assert len(rows) == 20
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    print(json.dumps(generate(args.destination.resolve()), ensure_ascii=False, indent=2))
