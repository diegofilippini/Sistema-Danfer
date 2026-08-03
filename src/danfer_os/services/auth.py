import base64
import hashlib
import hmac
import json
import secrets
from pathlib import Path
from uuid import UUID

from danfer_os.models.auth import LoginResult, User, UserAccessUpdate, UserCreate, UserRole


class AuthenticationError(ValueError):
    pass


VALID_PERMISSIONS = {
    "dashboard", "crm", "quotes", "library", "engineering", "bom", "pcp",
    "integrations", "coordination", "quality", "maintenance", "users", "audit",
    "system", "quality-dashboard", "deviations", "management-dashboard", "monthly-analysis",
}


class AuthService:
    def __init__(
        self,
        storage_path: Path | None = None,
        require_initial_password_change: bool = True,
    ) -> None:
        self._storage_path = storage_path
        self._users: dict[UUID, tuple[User, str]] = {}
        self._sessions: dict[str, UUID] = {}
        self._load()
        if not self._users:
            created = self.create_user(
                UserCreate(
                    username="admin",
                    name="Administrador Danfer",
                    password="Danfer@2026",
                    role=UserRole.ADMIN,
                )
            )
            if not require_initial_password_change:
                self._set_password_change_requirement(created.id, False)
        elif not require_initial_password_change:
            for user_id, (user, _) in list(self._users.items()):
                if user.must_change_password:
                    self._set_password_change_requirement(user_id, False)

    def _set_password_change_requirement(self, user_id: UUID, required: bool) -> None:
        user, password_hash = self._users[user_id]
        self._users[user_id] = (
            user.model_copy(update={"must_change_password": required}),
            password_hash,
        )
        self._save()

    @staticmethod
    def _hash(password: str, salt: bytes | None = None) -> str:
        salt = salt or secrets.token_bytes(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 310_000)
        return f"{base64.b64encode(salt).decode()}:{base64.b64encode(digest).decode()}"

    @classmethod
    def _verify(cls, password: str, encoded: str) -> bool:
        salt_text, expected_text = encoded.split(":", 1)
        candidate = cls._hash(password, base64.b64decode(salt_text)).split(":", 1)[1]
        return hmac.compare_digest(candidate, expected_text)

    def _load(self) -> None:
        if self._storage_path is None or not self._storage_path.exists():
            return
        payload = json.loads(self._storage_path.read_text(encoding="utf-8"))
        for value in payload.get("users", []):
            user = User.model_validate(value["user"])
            self._users[user.id] = (user, value["password_hash"])

    def _save(self) -> None:
        if self._storage_path is None:
            return
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "users": [
                {"user": user.model_dump(mode="json"), "password_hash": password_hash}
                for user, password_hash in self._users.values()
            ]
        }
        self._storage_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def create_user(self, data: UserCreate) -> User:
        if any(user.username.casefold() == data.username.casefold() for user, _ in self._users.values()):
            raise AuthenticationError("usuário já cadastrado")
        user = User(
            username=data.username.lower(),
            name=data.name,
            role=data.role,
            permissions=self._validate_permissions(data.permissions),
        )
        self._users[user.id] = (user, self._hash(data.password))
        self._save()
        return user.model_copy(deep=True)

    def list_users(self) -> list[User]:
        return [user.model_copy(deep=True) for user, _ in self._users.values()]

    @staticmethod
    def _validate_permissions(permissions: list[str] | None) -> list[str] | None:
        if permissions is None:
            return None
        normalized = list(dict.fromkeys(permissions))
        invalid = set(normalized) - VALID_PERMISSIONS
        if invalid:
            raise AuthenticationError(f"permissões inválidas: {', '.join(sorted(invalid))}")
        return normalized

    def update_access(self, user_id: UUID, data: UserAccessUpdate) -> User:
        current = self._users.get(user_id)
        if current is None:
            raise AuthenticationError("usuário não encontrado")
        user, password_hash = current
        changes = data.model_dump(exclude_unset=True)
        if "permissions" in changes:
            changes["permissions"] = self._validate_permissions(changes["permissions"])
        updated = user.model_copy(update=changes)
        self._users[user_id] = (updated, password_hash)
        self._save()
        return updated.model_copy(deep=True)

    def login(self, username: str, password: str) -> LoginResult:
        found = next(
            (
                (user, password_hash)
                for user, password_hash in self._users.values()
                if user.username.casefold() == username.casefold()
            ),
            None,
        )
        if found is None or not found[0].active or not self._verify(password, found[1]):
            raise AuthenticationError("usuário ou senha inválidos")
        token = secrets.token_urlsafe(32)
        self._sessions[token] = found[0].id
        return LoginResult(token=token, user=found[0])

    def session(self, token: str) -> User:
        user_id = self._sessions.get(token)
        if user_id is None or user_id not in self._users:
            raise AuthenticationError("sessão inválida")
        return self._users[user_id][0].model_copy(deep=True)

    def logout(self, token: str) -> None:
        self._sessions.pop(token, None)

    def change_password(self, token: str, current: str, new: str) -> User:
        user = self.session(token)
        stored, encoded = self._users[user.id]
        if not self._verify(current, encoded):
            raise AuthenticationError("senha atual inválida")
        updated = stored.model_copy(update={"must_change_password": False})
        self._users[user.id] = (updated, self._hash(new))
        self._save()
        return updated.model_copy(deep=True)
