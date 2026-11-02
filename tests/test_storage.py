import pytest

from core.storage import LocalStorage, file_key

USER = "00000000-0000-0000-0000-00000000000a"
HASH = "a" * 64


def test_roundtrip_and_delete(tmp_path):
    store = LocalStorage(tmp_path)
    key = file_key(USER, HASH, "jpg")
    assert store.read(key) is None
    store.save(key, b"abc")
    assert store.read(key) == b"abc"
    store.delete(key)
    assert store.read(key) is None
    store.delete(key)  # deleting twice is fine


@pytest.mark.parametrize(
    "key", ["../secret", f"{USER}/../../etc/passwd", f"{USER}/{HASH}.jpg/..", "/etc/passwd", f"{USER}/short.jpg", ""]
)
def test_keys_cannot_leave_the_storage_folder(tmp_path, key):
    store = LocalStorage(tmp_path)
    with pytest.raises(ValueError):
        store.read(key)
    with pytest.raises(ValueError):
        store.save(key, b"x")
