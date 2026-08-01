from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
from uuid import UUID

from danfer_os.models.pcp import (
    MaterialGroup,
    MaterialRequirement,
    ProductionOrder,
    ProductionOrderCreate,
    ProductionOrderUpdate,
    ProductionStatus,
    CalendarException,
    CostVariance,
    DailyCapacity,
    WorkCenter,
    WorkLog,
    WorkLogCreate,
    WorkLogType,
    DirectProductionRequest,
    DirectProductionRequestCreate,
    DirectProductionRequestUpdate,
)
from danfer_os.services.bom import BomNotFoundError, BomService
from danfer_os.services.technical_library import DocumentNotFoundError, TechnicalLibrary


class ProductionOrderNotFoundError(LookupError):
    pass


class PcpValidationError(ValueError):
    pass


class PcpService:
    _default_operations = {
        2: "Corte Laser", 3: "Guilhotina", 4: "Plasma", 5: "Dobra",
        6: "Calandra", 7: "Prensa", 8: "Chanfro", 9: "Solda",
    }
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

    def __init__(self, library: TechnicalLibrary, boms: BomService, storage_path: Path | None = None) -> None:
        self._library = library
        self._boms = boms
        self._orders: dict[UUID, ProductionOrder] = {}
        self._sequence = 0
        self._storage_path = storage_path
        self._work_centers: dict[int, WorkCenter] = {
            code: WorkCenter(operation_erp_code=code, name=name)
            for code, name in self._default_operations.items()
        }
        self._calendar: dict[date, CalendarException] = {}
        self._logs: dict[UUID, list[WorkLog]] = {}
        self._direct_requests: dict[UUID, DirectProductionRequest] = {}
        self._direct_request_sequence = 0
        self._load()

    def _load(self) -> None:
        if self._storage_path is None or not self._storage_path.exists():
            return
        payload = json.loads(self._storage_path.read_text(encoding="utf-8"))
        orders = [ProductionOrder.model_validate(item) for item in payload.get("orders", [])]
        self._orders = {item.id: item for item in orders}
        self._sequence = int(payload.get("sequence", 0))
        centers = [WorkCenter.model_validate(item) for item in payload.get("work_centers", [])]
        if centers:
            self._work_centers = {item.operation_erp_code: item for item in centers}
        exceptions = [CalendarException.model_validate(item) for item in payload.get("calendar", [])]
        self._calendar = {item.date: item for item in exceptions}
        self._logs = {
            UUID(key): [WorkLog.model_validate(item) for item in values]
            for key, values in payload.get("logs", {}).items()
        }
        direct = [DirectProductionRequest.model_validate(item) for item in payload.get("direct_requests", [])]
        self._direct_requests = {item.id: item for item in direct}
        self._direct_request_sequence = int(payload.get("direct_request_sequence", 0))

    def _save(self) -> None:
        if self._storage_path is None:
            return
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._storage_path.write_text(json.dumps({
            "version": 1,
            "sequence": self._sequence,
            "orders": [item.model_dump(mode="json") for item in self._orders.values()],
            "work_centers": [item.model_dump(mode="json") for item in self._work_centers.values()],
            "calendar": [item.model_dump(mode="json") for item in self._calendar.values()],
            "logs": {str(key): [item.model_dump(mode="json") for item in values] for key, values in self._logs.items()},
            "direct_request_sequence": self._direct_request_sequence,
            "direct_requests": [item.model_dump(mode="json") for item in self._direct_requests.values()],
        }, ensure_ascii=False, indent=2), encoding="utf-8")

    def create_direct_request(self, data: DirectProductionRequestCreate) -> DirectProductionRequest:
        self._direct_request_sequence += 1
        item = DirectProductionRequest(
            **data.model_dump(),
            number=f"SP-{datetime.now():%Y}-{self._direct_request_sequence:05d}",
        )
        self._direct_requests[item.id] = item
        self._save()
        return item.model_copy(deep=True)

    def direct_requests(self) -> list[DirectProductionRequest]:
        return [item.model_copy(deep=True) for item in sorted(self._direct_requests.values(), key=lambda value: value.created_at, reverse=True)]

    def update_direct_request(self, request_id: UUID, data: DirectProductionRequestUpdate) -> DirectProductionRequest:
        current = self._direct_requests.get(request_id)
        if current is None:
            raise ProductionOrderNotFoundError(request_id)
        updated = current.model_copy(update=data.model_dump(exclude_unset=True))
        self._direct_requests[request_id] = updated
        self._save()
        return updated.model_copy(deep=True)

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
        self._save()
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

    def find_by_number(self, number: str) -> ProductionOrder:
        order = next((item for item in self._orders.values() if item.number.casefold() == number.casefold()), None)
        if order is None:
            raise ProductionOrderNotFoundError(number)
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
        self._save()
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

    def set_work_center(self, center: WorkCenter) -> WorkCenter:
        self._work_centers[center.operation_erp_code] = center
        self._save()
        return center.model_copy(deep=True)

    def work_centers(self) -> list[WorkCenter]:
        return [item.model_copy(deep=True) for item in sorted(self._work_centers.values(), key=lambda item: item.operation_erp_code)]

    def set_calendar_exception(self, exception: CalendarException) -> CalendarException:
        self._calendar[exception.date] = exception
        self._save()
        return exception.model_copy(deep=True)

    def calendar(self, start: date, end: date) -> list[CalendarException]:
        if end < start:
            raise PcpValidationError("data final anterior à data inicial")
        return [self._calendar[item].model_copy(deep=True) for item in sorted(self._calendar) if start <= item <= end]

    def add_log(self, order_id: UUID, data: WorkLogCreate) -> WorkLog:
        self.get(order_id)
        if data.amount is not None:
            cost = data.amount
        elif data.type == WorkLogType.OPERATION:
            center = self._work_centers.get(data.operation_erp_code or 0)
            rate = center.hourly_rate if center else data.unit_cost
            cost = data.minutes / 60 * rate
        else:
            cost = data.quantity * data.unit_cost
        log = WorkLog(**data.model_dump(), calculated_cost=round(cost, 2))
        self._logs.setdefault(order_id, []).append(log)
        self._save()
        return log.model_copy(deep=True)

    def logs(self, order_id: UUID) -> list[WorkLog]:
        self.get(order_id)
        return [item.model_copy(deep=True) for item in self._logs.get(order_id, [])]

    def costs(self, order_id: UUID) -> CostVariance:
        order = self.get(order_id)
        totals = {kind: 0.0 for kind in WorkLogType}
        for log in self._logs.get(order_id, []):
            totals[log.type] += log.calculated_cost
        estimated = order.estimated_material_cost + order.estimated_process_cost
        actual = sum(totals.values())
        variance = actual - estimated
        return CostVariance(
            order_id=order.id, order_number=order.number,
            estimated_material_cost=order.estimated_material_cost,
            estimated_process_cost=order.estimated_process_cost,
            estimated_total_cost=round(estimated, 2),
            actual_material_cost=round(totals[WorkLogType.MATERIAL], 2),
            actual_process_cost=round(totals[WorkLogType.OPERATION], 2),
            actual_external_cost=round(totals[WorkLogType.EXTERNAL], 2),
            actual_quality_cost=round(totals[WorkLogType.QUALITY], 2),
            actual_total_cost=round(actual, 2), variance_value=round(variance, 2),
            variance_percent=round(variance / estimated * 100, 2) if estimated else None,
        )

    def daily_capacity(self, start: date, days: int = 7) -> list[DailyCapacity]:
        if not 1 <= days <= 62:
            raise PcpValidationError("período permitido: 1 a 62 dias")
        result: list[DailyCapacity] = []
        for offset in range(days):
            current_date = start + timedelta(days=offset)
            for center in self._work_centers.values():
                if not center.active:
                    continue
                available = 0 if current_date.weekday() >= 5 else center.daily_capacity_minutes
                if current_date in self._calendar:
                    available = self._calendar[current_date].available_minutes
                loads: list[tuple[str, float]] = []
                for order in self._orders.values():
                    if order.due_date != current_date or order.status in {ProductionStatus.COMPLETED, ProductionStatus.CANCELLED}:
                        continue
                    try:
                        product = self._library.get(order.product_id)
                    except DocumentNotFoundError:
                        # Mantém OPs históricas legíveis mesmo quando o cadastro técnico
                        # de origem não está mais disponível para recalcular sua carga.
                        continue
                    minutes = sum(step.estimated_minutes * order.quantity for step in product.routing if step.erp_code == center.operation_erp_code)
                    if minutes:
                        loads.append((order.number, minutes))
                planned = sum(minutes for _, minutes in loads)
                result.append(DailyCapacity(
                    date=current_date, operation_erp_code=center.operation_erp_code,
                    operation=center.name, available_minutes=round(available, 2),
                    planned_minutes=round(planned, 2), remaining_minutes=round(available - planned, 2),
                    utilization_percent=round(planned / available * 100, 2) if available else (100 if planned else 0),
                    overloaded=planned > available, orders=[number for number, _ in loads],
                ))
        return result
