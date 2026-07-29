from fastapi import APIRouter

router = APIRouter(tags=["sistema"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "danfer-industrial-os"}

