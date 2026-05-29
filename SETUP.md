# Setup

You need two OAuth apps (one-time). Both are free.

## 1. Google Photos

1. Go to https://console.cloud.google.com/ and create a project (any name).
2. APIs & Services -> Library -> search "Photos Library API" -> Enable.
3. APIs & Services -> OAuth consent screen:
   - User type: External. Fill the required name/email fields.
   - Add yourself under "Test users" (your own Google account).
   - NOTE: in "Testing" mode the login is valid ~7 days, which is fine for a
     one-time move. Re-run the auth flow if it expires.
4. APIs & Services -> Credentials -> Create Credentials -> OAuth client ID:
   - Application type: **Desktop app**.
   - Download the JSON. Save it as `.dbtogp/client_secret.json` in this project
     (the script creates `.dbtogp/` on first run; you can `mkdir .dbtogp` now).

## 2. Dropbox

1. Go to https://www.dropbox.com/developers/apps -> Create app.
2. Choose "Scoped access" and "Full Dropbox" (or App folder if your photos are there).
3. In the app's **Permissions** tab, enable:
   `files.metadata.read`, `files.content.read`, `files.content.write`. Submit.
4. On the app's Settings tab, copy the **App key**. Give it to the script either way:
   - env var: `export DROPBOX_APP_KEY=your_app_key_here`, or
   - file: `echo your_app_key_here > .dbtogp/dropbox_app_key`
   The env var wins if both are set. (No app secret is needed — the script uses PKCE.)

## First run

```bash
uv sync                          # one-time: install deps into .venv
export DROPBOX_APP_KEY=your_app_key_here   # or: echo ... > .dbtogp/dropbox_app_key
uv run dbtogp --folder "/Camera Uploads" --album "My Album" --dry-run
# --album is optional; it defaults to the folder's name ("Camera Uploads" here)
```

The first run opens a browser for Google sign-in and prints a Dropbox auth URL to
paste a code back. Tokens are cached in `.dbtogp/` so later runs are non-interactive.

## IMPORTANT: original quality

Before a real run, set photos.google.com -> Settings -> "Upload size" to
**Original quality**, or photos over 16MP and videos over 1080p will be downscaled.
