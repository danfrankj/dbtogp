"""Thin wrappers around the Dropbox SDK and the Google Photos REST API.
Exposes the same method names the mover's fakes use:
  DropboxClient: list_folder(path) -> (subfolders, RemoteFile list), download, delete
  PhotosClient:  ensure_album, upload_bytes, add_to_album
"""
import json
import mimetypes
import os

import requests

import dropbox
from dropbox.files import FileMetadata, FolderMetadata
from dropbox import DropboxOAuth2FlowNoRedirect

from helpers import RemoteFile, with_retry

# Transient conditions worth retrying. Dropbox SDK errors don't inherit from
# requests' exceptions, so the retriable Dropbox ones are listed explicitly.
_NET_ERRORS = (requests.exceptions.RequestException, ConnectionError, TimeoutError,
               dropbox.exceptions.RateLimitError, dropbox.exceptions.InternalServerError)


class DropboxClient:
    def __init__(self, app_key, token_path):
        self._app_key = app_key
        self._token_path = token_path
        self._dbx = dropbox.Dropbox(
            oauth2_refresh_token=self._load_or_authorize(),
            app_key=app_key,
        )

    def _load_or_authorize(self):
        if os.path.exists(self._token_path):
            with open(self._token_path) as fh:
                return json.load(fh)["refresh_token"]
        flow = DropboxOAuth2FlowNoRedirect(
            self._app_key, use_pkce=True, token_access_type="offline",
            scope=["files.content.read", "files.content.write", "files.metadata.read"],
        )
        url = flow.start()
        print("\n1. Visit:", url)
        print("2. Click Allow, then copy the authorization code.")
        code = input("3. Paste the code here: ").strip()
        result = flow.finish(code)
        with open(self._token_path, "w") as fh:
            json.dump({"refresh_token": result.refresh_token}, fh)
        os.chmod(self._token_path, 0o600)
        return result.refresh_token

    def list_folder(self, path):
        """Return (subfolder_names, [RemoteFile]). Top level only."""
        subfolders, files = [], []
        res = with_retry(lambda: self._dbx.files_list_folder(path),
                         retry_on=_NET_ERRORS)
        while True:
            for entry in res.entries:
                if isinstance(entry, FolderMetadata):
                    subfolders.append(entry.name)
                elif isinstance(entry, FileMetadata):
                    files.append(RemoteFile(id=entry.id, name=entry.name,
                                            path=entry.path_display, size=entry.size))
            if not res.has_more:
                break
            cursor = res.cursor
            res = with_retry(lambda: self._dbx.files_list_folder_continue(cursor),
                             retry_on=_NET_ERRORS)
        return subfolders, files

    def download(self, file_id, dest):
        with_retry(lambda: self._dbx.files_download_to_file(dest, file_id),
                   retry_on=_NET_ERRORS)

    def delete(self, file_id):
        with_retry(lambda: self._dbx.files_delete_v2(file_id),
                   retry_on=_NET_ERRORS)


from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

_PHOTOS_SCOPES = ["https://www.googleapis.com/auth/photoslibrary.appendonly"]
_API = "https://photoslibrary.googleapis.com/v1"


class PhotosClient:
    def __init__(self, client_secret_path, token_path):
        self._token_path = token_path
        self._creds = self._load_or_authorize(client_secret_path)

    def _load_or_authorize(self, client_secret_path):
        creds = None
        if os.path.exists(self._token_path):
            creds = Credentials.from_authorized_user_file(self._token_path,
                                                          _PHOTOS_SCOPES)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    client_secret_path, _PHOTOS_SCOPES)
                creds = flow.run_local_server(port=0)
            with open(self._token_path, "w") as fh:
                fh.write(creds.to_json())
            os.chmod(self._token_path, 0o600)
        return creds

    def _headers(self, extra=None):
        if not self._creds.valid:
            self._creds.refresh(Request())
        h = {"Authorization": "Bearer " + self._creds.token}
        if extra:
            h.update(extra)
        return h

    def _post(self, url, *, headers=None, json_body=None, data=None):
        def do():
            r = requests.post(url, headers=headers, json=json_body, data=data,
                              timeout=300)
            r.raise_for_status()
            return r
        return with_retry(do, retry_on=(requests.exceptions.RequestException,),
                          attempts=5)

    def ensure_album(self, title):
        """Create an album the API owns; return its id."""
        r = self._post(f"{_API}/albums",
                       headers=self._headers({"Content-type": "application/json"}),
                       json_body={"album": {"title": title}})
        return r.json()["id"]

    def upload_bytes(self, local_path, name):
        mime = mimetypes.guess_type(name)[0] or "application/octet-stream"
        with open(local_path, "rb") as fh:
            body = fh.read()
        r = self._post(f"{_API}/uploads",
                       headers=self._headers({
                           "Content-type": "application/octet-stream",
                           "X-Goog-Upload-Content-Type": mime,
                           "X-Goog-Upload-Protocol": "raw",
                       }),
                       data=body)
        return r.text  # upload token

    def add_to_album(self, album_id, upload_token, name):
        body = {"albumId": album_id,
                "newMediaItems": [{"description": "",
                                   "simpleMediaItem": {"fileName": name,
                                                       "uploadToken": upload_token}}]}
        r = self._post(f"{_API}/mediaItems:batchCreate",
                       headers=self._headers({"Content-type": "application/json"}),
                       json_body=body)
        result = r.json()["newMediaItemResults"][0]
        status = result.get("status", {})
        # google.rpc.Status: code 0 (or absent) == OK; anything else is a failure.
        if status.get("code", 0) != 0:
            raise RuntimeError(f"batchCreate failed for {name}: {status}")
        return result["mediaItem"]["id"]
