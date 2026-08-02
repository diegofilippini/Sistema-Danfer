from __future__ import annotations

from datetime import date, timedelta
import json
from pathlib import Path
import random

from fastapi.testclient import TestClient

from danfer_os.main import create_app


SEED = 550200
LOT = "TESTE-ESTRUTURAL-200-20260802"
OPERATIONS = {
    "venda_industrializacao": "venda",
    "venda_uso_consumo": "venda",
    "industrializacao": "servico",
    "industrializacao_material_terceiros": "servico",
}
MATERIALS = [
    ("Aço carbono SAE 1020", 7.85, [0.9, 1.2, 1.5, 2.0, 3.0, 4.75, 6.35, 8.0, 9.5, 12.7]),
    ("Aço inox 304", 24.50, [1.0, 1.2, 1.5, 2.0, 3.0, 4.75, 6.35]),
    ("Alumínio 5052", 29.80, [1.0, 1.5, 2.0, 3.0, 4.0, 6.0]),
]
PROCESSES = [
    ("Corte Laser", 360.0), ("Dobra", 260.0), ("Calandra", 240.0),
    ("Solda", 160.0), ("Guilhotina", 200.0),
]


def client_payload(index: int) -> dict:
    return {
        "name": f"Cliente Teste Estrutural {index:02d}",
        "erp_code": f"TST-{index:04d}",
        "document": f"99.999.{index:03d}/0001-{index % 97:02d}",
        "contact": f"Comprador {index:02d}",
        "email": f"compras{index:02d}@teste.local",
        "phone": f"(54) 9999-{index:04d}",
        "payment_terms": random.choice(["À vista", "28 dias", "28/35 dias", "30/45/60 dias"]),
        "freight_type": random.choice(["FOB", "CIF"]),
        "notes": LOT,
    }


def item_payload(operation: str, quote_index: int, item_index: int) -> dict:
    material, price_kg, thicknesses = random.choice(MATERIALS)
    thickness = random.choice(thicknesses)
    quantity = random.choice([1, 2, 3, 5, 8, 10, 15, 20, 25, 40, 60, 100])
    width = random.randrange(80, 1250, 10)
    length = random.randrange(100, 2850, 10)
    density = 2.70 if "Alumínio" in material else 7.90 if "inox" in material else 7.85
    weight = round(width * length * thickness * density / 1_000_000, 3)
    selected_processes = [PROCESSES[0], *random.sample(PROCESSES[1:], random.randint(0, 3))]
    processes = []
    for name, rate in selected_processes:
        minutes = round(random.uniform(1.5, 35), 2)
        processes.append({"name": name, "minutes": minutes, "hourly_rate": rate,
                          "external_cost": round(random.choice([0, 0, 0, random.uniform(10, 90)]), 2)})
    is_service = operation in {"industrializacao", "industrializacao_material_terceiros"}
    nesting_mode = random.choice(["automatico", "automatico", "forcar_ncav"])
    utilization = round(random.uniform(58, 94), 2) if nesting_mode == "forcar_ncav" else None
    cut_length = round(2 * (width + length) * random.uniform(1.0, 2.8), 2)
    laser_minutes = round(cut_length / random.uniform(1800, 6000) + random.randint(2, 40) / 60, 2)
    return {
        "code": f"{operation[:3].upper()}-{quote_index:03d}-{item_index:02d}",
        "description": random.choice(["Suporte", "Tampa", "Base", "Reforço", "Flange", "Conjunto", "Perfil", "Chapa recortada"])
                       + f" teste {quote_index:03d}/{item_index:02d}",
        "quantity": quantity, "unit": "un", "material": material,
        "thickness_mm": thickness, "width_mm": width, "length_mm": length,
        "net_weight_kg": weight,
        "material_price_kg": 0 if is_service else price_kg,
        "cut_length_mm": cut_length, "piercings": random.randint(2, 55),
        "laser_estimated_minutes": laser_minutes,
        "laser_additional_minutes": round(random.choice([0, 0, random.uniform(0.5, 8)]), 2),
        "laser_additional_reason": "Furações demoradas" if random.random() < 0.25 else "",
        "bend_estimated_minutes": round(random.uniform(0, 12), 2) if any(p[0] == "Dobra" for p in selected_processes) else 0,
        "bend_additional_minutes": round(random.choice([0, 0, random.uniform(0.5, 6)]), 2),
        "bend_additional_reason": "Geometria complexa" if random.random() < 0.2 else "",
        "nesting_mode": nesting_mode, "utilization_percent": utilization,
        "processes": processes, "margin_percent": round(random.uniform(22, 42), 2),
        "notes": f"Item aleatório do lote {LOT}",
    }


