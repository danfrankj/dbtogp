import types

from clients import _is_not_found, _throttle_backoff


def _api_error(is_path, not_found):
    lookup = types.SimpleNamespace(is_not_found=lambda: not_found)
    err = types.SimpleNamespace(is_path=lambda: is_path, get_path=lambda: lookup)
    return types.SimpleNamespace(error=err)


def test_is_not_found_true_for_missing_path():
    assert _is_not_found(_api_error(is_path=True, not_found=True)) is True


def test_is_not_found_false_for_present_path():
    assert _is_not_found(_api_error(is_path=True, not_found=False)) is False


def test_is_not_found_false_for_non_path_error():
    assert _is_not_found(_api_error(is_path=False, not_found=False)) is False


def test_is_not_found_false_for_unexpected_shape():
    assert _is_not_found(types.SimpleNamespace(error=object())) is False


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
