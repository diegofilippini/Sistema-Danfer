from fastapi import APIRouter

router = APIRouter(tags=["integridade"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
