from __future__ import annotations

import pytest

from arr_doctor import paths


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("/downloads/", "/downloads"),
        ("/downloads//tv/", "/downloads/tv"),
        ("/", "/"),
        ("D:\\Downloads\\TV\\", "d:/downloads/tv"),
        ("C:\\", "c:/"),
        ("\\\\NAS\\Media\\", "//nas/media"),
        ("", ""),
    ],
)
def test_normalize(raw: str, expected: str) -> None:
    assert paths.normalize(raw) == expected


def test_posix_paths_stay_case_sensitive() -> None:
    assert not paths.same("/Downloads", "/downloads")
    assert paths.same("D:\\Downloads", "d:/downloads/")


@pytest.mark.parametrize(
    ("path", "folder", "inside"),
    [
        ("/downloads/a/b.mkv", "/downloads/", True),
        ("/downloads", "/downloads/", True),
        ("/downloads-old/b.mkv", "/downloads", False),
        ("D:\\DL\\Show\\x.mkv", "d:\\dl", True),
        ("D:\\DL2\\x.mkv", "D:\\DL", False),
        ("\\\\nas\\media\\x.mkv", "\\\\NAS\\media\\", True),
        ("/x", "", False),
    ],
)
def test_is_within(path: str, folder: str, inside: bool) -> None:
    assert paths.is_within(path, folder) is inside


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/downloads/Release/file.mkv", "/downloads/Release"),
        ("/downloads/Release/", "/downloads"),
        ("/file.mkv", "/"),
        ("D:\\Downloads\\Release", "D:\\Downloads"),
        ("D:\\Release", "D:\\"),
        ("\\\\nas\\media\\x", "\\\\nas\\media"),
    ],
)
def test_parent(path: str, expected: str) -> None:
    assert paths.parent(path) == expected


def test_basename() -> None:
    assert paths.basename("D:\\Downloads\\Release\\") == "Release"
    assert paths.basename("/downloads/file.mkv") == "file.mkv"
