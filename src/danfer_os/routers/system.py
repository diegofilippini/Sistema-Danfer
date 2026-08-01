from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi import APIRouter
from fastapi.responses import StreamingResponse


def create_router(data_dir: Path) -> APIRouter:
    router = APIRouter(prefix="/system", tags=["sistema"])

    @router.get("/version")
    def version() -> dict[str, str]:
        return {"version": "0.4.0", "data_schema": "1"}

    @router.get("/backup")
    def backup() -> StreamingResponse:
        buffer = BytesIO()
        with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
            if data_dir.exists():
                for path in data_dir.rglob("*"):
                    if path.is_file():
                        archive.write(path, path.relative_to(data_dir))
            archive.writestr("MANIFEST.txt", "Danfer Industrial OS\nSchema: 1\n")
        buffer.seek(0)
        return StreamingResponse(buffer, media_type="application/zip", headers={"Content-Disposition": "attachment; filename=danfer-backup.zip"})

    return router
