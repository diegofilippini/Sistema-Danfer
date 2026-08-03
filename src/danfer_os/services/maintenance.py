from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from threading import RLock


CRM_DEFAULTS = {
    "paymentTerms": [
        {"codigo": "AVISTA", "descricao": "À vista", "ativo": "Sim"},
        {"codigo": "28DDL", "descricao": "28 dias", "ativo": "Sim"},
        {"codigo": "28_35_42DDL", "descricao": "28/35/42 dias", "ativo": "Sim"},
        {"codigo": "30_60DDL", "descricao": "30/60 dias", "ativo": "Sim"},
    ],
    "laserParameters": [{"parametro": "Margem adicional no tempo de laser", "valor": 50, "unidade": "%", "ativo": "Sim"}],
    "crmStages": [
        {"ordem": 1, "nome": "Em elaboração", "cor": "#64748b", "probabilidade": 10, "prazoDias": 0, "tipo": "Aberta", "exigeMotivo": "Não", "ativo": "Sim"},
        {"ordem": 2, "nome": "Enviado ao cliente", "cor": "#2563eb", "probabilidade": 25, "prazoDias": 2, "tipo": "Aberta", "exigeMotivo": "Não", "ativo": "Sim"},
        {"ordem": 3, "nome": "Em negociação", "cor": "#7c3aed", "probabilidade": 50, "prazoDias": 5, "tipo": "Aberta", "exigeMotivo": "Não", "ativo": "Sim"},
        {"ordem": 4, "nome": "Revisão solicitada", "cor": "#d97706", "probabilidade": 60, "prazoDias": 3, "tipo": "Aberta", "exigeMotivo": "Não", "ativo": "Sim"},
        {"ordem": 5, "nome": "Aprovado parcialmente", "cor": "#0891b2", "probabilidade": 80, "prazoDias": 2, "tipo": "Aberta", "exigeMotivo": "Não", "ativo": "Sim"},
        {"ordem": 6, "nome": "Aprovado", "cor": "#16a34a", "probabilidade": 100, "prazoDias": 0, "tipo": "Ganha", "exigeMotivo": "Não", "ativo": "Sim"},
        {"ordem": 7, "nome": "Perdido", "cor": "#dc2626", "probabilidade": 0, "prazoDias": 0, "tipo": "Perdida", "exigeMotivo": "Sim", "ativo": "Sim"},
    ],
    "crmActivities": [
        {"codigo": "LIG", "descricao": "Ligação", "prazoProximo": 2, "exigeObservacao": "Não", "ativo": "Sim"},
        {"codigo": "WPP", "descricao": "WhatsApp", "prazoProximo": 2, "exigeObservacao": "Não", "ativo": "Sim"},
        {"codigo": "EMAIL", "descricao": "E-mail", "prazoProximo": 3, "exigeObservacao": "Não", "ativo": "Sim"},
        {"codigo": "VISITA", "descricao": "Visita comercial", "prazoProximo": 5, "exigeObservacao": "Sim", "ativo": "Sim"},
        {"codigo": "FOLLOW", "descricao": "Cobrança de retorno", "prazoProximo": 3, "exigeObservacao": "Não", "ativo": "Sim"},
    ],
    "crmLossReasons": [
        {"codigo": "PRECO", "descricao": "Preço", "categoria": "Comercial", "exigeJustificativa": "Não", "ativo": "Sim"},
        {"codigo": "PRAZO", "descricao": "Prazo de entrega", "categoria": "Operacional", "exigeJustificativa": "Não", "ativo": "Sim"},
        {"codigo": "CONCOR", "descricao": "Concorrente escolhido", "categoria": "Mercado", "exigeJustificativa": "Sim", "ativo": "Sim"},
        {"codigo": "CANCEL", "descricao": "Projeto cancelado", "categoria": "Cliente", "exigeJustificativa": "Não", "ativo": "Sim"},
        {"codigo": "SEMRET", "descricao": "Sem retorno", "categoria": "Relacionamento", "exigeJustificativa": "Não", "ativo": "Sim"},
    ],
    "crmRules": [
        {"regra": "Primeiro contato após envio", "valor": 2, "unidade": "dias úteis", "ativo": "Sim"},
        {"regra": "Alerta amarelo sem movimentação", "valor": 4, "unidade": "dias", "ativo": "Sim"},
        {"regra": "Alerta vermelho sem movimentação", "valor": 8, "unidade": "dias", "ativo": "Sim"},
        {"regra": "Margem mínima sem aprovação", "valor": 30, "unidade": "%", "ativo": "Sim"},
    ],
}


class MaintenanceService:
    def __init__(self, storage_path: Path | None = None) -> None:
        self._storage_path = storage_path
        self._lock = RLock()
        seed_path = Path(__file__).parents[1] / "v051_maintenance.json"
        self._data = json.loads(seed_path.read_text(encoding="utf-8"))
        self._data.update({key: deepcopy(value) for key, value in CRM_DEFAULTS.items()})
        if storage_path and storage_path.exists():
            saved = json.loads(storage_path.read_text(encoding="utf-8"))
            self._data.update(saved)
        # Correções aprovadas na consolidação: a densidade 780 era erro de
        # digitação e existem somente duas chapas padrão oficiais.
        for material in self._data.get("materials", []):
            if float(material.get("densidade", 0)) < 5000:
                material["densidade"] = 7850
        self._data["standardSheets"] = [
            {"codigo": "CH1200", "largura": 1200.0, "comprimento": 3000.0},
            {"codigo": "CH1500", "largura": 1500.0, "comprimento": 3000.0},
        ]

    def categories(self) -> dict[str, int]:
        return {key: len(value) for key, value in self._data.items() if isinstance(value, list)}

    def get(self, category: str) -> list[dict]:
        value = self._data.get(category)
        if not isinstance(value, list):
            raise KeyError(category)
        return deepcopy(value)

    def replace(self, category: str, rows: list[dict]) -> list[dict]:
        if category not in self.categories():
            raise KeyError(category)
        with self._lock:
            self._data[category] = deepcopy(rows)
            self._save()
        return deepcopy(rows)

    def reset(self) -> None:
        with self._lock:
            seed_path = Path(__file__).parents[1] / "v051_maintenance.json"
            self._data = json.loads(seed_path.read_text(encoding="utf-8"))
            self._data.update({key: deepcopy(value) for key, value in CRM_DEFAULTS.items()})
            self._save()

    def _save(self) -> None:
        if not self._storage_path:
            return
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._storage_path.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")
