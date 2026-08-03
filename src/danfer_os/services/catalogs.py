from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from threading import RLock
from uuid import UUID

from danfer_os.models.catalogs import (
    Material, MaterialCreate, MaterialUpdate, Operation, OperationUpdate,
    PriceTableChange, PriceTableImportResult, PriceTableMapping,
    RoutingTemplate, RoutingTemplateCreate, RoutingTemplateStep, RoutingTemplateUpdate,
)
from danfer_os.models.importer import FileUpload, ImportPreview
from danfer_os.services.importer import ImporterService
from danfer_os.services.technical_library import TechnicalLibrary


ERP_OPERATIONS = {
    2: "Corte Laser",
    3: "Guilhotina",
    4: "Plasma",
    5: "Dobra",
    6: "Calandra",
    7: "Prensa",
    8: "Chanfro",
    9: "Solda",
    60: "Calandra por peso",
}

DEFAULT_OPERATION_COSTS = {
    2: {"hourly_rate": 360}, 3: {"hourly_rate": 200},
    5: {"hourly_rate": 260}, 6: {"hourly_rate": 240},
    9: {"hourly_rate": 160},
    60: {"pricing_mode": "peso", "weight_rate": 1.80},
}

DEFAULT_ROUTING_TEMPLATES = (
    ("Laser", [(2, "Corte Laser", 0)]),
    ("Laser + Dobra", [(2, "Corte Laser", 0), (5, "Dobra", 5)]),
    ("Laser + Dobra + Calandra", [(2, "Corte Laser", 0), (5, "Dobra", 5), (6, "Calandra", 8)]),
    ("Corte + Dobra", [(2, "Corte Laser", 0), (5, "Dobra", 5)]),
    ("Corte + Calandra", [(2, "Corte Laser", 5), (6, "Calandra", 8)]),
    ("Corte + Dobra + Solda", [(2, "Corte Laser", 5), (5, "Dobra", 5), (9, "Solda", 10)]),
    ("Guilhotina + Dobra", [(3, "Guilhotina", 4), (5, "Dobra", 5)]),
    ("Plasma + Chanfro + Solda", [(4, "Plasma", 8), (8, "Chanfro", 6), (9, "Solda", 10)]),
)


class CatalogNotFoundError(LookupError):
    pass