def main() -> None:
    random.seed(SEED)
    root = Path(__file__).resolve().parents[1]
    api = TestClient(create_app(data_dir=root / "data"))
    clients = api.get("/api/v1/commercial/clients").json()
    by_name = {row["name"]: row for row in clients}
    test_clients = []
    for index in range(1, 21):
        payload = client_payload(index)
        existing = by_name.get(payload["name"])
        if existing is None:
            response = api.post("/api/v1/commercial/clients", json=payload)
            response.raise_for_status()
            existing = response.json()
        test_clients.append(existing)

    existing_quotes = api.get("/api/v1/commercial/quotes").json()
    existing_keys = {row.get("internal_notes", "") for row in existing_quotes}
    generated = []
    for operation, quote_type in OPERATIONS.items():
        for index in range(1, 51):
            key = f"{LOT}|{operation}|{index:03d}"
            existing = next((row for row in existing_quotes if row.get("internal_notes") == key), None)
            if existing is not None:
                generated.append(existing)
                continue
            client = random.choice(test_clients)
            item_count = random.randint(1, 8)
            valid_until = date.today() + timedelta(days=random.choice([10, 15, 30]))
            payload = {
                "type": quote_type, "commercial_operation": operation,
                "billing_unit": random.choice(["danfer", "df"]), "client_id": client["id"],
                "requester": client["contact"], "prepared_by": "Analista de Custos — lote de testes",
                "valid_until": str(valid_until),
                "expected_delivery": str(valid_until + timedelta(days=random.randint(5, 35))),
                "payment_terms": client["payment_terms"],
                "freight_type": random.choice(["FOB", "CIF"]),
                "nature_operation": "Venda de produção" if quote_type == "venda" else "Industrialização",
                "margin_percent": round(random.uniform(25, 38), 2),
                "ipi_percent": random.choice([0, 3.25, 5, 9.75]) if quote_type == "venda" else 0,
                "cbs_percent": 0.9, "ibs_percent": 0.1,
                "freight_value": round(random.choice([0, 0, random.uniform(50, 650)]), 2),
                "discount_value": 0,
                "items": [item_payload(operation, index, item_index)
                          for item_index in range(1, item_count + 1)],
                "observations": "Orçamento genérico para comparação estrutural com a planilha atual.",
                "internal_notes": key,
            }
            response = api.post("/api/v1/commercial/quotes", json=payload)
            if response.status_code != 201:
                raise RuntimeError(f"Falha em {key}: {response.status_code} {response.text}")
            generated.append(response.json())

    clients_by_id = {row["id"]: row for row in api.get("/api/v1/commercial/clients").json()}
    report = {
        "lot": LOT, "seed": SEED, "generated_count": len(generated),
        "quotes": [{**quote, "client_name": clients_by_id[quote["client_id"]]["name"],
                    "client_erp_code": clients_by_id[quote["client_id"]].get("erp_code", "")}
                   for quote in generated],
    }
    output = root / "output" / "test-quotes-200.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    counts = {operation: sum(q["commercial_operation"] == operation for q in generated)
              for operation in OPERATIONS}
    print(json.dumps({"total": len(generated), "counts": counts, "report": str(output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
