from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql://postgres:postgres@localhost:5432/odibets"
    secret_key: str = "change-me-in-production-use-openssl-rand-hex-32"
    session_expire_hours: int = 24
    bcrypt_rounds: int = 12
    admin_email: str = "admin@odibets.local"
    admin_password: str = "AdminPass123!"
    cors_origins: str = "*"


settings = Settings()