class CatalogService:
    def __init__(self, storage_path: Path | None = None) -> None:
        self._storage_path = storage_path
        self._lock = RLock()
        self._materials: dict[UUID, Material] = {}
        self._price_importer = ImporterService(TechnicalLibrary())
        self._price_import_history: list[PriceTableImportResult] = []
        self._operations: dict[int, Operation] = {
            code: Operation(erp_code=code, name=name, **DEFAULT_OPERATION_COSTS.get(code, {}))
            for code, name in ERP_OPERATIONS.items()
        }
        self._routing_templates: dict[UUID, RoutingTemplate] = {
            template.id: template
            for name, raw_steps in DEFAULT_ROUTING_TEMPLATES
            for template in [RoutingTemplate(
                name=name,
                description="Roteiro padrão recuperado para seleção rápida no orçamento.",
                steps=[RoutingTemplateStep(
                    operation_erp_code=code, process=process, default_minutes=minutes
                ) for code, process, minutes in raw_steps],
            )]
        }
        self._load()
        self._ensure_primary_routing_templates()
        self._seed_v051()

    def _ensure_primary_routing_templates(self) -> None:
        required = DEFAULT_ROUTING_TEMPLATES[:3]
        existing_names = {item.name.casefold() for item in self._routing_templates.values()}
        changed = False
        for name, raw_steps in required:
            if name.casefold() in existing_names:
                continue
            template = RoutingTemplate(
                name=name,
                description="Roteiro principal para seleção rápida no orçamento.",
                steps=[RoutingTemplateStep(
                    operation_erp_code=code, process=process, default_minutes=minutes
                ) for code, process, minutes in raw_steps],
            )
            self._routing_templates[template.id] = template
            changed = True
        if changed:
            self._save()

    def _seed_v051(self) -> None:
        """Recupera os cadastros aprovados da v0.51 somente quando não há dados atuais."""
        seed_path = Path(__file__).parents[1] / "v051_maintenance.json"
        if not seed_path.exists():
            return
        source = json.loads(seed_path.read_text(encoding="utf-8"))
        changed = False
        # Um catálogo persistido sem roteiros é uma escolha administrativa; só
        # substituímos os padrões de fábrica na primeira inicialização.
        if self._storage_path is None or not self._storage_path.exists():
            recovered = dict(self._routing_templates)
            for raw in source.get("models", []):
                codes = [int(value) for value in str(raw.get("codigosERP", "")).split(";") if value.strip().isdigit()]
                steps = [RoutingTemplateStep(
                    operation_erp_code=code,
                    process=ERP_OPERATIONS.get(code, f"Operação {code}"),
                    default_minutes=5,
                ) for code in codes]
                if not steps:
                    continue
                template = RoutingTemplate(
                    name=f"{raw.get('codigo', '')} · {raw.get('descricao', 'Modelo')}".strip(" ·"),
                    description=str(raw.get("descricao") or "Modelo recuperado da v0.51"),
                    steps=steps,
                    active=str(raw.get("ativo", "Sim")).casefold() == "sim",
                )
                recovered[template.id] = template
            if recovered:
                self._routing_templates = recovered
                changed = True
        if changed:
            self._save()

    def _load(self) -> None:
        if self._storage_path is None or not self._storage_path.exists():
            return
        payload = json.loads(self._storage_path.read_text(encoding="utf-8"))
        self._materials = {
            item.id: item for item in map(Material.model_validate, payload.get("materials", []))
        }
        self._price_import_history = [
            PriceTableImportResult.model_validate(item)
            for item in payload.get("price_import_history", [])
        ]
        for raw in payload.get("operations", []):
            operation = Operation.model_validate(raw)
            self._operations[operation.erp_code] = operation
        for code, defaults in DEFAULT_OPERATION_COSTS.items():
            current = self._operations[code]
            if not current.hourly_rate and not current.weight_rate and not current.fixed_cost:
                self._operations[code] = current.model_copy(update=defaults)
        if "routing_templates" in payload:
            self._routing_templates = {
                item.id: item
                for item in map(RoutingTemplate.model_validate, payload["routing_templates"])
            }

    def _save(self) -> None:
        if self._storage_path is None:
            return
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._storage_path.write_text(json.dumps({
            "version": 2,
            "materials": [item.model_dump(mode="json") for item in self._materials.values()],
            "price_import_history": [item.model_dump(mode="json") for item in self._price_import_history[-100:]],
            "operations": [item.model_dump(mode="json") for item in self._operations.values()],
            "routing_templates": [
                item.model_dump(mode="json") for item in self._routing_templates.values()
            ],
        }, ensure_ascii=False, indent=2), encoding="utf-8")

    def create_material(self, data: MaterialCreate) -> Material:
        with self._lock:
            if any(item.erp_code.casefold() == data.erp_code.casefold() for item in self._materials.values()):
                raise ValueError("código ERP do material já cadastrado")
            material = Material(**data.model_dump())
            self._materials[material.id] = material
            self._save()
        return material.model_copy(deep=True)

    def seed_legacy_materials(self, rows: list[dict]) -> int:
        """Importa o cadastro histórico somente quando o catálogo ainda está vazio."""
        if self._materials:
            return 0
        created = 0
        for row in rows:
            density = float(row.get("densidade") or 7850)
            if density < 5000:  # corrige registros históricos digitados como 780
                density = 7850
            self.create_material(MaterialCreate(
                erp_code=str(row.get("codigoERP") or f"LEG-{created + 1}"),
                description=str(row.get("material") or "Material"),
                specification=str(row.get("descricao") or ""),
                thickness_mm=float(row.get("espessura") or 0),
                price_per_kg=float(row.get("valorKg") or 0),
                density_kg_m3=density,
                laser_speed_mm_min=float(row.get("velLaser") or 0),
                plasma_speed_mm_min=float(row.get("velPlasma") or 0),
            ))
            created += 1
        return created

    def list_materials(self, query: str = "", active: bool | None = None) -> list[Material]:
        needle = query.strip().casefold()
        items = list(self._materials.values())
        if active is not None:
            items = [item for item in items if item.active is active]
        if needle:
            items = [item for item in items if needle in item.erp_code.casefold()
                     or needle in item.description.casefold()
                     or needle in item.specification.casefold()]
        return [item.model_copy(deep=True) for item in sorted(items, key=lambda item: (item.description, item.thickness_mm))]

    def update_material(self, material_id: UUID, data: MaterialUpdate) -> Material:
        with self._lock:
            current = self._materials.get(material_id)
            if current is None:
                raise CatalogNotFoundError(material_id)
            updated = current.model_copy(update={
                **data.model_dump(exclude_unset=True),
                "updated_at": datetime.now(timezone.utc),
            })
            self._materials[material_id] = updated
            self._save()
        return updated.model_copy(deep=True)

    def delete_material(self, material_id: UUID) -> None:
        with self._lock:
            if self._materials.pop(material_id, None) is None:
                raise CatalogNotFoundError(material_id)
            self._save()

    def preview_price_table(self, upload: FileUpload) -> ImportPreview:
        return self._price_importer.preview(upload)

    @staticmethod
    def _number(value: str, field: str) -> float:
        text = str(value).strip().replace("R$", "").replace(" ", "")
        if not text:
            raise ValueError(f"{field} vazio")
        if "," in text:
            text = text.replace(".", "").replace(",", ".")
        return float(text)

    def apply_price_table(
        self, session_id: UUID, mapping: PriceTableMapping, imported_by: str = ""
    ) -> PriceTableImportResult:
        session = self._price_importer._sessions.get(session_id)
        if session is None:
            raise CatalogNotFoundError(session_id)
        required = [mapping.erp_code_column, mapping.price_column]
        optional = [mapping.description_column, mapping.thickness_column,
                    mapping.specification_column, mapping.density_column]
        missing = [column for column in [*required, *filter(None, optional)] if column not in session.columns]
        if missing:
            raise ValueError(f"coluna não encontrada: {', '.join(missing)}")
        indexes = {column: index for index, column in enumerate(session.columns)}
        existing = {item.erp_code.casefold(): item for item in self._materials.values()}
        changes: list[PriceTableChange] = []
        errors: list[str] = []
        created = updated_count = unchanged = 0
        with self._lock:
            for row_number, cells in enumerate(session.rows, start=2):
                try:
                    code = cells[indexes[mapping.erp_code_column]].strip()
                    if not code:
                        raise ValueError("código ERP vazio")
                    price = self._number(cells[indexes[mapping.price_column]], "preço")
                    if price < 0:
                        raise ValueError("preço negativo")
                    current = existing.get(code.casefold())
                    description = cells[indexes[mapping.description_column]].strip() if mapping.description_column else ""
                    if current:
                        if current.price_per_kg == price:
                            unchanged += 1
                            continue
                        revised = current.model_copy(update={
                            "price_per_kg": price,
                            **({"description": description} if description else {}),
                            "updated_at": datetime.now(timezone.utc),
                        })
                        self._materials[current.id] = revised
                        existing[code.casefold()] = revised
                        updated_count += 1
                        changes.append(PriceTableChange(
                            erp_code=code, description=revised.description, action="atualizado",
                            old_price=current.price_per_kg, new_price=price,
                        ))
                    else:
                        if not mapping.create_missing:
                            raise ValueError("material não cadastrado")
                        if not description:
                            raise ValueError("descrição obrigatória para material novo")
                        if not mapping.thickness_column:
                            raise ValueError("coluna de espessura obrigatória para material novo")
                        thickness = self._number(cells[indexes[mapping.thickness_column]], "espessura")
                        specification = cells[indexes[mapping.specification_column]].strip() if mapping.specification_column else ""
                        density = self._number(cells[indexes[mapping.density_column]], "densidade") if mapping.density_column and cells[indexes[mapping.density_column]].strip() else 7850
                        material = Material(
                            erp_code=code, description=description, specification=specification,
                            thickness_mm=thickness, price_per_kg=price, density_kg_m3=density,
                        )
                        self._materials[material.id] = material
                        existing[code.casefold()] = material
                        created += 1
                        changes.append(PriceTableChange(
                            erp_code=code, description=description, action="criado",
                            new_price=price,
                        ))
                except (ValueError, IndexError) as error:
                    errors.append(f"Linha {row_number}: {error}")
            result = PriceTableImportResult(
                filename=session.filename, total_rows=len(session.rows), created=created,
                updated=updated_count, unchanged=unchanged, invalid=len(errors),
                changes=changes, errors=errors, imported_by=imported_by,
            )
            self._price_import_history.append(result)
            self._save()
        return result.model_copy(deep=True)

    def price_import_history(self) -> list[PriceTableImportResult]:
        return [item.model_copy(deep=True) for item in reversed(self._price_import_history)]

    def list_operations(self, active: bool | None = None) -> list[Operation]:
        items = self._operations.values()
        if active is not None:
            items = (item for item in items if item.active is active)
        return [item.model_copy(deep=True) for item in sorted(items, key=lambda item: item.erp_code)]

    def update_operation(self, erp_code: int, data: OperationUpdate) -> Operation:
        with self._lock:
            current = self._operations.get(erp_code)
            if current is None:
                raise CatalogNotFoundError(erp_code)
            updated = current.model_copy(update={
                **data.model_dump(exclude_unset=True),
                "updated_at": datetime.now(timezone.utc),
            })
            self._operations[erp_code] = updated
            self._save()
        return updated.model_copy(deep=True)

    def list_routing_templates(self, active: bool | None = None) -> list[RoutingTemplate]:
        items = list(self._routing_templates.values())
        if active is not None:
            items = [item for item in items if item.active is active]
        primary = {"laser": 0, "laser + dobra": 1, "laser + dobra + calandra": 2}
        return [item.model_copy(deep=True) for item in sorted(
            items, key=lambda item: (primary.get(item.name.casefold(), 99), item.name)
        )]

    def create_routing_template(self, data: RoutingTemplateCreate) -> RoutingTemplate:
        with self._lock:
            template = RoutingTemplate(**data.model_dump())
            self._routing_templates[template.id] = template
            self._save()
        return template.model_copy(deep=True)

    def update_routing_template(self, template_id: UUID, data: RoutingTemplateUpdate) -> RoutingTemplate:
        with self._lock:
            current = self._routing_templates.get(template_id)
            if current is None:
                raise CatalogNotFoundError(template_id)
            updated = current.model_copy(update={
                **data.model_dump(exclude_unset=True),
                "updated_at": datetime.now(timezone.utc),
            })
            self._routing_templates[template_id] = updated
            self._save()
        return updated.model_copy(deep=True)
