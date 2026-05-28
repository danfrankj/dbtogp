# Dropbox → Google Photos Mover Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A robust, restart-safe Python script that moves the media files from one top-level Dropbox folder into a Google Photos album (upload, confirm, then delete from Dropbox), preserving original bytes (and thus metadata and resolution).

**Architecture:** All decision logic lives in SDK-free modules (`helpers`, `ledger`, `reconcile`, `mover`) that unit-test against fake clients. The real network code is isolated in `clients.py` (Dropbox SDK + Google Photos REST). A JSON ledger written atomically after every state change drives restart recovery. The CLI (`dbtogp.py`) wires real clients into the mover.

**Tech Stack:** Python 3.9, `dropbox` SDK, `google-auth-oauthlib`, `requests`, `pytest`.

---

## File Structure

```
dbtogp/
  dbtogp.py          # CLI entry: arg parsing, builds real clients, calls mover.run
  mover.py           # orchestration: run(), move_one(), ConsoleReporter — NO sdk imports
  reconcile.py       # plan_work(): restart-safe decision of what to do per file
  ledger.py          # Ledger: load / atomic save / status / mark
  clients.py         # DropboxClient, PhotosClient (auth + API calls + retry)
  helpers.py         # RemoteFile, slugify, is_media_file, human_size, tally_line, with_retry
  requirements.txt
  SETUP.md           # how to create the Google + Dropbox OAuth apps
  README.md
  tests/
    test_helpers.py
    test_ledger.py
    test_reconcile.py
    test_mover.py
```

**Why these boundaries:** `helpers`, `ledger`, `reconcile`, `mover` import no SDKs, so the
restart/robustness logic — the crux of the requirements — is fully unit-tested with fakes.
`clients.py` is the only file touching the network and is exercised manually / in real runs.

**Shared data shape** — `RemoteFile` (defined in `helpers.py`, used everywhere):

```python
@dataclass(frozen=True)
class RemoteFile:
    id: str        # Dropbox file id, e.g. "id:abc123" — stable across renames
    name: str      # filename, e.g. "IMG_0421.HEIC"
    path: str      # path_display, for logging
    size: int      # bytes
```

**Ledger file shape** (`<config-dir>/<album-slug>.json`):

```json
{
  "meta": {"album_id": "ABC", "album_name": "Trip", "folder": "/Trip"},
  "files": {
    "id:abc123": {"name": "IMG_1.HEIC", "size": 123, "status": "deleted",
                  "media_item_id": "X", "error": null, "updated_at": 1700000000.0}
  }
}
```

Statuses: absent (never seen) / `uploaded` (in Photos, still in Dropbox) / `deleted`
(done) / `error` (failed, left in Dropbox).

---

## Task 1: Project scaffold

**Files:**
- Create: `requirements.txt`, `.gitignore`, `tests/__init__.py`

- [ ] **Step 1: Initialize git and create requirements.txt**

```bash
cd /Users/danielfrank/src/dbtogp
git init
```

Create `requirements.txt`:

```
dropbox>=12,<13
google-auth-oauthlib>=1.2,<2
requests>=2.31
pytest>=8.0
```

- [ ] **Step 2: Create .gitignore**

Create `.gitignore`:

```
.dbtogp/
__pycache__/
*.pyc
.venv/
venv/
```

- [ ] **Step 3: Create empty tests package**

Create `tests/__init__.py` (empty file).

- [ ] **Step 4: Set up a virtualenv and install deps**

```bash
cd /Users/danielfrank/src/dbtogp
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```
Expected: installs succeed, `pytest` available at `.venv/bin/pytest`.

- [ ] **Step 5: Commit**

```bash
git add requirements.txt .gitignore tests/__init__.py
git commit -m "chore: scaffold project (deps, gitignore, tests package)"
```

---

## Task 2: Pure helpers

**Files:**
- Create: `helpers.py`
- Test: `tests/test_helpers.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_helpers.py`:

