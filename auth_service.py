import hashlib
import re
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
from sqlalchemy.orm import Session

from config import settings
from models import User, UserRole, UserSession, UserStatus

PASSWORD_PATTERN = re.compile(r"^(?=.*[A-Za-z])(?=.*\d).{8,}$")


class AuthError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def validate_password_strength(password: str) -> None:
    if not PASSWORD_PATTERN.match(password):
        raise AuthError(
            "Password must be at least 8 characters and include both letters and numbers.",
            400,
        )


def hash_password(password: str) -> str:
    salt = bcrypt.gensalt(rounds=settings.bcrypt_rounds)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), password_hash.encode("utf-8"))


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_session_token() -> str:
    return secrets.token_urlsafe(48)


def register_user(db: Session, email: str, password: str, phone_number: str | None = None) -> User:
    normalized_email = email.strip().lower()
    validate_password_strength(password)

    existing = db.query(User).filter(User.email == normalized_email).first()
    if existing:
        raise AuthError("An account with this email already exists.", 409)

    user = User(
        email=normalized_email,
        password_hash=hash_password(password),
        phone_number=phone_number.strip() if phone_number else None,
        credits=0,
        status=UserStatus.active,
        role=UserRole.user,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def create_user_session(
    db: Session,
    user: User,
    device_id: str,
    device_name: str,
    ip_address: str | None,
    user_agent: str | None,
) -> tuple[str, UserSession]:
    if user.status != UserStatus.active:
        raise AuthError("Your account is inactive. Contact support.", 403)

    token = generate_session_token()
    token_hash = hash_token(token)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=settings.session_expire_hours)

    existing = db.query(UserSession).filter(UserSession.user_id == user.id).first()
    if existing:
        existing.token_hash = token_hash
        existing.device_id = device_id
        existing.device_name = device_name
        existing.ip_address = ip_address
        existing.user_agent = user_agent
        existing.is_active = True
        existing.last_active_at = datetime.now(timezone.utc)
        existing.expires_at = expires_at
        session = existing
    else:
        session = UserSession(
            user_id=user.id,
            token_hash=token_hash,
            device_id=device_id,
            device_name=device_name,
            ip_address=ip_address,
            user_agent=user_agent,
            is_active=True,
            expires_at=expires_at,
        )
        db.add(session)

    db.commit()
    db.refresh(session)
    return token, session


def authenticate_user(db: Session, email: str, password: str) -> User:
    normalized_email = email.strip().lower()
    user = db.query(User).filter(User.email == normalized_email).first()
    if not user or not verify_password(password, user.password_hash):
        raise AuthError("Invalid email or password.", 401)
    if user.status != UserStatus.active:
        raise AuthError("Your account is inactive. Contact support.", 403)
    return user


def login_user(
    db: Session,
    email: str,
    password: str,
    device_id: str,
    device_name: str,
    ip_address: str | None,
    user_agent: str | None,
) -> tuple[User, str]:
    user = authenticate_user(db, email, password)
    token, _session = create_user_session(db, user, device_id, device_name, ip_address, user_agent)
    return user, token


def get_session_from_token(db: Session, token: str) -> UserSession | None:
    token_hash = hash_token(token)
    session = db.query(UserSession).filter(UserSession.token_hash == token_hash, UserSession.is_active.is_(True)).first()
    if not session:
        return None

    now = datetime.now(timezone.utc)
    expires_at = session.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < now:
        session.is_active = False
        db.commit()
        return None

    session.last_active_at = now
    db.commit()
    return session


def logout_user(db: Session, token: str) -> None:
    token_hash = hash_token(token)
    session = db.query(UserSession).filter(UserSession.token_hash == token_hash).first()
    if session:
        session.is_active = False
        db.commit()


def seed_admin_user(db: Session) -> None:
    admin = db.query(User).filter(User.email == settings.admin_email.lower()).first()
    if admin:
        return
    validate_password_strength(settings.admin_password)
    admin = User(
        email=settings.admin_email.lower(),
        password_hash=hash_password(settings.admin_password),
        phone_number=None,
        credits=1000,
        status=UserStatus.active,
        role=UserRole.admin,
    )
    db.add(admin)
    db.commit()
