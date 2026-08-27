# ytmusic-transfer — project notes for Claude

One-shot CLI script: reads YouTube Music "Liked Music", finds each track on
SoundCloud by search, adds matches to a SoundCloud playlist ("Favorite" by
default). No downloading. Pure Python, flat file layout, no package/src dir.

## Files

- `main.py` — orchestration, CLI args, progress bar, checkpointing.
- `config.py` — `.env` loading/validation (`Config` dataclass).
- `ytmusic_client.py` — wraps `ytmusicapi`; `connect()` + `get_liked_songs()`.
- `soundcloud_client.py` — hand-rolled client for SoundCloud's unofficial
  `api-v2.soundcloud.com`; `SoundCloudClient` with search/playlist methods.
- `matcher.py` — title/artist normalization + `rapidfuzz` fuzzy matching.
- `state.py` — `state.json` load/save (atomic write via tmp+replace).

## Credentials (all via `.env`, see `.env.example`)

- `YTMUSIC_OAUTH_CLIENT_ID` / `YTMUSIC_OAUTH_CLIENT_SECRET`: preferred auth
  path, added after `YTMUSIC_HEADERS_RAW` browser cookies turned out to get
  invalidated within a single working session (confirmed live 2026-08-26 —
  worked, then a fresh `--dry-run` minutes later hit `401 Unauthorized` with
  no code change; suspected cause: burst of debug script requests during
  troubleshooting tripped Google's abuse detection, but browser-cookie auth
  is inherently short-lived regardless). Uses `ytmusicapi`'s OAuth device
  flow (`OAuthCredentials` + `setup_oauth`, both re-exported from the
  top-level `ytmusicapi` package) — the same flow YouTube uses for TV/limited
  -input-device sign-in. `ytmusic_client.connect()` checks for both vars; if
  present, it uses OAuth and ignores `YTMUSIC_HEADERS_RAW` entirely.
  - Client ID/secret come from a **Google Cloud Console** OAuth client of
    type "TVs and Limited Input devices" (user must create this themselves —
    a few clicks, free, no billing needed).
  - `ytmusic_client.OAUTH_TOKEN_PATH` (`ytmusic_oauth.json`, gitignored) is
    created on first run via `setup_oauth(..., open_browser=True)` — prints
    a URL + code, blocks until the user approves in a browser. Every run
    after that loads the cached refresh token from that file and
    `RefreshingToken` (inside ytmusicapi) auto-refreshes the access token as
    needed — no more manual re-copying.
  - Passed to `YTMusic(auth=str(OAUTH_TOKEN_PATH), oauth_credentials=...)`.
    Unverified against a live long-running instance beyond initial setup —
    if refresh ever fails, check `ytmusic_oauth.json`'s `refresh_token`
    field is still present and non-empty.
  - **`ytmusicapi`'s own `setup_oauth()`/`RefreshingToken.prompt_for_token()`
    is NOT used** — it crashes (confirmed live, 2026-08-26):
    `TypeError: __init__() got an unexpected keyword argument
    'refresh_token_expires_in'`. Google's OAuth token endpoint now returns
    that extra field; ytmusicapi's `Token` dataclass doesn't have it and
    `prompt_for_token` does `cls(credentials=credentials, **raw_token)` with
    no filtering. Fixed upstream in ytmusicapi 1.12 (PR #932, GitHub issue
    #921), **but 1.12 requires Python >=3.10** and this project's `.venv` is
    3.9.6 (`pip install --upgrade` confirmed no 3.9-compatible release past
    1.10.3 exists). Rather than force a Python upgrade, `_run_oauth_device_flow`
    in `ytmusic_client.py` reimplements the same device-code flow inline,
    filtering `raw_token` down to `Token.members()` before constructing
    `RefreshingToken` — same behavior, just drops the unknown field. If this
    project's `.venv` is ever rebuilt on Python 3.10+, this workaround can be
    deleted in favor of plain `ytmusicapi.setup_oauth()`.
- `YTMUSIC_HEADERS_RAW`: fallback, only used when the OAuth vars above are
  both empty. Raw browser request headers pasted as-is. Passed to
  `ytmusicapi.setup(filepath=None, headers_raw=...)`, which returns a **JSON
  string** (not a dict) — that string is passed straight to `YTMusic(auth=...)`;
  `YTMusic` detects a string starting with `{` and `json.loads`s it itself
  (see `parse_auth_str` in ytmusicapi's source). Verified against the
  installed package source (ytmusicapi ~1.x) in this session, not just docs.
  - `setup_browser` only *raises* if `cookie` or `x-goog-authuser` is
    missing, but `authorization` (the `SAPISIDHASH ...` header, copied from
    a real POST request to `/youtubei/v1/...`) **must also be pasted**.
    Verified against installed `ytmusicapi==1.10.3` source
    (`auth/auth_parse.py`, `determine_auth_type`): it only assigns
    `AuthType.BROWSER` when an `authorization` header containing
    `SAPISIDHASH` is already present in the parsed headers. Only *after*
    that classification does `YTMusic` recompute a fresh `SAPISIDHASH` per
    request from the cookie (`ytmusic.py`, `_send_request`). Without an
    `authorization` header up front, `determine_auth_type` falls back to
    `AuthType.OAUTH_CUSTOM_CLIENT` and `YTMusic(auth=...)` raises
    `YTMusicUserError: oauth JSON provided ... but oauth_credentials not
    provided` — this superseded an earlier (wrong) note in this file
    claiming `Authorization` didn't need to be pasted.
  - Credentials are valid as long as the browser session is (reportedly
    ~2 years unless the user logs out) — no refresh flow implemented, none
    needed for this use case.
  - `get_liked_songs(limit=None)` paginates internally and returns everything
    (confirmed via source: it's `get_playlist("LM", limit)`, and
    `get_playlist`'s docstring explicitly states `None` retrieves all).
- `YTMUSIC_USER_ID`: optional, only needed when "Liked Music" lives on a
  YouTube **Brand Account** (a secondary channel switched via the avatar
  menu on music.youtube.com — distinct from having multiple Google accounts
  logged in, which is what `X-Goog-AuthUser` selects). Passed as
  `YTMusic(auth=..., user=...)`. Symptom when missing on such an account:
  `get_liked_songs` connects fine (`auth_type == BROWSER`, no auth error)
  but returns `trackCount: 0` / `owned: False`, even though the browser UI
  shows liked tracks — confirmed live during setup: `X-Goog-AuthUser` 0-3 all
  returned empty (valid sessions, no sign-in prompt) while the account
  visibly had liked songs in the browser. Get the ID from
  `myaccount.google.com/brandaccounts` → select the channel → the number in
  the URL after `/b/`.
- `SOUNDCLOUD_OAUTH_TOKEN`: the user's personal OAuth token, extracted from
  their own browser session (`Authorization: OAuth ...` header on any
  `api-v2.soundcloud.com` request). No app registration involved — SoundCloud
  closed public API signups years ago.
- `SOUNDCLOUD_CLIENT_ID`: optional. `SoundCloudClient._discover_client_id()`
  auto-scrapes it from soundcloud.com's own web JS bundles (fetches the
  homepage, regexes `<script src>` URLs under `a-v2.sndcdn.com/assets/`, then
  regexes `client_id:"..."` out of each). This trick is borrowed from how
  `soundcloud.ts` (an OSS wrapper) does it. If SoundCloud changes their CDN
  host or JS bundling, this regex is the first thing to fix.

## SoundCloud API — known-uncertain areas

`api-v2.soundcloud.com` is entirely undocumented (reverse-engineered from the
web client). These endpoints/shapes were corroborated across multiple
independent sources (gists, OSS wrapper repos, official-docs analogues) during
research, but **not verified against a live account** — if something breaks,
start here:

- `GET /search/tracks?q=...&limit=...` — search, returns
  `{"collection": [{id, title, user: {username}, ...}], "next_href": ...}`.
  Fairly high confidence, this shape is stable/well-known.
- `GET /users/:id/playlists?limit=100&linked_partitioning=1` — the user's own
  playlists, paginated via `next_href`. **Confirmed live** against a real
  account (2026-08-26): `/me/playlists` and `/me/library/playlists` both
  404 on v2 — there is no `/me/...`-prefixed playlists route. The user's own
  numeric id is fetched once from `GET /me` (`SoundCloudClient.__init__`
  stores it as `self.user_id`) and substituted into the path.
  `/users/:id/playlists/liked_and_owned` also works but includes playlists
  the user merely *likes*, not just owns — not used here since we only need
  the user's own "Favorite" playlist.
- `GET /playlists/:id?representation=full` — full playlist incl. `tracks`
  (each with at least an `id`).
- `POST /playlists` and `PUT /playlists/:id` with body
  `{"playlist": {"title": ..., "sharing": ..., "tracks": [{"id": <int>}, ...]}}`
  — **lowest confidence** part of this project. This mirrors the officially
  documented (but no-longer-registerable) `api.soundcloud.com` v1 payload
  shape; v2 is assumed to accept the same shape since it's a broad superset of
  v1 for the same resources, but this was never confirmed live. There is no
  documented endpoint to add a *single* track — the whole `tracks` array must
  be resent on every update, hence `main.py` fetches existing track ids once
  and always PUTs the full accumulated list.
  - `soundcloud_client.SoundCloudClient._request` raises `SoundCloudError`
    with the response status + body text on any non-2xx response — if the
    payload shape is wrong, the error message from a real run will show
    SoundCloud's actual complaint, which is the fastest way to fix this.

## `state.json` schema

```json
{
  "version": 1,
  "processed": {
    "<youtube-video-id>": {
      "title": "Artist - Title",
      "status": "added" | "not_found",
      "soundcloud_track_id": 123456,
      "score": 87.5
    }
  }
}
```

`main.py` only marks an entry `"added"` *after* a successful playlist PUT
(checkpointed every `--checkpoint-every` matches, default 25, and flushed
again in a `finally` block on exit/interrupt/exception) — so state never
claims a track was added when the playlist update actually failed partway.
`"not_found"` entries are skipped on future runs unless `--retry-failed`.

## Matching

`matcher.normalize()` strips bracketed noise tags (`official`, `video`,
`audio`, `lyrics`, `remaster*`, `hd`, `hq`, `explicit`, `clean`) and
punctuation, then `matcher.best_match()` scores `"<artist> <title>"` against
each SoundCloud candidate with `rapidfuzz.fuzz.token_sort_ratio` (order-
insensitive token comparison — handles "Artist - Title" vs "Title by Artist"
style differences). Default acceptance threshold: 75/100, via
`MATCH_THRESHOLD` in `.env`.

## Testing note

There is no committed test suite (kept out per "don't create excess" — this
is a small personal script, not a library). The orchestration logic in
`main.py` (resume/skip, checkpointing, `--dry-run`, `--retry-failed`) was
verified during development with a throwaway mocked-client smoke test, not
against real YouTube Music / SoundCloud accounts — nobody has run this
end-to-end against live APIs yet. If you're picking this project back up,
that live first-run is the highest-value next step, ideally with
`--dry-run --limit 10` first.
