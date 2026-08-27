"""Minimal client for SoundCloud's undocumented api-v2 - just enough to
search tracks and manage a single playlist's track list.

SoundCloud closed public API registration years ago; this mirrors what
soundcloud.com's own web player calls internally. See CLAUDE.md for the
endpoints this relies on and which parts are unverified assumptions.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass

import requests as plain_requests
from curl_cffi import requests

API_V2 = "https://api-v2.soundcloud.com"
WEB_URL = "https://soundcloud.com"

_IMPERSONATE = "chrome124"
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


@dataclass(frozen=True)
class SCTrack:
    id: int
    title: str
    artist: str


class SoundCloudError(RuntimeError):
    pass


class SoundCloudClient:
    def __init__(
        self,
        oauth_token: str,
        client_id: str | None = None,
        request_delay_ms: int = 300,
        datadome_cookie: str | None = None,
    ):
        self.client_id = client_id or self._discover_client_id()
        self.request_delay = request_delay_ms / 1000
        self.session = requests.Session(impersonate=_IMPERSONATE)
        self.session.headers.update({
            "Authorization": f"OAuth {oauth_token}",
            "User-Agent": _USER_AGENT,
            "Referer": f"{WEB_URL}/",
            "Origin": WEB_URL,
        })
        if datadome_cookie:
            self.session.cookies.set("datadome", datadome_cookie, domain=".soundcloud.com")
        self.user_id = self._request("GET", "/me").json()["id"]

    @staticmethod
    def _discover_client_id() -> str:
        """Scrapes soundcloud.com's own web assets for the client_id its
        web player uses, so users don't have to extract one by hand."""
        html = plain_requests.get(WEB_URL, timeout=15, headers={"User-Agent": _USER_AGENT}).text
        script_urls = re.findall(r'https://a-v2\.sndcdn\.com/assets/[^\s"\']+\.js', html)
        for url in script_urls:
            js = plain_requests.get(url, timeout=15).text
            match = re.search(r'client_id\s*:\s*"([a-zA-Z0-9]+)"', js)
            if match:
                return match.group(1)
        raise SoundCloudError(
            "Could not auto-discover a SoundCloud client_id. "
            "Set SOUNDCLOUD_CLIENT_ID manually in .env (see README.md)."
        )

    def _request(self, method: str, path: str, **kwargs) -> requests.Response:
        params = kwargs.pop("params", None) or {}
        params["client_id"] = self.client_id
        url = path if path.startswith("http") else f"{API_V2}{path}"
        response = self.session.request(method, url, params=params, timeout=20, **kwargs)
        time.sleep(self.request_delay)
        if not response.ok:
            raise SoundCloudError(f"{method} {url} -> {response.status_code}: {response.text[:500]}")
        return response

    def search_tracks(self, query: str, limit: int = 5) -> list[SCTrack]:
        data = self._request("GET", "/search/tracks", params={"q": query, "limit": limit}).json()
        tracks = []
        for item in data.get("collection", []):
            user = item.get("user") or {}
            tracks.append(SCTrack(
                id=item["id"],
                title=item.get("title") or "",
                artist=user.get("username") or "",
            ))
        return tracks

    def find_playlist_by_title(self, title: str) -> dict | None:
        path = f"/users/{self.user_id}/playlists"
        params = {"limit": 100, "linked_partitioning": 1}
        while path:
            data = self._request("GET", path, params=params).json()
            for playlist in data.get("collection", []):
                if playlist.get("title") == title:
                    return playlist
            path = data.get("next_href")
            params = {}
        return None

    def create_playlist(self, title: str, sharing: str = "private") -> dict:
        body = {"playlist": {"title": title, "sharing": sharing, "tracks": []}}
        return self._request("POST", "/playlists", json=body).json()

    def get_playlist_track_ids(self, playlist_id: int) -> list[int]:
        data = self._request("GET", f"/playlists/{playlist_id}", params={"representation": "full"}).json()
        return [t["id"] for t in data.get("tracks", []) if "id" in t]

    def set_playlist_tracks(self, playlist_id: int, track_ids: list[int]) -> None:
        body = {"playlist": {"tracks": [{"id": tid} for tid in track_ids]}}
        self._request("PUT", f"/playlists/{playlist_id}", json=body)
