from tests.conftest import _login_payload, _register_payload


def test_payment_options_require_auth(client):
    resp = client.get("/api/billing/payments")
    assert resp.status_code == 401


def test_payment_options_from_env(client, auth_headers, monkeypatch):
    monkeypatch.setenv("PAYMENT_CRYPTO_COIN", "USDT")
    monkeypatch.setenv("PAYMENT_CRYPTO_NETWORK", "TRC20")
    monkeypatch.setenv("PAYMENT_CRYPTO_ADDRESS", "TExampleWalletAddress123")
    monkeypatch.setenv("PAYMENT_WHATSAPP_NUMBER", "+254700000000")
    monkeypatch.setenv(
        "PAYMENT_WHATSAPP_MESSAGE",
        "Hi, add credits for {email}. Balance {credits}.",
    )
    resp = client.get("/api/billing/payments", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["crypto"]["configured"] is True
    assert body["crypto"]["coin"] == "USDT"
    assert body["crypto"]["network"] == "TRC20"
    assert body["crypto"]["address"] == "TExampleWalletAddress123"
    assert body["whatsapp"]["configured"] is True
    assert body["whatsapp"]["number"] == "254700000000"
    assert "dashboard@example.com" in body["whatsapp"]["message"]
    assert body["whatsapp"]["url"].startswith("https://wa.me/254700000000?text=")


def test_admin_can_update_payment_settings(client, db_session, device_headers, monkeypatch):
    from auth_service import hash_password
    from models import User, UserRole, UserStatus

    monkeypatch.delenv("PAYMENT_CRYPTO_ADDRESS", raising=False)
    admin = User(
        email="pay-admin@example.com",
        password_hash=hash_password("AdminPass123"),
        status=UserStatus.active,
        role=UserRole.admin,
        credits=0,
    )
    db_session.add(admin)
    db_session.commit()
    login = client.post(
        "/auth/login",
        json=_login_payload("pay-admin@example.com", password="AdminPass123"),
        headers=device_headers,
    )
    headers = {**device_headers, "Authorization": f"Bearer {login.json()['access_token']}"}

    updated = client.put(
        "/admin/payments",
        headers=headers,
        json={
            "crypto_coin": "BTC",
            "crypto_network": "BTC",
            "crypto_address": "bc1exampleaddress",
            "whatsapp_number": "254711111111",
            "whatsapp_message": "Need credits for {email}",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["crypto_coin"] == "BTC"
    assert updated.json()["crypto_address"] == "bc1exampleaddress"

    listed = client.get("/admin/payments", headers=headers)
    assert listed.status_code == 200
    assert listed.json()["whatsapp_number"] == "254711111111"
