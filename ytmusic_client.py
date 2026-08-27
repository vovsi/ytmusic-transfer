"""YouTube Music client: fetches the user's liked songs via ytmusicapi."""
from __future__ import annotations

import webbrowser
from dataclasses import dataclass
from pathlib import Path

from ytmusicapi import OAuthCredentials, YTMusic, setup
from ytmusicapi.auth.oauth.token import RefreshingToken, Token

OAUTH_TOKEN_PATH = Path("ytmusic_oauth.json")


@dataclass(frozen=True)
class YTTrack:
    video_id: str
    title: str
    artist: str


def _run_oauth_device_flow(credentials: OAuthCredentials, to_file: Path) -> None:
    """Reimplements ytmusicapi's RefreshingToken.prompt_for_token, dropping any
    token fields it doesn't know about (Google's token endpoint now returns
    "refresh_token_expires_in", which crashes ytmusicapi<1.12 with a
    TypeError -- fixed upstream in 1.12, but that requires Python 3.10+ and
    this project targets 3.9. See https://github.com/sigma67/ytmusicapi/issues/921."""
    code = credentials.get_code()
    url = f"{code['verification_url']}?user_code={code['user_code']}"
    webbrowser.open(url)
    input(f"Go to {url}, finish the login flow and press Enter when done, Ctrl-C to abort")
    raw_token = credentials.token_from_code(code["device_code"])
    known_fields = {k: v for k, v in raw_token.items() if k in Token.members()}
    token = RefreshingToken(credentials=credentials, **known_fields)
    token.update(token.as_dict())
    token.local_cache = to_file


def connect(
    headers_raw: str | None,
    user_id: str | None = None,
    oauth_client_id: str | None = None,
    oauth_client_secret: str | None = None,
) -> YTMusic:
    """Connects via OAuth (auto-refreshing, preferred) if client credentials are
    given, otherwise falls back to pasted browser headers."""
    if oauth_client_id and oauth_client_secret:
        credentials = OAuthCredentials(client_id=oauth_client_id, client_secret=oauth_client_secret)
        if not OAUTH_TOKEN_PATH.is_file():
            print(f"No {OAUTH_TOKEN_PATH} found — starting one-time OAuth setup...")
            _run_oauth_device_flow(credentials, OAUTH_TOKEN_PATH)
        return YTMusic(auth=str(OAUTH_TOKEN_PATH), user=user_id, oauth_credentials=credentials)

    auth = setup(filepath=None, headers_raw=headers_raw)
    return YTMusic(auth=auth, user=user_id)


def get_liked_songs(yt: YTMusic) -> list[YTTrack]:
    """Returns every track in "Liked Music" (paginates internally)."""
    result = yt.get_liked_songs(limit=None)
    tracks = []
    for item in result.get("tracks", []):
        video_id = item.get("videoId")
        if not video_id:
            continue
        artists = item.get("artists") or []
        artist = ", ".join(a["name"] for a in artists if a.get("name")) or "Unknown Artist"
        title = item.get("title") or "Unknown Title"
        tracks.append(YTTrack(video_id=video_id, title=title, artist=artist))
    return tracks
