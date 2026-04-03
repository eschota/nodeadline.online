from libs.torrent import tracker


def test_register_list():
    tracker.register_content(
        infohash_hex="ab" * 20,
        owner_sub="u1",
        share_id="s1",
        file_count=1,
        total_bytes=10,
        snapshot_revision=1,
    )
    lst = tracker.list_content()
    assert len(lst) >= 1
