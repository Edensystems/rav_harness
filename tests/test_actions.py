from unittest.mock import MagicMock, patch

from schemas import TaskPayload
from server import process_single_user
from tests.conftest import _login_payload, _register_payload


def test_billing_catalog_includes_new_actions_enabled(client, auth_headers):
    resp = client.get("/api/billing", headers=auth_headers)
    assert resp.status_code == 200
    rates = {item["task_type"]: item for item in resp.json()["rates"]}
    for task_type in ("withdrawal", "cashout", "virtual_bet", "rollover"):
        assert task_type in rates
        assert rates[task_type]["enabled"] is True


def test_admin_can_disable_action(client, db_session, device_headers, monkeypatch):
    from auth_service import hash_password
    from models import User, UserRole, UserStatus

    admin = User(
        email="actions-admin@example.com",
        password_hash=hash_password("AdminPass123"),
        status=UserStatus.active,
        role=UserRole.admin,
        credits=0,
    )
    db_session.add(admin)
    db_session.commit()
    login = client.post(
        "/auth/login",
        json=_login_payload("actions-admin@example.com", password="AdminPass123"),
        headers=device_headers,
    )
    headers = {**device_headers, "Authorization": f"Bearer {login.json()['access_token']}"}

    disabled = client.put(
        "/admin/actions",
        headers=headers,
        json={"task_type": "withdrawal", "enabled": False},
    )
    assert disabled.status_code == 200
    assert disabled.json()["enabled"] is False

    monkeypatch.setattr("server.run_automation_engine", lambda *args, **kwargs: None)
    user = client.post(
        "/auth/register",
        json=_register_payload("action-user@example.com"),
        headers={"X-Device-Id": "action-device-001", "X-Device-Name": "Other"},
    )
    user_headers = {
        "X-Device-Id": "action-device-001",
        "X-Device-Name": "Other",
        "Authorization": f"Bearer {user.json()['access_token']}",
    }
    blocked = client.post(
        "/api/start_task",
        headers=user_headers,
        json={
            "task_type": "withdrawal",
            "target_numbers": ["254700000000"],
            "target_password": "secret",
            "amount": "50",
        },
    )
    assert blocked.status_code == 423


def test_withdrawal_requires_amount(client, auth_headers):
    resp = client.post(
        "/api/start_task",
        headers=auth_headers,
        json={
            "task_type": "withdrawal",
            "target_numbers": ["254700000000"],
            "target_password": "secret",
        },
    )
    assert resp.status_code == 400


def test_cashout_starts_without_bet_id(client, auth_headers, monkeypatch):
    monkeypatch.setattr("server.run_automation_engine", lambda *args, **kwargs: None)
    resp = client.post(
        "/api/start_task",
        headers=auth_headers,
        json={
            "task_type": "cashout",
            "target_numbers": ["254700000000"],
            "target_password": "secret",
        },
    )
    assert resp.status_code == 200
    assert "cashout_output_" in resp.json()["output_filename"]


def test_withdrawal_skeleton_writes_output(tmp_path):
    output_path = tmp_path / "withdrawal.txt"
    payload = TaskPayload(
        task_type="withdrawal",
        target_numbers=["254700000000"],
        target_password="secret",
        amount="25",
    )
    logs = []
    stop_event = MagicMock()
    stop_event.is_set.return_value = False
    auth = {
        "access_token": "tok",
        "session_token": "sess",
        "cookies": {"odibetskenya": "abc"},
        "ua": "Mozilla/5.0",
        "data": {},
    }
    with patch("server._get_auth_details", return_value=auth):
        process_single_user("254700000000", payload, logs.append, stop_event, str(output_path), job=None)
    assert "254700000000 Withdrawal: 25" in output_path.read_text(encoding="utf-8")
    assert any("SKELETON (Withdrawal)" in line for line in logs)


def test_cashout_skeleton_writes_output(tmp_path):
    output_path = tmp_path / "cashout.txt"
    payload = TaskPayload(
        task_type="cashout",
        target_numbers=["254700000000"],
        target_password="secret",
        bet_id="BET123",
    )
    logs = []
    stop_event = MagicMock()
    stop_event.is_set.return_value = False
    auth = {
        "access_token": "tok",
        "session_token": "sess",
        "cookies": {"odibetskenya": "abc"},
        "ua": "Mozilla/5.0",
        "data": {},
    }
    with patch("server._get_auth_details", return_value=auth):
        process_single_user("254700000000", payload, logs.append, stop_event, str(output_path), job=None)
    assert "254700000000 Cashout: BET123" in output_path.read_text(encoding="utf-8")
