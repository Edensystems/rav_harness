from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from auth_service import get_session_from_token
from database import get_db
from models import User, UserRole, UserStatus

router = APIRouter(tags=["dependencies"])


def get_current_user(
    request: Request,
    authorization: str = Header(None),
    db: Session = Depends(get_db),
) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid or missing authorization token")

    token = authorization.split(" ", 1)[1]
    session = get_session_from_token(db, token)
    if not session:
        raise HTTPException(
            status_code=401,
            detail="Session expired or you are logged in on another device. Please log in again.",
        )

    device_id = request.headers.get("X-Device-Id")
    if device_id and session.device_id != device_id:
        raise HTTPException(
            status_code=401,
            detail="Session bound to another device. Please log in again on this device.",
        )

    user = db.query(User).filter(User.id == session.user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    if user.status != UserStatus.active:
        raise HTTPException(status_code=403, detail="Account inactive")

    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != UserRole.admin:
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return user
