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
            reporter.step("🗑️ would delete", True)
            return
        dbx.delete(rf.id)
        reporter.step("🗑️ delete", True)
        ledger.mark(rf.id, "deleted", name=rf.name, size=rf.size)
        return

    # action == "upload"
    if dry_run:
        reporter.step("📤🗑️ would upload + delete", True)
        return

    # Unique temp name so concurrent ids never collide (id contains ':').
    safe = rf.id.replace(":", "_").replace("/", "_")
    tmp = os.path.join(tmp_dir, f"{safe}__{rf.name}")
    try:
        dbx.download(rf.id, tmp)
        reporter.step("📥 download", True)

        token = photos.upload_bytes(tmp, rf.name)
        reporter.step("📤 upload", True)

        media_id = photos.add_to_album(album_id, token, rf.name)
        reporter.step("📸 album", True)

        # Record success BEFORE deleting: a crash here recovers as delete_only.
        ledger.mark(rf.id, "uploaded", name=rf.name, size=rf.size,
                    media_item_id=media_id)

        dbx.delete(rf.id)
        reporter.step("🗑️ delete", True)
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
