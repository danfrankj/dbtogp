from dbtogp import folder_is_emptied
from helpers import RemoteFile

_FILE = RemoteFile(id="id:1", name="a.jpg", path="/a.jpg", size=10)


def test_offer_delete_when_empty_and_no_errors():
    assert folder_is_emptied(errors=0, subfolders=[], files=[]) is True


def test_no_offer_when_errors():
    assert folder_is_emptied(errors=1, subfolders=[], files=[]) is False


def test_no_offer_when_files_remain():
    assert folder_is_emptied(errors=0, subfolders=[], files=[_FILE]) is False


def test_no_offer_when_subfolders_remain():
    assert folder_is_emptied(errors=0, subfolders=["sub"], files=[]) is False
