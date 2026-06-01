from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from config.settings import settings


STATUS_PATH = Path(settings.DATA_DIR) / "feed_status.json"


def write_feed_status(state: str, **details) -> None:
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "state": state,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        **details,
    }
    temp_path = STATUS_PATH.with_suffix(".tmp")
    temp_path.write_text(json.dumps(payload, indent=2))
    temp_path.replace(STATUS_PATH)