```python
import pytest
from helpers import (RemoteFile, slugify, is_media_file, human_size,
                     tally_line, with_retry)


def test_slugify_basics():
    assert slugify("Summer Trip 2024") == "summer-trip-2024"
    assert slugify("  A/B:C  ") == "a-b-c"
    assert slugify("!!!") == "album"  # never empty


def test_is_media_file():
    assert is_media_file("a.JPG") is True
    assert is_media_file("a.heic") is True
    assert is_media_file("clip.MP4") is True
    assert is_media_file("movie.mov") is True
    assert is_media_file("notes.txt") is False
    assert is_media_file("archive.zip") is False
    assert is_media_file("noext") is False


def test_human_size():
    assert human_size(0) == "0 B"
    assert human_size(512) == "512 B"
    assert human_size(1024) == "1.0 KB"
    assert human_size(1536) == "1.5 KB"
    assert human_size(1048576) == "1.0 MB"


def test_tally_line():
    line = tally_line(done=12, errors=1, left=228, bytes_done=1024, bytes_total=2048)
    assert "12 done" in line
    assert "1 error" in line
    assert "228 left" in line
    assert "1.0 KB / 2.0 KB" in line


def test_remotefile_is_frozen():
    rf = RemoteFile(id="id:1", name="a.jpg", path="/a.jpg", size=10)
    with pytest.raises(Exception):
        rf.name = "b.jpg"


def test_with_retry_succeeds_first_try():
    calls = []
    result = with_retry(lambda: calls.append(1) or "ok", attempts=3, sleep=lambda s: None)
    assert result == "ok"
    assert len(calls) == 1


def test_with_retry_retries_then_succeeds():
    state = {"n": 0}
    slept = []

    def flaky():
        state["n"] += 1
        if state["n"] < 3:
            raise ValueError("transient")
        return "ok"

    result = with_retry(flaky, attempts=5, base=0.01, sleep=slept.append)
    assert result == "ok"
    assert state["n"] == 3
    assert len(slept) == 2  # slept before the 2 retries


def test_with_retry_gives_up_and_raises():
    def always_fail():
        raise ValueError("nope")

    with pytest.raises(ValueError):
        with_retry(always_fail, attempts=3, base=0.01, sleep=lambda s: None)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_helpers.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'helpers'`.

- [ ] **Step 3: Implement helpers.py**

Create `helpers.py`:

```python
"""Pure, SDK-free helpers shared across the mover."""
import re
from dataclasses import dataclass

# Formats Google Photos accepts that we expect from a phone/camera folder.
MEDIA_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff", ".tif",
    ".heic", ".heif", ".raw", ".dng", ".cr2", ".nef", ".arw",
    ".mp4", ".mov", ".m4v", ".mkv", ".avi", ".mpg", ".mpeg", ".3gp", ".webm",
}


@dataclass(frozen=True)
class RemoteFile:
    id: str
    name: str
    path: str
    size: int


def slugify(name):
    """Filesystem-safe slug for naming the ledger file. Never empty."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return slug or "album"


def is_media_file(name):
    dot = name.rfind(".")
    if dot == -1:
        return False
    return name[dot:].lower() in MEDIA_EXTENSIONS


def human_size(num):
    units = ["B", "KB", "MB", "GB", "TB"]
    if num < 1024:
        return f"{num} B"
    size = float(num)
    for unit in units[1:]:
        size /= 1024
        if size < 1024 or unit == units[-1]:
            return f"{size:.1f} {unit}"


def tally_line(done, errors, left, bytes_done, bytes_total):
    err_word = "error" if errors == 1 else "errors"
    return (f"Progress: {done} done · {errors} {err_word} · {left} left "
            f"· {human_size(bytes_done)} / {human_size(bytes_total)}")


def with_retry(fn, attempts=5, base=1.0, sleep=None, retry_on=(Exception,)):
    """Call fn(); on a ret_on exception, back off exponentially and retry.
    `sleep` is injectable for tests. Re-raises the last error after `attempts`."""
    import time
    sleep = sleep or time.sleep
    last = None
    for i in range(attempts):
        try:
            return fn()
        except retry_on as e:
            last = e
            if i < attempts - 1:
                sleep(base * (2 ** i))
    raise last
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_helpers.py -v`
Expected: PASS (all 8 tests).

- [ ] **Step 5: Commit**

```bash
git add helpers.py tests/test_helpers.py
git commit -m "feat: pure helpers (RemoteFile, slugify, is_media_file, human_size, tally_line, with_retry)"
```

---

## Task 2.5: Add note that `with_retry`'s `retry_on` is broad by design

