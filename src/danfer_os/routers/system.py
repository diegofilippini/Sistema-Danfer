from datetime import datetime
from io import BytesIO
import json
from pathlib import Path
from zipfile import BadZipFile, ZIP_DEFLATED, ZipFile

from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import StreamingResponse


def create_router(data_dir: Path) -> APIRouter:
    router = APIRouter(prefix="/system", tags=["sistema"])

    @router.get("/version")
    def version() -> dict[str, str]:
        return {"version": "1.0.0", "data_schema": "2"}

    @router.get("/backup")
    def backup() -> StreamingResponse:
        buffer = BytesIO()
        with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
            if data_dir.exists():
                for path in data_dir.rglob("*"):
                    if path.is_file():
                        archive.write(path, path.relative_to(data_dir))
            archive.writestr("MANIFEST.txt", "Danfer Industrial OS 1.0.0\nSchema: 2\n")
        buffer.seek(0)
        return StreamingResponse(buffer, media_type="application/zip", headers={"Content-Disposition": "attachment; filename=danfer-backup.zip"})

    @router.post("/restore")
    def restore(payload: bytes = Body(media_type="application/zip")) -> dict[str, object]:
        if len(payload) > 50 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="backup excede 50 MB")
        try:
            source = ZipFile(BytesIO(payload))
            entries = []
            for info in source.infolist():
                relative = Path(info.filename)
                if info.is_dir() or info.filename == "MANIFEST.txt":
                    continue
                if relative.is_absolute() or ".." in relative.parts:
                    raise ValueError("caminho inseguro no backup")
                content = source.read(info)
                if relative.suffix.casefold() == ".json":
                    json.loads(content.decode("utf-8"))
                entries.append((relative, content))
        except (BadZipFile, ValueError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise HTTPException(status_code=422, detail="backup inválido ou inseguro") from error
        if not entries:
            raise HTTPException(status_code=422, detail="backup sem arquivos de dados")

        backup_dir = data_dir.parent / "data-backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        snapshot = backup_dir / f"pre-restore-{datetime.now():%Y%m%d-%H%M%S}.zip"
        with ZipFile(snapshot, "w", ZIP_DEFLATED) as archive:
            if data_dir.exists():
                for path in data_dir.rglob("*"):
                    if path.is_file():
                        archive.write(path, path.relative_to(data_dir))
        for relative, content in entries:
            destination = data_dir / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
        return {
            "restored_files": [str(relative).replace("\\", "/") for relative, _ in entries],
            "pre_restore_backup": snapshot.name,
            "restart_required": True,
        }

    return router
