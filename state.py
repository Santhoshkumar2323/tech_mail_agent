import json
import os
from datetime import datetime, timedelta, timezone


def load_state(state_file: str, default_lookback_days: int) -> dict:
    now = datetime.now(timezone.utc)

    if not os.path.exists(state_file):
        return {
            "window_start": now - timedelta(days=default_lookback_days),
            "window_end": now,
            "sent_ids": set(),
        }

    with open(state_file, "r") as f:
        data = json.load(f)

    last_run_end = datetime.fromisoformat(data["last_run_end"])

    return {
        "window_start": last_run_end,
        "window_end": now,
        "sent_ids": set(data.get("sent_ids", [])),
    }


def save_state(state_file: str, window_end: datetime, sent_ids: set, keep_last_n: int = 500) -> None:
    trimmed_ids = list(sent_ids)[-keep_last_n:]

    data = {
        "last_run_end": window_end.isoformat(),
        "sent_ids": trimmed_ids,
    }

    with open(state_file, "w") as f:
        json.dump(data, f, indent=2)


def time_since_last_run(state_file: str):
    if not os.path.exists(state_file):
        return None

    with open(state_file, "r") as f:
        data = json.load(f)

    last_run_end = datetime.fromisoformat(data["last_run_end"])
    return datetime.now(timezone.utc) - last_run_end


def make_item_id(source: str, identifier: str) -> str:
    return f"{source}:{identifier}"