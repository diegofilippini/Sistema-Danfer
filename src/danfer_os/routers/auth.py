from uuid import UUID

from fastapi import APIRouter, Cookie, HTTPException, Response, status

from danfer_os.models.auth import LoginRequest, LoginResult, PasswordChange, User, UserAccessUpdate, UserCreate
from danfer_os.services.auth import AuthenticationError, AuthService


def create_router(service: AuthService) -> APIRouter:
    router = APIRouter(prefix="/auth", tags=["autenticação"])

    @router.post("/login", response_model=LoginResult)
    def login(data: LoginRequest, response: Response) -> LoginResult:
        try:
            result = service.login(data.username, data.password)
        except AuthenticationError as error:
            raise HTTPException(status_code=401, detail=str(error)) from error
        response.set_cookie(
            "danfer_session",
            result.token,
            httponly=True,
            samesite="strict",
            max_age=8 * 60 * 60,
        )
        return result

    @router.get("/me", response_model=User)
    def me(danfer_session: str | None = Cookie(default=None)) -> User:
        if not danfer_session:
            raise HTTPException(status_code=401, detail="não autenticado")
        try:
            return service.session(danfer_session)
        except AuthenticationError as error:
            raise HTTPException(status_code=401, detail=str(error)) from error

    @router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
    def logout(
        response: Response,
        danfer_session: str | None = Cookie(default=None),
    ) -> Response:
        if danfer_session:
            service.logout(danfer_session)
        response.delete_cookie("danfer_session")
        return Response(status_code=204)

    @router.post("/users", response_model=User, status_code=201)
    def create_user(data: UserCreate) -> User:
        try:
            return service.create_user(data)
        except AuthenticationError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @router.get("/users", response_model=list[User])
    def users() -> list[User]:
        return service.list_users()

    @router.patch("/users/{user_id}", response_model=User)
    def update_user_access(user_id: UUID, data: UserAccessUpdate) -> User:
        try:
            return service.update_access(user_id, data)
        except AuthenticationError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @router.post("/change-password", response_model=User)
    def change_password(
        data: PasswordChange,
        danfer_session: str | None = Cookie(default=None),
    ) -> User:
        if not danfer_session:
            raise HTTPException(status_code=401, detail="não autenticado")
        try:
            return service.change_password(
                danfer_session, data.current_password, data.new_password
            )
        except AuthenticationError as error:
            raise HTTPException(status_code=401, detail=str(error)) from error

    return router
