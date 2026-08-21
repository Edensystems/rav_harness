import os

import pytest

POSTGRES_TEST_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/odibets_test",
)


def _pick_test_database_url() -> tuple[str, bool]:
    try:
        from sqlalchemy import create_engine, text

        engine = create_engine(POSTGRES_TEST_URL)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        engine.dispose()
        return POSTGRES_TEST_URL, True
    except Exception:
        return "sqlite://", False


TEST_DATABASE_URL, USING_POSTGRES = _pick_test_database_url()
os.environ["DATABASE_URL"] = TEST_DATABASE_URL

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from auth_service import hash_password
from database import Base, get_db
from models import User, UserRole, UserStatus


def _database_available() -> bool:
    return True


@pytest.fixture(scope="session")
def engine():
    kwargs = {}
    if TEST_DATABASE_URL.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
        kwargs["poolclass"] = StaticPool
    engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True, **kwargs)
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture()
def db_session(engine):
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()
    for table in reversed(Base.metadata.sorted_tables):
        session.execute(table.delete())
    session.commit()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(db_session):
    from server import app

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def device_headers():
    return {"X-Device-Id": "test-device-001", "X-Device-Name": "Pytest Client"}


@pytest.fixture()
def auth_headers(client, device_headers):
    """An authenticated request context for endpoints protected by get_current_user."""
    email = "dashboard@example.com"
    client.post("/auth/register", json=_register_payload(email), headers=device_headers)
    response = client.post("/auth/login", json=_login_payload(email), headers=device_headers)
    assert response.status_code == 200
    return {**device_headers, "Authorization": f"Bearer {response.json()['access_token']}"}


def _register_payload(email: str, password: str = "Password123"):
    return {"email": email, "password": password, "phone_number": "+254700000000"}


def _login_payload(email: str, password: str = "Password123", device_id: str = "test-device-001"):
    return {
        "email": email,
        "password": password,
        "device_id": device_id,
        "device_name": "Pytest Client",
    }
