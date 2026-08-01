from datetime import datetime, timezone
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class UserRole(StrEnum):
    ADMIN = "administrador"
    COMMERCIAL = "comercial"
    PCP = "pcp"
    ENGINEERING = "engenharia"
    PRODUCTION = "producao"
    QUALITY = "qualidade"
    VIEWER = "consulta"


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9._-]+$")
    name: str = Field(min_length=2, max_length=120)
    password: str = Field(min_length=8, max_length=128)
    role: UserRole
    permissions: list[str] | None = None


class User(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    username: str
    name: str
    role: UserRole
    active: bool = True
    must_change_password: bool = True
    permissions: list[str] | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResult(BaseModel):
    token: str
    user: User


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


class UserAccessUpdate(BaseModel):
    role: UserRole | None = None
    active: bool | None = None
    permissions: list[str] | None = None
