from fastapi import APIRouter

from danfer_os.models.dashboard import DashboardSummary
from danfer_os.services.dashboard import DashboardService


def create_router(service: DashboardService) -> APIRouter:
    router = APIRouter(prefix="/dashboard", tags=["dashboard"])

    @router.get("/industrial", response_model=DashboardSummary)
    def industrial_dashboard() -> DashboardSummary:
        return service.summary()

    return router