This is a one-line doc step, no code change beyond a comment, to make the retry policy
explicit for the engineer wiring clients later.

- [ ] **Step 1: Add a clarifying comment in helpers.py**

In `helpers.py`, just below the `with_retry` def line, the docstring already explains
behavior. Add this comment immediately after the docstring:

```python
    # Clients pass a narrow retry_on (HTTP 429/5xx + network errors). The default
    # is broad only so tests can use ValueError; production callers MUST narrow it.
```

- [ ] **Step 2: Re-run helpers tests**

Run: `.venv/bin/pytest tests/test_helpers.py -v`
Expected: PASS (unchanged).

- [ ] **Step 3: Commit**

```bash
git add helpers.py
git commit -m "docs: clarify with_retry retry_on policy"
```

---

## Task 3: Ledger

**Files:**
- Create: `ledger.py`
- Test: `tests/test_ledger.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_ledger.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_ledger.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ledger'`.

- [ ] **Step 3: Implement ledger.py**

Create `ledger.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_ledger.py -v`
Expected: PASS (all 5 tests).

- [ ] **Step 5: Commit**

```bash
git add ledger.py tests/test_ledger.py
git commit -m "feat: crash-safe JSON ledger with atomic save"
```

---

## Task 4: Restart reconciliation

**Files:**
- Create: `reconcile.py`
- Test: `tests/test_reconcile.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_reconcile.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_reconcile.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'reconcile'`.

- [ ] **Step 3: Implement reconcile.py**

Create `reconcile.py`:

```python
"""Decide, from the ledger + a fresh remote listing, what to do per file.
This is the heart of restart-safety: it never re-uploads completed work."""
from dataclasses import dataclass

from helpers import RemoteFile


@dataclass(frozen=True)
class WorkItem:
    rf: RemoteFile
    action: str  # "upload" (download+upload+album+delete) or "delete_only"


def plan_work(remote_files, ledger):
    """Return (todo, skipped_count). `remote_files` is the CURRENT Dropbox listing,
    so any file present here that the ledger calls 'uploaded' only needs deleting."""
    todo = []
    skipped = 0
    for rf in remote_files:
        st = ledger.status(rf.id)
        if st == "deleted":
            skipped += 1
        elif st == "uploaded":
            todo.append(WorkItem(rf, "delete_only"))
        else:  # "absent" or "error"
            todo.append(WorkItem(rf, "upload"))
    return todo, skipped
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_reconcile.py -v`
Expected: PASS (all 4 tests).

- [ ] **Step 5: Commit**

```bash
git add reconcile.py tests/test_reconcile.py
git commit -m "feat: restart-safe work reconciliation"
```

---

## Task 5: Mover orchestration (with fakes)

This is the per-file pipeline and the main loop. It takes injected client objects and a
reporter, so it is fully testable without any network. The `move_one` contract:

- **upload action:** download → upload bytes → add to album → ledger `uploaded` →
  delete from Dropbox → ledger `deleted`. The ledger flips to `uploaded` *before* the
  delete, so a crash between them is recovered as `delete_only` on the next run.
- **delete_only action:** delete from Dropbox → ledger `deleted`.
- Any exception is caught by `run()`, recorded as `error` (file stays in Dropbox), and the
  loop continues.

**Files:**
- Create: `mover.py`
- Test: `tests/test_mover.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_mover.py`:

```python
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
    # temp file cleaned up
    assert list(tmp_path.glob("*.tmp")) == []


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
    assert list(tmp_path.glob("*.tmp")) == []  # temp still cleaned


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
    assert photos.uploaded == []  # still no re-upload
    assert led.status("id:1") == "deleted"


def test_dry_run_does_nothing_destructive(tmp_path):
    led = Ledger.load(str(tmp_path / "x.json"))
    dbx, photos = FakeDropbox(), FakePhotos()
    move_one(WorkItem(rf(1), "upload"), dbx, photos, led, "ALB",
             NullReporter(), str(tmp_path), dry_run=True)
    assert dbx.downloaded == [] and photos.uploaded == [] and dbx.deleted == []
    assert led.status("id:1") == "absent"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_mover.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mover'`.

- [ ] **Step 3: Implement mover.py**

Create `mover.py`:

