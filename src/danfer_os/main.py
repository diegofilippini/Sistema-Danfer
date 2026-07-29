from fastapi import FastAPI

from danfer_os.routers.health import router as health_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="Danfer Industrial OS",
        version="0.1.0",
        description="API central para os módulos industriais da Danfer.",
    )
    app.include_router(health_router, prefix="/api/v1")
    return app


app = create_app()

