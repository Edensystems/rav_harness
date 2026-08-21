from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from auth_service import AuthError, get_session_from_token, login_user, logout_user, register_user
from database import get_db
from models import User, UserRole
from schemas import AuthResponse, AuthUserResponse, LoginRequest, MessageResponse, RegisterRequest

router = APIRouter(prefix="/auth", tags=["auth"])


def _client_meta(request: Request, device_id: str, device_name: str) -> tuple[str, str, str | None, str | None]:
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")
    return device_id, device_name, ip, ua


@router.post("/register", response_model=AuthResponse, status_code=201)
def register(payload: RegisterRequest, request: Request, db: Session = Depends(get_db)):
    try:
        user = register_user(db, payload.email, payload.password, payload.phone_number)
        device_id = request.headers.get("X-Device-Id", "unknown-device")
        device_name = request.headers.get("X-Device-Name", "Desktop Client")
        _device_id, _device_name, ip, ua = _client_meta(request, device_id, device_name)
        _user, token = login_user(db, user.email, payload.password, device_id, device_name, ip, ua)
    except AuthError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    return AuthResponse(
        access_token=token,
        user=AuthUserResponse.model_validate(user),
    )


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    try:
        device_id, device_name, ip, ua = _client_meta(request, payload.device_id, payload.device_name)
        user, token = login_user(db, payload.email, payload.password, device_id, device_name, ip, ua)
    except AuthError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    return AuthResponse(
        access_token=token,
        user=AuthUserResponse.model_validate(user),
    )


@router.post("/logout", response_model=MessageResponse)
def logout(request: Request, db: Session = Depends(get_db)):
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = auth.split(" ", 1)[1]
    logout_user(db, token)
    return MessageResponse(message="Logged out successfully")


@router.get("/me", response_model=AuthUserResponse)
def me(request: Request, db: Session = Depends(get_db)):
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = auth.split(" ", 1)[1]
    session = get_session_from_token(db, token)
    if not session:
        raise HTTPException(status_code=401, detail="Session expired or invalid. Please log in again.")

    user = db.query(User).filter(User.id == session.user_id).first()
    if not user or user.status.value != "active":
        raise HTTPException(status_code=403, detail="Account inactive")

    return AuthUserResponse.model_validate(user)
