"""Crash-safe JSON ledger. Written atomically after every change."""
import json
import os
import time


class Ledger:
    def __init__(self, path, data):
        self.path = path
        self.data = data

    @classmethod
    def load(cls, path):
        if os.path.exists(path):
            with open(path) as fh:
                data = json.load(fh)
        else:
            data = {"meta": {}, "files": {}}
        data.setdefault("meta", {})
        data.setdefault("files", {})
        return cls(path, data)

    def save(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w") as fh:
            json.dump(self.data, fh, indent=2)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, self.path)  # atomic on POSIX

    def album_id(self):
        return self.data["meta"].get("album_id")

    def set_album(self, album_id, name, folder):
        self.data["meta"] = {"album_id": album_id, "album_name": name, "folder": folder}
        self.save()

    def status(self, file_id):
        rec = self.data["files"].get(file_id)
        return rec["status"] if rec else "absent"

    def mark(self, file_id, status, *, name=None, size=None,
             media_item_id=None, error=None):
        rec = self.data["files"].get(file_id, {})
        rec["status"] = status
        if name is not None:
            rec["name"] = name
        if size is not None:
            rec["size"] = size
        if media_item_id is not None:
            rec["media_item_id"] = media_item_id
        rec["error"] = error
        rec["updated_at"] = time.time()
        self.data["files"][file_id] = rec
        self.save()
