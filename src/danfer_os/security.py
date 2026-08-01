from collections.abc import Awaitable, Callable

from fastapi import Request
from fastapi.responses import JSONResponse, Response

from danfer_os.models.auth import UserRole
from danfer_os.services.auth import AuthenticationError, AuthService


PUBLIC_PATHS = {"/api/v1/health", "/api/v1/auth/login"}
ROLE_PREFIXES = {
    "/api/v1/auth/users": {UserRole.ADMIN},
    "/api/v1/system": {UserRole.ADMIN},
    "/api/v1/commercial": {UserRole.ADMIN, UserRole.COMMERCIAL},
    "/api/v1/imports": {UserRole.ADMIN, UserRole.COMMERCIAL, UserRole.ENGINEERING},
    "/api/v1/engineering": {UserRole.ADMIN, UserRole.ENGINEERING, UserRole.COMMERCIAL},
    "/api/v1/pcp": {UserRole.ADMIN, UserRole.PCP, UserRole.PRODUCTION},
    "/api/v1/quality": {UserRole.ADMIN, UserRole.QUALITY, UserRole.PRODUCTION},
    "/api/v1/maintenance": {UserRole.ADMIN, UserRole.PRODUCTION},
    "/api/v1/catalogs": {UserRole.ADMIN, UserRole.ENGINEERING, UserRole.COMMERCIAL},
    "/api/v1/technical-library": {UserRole.ADMIN, UserRole.ENGINEERING, UserRole.COMMERCIAL, UserRole.PCP, UserRole.VIEWER},
    "/api/v1/boms": {UserRole.ADMIN, UserRole.ENGINEERING, UserRole.PCP},
    "/api/v1/integrations": {UserRole.ADMIN, UserRole.COMMERCIAL, UserRole.PCP},
    "/api/v1/billing": {UserRole.ADMIN, UserRole.COMMERCIAL},
    "/api/v1/requests": {UserRole.ADMIN, UserRole.COMMERCIAL, UserRole.PCP, UserRole.ENGINEERING, UserRole.PRODUCTION, UserRole.QUALITY},
    "/api/v1/communications": {UserRole.ADMIN, UserRole.COMMERCIAL},
    "/api/v1/audit": {UserRole.ADMIN},
}


def security_middleware(auth: AuthService):
    async def middleware(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        path = request.url.path
        if not path.startswith("/api/v1") or path in PUBLIC_PATHS:
            return await call_next(request)
        token = request.cookies.get("danfer_session")
        try:
            user = auth.session(token or "")
        except AuthenticationError:
            return JSONResponse({"detail": "não autenticado"}, status_code=401)
        allowed = next(
            (roles for prefix, roles in ROLE_PREFIXES.items() if path.startswith(prefix)),
            None,
        )
        if allowed and user.role not in allowed:
            return JSONResponse({"detail": "acesso não autorizado para este perfil"}, status_code=403)
        request.state.user = user
        return await call_next(request)

    return middleware
