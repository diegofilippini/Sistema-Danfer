from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from danfer_os.models.catalogs import (
    Material, MaterialCreate, MaterialUpdate, Operation, OperationUpdate, QuoteMaterialOption,
    RoutingTemplate, RoutingTemplateCreate, RoutingTemplateUpdate,
)
from danfer_os.services.catalogs import CatalogNotFoundError, CatalogService


def create_router(service: CatalogService) -> APIRouter:
    router = APIRouter(prefix="/catalogs", tags=["cadastros industriais"])

    @router.get("/materials", response_model=list[Material])
    def list_materials(q: str = Query(default="", max_length=100), active: bool | None = None) -> list[Material]:
        return service.list_materials(q, active)

    @router.get("/quote-materials", response_model=list[QuoteMaterialOption])
    def quote_materials(q: str = Query(default="", max_length=100)) -> list[QuoteMaterialOption]:
        return [
            QuoteMaterialOption.model_validate(item, from_attributes=True)
            for item in service.list_materials(q, True)
        ]

    @router.post("/materials", response_model=Material, status_code=status.HTTP_201_CREATED)
    def create_material(data: MaterialCreate) -> Material:
        try:
            return service.create_material(data)
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @router.patch("/materials/{material_id}", response_model=Material)
    def update_material(material_id: UUID, data: MaterialUpdate) -> Material:
        try:
            return service.update_material(material_id, data)
        except CatalogNotFoundError as error:
            raise HTTPException(status_code=404, detail="material não encontrado") from error

    @router.get("/operations", response_model=list[Operation])
    def list_operations(active: bool | None = None) -> list[Operation]:
        return service.list_operations(active)

    @router.patch("/operations/{erp_code}", response_model=Operation)
    def update_operation(erp_code: int, data: OperationUpdate) -> Operation:
        try:
            return service.update_operation(erp_code, data)
        except CatalogNotFoundError as error:
            raise HTTPException(status_code=404, detail="operação não encontrada") from error

    @router.get("/routing-templates", response_model=list[RoutingTemplate])
    def routing_templates(active: bool | None = None) -> list[RoutingTemplate]:
        return service.list_routing_templates(active)

    @router.get("/quote-routing-templates", response_model=list[RoutingTemplate])
    def quote_routing_templates() -> list[RoutingTemplate]:
        # Não há valores de custo no modelo: somente sequência e tempos editáveis.
        return service.list_routing_templates(True)

    @router.post("/routing-templates", response_model=RoutingTemplate, status_code=201)
    def create_routing_template(data: RoutingTemplateCreate) -> RoutingTemplate:
        return service.create_routing_template(data)

    @router.patch("/routing-templates/{template_id}", response_model=RoutingTemplate)
    def update_routing_template(template_id: UUID, data: RoutingTemplateUpdate) -> RoutingTemplate:
        try:
            return service.update_routing_template(template_id, data)
        except CatalogNotFoundError as error:
            raise HTTPException(status_code=404, detail="roteiro não encontrado") from error

    return router
