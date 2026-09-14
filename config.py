import os

from dotenv import dotenv_values
from pydantic_settings import BaseSettings, SettingsConfigDict

MIN_TASK_CONNECTIONS = 1
MAX_TASK_CONNECTIONS = 50
DEFAULT_TASK_CONNECTIONS = 3


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql://postgres:postgres@localhost:5432/odibets"
    secret_key: str = "change-me-in-production-use-openssl-rand-hex-32"
    session_expire_hours: int = 24
    bcrypt_rounds: int = 12
    admin_email: str = "admin@odibets.local"
    admin_password: str = "AdminPass123!"
    cors_origins: str = "*"
    task_connections: int = DEFAULT_TASK_CONNECTIONS
    payment_crypto_coin: str = "USDT"
    payment_crypto_network: str = "TRC20"
    payment_crypto_address: str = ""
    payment_whatsapp_number: str = ""
    payment_whatsapp_message: str = (
        "Hi, I want to add credits to my account ({email}). Current balance: {credits}."
    )


settings = Settings()


def _clamp_connections(value: int) -> int:
    return max(MIN_TASK_CONNECTIONS, min(int(value), MAX_TASK_CONNECTIONS))


def get_task_connections() -> int:
    """Read TASK_CONNECTIONS live so env/admin/.env changes apply to the next job."""
    raw = os.getenv("TASK_CONNECTIONS")
    if raw is None or str(raw).strip() == "":
        raw = dotenv_values(".env").get("TASK_CONNECTIONS")
    if raw is None or str(raw).strip() == "":
        raw = settings.task_connections
    try:
        return _clamp_connections(int(str(raw).strip()))
    except (TypeError, ValueError):
        return DEFAULT_TASK_CONNECTIONS


def set_task_connections(value: int) -> int:
    clamped = _clamp_connections(value)
    os.environ["TASK_CONNECTIONS"] = str(clamped)
    return clamped
