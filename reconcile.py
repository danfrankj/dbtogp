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
