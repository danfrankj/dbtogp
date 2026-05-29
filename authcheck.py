#!/usr/bin/env python3
"""Verify Dropbox and Google Photos auth without moving anything.

  uv run dbtogp-auth                 # uses .dbtogp/
  uv run dbtogp-auth --config-dir X  # custom config dir

On the first run this triggers the same OAuth flows as the mover (browser for
Google, paste-a-code for Dropbox) and caches the tokens, so the real run is
non-interactive. On later runs it just confirms the cached tokens still work.
"""
import argparse
import os
import sys

from clients import DropboxClient, PhotosClient
from dbtogp import resolve_creds


def main(argv=None):
    p = argparse.ArgumentParser(description="Check Dropbox + Google Photos auth.")
    p.add_argument("--config-dir", default=os.path.join(os.path.dirname(__file__), ".dbtogp"))
    p.add_argument("--client-secret", default=None)
    args = p.parse_args(argv if argv is not None else sys.argv[1:])

    config_dir, client_secret, app_key = resolve_creds(args.config_dir, args.client_secret)

    print("Checking Dropbox...")
    dbx = DropboxClient(app_key, os.path.join(config_dir, "dropbox_token.json"))
    dbx.verify()
    print("  OK - token valid (file access).")

    print("Checking Google Photos...")
    PhotosClient(client_secret, os.path.join(config_dir, "google_token.json"))
    print("  OK - authorized (append-only).")

    print("\nBoth good. You're ready to run dbtogp.")


if __name__ == "__main__":
    main()
