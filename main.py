#!/usr/bin/env python3
"""Transfers YouTube Music "Liked Music" into a SoundCloud playlist.

Matches each liked track by title/artist search (nothing is downloaded).
Safe to re-run: already-transferred tracks are skipped via state.json, so
re-running only picks up songs liked since the last run.
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from tqdm import tqdm

import soundcloud_client
import ytmusic_client
from config import load_config
from matcher import best_match
from state import load_state, save_state

STATE_PATH = Path("state.json")
NOT_FOUND_REPORT_PATH = Path("not_found.csv")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Search and match only; never modify the SoundCloud playlist or state.json.",
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Only process the first N new tracks (useful for a quick test run).",
    )
    parser.add_argument(
        "--retry-failed", action="store_true",
        help="Also retry tracks that were previously marked as not found.",
    )
    parser.add_argument(
        "--checkpoint-every", type=int, default=25,
        help="Flush newly matched tracks to the SoundCloud playlist every N matches (default: 25).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_config()
    state = load_state(STATE_PATH)
    processed = state["processed"]

    print("Connecting to YouTube Music...")
    yt = ytmusic_client.connect(
        config.ytmusic_headers_raw,
        config.ytmusic_user_id,
        config.ytmusic_oauth_client_id,
        config.ytmusic_oauth_client_secret,
    )
    liked = ytmusic_client.get_liked_songs(yt)
    print(f"Found {len(liked)} liked tracks on YouTube Music.")

    pending = []
    for track in liked:
        entry = processed.get(track.video_id)
        if entry is None:
            pending.append(track)
        elif entry["status"] == "not_found" and args.retry_failed:
            pending.append(track)

    if args.limit is not None:
        pending = pending[: args.limit]

    already_added = sum(1 for e in processed.values() if e["status"] == "added")
    print(f"{already_added} already in the SoundCloud playlist, {len(pending)} to process now.")

    if not pending:
        print("Nothing to do.")
        return 0

    print("Connecting to SoundCloud...")
    sc = soundcloud_client.SoundCloudClient(
        oauth_token=config.soundcloud_oauth_token,
        client_id=config.soundcloud_client_id,
        request_delay_ms=config.request_delay_ms,
        datadome_cookie=config.soundcloud_datadome_cookie,
    )

    playlist = sc.find_playlist_by_title(config.playlist_name)
    existing_track_ids: list[int] = []
    playlist_id = None
    if playlist is None:
        if args.dry_run:
            print(f'Playlist "{config.playlist_name}" does not exist yet (would be created).')
        else:
            print(f'Creating SoundCloud playlist "{config.playlist_name}"...')
            playlist = sc.create_playlist(config.playlist_name)
            playlist_id = playlist["id"]
    else:
        playlist_id = playlist["id"]
        if not args.dry_run:
            existing_track_ids = sc.get_playlist_track_ids(playlist_id)

    not_found_rows = []
    batch: list[int] = []
    added_count = 0

    def flush() -> None:
        nonlocal batch, existing_track_ids
        if not batch or args.dry_run:
            return
        existing_track_ids = existing_track_ids + batch
        sc.set_playlist_tracks(playlist_id, existing_track_ids)
        batch = []
        save_state(STATE_PATH, state)

    progress = tqdm(pending, unit="track")
    try:
        for track in progress:
            progress.set_description(f"{track.artist} - {track.title}"[:60])
            candidates = sc.search_tracks(f"{track.artist} {track.title}", limit=15)
            match, score = best_match(track.title, track.artist, candidates, config.match_threshold)

            if not match:
                title_only_candidates = sc.search_tracks(track.title, limit=15)
                title_only_match, title_only_score = best_match(
                    track.title, track.artist, title_only_candidates, config.match_threshold
                )
                if title_only_match and title_only_score > score:
                    match, score = title_only_match, title_only_score

            label = f"{track.artist} - {track.title}"
            if match:
                processed[track.video_id] = {
                    "title": label,
                    "status": "added",
                    "soundcloud_track_id": match.id,
                    "score": round(score, 1),
                }
                if not args.dry_run:
                    batch.append(match.id)
                    if len(batch) >= args.checkpoint_every:
                        flush()
                added_count += 1
            else:
                processed[track.video_id] = {
                    "title": label,
                    "status": "not_found",
                    "soundcloud_track_id": None,
                    "score": round(score, 1),
                }
                not_found_rows.append((track.artist, track.title, round(score, 1)))
            progress.set_postfix(added=added_count, not_found=len(not_found_rows))
    finally:
        flush()
        if not args.dry_run:
            save_state(STATE_PATH, state)

    if not_found_rows:
        with NOT_FOUND_REPORT_PATH.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["artist", "title", "best_match_score"])
            writer.writerows(not_found_rows)
        print(f"{len(not_found_rows)} tracks had no confident match -> {NOT_FOUND_REPORT_PATH}")

    suffix = " (dry run, nothing was saved)" if args.dry_run else ""
    print(f"Done. Added {added_count} tracks{suffix}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
