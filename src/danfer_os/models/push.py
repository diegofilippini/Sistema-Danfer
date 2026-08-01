from datetime import datetime, timezone
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class PushKeys(BaseModel):
    p256dh: str = Field(min_length=10, max_length=500)
    auth: str = Field(min_length=5, max_length=200)


class PushSubscriptionCreate(BaseModel):
    username: str = Field(min_length=2, max_length=50)
    role: str = Field(default="", max_length=40)
    endpoint: str = Field(min_length=20, max_length=2000)
    keys: PushKeys


class PushSubscription(PushSubscriptionCreate):
    id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PushStatus(BaseModel):
    available: bool
    public_key: str = ""
    subscriptions: int = 0
    detail: str = ""
