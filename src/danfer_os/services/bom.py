from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from danfer_os.models.bom import (
    BillOfMaterials,
    BomCreate,
    BomUpdate,
    ExplodedComponent,
)
from danfer_os.services.technical_library import DocumentNotFoundError, TechnicalLibrary


class BomNotFoundError(LookupError):
    pass


class BomValidationError(ValueError):
    pass


class BomService:
    def __init__(self, library: TechnicalLibrary) -> None:
        self._library = library
        self._boms: dict[UUID, BillOfMaterials] = {}

    def _validate(self, data: BomCreate, ignored_bom_id: UUID | None = None) -> None:
        try:
            self._library.get(data.product_id)
            for component in data.components:
                self._library.get(component.part_id)
        except DocumentNotFoundError as error:
            raise BomValidationError("produto ou componente não cadastrado") from error
        if any(component.part_id == data.product_id for component in data.components):
            raise BomValidationError("um produto não pode ser componente de si mesmo")
        if len({item.part_id for item in data.components}) != len(data.components):
            raise BomValidationError("componente duplicado")
        for bom in self._boms.values():
            if bom.id != ignored_bom_id and bom.product_id == data.product_id and bom.status == data.status:
                raise BomValidationError("já existe uma BOM deste produto com o mesmo status")

    def create(self, data: BomCreate) -> BillOfMaterials:
        self._validate(data)
        bom = BillOfMaterials(**data.model_dump())
        self._boms[bom.id] = bom
        try:
            self._assert_acyclic(bom.product_id)
        except BomValidationError:
            self._boms.pop(bom.id, None)
            raise
        return bom.model_copy(deep=True)

    def list(self) -> list[BillOfMaterials]:
        return [item.model_copy(deep=True) for item in self._boms.values()]

    def get(self, bom_id: UUID) -> BillOfMaterials:
        bom = self._boms.get(bom_id)
        if bom is None:
            raise BomNotFoundError(bom_id)
        return bom.model_copy(deep=True)

    def update(self, bom_id: UUID, data: BomUpdate) -> BillOfMaterials:
        current = self.get(bom_id)
        updated = current.model_copy(
            update={
                **data.model_dump(exclude_unset=True),
                "updated_at": datetime.now(timezone.utc),
            }
        )
        validation = BomCreate.model_validate(updated.model_dump())
        self._validate(validation, ignored_bom_id=bom_id)
        self._boms[bom_id] = updated
        try:
            self._assert_acyclic(updated.product_id)
        except BomValidationError:
            self._boms[bom_id] = current
            raise
        return updated.model_copy(deep=True)

    def delete(self, bom_id: UUID) -> None:
        if self._boms.pop(bom_id, None) is None:
            raise BomNotFoundError(bom_id)

    def _for_product(self, product_id: UUID) -> BillOfMaterials | None:
        candidates = [
            item for item in self._boms.values()
            if item.product_id == product_id and item.status.value != "obsoleta"
        ]
        return candidates[-1] if candidates else None

    def _assert_acyclic(self, product_id: UUID) -> None:
        def visit(part_id: UUID, path: set[UUID]) -> None:
            if part_id in path:
                raise BomValidationError("a estrutura contém uma referência circular")
            bom = self._for_product(part_id)
            if bom:
                for component in bom.components:
                    visit(component.part_id, path | {part_id})
        visit(product_id, set())

    def explode(self, bom_id: UUID, quantity: float = 1) -> list[ExplodedComponent]:
        root = self.get(bom_id)
        result: list[ExplodedComponent] = []

        def expand(product_id: UUID, multiplier: float, level: int) -> None:
            bom = self._for_product(product_id)
            if bom is None:
                return
            for component in bom.components:
                required = round(
                    multiplier * component.quantity * (1 + component.scrap_percent / 100),
                    6,
                )
                result.append(
                    ExplodedComponent(
                        part_id=component.part_id,
                        quantity=required,
                        unit=component.unit,
                        level=level,
                    )
                )
                expand(component.part_id, required, level + 1)

        expand(root.product_id, quantity, 1)
        return result
