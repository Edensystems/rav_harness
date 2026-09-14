import json
import os
import uuid
from pathlib import Path

DEVICE_DIR = Path.home() / ".odibets_client"
DEVICE_FILE = DEVICE_DIR / "device.json"


def get_device_id() -> str:
    DEVICE_DIR.mkdir(parents=True, exist_ok=True)
    if DEVICE_FILE.exists():
        try:
            data = json.loads(DEVICE_FILE.read_text(encoding="utf-8"))
            device_id = data.get("device_id")
            if device_id:
                return device_id
        except (json.JSONDecodeError, OSError):
            pass

    device_id = str(uuid.uuid4())
    DEVICE_FILE.write_text(json.dumps({"device_id": device_id}, indent=2), encoding="utf-8")
    return device_id


def get_device_name() -> str:
    return f"{os.environ.get('COMPUTERNAME') or os.environ.get('HOSTNAME') or 'Desktop'}-Client"
