import types

from clients import _throttle_backoff


def _err(status, headers=None):
    resp = types.SimpleNamespace(status_code=status, headers=headers or {})
    return types.SimpleNamespace(response=resp)


def test_throttle_honors_retry_after_header():
    assert _throttle_backoff(_err(429, {"Retry-After": "45"}), 4) == 45


def test_throttle_429_without_header_floors_at_30():
    assert _throttle_backoff(_err(429, {}), 4) == 30
    assert _throttle_backoff(_err(429, {}), 64) == 64  # keep the larger default


def test_throttle_non_429_uses_default():
    assert _throttle_backoff(_err(500), 4) == 4


def test_throttle_no_response_uses_default():
    assert _throttle_backoff(types.SimpleNamespace(response=None), 4) == 4
