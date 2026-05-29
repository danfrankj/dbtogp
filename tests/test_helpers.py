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


def test_with_retry_backoff_hook_overrides_wait():
    slept = []
    state = {"n": 0}

    def flaky():
        state["n"] += 1
        if state["n"] < 3:
            raise ValueError("transient")
        return "ok"

    # backoff hook ignores the exponential default and always asks for 9s.
    with_retry(flaky, attempts=5, base=1.0, sleep=slept.append,
               backoff=lambda e, default: 9)
    assert slept == [9, 9]
