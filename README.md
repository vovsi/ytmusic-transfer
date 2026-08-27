# ytmusic-transfer

Transfers your YouTube Music **"Liked Music"** playlist into a SoundCloud playlist
called **"Favorite"** (created automatically if it doesn't exist).

For every liked track, it searches SoundCloud by title/artist and adds the best
match. Nothing is downloaded — only track references are added to the playlist.

Safe to re-run any time: already-transferred tracks are remembered in
`state.json`, so a second run only picks up songs you liked since the last run.

## Requirements

- Python 3.9+
- A YouTube Music account with liked songs
- A SoundCloud account

## Setup

```bash
git clone <this-repo-url>
cd ytmusic-transfer
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

Now fill in `.env` with the credentials below.

### 1. YouTube Music credentials

**Preferred: OAuth (`YTMUSIC_OAUTH_CLIENT_ID` / `YTMUSIC_OAUTH_CLIENT_SECRET`)**

Browser-cookie auth (below) can get invalidated unpredictably — OAuth uses a
refresh token instead, so once it's set up you shouldn't need to touch it
again.

1. Go to [Google Cloud Console → Credentials](https://console.cloud.google.com/apis/credentials)
   (create a project first if you don't have one — it's free).
2. **Create Credentials → OAuth client ID** → Application type
   **"TVs and Limited Input devices"** → Create.
3. Copy the generated **Client ID** and **Client Secret** into
   `YTMUSIC_OAUTH_CLIENT_ID` / `YTMUSIC_OAUTH_CLIENT_SECRET` in `.env`.
4. Run the script (`python main.py --dry-run --limit 10` is a good first
   try). On first run it prints a URL and a code — open the URL, enter the
   code, approve access. This creates `ytmusic_oauth.json` (gitignored),
   which is reused (and auto-refreshed) on every future run — no more
   copying anything.

**Fallback: raw browser headers (`YTMUSIC_HEADERS_RAW`)**

Only used if the OAuth vars above are left empty. Expires/gets invalidated
much sooner than OAuth, and needs to be redone by hand each time that
happens.

1. Open [music.youtube.com](https://music.youtube.com) in your browser and log in.
2. Open DevTools (F12 or Cmd+Opt+I) → **Network** tab.
3. Reload the page, then filter requests by `browse`.
4. Click any `POST .../browse` request with status 200.
5. Copy the full **request headers** (Firefox: right-click the request →
   *Copy Value* → *Copy Request Headers*. Chrome: copy each header shown
   under "Request Headers" manually, or use the same right-click option if
   available). Must include `Cookie`, `X-Goog-AuthUser`, and `Authorization`
   (the `SAPISIDHASH ...` header) — copying the full block guarantees that.
6. Paste the whole block as the value of `YTMUSIC_HEADERS_RAW` in `.env`,
   wrapped in double quotes, one header per line.

**If "Liked Music" is on a Brand Account** (a secondary channel switched via
the avatar menu, not a separate Google login): set `YTMUSIC_USER_ID` too —
get the ID from `myaccount.google.com/brandaccounts` → select the channel →
the number in the URL after `/b/`.

### 2. SoundCloud credentials (`SOUNDCLOUD_OAUTH_TOKEN`)

1. Open [soundcloud.com](https://soundcloud.com) and log in.
2. Open DevTools → **Network** tab, keep it open.
3. Reload the page or click around (e.g. open "Your likes").
4. Find any request to `api-v2.soundcloud.com`.
5. In its request headers, copy the value of `Authorization`. It looks like
   `OAuth 2-XXXXXX-XXXXXXXXX-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`.
6. Paste it into `SOUNDCLOUD_OAUTH_TOKEN` in `.env` — either with or without
   the leading `OAuth ` prefix both work.

`SOUNDCLOUD_CLIENT_ID` can be left empty — the script fetches a current one
automatically from SoundCloud's own web assets. Set it manually only if
auto-discovery ever fails.

## Run

```bash
python main.py
```

You'll see a progress bar with the current track and a running
added/not-found count. Run it again later to transfer anything you've liked
since the last run — already-transferred tracks are skipped automatically.

Tracks that couldn't be confidently matched are written to `not_found.csv`
after each run, so you can search for them manually if you want.

## CLI options

| Flag | Effect |
|---|---|
| `--dry-run` | Search and match only. Never modifies the SoundCloud playlist or `state.json`. |
| `--limit N` | Only process the first N new tracks. Useful to test your setup before running on your full library. |
| `--retry-failed` | Also retries tracks previously marked as not found. |
| `--checkpoint-every N` | Save progress to the SoundCloud playlist every N newly matched tracks (default: 25). Lower it if you want to be able to stop with less potential rework. |

Example first run to sanity-check everything works:

```bash
python main.py --dry-run --limit 10
```

## How matching works

Each YouTube Music track is searched on SoundCloud by `"<artist> <title>"`.
Titles are normalized (noise like `(Official Video)`, `[Lyrics]`, `(Remastered)`
is stripped) and compared against the top search results with a fuzzy string
match. A result is accepted only if its score is at or above `MATCH_THRESHOLD`
(default 75/100, configurable in `.env`).

## Troubleshooting

- **401 / "Unauthorized" errors** — your YouTube Music headers or SoundCloud
  token expired or were copied incorrectly. Redo the corresponding step
  above. If this keeps happening with `YTMUSIC_HEADERS_RAW`, switch to
  `YTMUSIC_OAUTH_CLIENT_ID`/`SECRET` — it doesn't expire the same way.
- **SoundCloud request failed with a non-2xx status** — SoundCloud's API is
  undocumented and can change without notice. See `CLAUDE.md` for the exact
  endpoints this project relies on and where to look first.
- **Too many tracks end up in `not_found.csv`** — lower `MATCH_THRESHOLD` in
  `.env` (e.g. to 65), then run with `--retry-failed`.

## Disclaimer

This project uses SoundCloud's undocumented internal API (the same one
soundcloud.com's own web player uses), since SoundCloud closed public API
registration to new applications years ago. Use at your own risk and be
mindful of SoundCloud's Terms of Use.
