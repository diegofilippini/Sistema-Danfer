from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import os

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
from danfer_os.routers.commercial import create_router as create_commercial_router
from danfer_os.services.commercial import CommercialService
from danfer_os.routers.operations import create_router as create_operations_router
from danfer_os.services.operations import OperationsService
from danfer_os.routers.auth import create_router as create_auth_router
from danfer_os.services.auth import AuthService
from danfer_os.routers.workflows import create_router as create_workflows_router
from danfer_os.routers.engineering import create_router as create_engineering_router
from danfer_os.services.engineering import EngineeringService
from danfer_os.demo import seed_demo
from danfer_os.routers.system import create_router as create_system_router
from danfer_os.security import security_middleware
from danfer_os.routers.catalogs import create_router as create_catalogs_router
from danfer_os.services.catalogs import CatalogService
from danfer_os.routers.coordination import create_router as create_coordination_router
from danfer_os.services.coordination import CoordinationService


def create_app(
    library: TechnicalLibrary | None = None,
    data_dir: Path = Path("data"),
    enforce_auth: bool = False,
) -> FastAPI:
    isolated_test_mode = library is not None and data_dir == Path("data")
    library = library or TechnicalLibrary(data_dir / "technical-library.json")
    app = FastAPI(
        title="Danfer Industrial OS",
        version="1.2.0",
        description="API central para os módulos industriais da Danfer.",
    )
    auth_service = AuthService(data_dir / "auth.json")
    if enforce_auth:
        app.middleware("http")(security_middleware(auth_service))
    app.include_router(health_router, prefix="/api/v1")
    app.include_router(
        create_router(library),
        prefix="/api/v1",
    )
    bom_service = BomService(library)
    app.include_router(create_bom_router(bom_service), prefix="/api/v1")
    pcp_service = PcpService(
        library,
        bom_service,
        None if isolated_test_mode else data_dir / "pcp.json",
    )
    integration_service = IntegrationService(
        library, None if isolated_test_mode else data_dir / "integrations.json"
    )
    commercial_service = CommercialService(data_dir / "commercial.json")
    operations_service = OperationsService(data_dir / "operations.json")
    catalog_service = CatalogService(data_dir / "catalogs.json")
    if os.getenv("DANFER_SEED_DEMO") == "1":
        seed_demo(
            library,
            bom_service,
            pcp_service,
            commercial_service,
            operations_service,
        )
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
    app.include_router(
        create_commercial_router(commercial_service),
        prefix="/api/v1",
    )
    app.include_router(
        create_operations_router(operations_service, pcp_service),
        prefix="/api/v1",
    )
    app.include_router(
        create_auth_router(auth_service),
        prefix="/api/v1",
    )
    app.include_router(create_system_router(data_dir), prefix="/api/v1")
    app.include_router(
        create_workflows_router(
            commercial_service,
            library,
            bom_service,
            pcp_service,
            integration_service,
        ),
        prefix="/api/v1",
    )
    app.include_router(
        create_engineering_router(EngineeringService(), library),
        prefix="/api/v1",
    )
    app.include_router(create_catalogs_router(catalog_service), prefix="/api/v1")
    app.include_router(
        create_coordination_router(CoordinationService(
            None if isolated_test_mode else data_dir / "coordination.json"
        )),
        prefix="/api/v1",
    )
    static_dir = Path(__file__).with_name("static")
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="web")
    return app


app = create_app(enforce_auth=True)
