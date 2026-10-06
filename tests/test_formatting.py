from __future__ import annotations

from arr_doctor import formatting as fmt


def test_shorten() -> None:
    assert fmt.shorten(None) is None
    assert fmt.shorten("a  b\n c") == "a b c"
    long = "x" * 500
    out = fmt.shorten(long)
    assert len(out) == 200 and out.endswith("…")


def test_human_size() -> None:
    assert fmt.human_size(None) is None
    assert fmt.human_size(512) == "512 B"
    assert fmt.human_size(1536) == "2 KB"
    assert fmt.human_size(2_500_000_000) == "2.33 GB"
    assert fmt.human_size(5 * 1024**5) == "5120.00 TB"


def test_limited() -> None:
    out = fmt.limited([1, 2, 3], 2)
    assert out == {"total": 3, "returned": 2, "truncated": True, "items": [1, 2]}
    assert fmt.limited([1], 5, total=1)["truncated"] is False


def test_episode_code() -> None:
    assert fmt.episode_code(3, 4) == "S03E04"
    assert fmt.episode_code(None, 4) is None


def test_status_messages_flatten() -> None:
    q = {"statusMessages": [{"title": "file.mkv", "messages": ["a", "b"]}, {"title": "Only title", "messages": []}]}
    assert fmt.status_messages(q) == ["file.mkv: a", "file.mkv: b", "Only title"]


def test_queue_item_drops_empty_fields() -> None:
    item = fmt.queue_item({"id": 1, "title": "x", "statusMessages": [], "indexer": ""}, "radarr")
    assert item == {"id": 1, "service": "radarr", "title": "x"}
