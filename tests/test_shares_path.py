import os
import tempfile

import pytest

from libs.protocol import ShareEntry
from libs.shares import registry


@pytest.fixture()
def reg(tmp_path):
    registry.set_data_dir(str(tmp_path))
    d = tmp_path / "share"
    d.mkdir()
    (d / "a.txt").write_text("hi")
    sub = d / "sub"
    sub.mkdir()
    (sub / "b.txt").write_text("x")
    return str(d)


def test_safe_resolve_ok(reg):
    e = ShareEntry(
        share_id="1",
        local_path=reg,
        mount_path="m",
        owner_sub="x",
    )
    p = registry.safe_resolve_path(e, "a.txt")
    assert p and os.path.isfile(p)


def test_safe_resolve_traversal(reg):
    e = ShareEntry(share_id="1", local_path=reg, mount_path="m", owner_sub="x")
    assert registry.safe_resolve_path(e, "../outside") is None


def test_safe_resolve_nested(reg):
    e = ShareEntry(share_id="1", local_path=reg, mount_path="m", owner_sub="x")
    p = registry.safe_resolve_path(e, "sub/b.txt")
    assert p and os.path.isfile(p)
