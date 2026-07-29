import json
import os
from datetime import datetime, timedelta, timezone


def load_state(state_file: str, default_lookback_days: int) -> dict:
    """
    Loads last_run.json if it exists. If not (first-ever run), falls back
    to a default lookback window.

    Returns a dict with:
      - window_start: datetime to fetch items FROM
      - window_end: datetime to fetch items UP TO (now)
      - sent_ids: set of item IDs already sent in previous runs (for dedup)
    """
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
    """
    Writes the new state after a successful run.
    Keeps only the most recent `keep_last_n` sent_ids to stop the file
    from growing unbounded over time.
    """
    trimmed_ids = list(sent_ids)[-keep_last_n:]

    data = {
        "last_run_end": window_end.isoformat(),
        "sent_ids": trimmed_ids,
    }

    with open(state_file, "w") as f:
        json.dump(data, f, indent=2)


def make_item_id(source: str, identifier: str) -> str:
    """
    Builds a consistent dedup key, e.g. 'arxiv:2507.12345' or 'github:owner/repo'.
    """
    return f"{source}:{identifier}"