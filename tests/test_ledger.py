import json
from ledger import Ledger


def test_load_missing_file_is_empty(tmp_path):
    led = Ledger.load(str(tmp_path / "x.json"))
    assert led.album_id() is None
    assert led.status("id:1") == "absent"


def test_set_album_and_persist(tmp_path):
    p = str(tmp_path / "x.json")
    led = Ledger.load(p)
    led.set_album("ALB", "Trip", "/Trip")
    # reload from disk to prove it was saved
    led2 = Ledger.load(p)
    assert led2.album_id() == "ALB"
    assert led2.data["meta"]["album_name"] == "Trip"


def test_mark_transitions_and_persist(tmp_path):
    p = str(tmp_path / "x.json")
    led = Ledger.load(p)
    led.mark("id:1", "uploaded", name="a.jpg", size=10, media_item_id="M")
    assert led.status("id:1") == "uploaded"
    led.mark("id:1", "deleted")
    led2 = Ledger.load(p)
    assert led2.status("id:1") == "deleted"
    assert led2.data["files"]["id:1"]["media_item_id"] == "M"  # preserved
    assert led2.data["files"]["id:1"]["name"] == "a.jpg"       # preserved


def test_mark_error_records_message(tmp_path):
    led = Ledger.load(str(tmp_path / "x.json"))
    led.mark("id:9", "error", name="b.mov", size=5, error="boom")
    assert led.status("id:9") == "error"
    assert led.data["files"]["id:9"]["error"] == "boom"


def test_atomic_save_leaves_no_tmp(tmp_path):
    p = str(tmp_path / "x.json")
    led = Ledger.load(p)
    led.mark("id:1", "uploaded", name="a", size=1)
    files = [f.name for f in tmp_path.iterdir()]
    assert "x.json" in files
    assert not any(f.endswith(".tmp") for f in files)
    # file is valid JSON
    with open(p) as fh:
        json.load(fh)
