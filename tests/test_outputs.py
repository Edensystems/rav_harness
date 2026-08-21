import os

from models import TaskOutput, User
from tests.conftest import _register_payload


def test_outputs_list_and_detail(client, device_headers, db_session):
    email = "outputs@example.com"
    client.post("/auth/register", json=_register_payload(email), headers=device_headers)
    user = db_session.query(User).filter(User.email == email).first()

    output_path = "server_outputs/test_balance_output.txt"
    os.makedirs("server_outputs", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as handle:
        handle.write("254700000001 Actual: 10.00 | Bonus: 0.00\n")

    record = TaskOutput(
        user_id=user.id,
        job_id="test-job-001",
        task_type="balance",
        filename=os.path.basename(output_path),
        file_path=output_path,
        status="completed",
        processed=1,
        total=1,
        file_size=os.path.getsize(output_path),
    )
    db_session.add(record)
    db_session.commit()
    db_session.refresh(record)

    token = client.post(
        "/auth/login",
        json={
            "email": email,
            "password": "Password123",
            "device_id": "test-device-001",
            "device_name": "Pytest Client",
        },
        headers=device_headers,
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}", **device_headers}

    listing = client.get("/api/outputs", headers=headers)
    assert listing.status_code == 200
    outputs = listing.json()
    assert len(outputs) == 1
    assert outputs[0]["task_type"] == "balance"

    detail = client.get(f"/api/outputs/{record.id}", headers=headers)
    assert detail.status_code == 200
    body = detail.json()
    assert "254700000001" in body["content"]

    if os.path.exists(output_path):
        os.remove(output_path)
