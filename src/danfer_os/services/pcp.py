from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from danfer_os.models.pcp import (
    MaterialGroup,
    MaterialRequirement,
    ProductionOrder,
    ProductionOrderCreate,
    ProductionOrderUpdate,
    ProductionStatus,
)
from danfer_os.services.bom import BomNotFoundError, BomService
from danfer_os.services.technical_library import DocumentNotFoundError, TechnicalLibrary


class ProductionOrderNotFoundError(LookupError):
    pass


class PcpValidationError(ValueError):
    pass


class PcpService:
    _transitions = {
        ProductionStatus.PLANNED: {ProductionStatus.RELEASED, ProductionStatus.CANCELLED},
        ProductionStatus.RELEASED: {ProductionStatus.IN_PROGRESS, ProductionStatus.CANCELLED},
        ProductionStatus.IN_PROGRESS: {
            ProductionStatus.PAUSED,
            ProductionStatus.COMPLETED,
            ProductionStatus.CANCELLED,
        },
        ProductionStatus.PAUSED: {ProductionStatus.IN_PROGRESS, ProductionStatus.CANCELLED},
        ProductionStatus.COMPLETED: set(),
        ProductionStatus.CANCELLED: set(),
    }

    def __init__(self, library: TechnicalLibrary, boms: BomService) -> None:
        self._library = library
        self._boms = boms
        self._orders: dict[UUID, ProductionOrder] = {}
        self._sequence = 0

    def create(self, data: ProductionOrderCreate) -> ProductionOrder:
        try:
            product = self._library.get(data.product_id)
            bom = self._boms.get(data.bom_id)
        except (DocumentNotFoundError, BomNotFoundError) as error:
            raise PcpValidationError("produto ou BOM não encontrado") from error
        if bom.product_id != product.id:
            raise PcpValidationError("a BOM não pertence ao produto informado")
        requirements = []
        for component in self._boms.explode(data.bom_id, data.quantity):
            part = self._library.get(component.part_id)
            requirements.append(
                MaterialRequirement(
                    part_id=part.id,
                    danfer_code=part.danfer_code,
                    material=part.material,
                    thickness_mm=part.thickness_mm,
                    quantity=component.quantity,
                    unit=component.unit,
                )
            )
        self._sequence += 1
        order = ProductionOrder(
            **data.model_dump(),
            number=f"OP-{datetime.now():%Y}-{self._sequence:05d}",
            requirements=requirements,
        )
        self._orders[order.id] = order
        return order.model_copy(deep=True)

    def list(self, status: ProductionStatus | None = None) -> list[ProductionOrder]:
        orders = self._orders.values()
        if status:
            orders = (item for item in orders if item.status == status)
        return [item.model_copy(deep=True) for item in orders]

    def get(self, order_id: UUID) -> ProductionOrder:
        order = self._orders.get(order_id)
        if order is None:
            raise ProductionOrderNotFoundError(order_id)
        return order.model_copy(deep=True)

    def update(self, order_id: UUID, data: ProductionOrderUpdate) -> ProductionOrder:
        current = self.get(order_id)
        changes = data.model_dump(exclude_unset=True)
        next_status = changes.get("status")
        if next_status and next_status != current.status:
            if next_status not in self._transitions[current.status]:
                raise PcpValidationError(
                    f"transição inválida: {current.status.value} → {next_status.value}"
                )
        updated = current.model_copy(
            update={**changes, "updated_at": datetime.now(timezone.utc)}
        )
        self._orders[order_id] = updated
        return updated.model_copy(deep=True)

    def sequence(self) -> list[ProductionOrder]:
        active = [
            item for item in self._orders.values()
            if item.status not in {ProductionStatus.COMPLETED, ProductionStatus.CANCELLED}
        ]
        active.sort(key=lambda item: (item.due_date, item.priority, item.created_at))
        return [item.model_copy(deep=True) for item in active]

    def material_groups(self) -> list[MaterialGroup]:
        groups: dict[tuple[str, float | None], MaterialGroup] = {}
        for order in self._orders.values():
            if order.status == ProductionStatus.CANCELLED:
                continue
            for requirement in order.requirements:
                key = (requirement.material, requirement.thickness_mm)
                group = groups.setdefault(
                    key,
                    MaterialGroup(
                        material=requirement.material,
                        thickness_mm=requirement.thickness_mm,
                        orders=[],
                        total_quantity=0,
                    ),
                )
                if order.id not in group.orders:
                    group.orders.append(order.id)
                group.total_quantity = round(
                    group.total_quantity + requirement.quantity, 6
                )
        return sorted(
            groups.values(),
            key=lambda item: (item.material.casefold(), item.thickness_mm or 0),
        )
