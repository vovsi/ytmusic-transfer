"""Persists per-track transfer status so repeated runs only touch new tracks."""
from __future__ import annotations

import json
from pathlib import Path

STATE_VERSION = 1


def load_state(path: Path) -> dict:
    if not path.exists():
        return {"version": STATE_VERSION, "processed": {}}
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    data.setdefault("processed", {})
    return data


def save_state(path: Path, state: dict) -> None:
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    tmp.replace(path)