```python
"""Orchestration: the per-file pipeline and the main run loop.
Imports NO SDKs — clients are injected, so this is unit-tested with fakes."""
import os
import sys

from helpers import tally_line, human_size
from reconcile import plan_work


class NullReporter:
    """No-op reporter for tests."""
    def start(self, count, total_bytes): pass
    def begin_file(self, idx, total, rf): pass
    def step(self, label, ok): pass
    def tally(self, done, errors, left, bytes_done, bytes_total): pass
    def finish(self, summary): pass


class ConsoleReporter:
    """Obvious, live console progress."""
    def start(self, count, total_bytes):
        print(f"\nMoving {count} files ({human_size(total_bytes)}) "
              f"to Google Photos.\n")

    def begin_file(self, idx, total, rf):
        self._steps = []
        sys.stdout.write(f"[ {idx}/{total} ]  {rf.name}  ({human_size(rf.size)})\n")
        sys.stdout.write("            ")
        sys.stdout.flush()

    def step(self, label, ok):
        mark = "✓" if ok else "✗"
        sys.stdout.write(f"{label} {mark}   ")
        sys.stdout.flush()

    def tally(self, done, errors, left, bytes_done, bytes_total):
        sys.stdout.write("\n" + tally_line(done, errors, left, bytes_done, bytes_total)
                         + "\n\n")
        sys.stdout.flush()

    def finish(self, summary):
        print("\n" + "=" * 50)
        print(summary)
        print("=" * 50)


def move_one(item, dbx, photos, ledger, album_id, reporter, tmp_dir, dry_run):
    """Execute one WorkItem. Raises on failure (caller records the error)."""
    rf = item.rf

    if item.action == "delete_only":
        if dry_run:
            reporter.step("would delete", True)
            return
        dbx.delete(rf.id)
        reporter.step("delete", True)
        ledger.mark(rf.id, "deleted", name=rf.name, size=rf.size)
        return

    # action == "upload"
    if dry_run:
        reporter.step("would upload + delete", True)
        return

    # Unique temp name so concurrent ids never collide (id contains ':').
    safe = rf.id.replace(":", "_").replace("/", "_")
    tmp = os.path.join(tmp_dir, f"{safe}__{rf.name}")
    try:
        dbx.download(rf.id, tmp)
        reporter.step("download", True)

        token = photos.upload_bytes(tmp, rf.name)
        reporter.step("upload", True)

        media_id = photos.add_to_album(album_id, token, rf.name)
        reporter.step("album", True)

        # Record success BEFORE deleting: a crash here recovers as delete_only.
        ledger.mark(rf.id, "uploaded", name=rf.name, size=rf.size,
                    media_item_id=media_id)

        dbx.delete(rf.id)
        reporter.step("delete", True)
        ledger.mark(rf.id, "deleted", name=rf.name, size=rf.size)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def run(remote_files, dbx, photos, ledger, album_id, reporter, tmp_dir, dry_run):
    """Plan the work, then execute each item, tolerating per-file errors."""
    todo, skipped = plan_work(remote_files, ledger)
    total = len(todo)
    total_bytes = sum(w.rf.size for w in todo)
    reporter.start(total, total_bytes)

    done = errors = 0
    bytes_done = 0
    for idx, item in enumerate(todo, start=1):
        reporter.begin_file(idx, total, item.rf)
        try:
            move_one(item, dbx, photos, ledger, album_id, reporter, tmp_dir, dry_run)
            done += 1
        except Exception as e:  # noqa: BLE001 - one bad file must not stop the run
            errors += 1
            reporter.step("FAILED: " + str(e), False)
            if not dry_run:
                ledger.mark(item.rf.id, "error", name=item.rf.name,
                            size=item.rf.size, error=str(e))
        bytes_done += item.rf.size
        reporter.tally(done, errors, total - idx, bytes_done, total_bytes)

    summary = (f"Done. {done} moved, {errors} errors, {skipped} already-done skipped.\n"
               f"Ledger: {ledger.path}")
    reporter.finish(summary)
    return {"done": done, "errors": errors, "skipped": skipped}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_mover.py -v`
Expected: PASS (all 5 tests).

- [ ] **Step 5: Commit**

```bash
git add mover.py tests/test_mover.py
git commit -m "feat: mover orchestration with restart-safe per-file pipeline"
```

---

## Task 6: Real API clients

