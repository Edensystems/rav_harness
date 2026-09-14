from config import get_task_connections, set_task_connections
from tests.conftest import _login_payload, _register_payload


def test_task_connections_reads_live_env(monkeypatch):
    monkeypatch.setenv("TASK_CONNECTIONS", "8")
    assert get_task_connections() == 8

    monkeypatch.setenv("TASK_CONNECTIONS", "not-a-number")
    assert get_task_connections() == 3

    monkeypatch.setenv("TASK_CONNECTIONS", "999")
    assert get_task_connections() == 50


def test_set_task_connections_updates_env(monkeypatch):
    monkeypatch.delenv("TASK_CONNECTIONS", raising=False)
    assert set_task_connections(6) == 6
    assert get_task_connections() == 6


def test_admin_can_update_connections(client, db_session, device_headers, monkeypatch):
    from auth_service import hash_password
    from models import User, UserRole, UserStatus

    monkeypatch.setenv("TASK_CONNECTIONS", "3")
    admin = User(
        email="connections-admin@example.com",
        password_hash=hash_password("AdminPass123"),
        status=UserStatus.active,
        role=UserRole.admin,
        credits=0,
    )
    db_session.add(admin)
    db_session.commit()

    login = client.post(
        "/auth/login",
        json=_login_payload("connections-admin@example.com", password="AdminPass123"),
        headers=device_headers,
    )
    headers = {**device_headers, "Authorization": f"Bearer {login.json()['access_token']}"}

    listed = client.get("/admin/connections", headers=headers)
    assert listed.status_code == 200
    assert listed.json()["connections"] == 3

    updated = client.put("/admin/connections", headers=headers, json={"connections": 7})
    assert updated.status_code == 200
    assert updated.json()["connections"] == 7
    assert get_task_connections() == 7


def test_start_task_ignores_client_connections(client, auth_headers, monkeypatch):
    import server

    monkeypatch.setenv("TASK_CONNECTIONS", "4")
    monkeypatch.setattr(server, "run_automation_engine", lambda *args, **kwargs: None)
    resp = client.post(
        "/api/start_task",
        headers=auth_headers,
        json={
            "task_type": "balance",
            "target_numbers": ["254700000000"],
            "target_password": "secret",
            "connections": 40,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["connections"] == 4
