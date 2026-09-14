from unittest.mock import MagicMock, patch

from schemas import TaskPayload
from server import process_single_user


def test_streak_writes_name_and_available_streak(tmp_path):
    output_path = tmp_path / "streak_output.txt"
    payload = TaskPayload(
        task_type="streak",
        target_numbers=["254700000000"],
        target_password="secret",
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
    api_response = MagicMock()
    api_response.json.return_value = {"status_code": 200, "data": {"current_streak": 12}}
    api_response.raise_for_status.return_value = None

    with (
        patch("server._get_auth_details", return_value=auth),
        patch("server.requests.get", return_value=api_response),
    ):
        process_single_user("254700000000", payload, logs.append, stop_event, str(output_path), job=None)

    assert output_path.read_text(encoding="utf-8") == "254700000000 Streak: 12\n"
    assert any("SUCCESS (Streak)" in line and "12" in line for line in logs)