These touch the network and OAuth, so they are not unit-tested; they're verified in the
real run (Task 8). Keep them thin. Both expose exactly the methods the fakes in Task 5
implement, so `mover` works against either.

**Files:**
- Create: `clients.py`

- [ ] **Step 1: Implement DropboxClient**

Create `clients.py` with this content first:

```python
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

# Transient conditions worth retrying.
_NET_ERRORS = (requests.exceptions.RequestException, ConnectionError, TimeoutError)


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
```

- [ ] **Step 2: Append PhotosClient to clients.py**

Add to `clients.py`:

```python
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
        # google.rpc.Status: code 0 (or absent) / message "Success" == OK
        if status.get("code", 0) not in (0,) and status.get("message") != "Success":
            raise RuntimeError(f"batchCreate failed for {name}: {status}")
        return result["mediaItem"]["id"]
```

- [ ] **Step 3: Verify the module imports cleanly**

Run: `.venv/bin/python -c "import clients; print('ok')"`
Expected: prints `ok` (no syntax/import errors). This does not hit the network.

- [ ] **Step 4: Commit**

```bash
git add clients.py
git commit -m "feat: real Dropbox and Google Photos API clients"
```

---

## Task 7: CLI wiring and preconditions

**Files:**
- Create: `dbtogp.py`

- [ ] **Step 1: Implement dbtogp.py**

Create `dbtogp.py`:

```python
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

# Public Dropbox app key created per SETUP.md (PKCE app, no secret needed).
DROPBOX_APP_KEY = os.environ.get("DROPBOX_APP_KEY", "")


def parse_args(argv):
    p = argparse.ArgumentParser(description="Move a Dropbox folder to a Google Photos album.")
    p.add_argument("--folder", required=True, help="Dropbox folder path, e.g. /Trip")
    p.add_argument("--album", required=True, help="Google Photos album name")
    p.add_argument("--config-dir", default=os.path.join(os.path.dirname(__file__), ".dbtogp"),
                   help="Where tokens, ledger and log live (default .dbtogp/)")
    p.add_argument("--client-secret", default=None,
                   help="Path to Google client_secret.json (default <config-dir>/client_secret.json)")
    p.add_argument("--dry-run", action="store_true",
                   help="List what would happen; upload/delete nothing.")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv if argv is not None else sys.argv[1:])

    if not DROPBOX_APP_KEY:
        sys.exit("ERROR: set DROPBOX_APP_KEY (see SETUP.md).")

    config_dir = os.path.abspath(args.config_dir)
    os.makedirs(config_dir, exist_ok=True)
    client_secret = args.client_secret or os.path.join(config_dir, "client_secret.json")
    if not os.path.exists(client_secret):
        sys.exit(f"ERROR: Google client secret not found at {client_secret} (see SETUP.md).")

    print("=" * 60)
    print("REMINDER: Google Photos must be set to 'Original quality'")
    print("(photos.google.com -> Settings -> Upload size) or your photos")
    print("will be downscaled. The script cannot check or change this.")
    print("=" * 60)

    dbx = DropboxClient(DROPBOX_APP_KEY, os.path.join(config_dir, "dropbox_token.json"))
    photos = PhotosClient(client_secret, os.path.join(config_dir, "google_token.json"))

    # Precondition: list folder, assert no subfolders.
    subfolders, files = dbx.list_folder(args.folder)
    if subfolders:
        sys.exit("ERROR: folder contains subfolders, which is not supported:\n  - "
                 + "\n  - ".join(subfolders))

    media = [f for f in files if is_media_file(f.name)]
    skipped_nonmedia = len(files) - len(media)
    if skipped_nonmedia:
        print(f"Skipping {skipped_nonmedia} non-media file(s).")

    ledger = Ledger.load(os.path.join(config_dir, slugify(args.album) + ".json"))

    if args.dry_run:
        album_id = ledger.album_id() or "<dry-run-no-album>"
    else:
        album_id = ledger.album_id()
        if not album_id:
            album_id = photos.ensure_album(args.album)
            ledger.set_album(album_id, args.album, args.folder)

    run(media, dbx, photos, ledger, album_id, ConsoleReporter(),
        config_dir, args.dry_run)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify CLI arg parsing and the missing-key guard**

Run: `.venv/bin/python dbtogp.py --folder /X --album Y` (with `DROPBOX_APP_KEY` unset)
Expected: exits with `ERROR: set DROPBOX_APP_KEY (see SETUP.md).`

Run: `.venv/bin/python dbtogp.py --help`
Expected: prints usage with `--folder`, `--album`, `--config-dir`, `--client-secret`, `--dry-run`.

- [ ] **Step 3: Commit**

```bash
git add dbtogp.py
git commit -m "feat: CLI entrypoint, preconditions, album resolution, wiring"
```

---

## Task 8: Docs and a real end-to-end dry run

**Files:**
- Create: `SETUP.md`, `README.md`

- [ ] **Step 1: Write SETUP.md**

Create `SETUP.md`:

```markdown
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
4. On the app's Settings tab, copy the **App key**. Export it before running:
   `export DROPBOX_APP_KEY=your_app_key_here`
   (No app secret is needed — the script uses PKCE.)

