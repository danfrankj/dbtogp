import pytest
from helpers import RemoteFile
from ledger import Ledger
from reconcile import WorkItem
from mover import move_one, NullReporter


class FakeDropbox:
    def __init__(self):
        self.downloaded = []
        self.deleted = []
        self.fail_delete = False

    def download(self, file_id, dest):
        self.downloaded.append(file_id)
        with open(dest, "wb") as fh:
            fh.write(b"bytes")

    def delete(self, file_id):
        if self.fail_delete:
            raise RuntimeError("delete failed")
        self.deleted.append(file_id)


class FakePhotos:
    def __init__(self):
        self.uploaded = []
        self.added = []
        self.fail_upload = False

    def upload_bytes(self, local_path, name):
        if self.fail_upload:
            raise RuntimeError("upload failed")
        self.uploaded.append(name)
        return "token-" + name

    def add_to_album(self, album_id, token, name):
        self.added.append((album_id, token, name))
        return "media-" + name


def rf(i):
    return RemoteFile(id=f"id:{i}", name=f"f{i}.jpg", path=f"/f{i}.jpg", size=5)


def test_upload_happy_path(tmp_path):
    led = Ledger.load(str(tmp_path / "x.json"))
    dbx, photos = FakeDropbox(), FakePhotos()
    move_one(WorkItem(rf(1), "upload"), dbx, photos, led, "ALB",
             NullReporter(), str(tmp_path), dry_run=False)
    assert dbx.downloaded == ["id:1"]
    assert photos.uploaded == ["f1.jpg"]
    assert photos.added == [("ALB", "token-f1.jpg", "f1.jpg")]
    assert dbx.deleted == ["id:1"]
    assert led.status("id:1") == "deleted"
    assert led.data["files"]["id:1"]["media_item_id"] == "media-f1.jpg"
    # downloaded temp file was removed (only the ledger json remains)
    assert not any("f1.jpg" in f.name for f in tmp_path.iterdir())


def test_delete_only_action(tmp_path):
    led = Ledger.load(str(tmp_path / "x.json"))
    led.mark("id:1", "uploaded", name="f1.jpg", size=5, media_item_id="M")
    dbx, photos = FakeDropbox(), FakePhotos()
    move_one(WorkItem(rf(1), "delete_only"), dbx, photos, led, "ALB",
             NullReporter(), str(tmp_path), dry_run=False)
    assert photos.uploaded == []      # did NOT re-upload
    assert dbx.deleted == ["id:1"]
    assert led.status("id:1") == "deleted"


def test_upload_failure_leaves_file_and_does_not_delete(tmp_path):
    led = Ledger.load(str(tmp_path / "x.json"))
    dbx, photos = FakeDropbox(), FakePhotos()
    photos.fail_upload = True
    with pytest.raises(RuntimeError):
        move_one(WorkItem(rf(1), "upload"), dbx, photos, led, "ALB",
                 NullReporter(), str(tmp_path), dry_run=False)
    assert dbx.deleted == []                 # never deleted on upload failure
    assert led.status("id:1") in ("absent",) # not marked uploaded
    assert not any("f1.jpg" in f.name for f in tmp_path.iterdir())  # temp still cleaned


def test_crash_after_upload_recovers_as_delete_only(tmp_path):
    # Simulate: upload+album succeeded, ledger marked uploaded, then delete failed.
    led = Ledger.load(str(tmp_path / "x.json"))
    dbx, photos = FakeDropbox(), FakePhotos()
    dbx.fail_delete = True
    with pytest.raises(RuntimeError):
        move_one(WorkItem(rf(1), "upload"), dbx, photos, led, "ALB",
                 NullReporter(), str(tmp_path), dry_run=False)
    assert led.status("id:1") == "uploaded"  # recorded before delete
    # Next run: reconcile would give delete_only; simulate it succeeding now
    dbx.fail_delete = False
    move_one(WorkItem(rf(1), "delete_only"), dbx, photos, led, "ALB",
             NullReporter(), str(tmp_path), dry_run=False)
    assert photos.uploaded == ["f1.jpg"]  # uploaded once in first call, not again
    assert led.status("id:1") == "deleted"


def test_dry_run_does_nothing_destructive(tmp_path):
    led = Ledger.load(str(tmp_path / "x.json"))
    dbx, photos = FakeDropbox(), FakePhotos()
    move_one(WorkItem(rf(1), "upload"), dbx, photos, led, "ALB",
             NullReporter(), str(tmp_path), dry_run=True)
    assert dbx.downloaded == [] and photos.uploaded == [] and dbx.deleted == []
    assert led.status("id:1") == "absent"
