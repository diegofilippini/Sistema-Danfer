from fastapi import FastAPI
from pathlib import Path

from danfer_os.routers.health import router as health_router
from danfer_os.routers.technical_library import create_router
from danfer_os.routers.bom import create_router as create_bom_router
from danfer_os.services.bom import BomService
from danfer_os.routers.pcp import create_router as create_pcp_router
from danfer_os.services.pcp import PcpService
from danfer_os.routers.integrations import create_router as create_integrations_router
from danfer_os.services.integrations import IntegrationService
from danfer_os.routers.dashboard import create_router as create_dashboard_router
from danfer_os.services.dashboard import DashboardService
from danfer_os.routers.importer import create_router as create_importer_router
from danfer_os.services.importer import ImporterService
from danfer_os.services.technical_library import TechnicalLibrary


def create_app(library: TechnicalLibrary | None = None) -> FastAPI:
    library = library or TechnicalLibrary(Path("data/technical-library.json"))
    app = FastAPI(
        title="Danfer Industrial OS",
        version="0.2.0",
        description="API central para os módulos industriais da Danfer.",
    )
    app.include_router(health_router, prefix="/api/v1")
    app.include_router(
        create_router(library),
        prefix="/api/v1",
    )
    bom_service = BomService(library)
    app.include_router(create_bom_router(bom_service), prefix="/api/v1")
    pcp_service = PcpService(library, bom_service)
    integration_service = IntegrationService(library)
    app.include_router(create_pcp_router(pcp_service), prefix="/api/v1")
    app.include_router(
        create_integrations_router(integration_service), prefix="/api/v1"
    )
    app.include_router(
        create_dashboard_router(
            DashboardService(
                library,
                bom_service,
                pcp_service,
                integration_service,
            )
        ),
        prefix="/api/v1",
    )
    app.include_router(
        create_importer_router(ImporterService(library)),
        prefix="/api/v1",
    )
    return app


app = create_app()
