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
    "/api/v1/pcp": {UserRole.ADMIN, UserRole.PCP, UserRole.PRODUCTION, UserRole.COST_ANALYST},
    "/api/v1/quality": {UserRole.ADMIN, UserRole.QUALITY, UserRole.PRODUCTION},
    "/api/v1/maintenance": {UserRole.ADMIN, UserRole.PRODUCTION},
    "/api/v1/catalogs": {UserRole.ADMIN, UserRole.ENGINEERING, UserRole.COMMERCIAL},
    "/api/v1/technical-library": {UserRole.ADMIN, UserRole.ENGINEERING, UserRole.COMMERCIAL, UserRole.PCP, UserRole.VIEWER},
    "/api/v1/boms": {UserRole.ADMIN, UserRole.ENGINEERING, UserRole.PCP},
    "/api/v1/integrations": {UserRole.ADMIN, UserRole.COMMERCIAL, UserRole.PCP},
    "/api/v1/billing": {UserRole.ADMIN, UserRole.COMMERCIAL},
    "/api/v1/requests": {UserRole.ADMIN, UserRole.COMMERCIAL, UserRole.PCP, UserRole.ENGINEERING, UserRole.PRODUCTION, UserRole.QUALITY},
    "/api/v1/communications": {UserRole.ADMIN, UserRole.COMMERCIAL},
    "/api/v1/workflows": {UserRole.ADMIN, UserRole.COMMERCIAL, UserRole.PCP},
    "/api/v1/audit": {UserRole.ADMIN},
    "/api/v1/analytics": {UserRole.ADMIN, UserRole.COMMERCIAL, UserRole.PCP, UserRole.QUALITY, UserRole.VIEWER},
    "/api/v1/crm": {UserRole.ADMIN, UserRole.COMMERCIAL},
    "/api/v1/search": {UserRole.ADMIN, UserRole.COMMERCIAL, UserRole.PCP, UserRole.ENGINEERING, UserRole.PRODUCTION, UserRole.QUALITY, UserRole.VIEWER},
    "/api/v1/push": {UserRole.ADMIN, UserRole.COMMERCIAL, UserRole.PCP, UserRole.ENGINEERING, UserRole.PRODUCTION, UserRole.QUALITY, UserRole.VIEWER},
}

# Parâmetros de formação de preço pertencem à administração. A rota histórica é
# mantida para integrações existentes, mas não herda a permissão ampla do módulo
# comercial.
ADMIN_ONLY_PATHS = {"/api/v1/commercial/settings/costs"}
SENSITIVE_CATALOG_PREFIXES = {
    "/api/v1/catalogs/materials",
    "/api/v1/catalogs/operations",
    "/api/v1/catalogs/routing-templates",
}
ENGINEERING_ONLY_PREFIXES = {"/api/v1/engineering/nesting"}
PERMISSION_PREFIXES = {
    "/api/v1/auth/users": "users", "/api/v1/system": "system",
    "/api/v1/commercial": "quotes", "/api/v1/imports": "engineering",
    "/api/v1/engineering": "engineering", "/api/v1/pcp": "pcp",
    "/api/v1/quality": "quality", "/api/v1/maintenance": "maintenance",
    "/api/v1/catalogs/quote-materials": "quotes",
    "/api/v1/catalogs/quote-routing-templates": "quotes",
    "/api/v1/catalogs": "engineering", "/api/v1/technical-library": "library",
    "/api/v1/boms": "bom", "/api/v1/integrations": "integrations",
    "/api/v1/billing": "coordination", "/api/v1/requests": "coordination",
    "/api/v1/communications": "coordination", "/api/v1/workflows": "quotes",
    "/api/v1/audit": "audit", "/api/v1/dashboard": "dashboard",
    "/api/v1/analytics/quality": "quality-dashboard",
    "/api/v1/analytics/deviations": "deviations",
    "/api/v1/analytics/management": "management-dashboard",
    "/api/v1/analytics/monthly": "monthly-analysis",
    "/api/v1/crm": "crm",
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
        if user.must_change_password and path not in {
            "/api/v1/auth/me", "/api/v1/auth/change-password", "/api/v1/auth/logout"
        }:
            return JSONResponse(
                {"detail": "troca de senha obrigatória antes de continuar"},
                status_code=428,
            )
        if path in ADMIN_ONLY_PATHS:
            allowed = {UserRole.ADMIN}
        elif any(path.startswith(prefix) for prefix in (*SENSITIVE_CATALOG_PREFIXES, *ENGINEERING_ONLY_PREFIXES)):
            allowed = {UserRole.ADMIN, UserRole.ENGINEERING}
        else:
            allowed = next(
                (roles for prefix, roles in ROLE_PREFIXES.items() if path.startswith(prefix)),
                None,
            )
        if allowed and user.role not in allowed:
            return JSONResponse({"detail": "acesso não autorizado para este perfil"}, status_code=403)
        permission = next(
            (name for prefix, name in PERMISSION_PREFIXES.items() if path.startswith(prefix)),
            None,
        )
        if user.role != UserRole.ADMIN and user.permissions is not None and permission and permission not in user.permissions:
            return JSONResponse({"detail": "módulo não autorizado para este usuário"}, status_code=403)
        request.state.user = user
        return await call_next(request)

    return middleware