## First run

```bash
export DROPBOX_APP_KEY=your_app_key_here
.venv/bin/python dbtogp.py --folder "/Camera Uploads" --album "My Album" --dry-run
```

The first run opens a browser for Google sign-in and prints a Dropbox auth URL to
paste a code back. Tokens are cached in `.dbtogp/` so later runs are non-interactive.

## IMPORTANT: original quality

Before a real run, set photos.google.com -> Settings -> "Upload size" to
**Original quality**, or photos over 16MP and videos over 1080p will be downscaled.
```

- [ ] **Step 2: Write README.md**

Create `README.md`:

```markdown
# dbtogp — Dropbox folder -> Google Photos album

Moves the media files from one **top-level** Dropbox folder into a Google Photos
album: uploads the original file (preserving metadata and resolution), confirms it,
then deletes it from Dropbox. Safe to interrupt and re-run — a JSON ledger in
`.dbtogp/` tracks every file so nothing is uploaded twice or lost.

## Use

See `SETUP.md` for the one-time OAuth setup, then:

```bash
export DROPBOX_APP_KEY=...
.venv/bin/python dbtogp.py --folder "/Camera Uploads" --album "My Album" --dry-run  # preview
.venv/bin/python dbtogp.py --folder "/Camera Uploads" --album "My Album"            # for real
```

## Notes / limitations

- The folder must have **no subfolders** (the script aborts if it finds any).
- Google must be set to **Original quality** (the script can't check this).
- Albums are created by the script; it can't add to an album you made by hand.
- A tiny window exists between "added to album" and the ledger write; a crash there
  is recovered as a delete on the next run (no double upload).

## Tests

```bash
.venv/bin/pytest -v
```
```

- [ ] **Step 3: Run the full test suite**

Run: `.venv/bin/pytest -v`
Expected: PASS — all tests from Tasks 2–5 green.

- [ ] **Step 4: Commit**

```bash
git add SETUP.md README.md
git commit -m "docs: SETUP and README"
```

- [ ] **Step 5: Real dry run (manual, requires the user's OAuth setup)**

After completing `SETUP.md`:

```bash
export DROPBOX_APP_KEY=...
.venv/bin/python dbtogp.py --folder "<real folder>" --album "<name>" --dry-run
```
Expected: completes auth, lists the file count and total size, prints "would
upload + delete" per file, and uploads/deletes nothing. Confirm the count matches
what's in the Dropbox folder and that no subfolder error is wrongly raised.

---

## Self-Review notes (for the executor)

- **Spec coverage:** Dropbox API source (Task 6), delete-after-confirm (Task 5
  `move_one` ordering), top-level + no-subfolder assertion (Task 7), photos+videos
  filter (Task 2 `is_media_file` / Task 7), setup walkthrough (Task 8 `SETUP.md`),
  JSON atomic ledger (Task 3), one-at-a-time obvious progress (Task 5 `ConsoleReporter`),
  dry-run (Tasks 5 & 7), original-quality + app-album warnings (Task 7 banner, docs).
- **Restart safety:** ledger marks `uploaded` before delete; `plan_work` maps
  uploaded-but-present -> `delete_only` (Task 4 tests + Task 5 crash test).
- **Method-name contract:** fakes in Task 5 and real clients in Task 6 share the
  exact signatures `download(id,dest)`, `delete(id)`, `upload_bytes(path,name)`,
  `add_to_album(album,token,name)` — verified by `mover` calling only these.
```
