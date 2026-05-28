from helpers import RemoteFile
from ledger import Ledger
from reconcile import plan_work


def rf(i, size=10):
    return RemoteFile(id=f"id:{i}", name=f"f{i}.jpg", path=f"/f{i}.jpg", size=size)


def test_new_files_get_upload_action(tmp_path):
    led = Ledger.load(str(tmp_path / "x.json"))
    todo, skipped = plan_work([rf(1), rf(2)], led)
    assert skipped == 0
    assert [(w.rf.id, w.action) for w in todo] == [("id:1", "upload"), ("id:2", "upload")]


def test_deleted_files_are_skipped(tmp_path):
    led = Ledger.load(str(tmp_path / "x.json"))
    led.mark("id:1", "deleted", name="f1.jpg", size=10)
    todo, skipped = plan_work([rf(1), rf(2)], led)
    assert skipped == 1
    assert [(w.rf.id, w.action) for w in todo] == [("id:2", "upload")]


def test_uploaded_but_present_gets_delete_only(tmp_path):
    led = Ledger.load(str(tmp_path / "x.json"))
    led.mark("id:1", "uploaded", name="f1.jpg", size=10, media_item_id="M")
    todo, skipped = plan_work([rf(1)], led)
    assert skipped == 0
    assert [(w.rf.id, w.action) for w in todo] == [("id:1", "delete_only")]


def test_errored_files_are_retried_as_upload(tmp_path):
    led = Ledger.load(str(tmp_path / "x.json"))
    led.mark("id:1", "error", name="f1.jpg", size=10, error="boom")
    todo, skipped = plan_work([rf(1)], led)
    assert [(w.rf.id, w.action) for w in todo] == [("id:1", "upload")]
