from fastapi import APIRouter, Request

from danfer_os.models.push import PushStatus, PushSubscription, PushSubscriptionCreate
from danfer_os.services.push import PushService


def create_router(service: PushService) -> APIRouter:
    router = APIRouter(prefix="/push", tags=["push"])

    @router.get("/status", response_model=PushStatus)
    def status() -> PushStatus:
        return service.status()

    @router.post("/subscriptions", response_model=PushSubscription, status_code=201)
    def subscribe(data: PushSubscriptionCreate, request: Request) -> PushSubscription:
        user = getattr(request.state, "user", None)
        if user:
            data = data.model_copy(update={"username": user.username, "role": user.role.value})
        return service.subscribe(data)

    @router.delete("/subscriptions")
    def unsubscribe(endpoint: str) -> dict[str, bool]:
        return {"removed": service.unsubscribe(endpoint)}

    return router
