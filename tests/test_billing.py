from billing_service import charge_successful_action, seed_action_rates, set_action_rate
from tests.conftest import _login_payload, _register_payload


def test_billing_catalog_marks_bet_as_billable(client, auth_headers):
    resp = client.get("/api/billing", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    rates = {item["task_type"]: item for item in body["rates"]}
    assert rates["bet"]["billable"] is True
    assert rates["bet"]["rate"] == 1
    assert rates["balance"]["billable"] is False
    assert body["credits"] == 0


def test_billable_bet_requires_credits(client, auth_headers):
    resp = client.post(
        "/api/start_task",
        headers=auth_headers,
        json={
            "task_type": "bet",
            "target_numbers": ["254700000000"],
            "target_password": "secret",
            "share_code": "ABC123",
            "amount": "10",
        },
    )
    assert resp.status_code == 402


def test_free_action_is_not_billable(client, auth_headers):
    resp = client.get("/api/billing", headers=auth_headers)
    rates = {item["task_type"]: item for item in resp.json()["rates"]}
    assert rates["balance"]["billable"] is False
    assert rates["balance"]["rate"] == 0


def test_admin_can_update_claim_rate_and_grant_credits(client, db_session, device_headers):
    from auth_service import hash_password
    from models import User, UserRole, UserStatus

    admin = User(
        email="billing-admin@example.com",
        password_hash=hash_password("AdminPass123"),
        status=UserStatus.active,
        role=UserRole.admin,
        credits=0,
    )
    db_session.add(admin)
    db_session.commit()

    login = client.post(
        "/auth/login",
        json=_login_payload("billing-admin@example.com", password="AdminPass123"),
        headers=device_headers,
    )
    headers = {**device_headers, "Authorization": f"Bearer {login.json()['access_token']}"}

    seeded_user = client.post(
        "/auth/register",
        json=_register_payload("billed@example.com"),
        headers={"X-Device-Id": "other-device-001", "X-Device-Name": "Other"},
    )
    user_id = seeded_user.json()["user"]["id"]

    grant = client.patch(
        f"/admin/users/{user_id}/credits",
        headers=headers,
        json={"credits": 12.5},
    )
    assert grant.status_code == 200
    assert grant.json()["credits"] == 12.5

    rate = client.put("/admin/billing", headers=headers, json={"task_type": "claim", "rate": 0.5})
    assert rate.status_code == 200
    assert rate.json()["rate"] == 0.5
    assert rate.json()["billable"] is True


def test_successful_action_deducts_configured_rate(db_session):
    from auth_service import hash_password
    from models import User, UserRole, UserStatus

    seed_action_rates(db_session)
    user = User(
        email="charge-me@example.com",
        password_hash=hash_password("Password123"),
        status=UserStatus.active,
        role=UserRole.user,
        credits=5,
    )
    db_session.add(user)
    db_session.commit()

    first = charge_successful_action(user.id, "bet", "job-1", 1, db=db_session)
    assert first.charged is True
    assert float(first.balance) == 4

    db_session.refresh(user)
    assert float(user.credits) == 4

    set_action_rate(db_session, "claim", 0.5)
    second = charge_successful_action(user.id, "claim", "job-2", 0.5, db=db_session)
    assert second.charged is True
    db_session.refresh(user)
    assert float(user.credits) == 3.5
