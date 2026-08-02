from fastapi import APIRouter, HTTPException, Query

from danfer_os.models.dashboard import DashboardSummary
from danfer_os.services.dashboard import DashboardService


def create_router(service: DashboardService) -> APIRouter:
    router = APIRouter(prefix="/dashboard", tags=["dashboard"])

    @router.get("/industrial", response_model=DashboardSummary)
    def industrial_dashboard() -> DashboardSummary:
        return service.summary()

    @router.get("/deliveries")
    def delivery_board(days: int = Query(default=7)) -> dict:
        try:
            return service.delivery_board(days)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    return router
