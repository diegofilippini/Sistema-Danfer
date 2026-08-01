from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from threading import RLock
from uuid import UUID

from danfer_os.models.catalogs import Material, MaterialCreate, MaterialUpdate, Operation, OperationUpdate


ERP_OPERATIONS = {
    2: "Corte Laser",
    3: "Guilhotina",
    4: "Plasma",
    5: "Dobra",
    6: "Calandra",
    7: "Prensa",
    8: "Chanfro",
    9: "Solda",
}


class CatalogNotFoundError(LookupError):
    pass


class CatalogService:
    def __init__(self, storage_path: Path | None = None) -> None:
        self._storage_path = storage_path
        self._lock = RLock()
        self._materials: dict[UUID, Material] = {}
        self._operations: dict[int, Operation] = {
            code: Operation(erp_code=code, name=name) for code, name in ERP_OPERATIONS.items()
        }
        self._load()

    def _load(self) -> None:
        if self._storage_path is None or not self._storage_path.exists():
            return
        payload = json.loads(self._storage_path.read_text(encoding="utf-8"))
        self._materials = {
            item.id: item for item in map(Material.model_validate, payload.get("materials", []))
        }
        for raw in payload.get("operations", []):
            operation = Operation.model_validate(raw)
            self._operations[operation.erp_code] = operation

    def _save(self) -> None:
        if self._storage_path is None:
            return
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._storage_path.write_text(json.dumps({
            "version": 1,
            "materials": [item.model_dump(mode="json") for item in self._materials.values()],
            "operations": [item.model_dump(mode="json") for item in self._operations.values()],
        }, ensure_ascii=False, indent=2), encoding="utf-8")

    def create_material(self, data: MaterialCreate) -> Material:
        with self._lock:
            if any(item.erp_code.casefold() == data.erp_code.casefold() for item in self._materials.values()):
                raise ValueError("código ERP do material já cadastrado")
            material = Material(**data.model_dump())
            self._materials[material.id] = material
            self._save()
        return material.model_copy(deep=True)

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
