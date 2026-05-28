# Dropbox → Google Photos Mover — Design

**Date:** 2026-05-28
**Status:** Approved design, pending spec review

## Goal

A Python script that **moves** the media files from one Dropbox folder into a Google
Photos album. "Move" means: upload to Google Photos, confirm success, then delete the
file from Dropbox. The script must be robust across restarts, preserve all photo
metadata, and preserve resolution.

## Scope & decisions

- **Source access:** Dropbox API (files are not assumed to be synced locally).
- **Move semantics:** delete each file from Dropbox *after* Google Photos confirms the
  upload succeeded. Irreversible by design.
- **Folder scope:** top level of the named folder only. At startup the script asserts the
  folder contains **zero subfolders** and aborts (listing any found) if not.
- **Media types:** photos and videos (the formats Google Photos accepts). Other files are
  skipped and logged.
- **Credentials:** the user does not yet have OAuth apps; a `SETUP.md` walks through
  creating a Google Cloud OAuth client and a Dropbox app. The script runs the interactive
  OAuth flow on first run and caches refresh tokens.
- **Ledger:** a single JSON file (not SQLite), written atomically.
- **Concurrency:** one file at a time, with obvious console progress.

## Known platform constraints (surfaced to the user, not solvable in code)

1. **Resolution is an account setting.** The Photos Library API uploads the original file
   bytes as-is. Whether Google stores them at full resolution depends on
   *photos.google.com → Settings → Upload size*, which must be **"Original quality"**
   (not "Storage saver"). The script prints a prominent reminder at startup; it cannot
   read or change this setting via API.
2. **Albums must be app-created.** The Photos Library API can only add media to albums it
   created. The script creates (or reuses, via the ledger) its own album by the given
   name; it cannot append to an album the user made by hand in the Photos app.
3. **Metadata.** EXIF (date taken, GPS, camera) lives inside the original file bytes.
   Because the script uploads the original bytes unchanged, this metadata is preserved and
   read by Google Photos. The script sets no description and does not rewrite files.
4. **Google OAuth test-app token expiry.** A Google Cloud OAuth app in "Testing" mode
   issues refresh tokens that expire after 7 days. For a one-time migration this is fine;
   `SETUP.md` notes it and how to add yourself as a test user / publish if needed.

## Architecture

Single script `dbtogp.py` plus `SETUP.md` and `requirements.txt`.

```
python dbtogp.py --folder "/Path/In/Dropbox" --album "Album Name"
```

Optional flags: `--dry-run` (do everything except upload/delete — list what would happen),
`--config-dir` (default `.dbtogp/` inside the project folder, beside `dbtogp.py`).

**Config dir** (`<config-dir>`, default `.dbtogp/` in the project folder) holds the cached
OAuth tokens, the JSON ledger, and the log file. It's created on first run.

### Components

1. **Auth module (in-script)**
   - *Google:* installed-app OAuth flow (`google-auth-oauthlib`), scope
     `https://www.googleapis.com/auth/photoslibrary.appendonly`. Token cached to
     `<config-dir>/google_token.json`, auto-refreshed.
   - *Dropbox:* offline OAuth (refresh token) via the `dropbox` SDK, scopes
     `files.content.read` + `files.content.write`. Cached to
     `<config-dir>/dropbox_token.json`.

2. **Preconditions**
   - Resolve `--folder`; confirm it exists.
   - List its entries; assert there are **no subfolders** (abort, listing any found).
   - Print the "Original quality" reminder.

3. **Ledger** — JSON file at `<config-dir>/<album-slug>.json`.
   - Top-level dict: `{"meta": {"album_id": ..., "album_name": ..., "folder": ...},
     "files": { "<dropbox_file_id>": {...} }}`.
   - Per-file record: `path`, `size`, `status` (`pending`/`uploaded`/`deleted`),
     `google_media_item_id`, `error`, `updated_at`.
   - **Atomic write:** serialize to `<file>.tmp`, then `os.replace` over the real file.
     Saved after every state transition so a crash can't corrupt or lose progress.

4. **Per-file pipeline** (each step idempotent; safe to resume)
   1. Download Dropbox file → temp file (exact original bytes).
   2. Upload bytes → Photos `/v1/uploads` (raw protocol) → upload token.
   3. `mediaItems:batchCreate` with `albumId` → media item; verify the per-item status.
   4. Ledger → `uploaded` (record media item id).
   5. Delete the file from Dropbox via API.
   6. Ledger → `deleted`; remove temp file.

5. **Restart logic** (run at start, driven by the ledger)
   - Re-list the Dropbox folder; reconcile against the ledger by Dropbox file id.
   - `deleted` → skip.
   - `uploaded` but still present in Dropbox → redo the delete only (steps 5–6).
   - `pending` / unknown → full pipeline.
   - Never re-uploads an already-uploaded file.

6. **Album resolution**
   - If `meta.album_id` exists in the ledger, reuse it.
   - Else create a new album with the given name via `albums:create`, store its id in
     `meta`.

### Robustness

- Retry with exponential backoff on transient errors (HTTP 429 / 5xx, network timeouts);
  give up after a bounded number of attempts and mark the file `error` (left in Dropbox).
- One file at a time — fully resumable, simple to reason about.
- All actions logged to console **and** a log file at `<config-dir>/dbtogp.log`.

### Progress output (must be obvious)

- Startup banner: total file count and total bytes to move.
- Per file: a header line `[ 12/240 ]  IMG_0421.HEIC  (3.4 MB)` followed by an in-place
  updating step line (`↓ downloading… ✓   ↑ uploading… ✓   + album ✓   ✗ delete ✓`).
- A running tally after each file: `Progress: 12 done · 0 errors · 228 left · 41.2 MB / 1.8 GB`.
- Final summary: counts of uploaded / deleted / skipped / errored, and the location of the
  log and ledger. Errored files are listed so the user knows what stayed behind.

## Dependencies

`dropbox`, `google-auth-oauthlib`, `requests` (pinned in `requirements.txt`).

## Error handling summary

| Situation | Behavior |
|---|---|
| Folder has subfolders | Abort at startup, list them. |
| Non-media file | Skip, log, continue. |
| Transient upload/delete error | Retry with backoff; if exhausted, mark `error`, leave in Dropbox, continue. |
| Crash / Ctrl-C mid-run | Ledger reflects last completed step; rerun resumes cleanly. |
| `batchCreate` returns non-success status | Treat as failed upload (no delete); mark `error`. |
| Google "Storage saver" account setting | Cannot detect; warn at startup only. |

## Out of scope (YAGNI)

- Recursion / nested album structure.
- Concurrent / batched uploads.
- Two-way sync or re-running to pick up new Dropbox files added later (a rerun *would*
  pick them up, but ongoing sync is not a goal).
- Verifying stored resolution after upload.
