from typing import Any

from fastapi import APIRouter, HTTPException, Request

from danfer_os.services.maintenance import MaintenanceService


def create_router(service: MaintenanceService) -> APIRouter:
    router = APIRouter(prefix="/maintenance-config", tags=["manutenções"])

    def require_admin(request: Request) -> None:
        user = getattr(request.state, "user", None)
        role = getattr(user, "role", "") if user is not None else ""
        if user is not None and str(role).casefold() not in {"administrador", "admin"}:
            raise HTTPException(403, "somente o administrador pode alterar manutenções")

    @router.get("/categories")
    def categories() -> dict[str, int]:
        return service.categories()

    @router.get("/{category}")
    def get_category(category: str) -> list[dict[str, Any]]:
        try:
            return service.get(category)
        except KeyError as error:
            raise HTTPException(404, "cadastro de manutenção não encontrado") from error

    @router.put("/{category}")
    def replace_category(category: str, rows: list[dict[str, Any]], request: Request) -> list[dict[str, Any]]:
        require_admin(request)
        try:
            return service.replace(category, rows)
        except KeyError as error:
            raise HTTPException(404, "cadastro de manutenção não encontrado") from error

    @router.post("/reset/v051", status_code=204)
    def reset_v051(request: Request) -> None:
        require_admin(request)
        service.reset()

    return router
