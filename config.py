"""Loads and validates configuration from .env."""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Config:
    ytmusic_headers_raw: str | None
    ytmusic_oauth_client_id: str | None
    ytmusic_oauth_client_secret: str | None
    ytmusic_user_id: str | None
    soundcloud_oauth_token: str
    soundcloud_datadome_cookie: str | None
    soundcloud_client_id: str | None
    playlist_name: str
    match_threshold: float
    request_delay_ms: int


def load_config() -> Config:
    load_dotenv()

    headers_raw = os.getenv("YTMUSIC_HEADERS_RAW", "").strip() or None
    oauth_client_id = os.getenv("YTMUSIC_OAUTH_CLIENT_ID", "").strip() or None
    oauth_client_secret = os.getenv("YTMUSIC_OAUTH_CLIENT_SECRET", "").strip() or None
    oauth_token = os.getenv("SOUNDCLOUD_OAUTH_TOKEN", "").strip()

    missing = []
    if not headers_raw and not (oauth_client_id and oauth_client_secret):
        missing.append("YTMUSIC_HEADERS_RAW or YTMUSIC_OAUTH_CLIENT_ID+YTMUSIC_OAUTH_CLIENT_SECRET")
    if not oauth_token:
        missing.append("SOUNDCLOUD_OAUTH_TOKEN")
    if missing:
        sys.exit(
            "Missing required .env values: " + ", ".join(missing) +
            "\nSee README.md -> Setup for how to obtain them."
        )

    return Config(
        ytmusic_headers_raw=headers_raw,
        ytmusic_oauth_client_id=oauth_client_id,
        ytmusic_oauth_client_secret=oauth_client_secret,
        ytmusic_user_id=os.getenv("YTMUSIC_USER_ID", "").strip() or None,
        soundcloud_oauth_token=oauth_token,
        soundcloud_datadome_cookie=os.getenv("SOUNDCLOUD_DATADOME_COOKIE", "").strip() or None,
        soundcloud_client_id=os.getenv("SOUNDCLOUD_CLIENT_ID", "").strip() or None,
        playlist_name=os.getenv("SOUNDCLOUD_PLAYLIST_NAME", "Favorite").strip() or "Favorite",
        match_threshold=float(os.getenv("MATCH_THRESHOLD", "75")),
        request_delay_ms=int(os.getenv("REQUEST_DELAY_MS", "300")),
    )
