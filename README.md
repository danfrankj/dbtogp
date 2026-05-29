# dbtogp — Dropbox folder -> Google Photos album

Moves the media files from one **top-level** Dropbox folder into a Google Photos
album: uploads the original file (preserving metadata and resolution), confirms it,
then deletes it from Dropbox. Safe to interrupt and re-run — a JSON ledger in
`.dbtogp/` tracks every file so nothing is uploaded twice or lost.

## Use

Install dependencies with [uv](https://docs.astral.sh/uv/) (`uv sync` creates the
`.venv` and resolves everything from `pyproject.toml`/`uv.lock`). See `SETUP.md` for
the one-time OAuth setup, then:

```bash
uv sync
export DROPBOX_APP_KEY=...                                            # or .dbtogp/dropbox_app_key
uv run dbtogp-auth                                                    # verify both logins first
uv run dbtogp --folder "/Camera Uploads" --album "My Album" --dry-run  # preview
uv run dbtogp --folder "/Camera Uploads" --album "My Album"            # for real
```

## Notes / limitations

- The folder must have **no subfolders** (the script aborts if it finds any).
- Google must be set to **Original quality** (the script can't check this).
- Albums are created by the script; it can't add to an album you made by hand.
- A tiny window exists between "added to album" and the ledger write; a crash there
  is recovered as a delete on the next run (no double upload).
- After a clean run (no errors), if the Dropbox folder is left completely empty the
  script offers to delete it. Declined by default — press `y` to remove it.

## Tests

```bash
uv run pytest -v
```
