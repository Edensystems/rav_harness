from tests.conftest import _login_payload, _register_payload


def test_register_success(client, device_headers):
    email = "user_a@example.com"
    resp = client.post("/auth/register", json=_register_payload(email), headers=device_headers)
    assert resp.status_code == 201
    body = resp.json()
    assert body["access_token"]
    assert body["user"]["email"] == email
    assert body["user"]["status"] == "active"
    assert body["user"]["credits"] == 0


def test_register_duplicate_email(client, device_headers):
    email = "dup@example.com"
    first = client.post("/auth/register", json=_register_payload(email), headers=device_headers)
    assert first.status_code == 201
    second = client.post("/auth/register", json=_register_payload(email), headers=device_headers)
    assert second.status_code == 409


def test_register_weak_password(client, device_headers):
    resp = client.post(
        "/auth/register",
        json={"email": "weak@example.com", "password": "12345678"},
        headers=device_headers,
    )
    assert resp.status_code == 400


def test_login_success(client, device_headers):
    email = "login_ok@example.com"
    client.post("/auth/register", json=_register_payload(email), headers=device_headers)
    resp = client.post("/auth/login", json=_login_payload(email), headers=device_headers)
    assert resp.status_code == 200
    assert resp.json()["access_token"]


def test_login_wrong_password(client, device_headers):
    email = "login_bad@example.com"
    client.post("/auth/register", json=_register_payload(email), headers=device_headers)
    resp = client.post(
        "/auth/login",
        json=_login_payload(email, password="WrongPass1"),
        headers=device_headers,
    )
    assert resp.status_code == 401


def test_login_inactive_user(client, db_session, device_headers):
    from auth_service import hash_password
    from models import User, UserRole, UserStatus

    email = "inactive@example.com"
    user = User(
        email=email,
        password_hash=hash_password("Password123"),
        status=UserStatus.inactive,
        role=UserRole.user,
        credits=0,
    )
    db_session.add(user)
    db_session.commit()

    resp = client.post("/auth/login", json=_login_payload(email), headers=device_headers)
    assert resp.status_code == 403


def test_single_device_session_enforced(client, device_headers):
    email = "single_device@example.com"
    client.post("/auth/register", json=_register_payload(email), headers=device_headers)

    first = client.post("/auth/login", json=_login_payload(email), headers=device_headers)
    token_a = first.json()["access_token"]

    second_headers = {"X-Device-Id": "test-device-002", "X-Device-Name": "Other Device"}
    second_payload = _login_payload(email, device_id="test-device-002")
    second = client.post("/auth/login", json=second_payload, headers=second_headers)
    token_b = second.json()["access_token"]

    stale = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token_a}", "X-Device-Id": "test-device-001"},
    )
    assert stale.status_code == 401

    active = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token_b}", "X-Device-Id": "test-device-002"},
    )
    assert active.status_code == 200


def test_logout_invalidates_session(client, device_headers):
    email = "logout@example.com"
    client.post("/auth/register", json=_register_payload(email), headers=device_headers)
    login = client.post("/auth/login", json=_login_payload(email), headers=device_headers)
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}", **device_headers}

    out = client.post("/auth/logout", headers=headers)
    assert out.status_code == 200

    me = client.get("/auth/me", headers=headers)
    assert me.status_code == 401


def test_protected_route_without_token(client):
    resp = client.get("/auth/me")
    assert resp.status_code == 401


def test_lists_crud(client, device_headers):
    email = "lists@example.com"
    reg = client.post("/auth/register", json=_register_payload(email), headers=device_headers)
    token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}", **device_headers}

    create = client.post(
        "/api/lists",
        headers=headers,
        json={"name": "Main Targets", "items": ["254711111111", "254722222222"]},
    )
    assert create.status_code == 201
    created = create.json()
    assert created["name"] == "Main Targets"
    assert len(created["items"]) == 2

    all_lists = client.get("/api/lists", headers=headers)
    assert all_lists.status_code == 200
    assert len(all_lists.json()) == 1

    list_id = created["id"]
    add_item = client.post(
        f"/api/lists/{list_id}/items",
        headers=headers,
        json={"value": "254733333333"},
    )
    assert add_item.status_code == 201

    fetched = client.get(f"/api/lists/{list_id}", headers=headers)
    assert fetched.status_code == 200
    assert len(fetched.json()["items"]) == 3

    delete_item_id = fetched.json()["items"][0]["id"]
    deleted = client.delete(f"/api/lists/{list_id}/items/{delete_item_id}", headers=headers)
    assert deleted.status_code == 200

    removed = client.delete(f"/api/lists/{list_id}", headers=headers)
    assert removed.status_code == 200


def test_replace_user_list(client, device_headers):
    email = "replace_list@example.com"
    reg = client.post("/auth/register", json=_register_payload(email), headers=device_headers)
    token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}", **device_headers}

    create = client.post(
        "/api/lists",
        headers=headers,
        json={"name": "Targets", "items": ["111", "222", "111"]},
    )
    list_id = create.json()["id"]

    replace = client.put(
        f"/api/lists/{list_id}",
        headers=headers,
        json={"name": "Targets Clean", "items": ["111", "222", "333"]},
    )
    assert replace.status_code == 200
    body = replace.json()
    assert body["name"] == "Targets Clean"
    assert len(body["items"]) == 3
    assert [item["value"] for item in body["items"]] == ["111", "222", "333"]


def test_task_requires_auth(client):
    resp = client.post(
        "/api/start_task",
        json={
            "task_type": "balance",
            "target_numbers": ["254700000000"],
            "target_password": "secret",
        },
    )
    assert resp.status_code == 401
