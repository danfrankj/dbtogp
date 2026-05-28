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
    # Clients pass a narrow retry_on (HTTP 429/5xx + network errors). The default
    # is broad only so tests can use ValueError; production callers MUST narrow it.
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
