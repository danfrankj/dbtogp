#!/usr/bin/env python3
"""Move a top-level Dropbox folder into a Google Photos album.

Usage:
  python dbtogp.py --folder "/Path/In/Dropbox" --album "Album Name"
  python dbtogp.py --folder "/Path" --album "Name" --dry-run
"""
import argparse
import os
import sys

from clients import DropboxClient, PhotosClient
from helpers import slugify, is_media_file
from ledger import Ledger
from mover import run, ConsoleReporter


def parse_args(argv):
    p = argparse.ArgumentParser(description="Move a Dropbox folder to a Google Photos album.")
    p.add_argument("--folder", required=True, help="Dropbox folder path, e.g. /Trip")
    p.add_argument("--album", default=None,
                   help="Google Photos album name (default: the folder's name)")
    p.add_argument("--config-dir", default=os.path.join(os.path.dirname(__file__), ".dbtogp"),
                   help="Where tokens, ledger and log live (default .dbtogp/)")
    p.add_argument("--client-secret", default=None,
                   help="Path to Google client_secret.json (default <config-dir>/client_secret.json)")
    p.add_argument("--dry-run", action="store_true",
                   help="List what would happen; upload/delete nothing.")
    p.add_argument("--delete-empty", action="store_true",
                   help="After a clean run, delete the emptied folder without prompting "
                        "(for unattended/batch runs).")
    return p.parse_args(argv)


def resolve_creds(config_dir_arg, client_secret_arg=None):
    """Resolve the config dir and both credential locations, exiting with a
    helpful message if either is missing. Shared by the mover and the auth check."""
    config_dir = os.path.abspath(config_dir_arg)
    os.makedirs(config_dir, exist_ok=True)

    client_secret = client_secret_arg or os.path.join(config_dir, "client_secret.json")
    if not os.path.exists(client_secret):
        sys.exit(f"ERROR: Google client secret not found at {client_secret} (see SETUP.md).")

    # Public Dropbox app key (PKCE app, no secret needed): env var wins, else a file.
    key_file = os.path.join(config_dir, "dropbox_app_key")
    app_key = os.environ.get("DROPBOX_APP_KEY", "")
    if not app_key and os.path.exists(key_file):
        app_key = open(key_file).read().strip()
    if not app_key:
        sys.exit(f"ERROR: set DROPBOX_APP_KEY or write it to {key_file} (see SETUP.md).")

    return config_dir, client_secret, app_key


def album_from_folder(folder):
    """The Dropbox folder's own name, e.g. /photos/Trip 2024/ -> 'Trip 2024'.
    Empty only for the root, which the caller rejects."""
    return folder.rstrip("/").rsplit("/", 1)[-1]


def folder_is_emptied(errors, subfolders, files):
    """After a run, the folder is safe to offer for deletion only if nothing
    failed and a fresh listing shows it completely empty (no leftovers)."""
    return errors == 0 and not subfolders and not files


def main(argv=None):
    args = parse_args(argv if argv is not None else sys.argv[1:])

    album = args.album or album_from_folder(args.folder)
    if not album:
        sys.exit("ERROR: could not derive an album name from --folder; pass --album.")

    config_dir, client_secret, app_key = resolve_creds(args.config_dir, args.client_secret)

    print("=" * 60)
    print("REMINDER: Google Photos must be set to 'Original quality'")
    print("(photos.google.com -> Settings -> Upload size) or your photos")
    print("will be downscaled. The script cannot check or change this.")
    print("=" * 60)

    dbx = DropboxClient(app_key, os.path.join(config_dir, "dropbox_token.json"))
    photos = PhotosClient(client_secret, os.path.join(config_dir, "google_token.json"))

    # Precondition: list folder, assert no subfolders. A missing folder means a
    # prior run already moved and deleted it, so there's nothing left to do.
    try:
        subfolders, files = dbx.list_folder(args.folder)
    except FileNotFoundError:
        print(f"Folder {args.folder} not found — already moved, nothing to do.")
        return
    if subfolders:
        sys.exit("ERROR: folder contains subfolders, which is not supported:\n  - "
                 + "\n  - ".join(subfolders))

    media = [f for f in files if is_media_file(f.name)]
    skipped_nonmedia = len(files) - len(media)
    if skipped_nonmedia:
        print(f"Skipping {skipped_nonmedia} non-media file(s).")

    ledger = Ledger.load(os.path.join(config_dir, slugify(album) + ".json"))

    if args.dry_run:
        album_id = ledger.album_id() or "<dry-run-no-album>"
    else:
        album_id = ledger.album_id()
        if not album_id:
            album_id = photos.ensure_album(album)
            ledger.set_album(album_id, album, args.folder)

    result = run(media, dbx, photos, ledger, album_id, ConsoleReporter(),
                 config_dir, args.dry_run)

    if not args.dry_run:
        subfolders, files = dbx.list_folder(args.folder)  # fresh listing post-move
        # files_delete_v2 rejects a trailing slash (malformed_path) that
        # files_list_folder tolerates; strip it, and never offer to delete root.
        folder = args.folder.rstrip("/")
        if folder and folder_is_emptied(result["errors"], subfolders, files):
            if args.delete_empty:
                confirmed = True
            else:
                try:
                    answer = input(f'\nDelete now-empty folder "{folder}"? [y/N] ')
                except EOFError:
                    answer = ""  # non-interactive: keep the folder
                confirmed = answer.strip().lower() in ("y", "yes")
            if confirmed:
                dbx.delete(folder)
                print(f'Deleted {folder}.')


if __name__ == "__main__":
    main()
