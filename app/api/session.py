from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.auth.session import MemberSession, require_session
from app.clients.auth import AuthServiceError, StockTrackerAuthClient
from app.schemas.auth import LoginRequest, MemberProfile, RegisterRequest, WatchlistItem


router = APIRouter(prefix="/api", tags=["member-session"])
SESSION_MAX_AGE_SECONDS = 24 * 60 * 60


@router.post("/session/login", response_model=MemberProfile)
async def login(payload: LoginRequest, request: Request, response: Response) -> MemberProfile:
    client: StockTrackerAuthClient = request.app.state.auth_client
    try:
        token = await client.login(payload.identifier.strip(), payload.password)
        request.app.state.session_manager.decode(token)
        profile = await client.me(token)
    except AuthServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="會員登入憑證無法驗證") from exc

    set_session_cookie(request, response, token)
    return MemberProfile.model_validate(profile)


@router.post("/session/register", response_model=MemberProfile, status_code=201)
async def register(
    payload: RegisterRequest,
    request: Request,
    response: Response,
) -> MemberProfile:
    client: StockTrackerAuthClient = request.app.state.auth_client
    try:
        await client.register(payload.username.strip(), payload.email, payload.password)
        token = await client.login(payload.username.strip(), payload.password)
        request.app.state.session_manager.decode(token)
        profile = await client.me(token)
    except AuthServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="會員登入憑證無法驗證") from exc

    set_session_cookie(request, response, token)
    return MemberProfile.model_validate(profile)


@router.get("/session/me", response_model=MemberProfile)
async def me(
    request: Request,
    session: MemberSession = Depends(require_session),
) -> MemberProfile:
    client: StockTrackerAuthClient = request.app.state.auth_client
    try:
        profile = await client.me(session.token)
    except AuthServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return MemberProfile.model_validate(profile)


@router.post("/session/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, response: Response) -> None:
    manager = request.app.state.session_manager
    response.delete_cookie(
        manager.cookie_name,
        path="/",
        secure=request.app.state.session_cookie_secure,
        httponly=True,
        samesite="lax",
    )


@router.get("/member/watchlist", response_model=list[WatchlistItem])
async def watchlist(
    request: Request,
    session: MemberSession = Depends(require_session),
) -> list[WatchlistItem]:
    client: StockTrackerAuthClient = request.app.state.auth_client
    try:
        items = await client.watchlist(session.token)
    except AuthServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return [WatchlistItem.model_validate(item) for item in items]


def set_session_cookie(request: Request, response: Response, token: str) -> None:
    manager = request.app.state.session_manager
    response.set_cookie(
        manager.cookie_name,
        token,
        max_age=SESSION_MAX_AGE_SECONDS,
        path="/",
        secure=request.app.state.session_cookie_secure,
        httponly=True,
        samesite="lax",
    )
