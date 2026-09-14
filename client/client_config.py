import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AutomationIdentity:
    id: str
    name: str
    description: str
    environment: str
    category: str = "betting-automation"

    @property
    def dashboard_title(self) -> str:
        return f"{self.name} Dashboard"


def app_dir() -> Path:
    """Folder that contains the exe (frozen) or this source file (dev)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def bundled_dir() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return app_dir()


def load_automation_identity() -> AutomationIdentity:
    return AutomationIdentity(
        id=os.getenv("AUTOMATION_ID", "odibets-automation"),
        name=os.getenv("AUTOMATION_NAME", "Batting Automation Assistant"),
        description=os.getenv(
            "AUTOMATION_DESCRIPTION",
            "Account management, batch operations, and server-side execution control center.",
        ),
        environment=os.getenv("AUTOMATION_ENV", "production"),
    )


def load_server_url() -> str:
    """
    Resolve the API base URL so a packaged exe can point at a hosted server.

    Order: AUTOMATION_SERVER_URL env var, then client.settings.json next to the
    exe, then a bundled copy, then localhost for local development.
    """
    env_url = os.getenv("AUTOMATION_SERVER_URL", "").strip()
    if env_url:
        return env_url.rstrip("/")

    for candidate in (app_dir() / "client.settings.json", bundled_dir() / "client.settings.json"):
        if not candidate.is_file():
            continue
        try:
            data = json.loads(candidate.read_text(encoding="utf-8"))
            url = str(data.get("server_url") or "").strip()
            if url:
                return url.rstrip("/")
        except (OSError, json.JSONDecodeError):
            continue

    return "http://127.0.0.1:8000"
