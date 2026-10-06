from __future__ import annotations

import pytest

from arr_doctor.config import Settings
from tests.conftest import make_settings


def test_services_need_url_and_key() -> None:
    s = Settings(_env_file=None, sonarr_url="http://x:1/", sonarr_api_key="k", radarr_url="http://y:2")
    assert s.sonarr is not None and s.sonarr.url == "http://x:1"
    assert s.radarr is None
    assert s.prowlarr is None
    assert s.incomplete_services() == ["radarr"]


def test_blank_values_are_unset() -> None:
    s = Settings(_env_file=None, sonarr_url="  ", sonarr_api_key="")
    assert s.sonarr_url is None and s.sonarr is None


def test_defaults() -> None:
    s = Settings(_env_file=None)
    assert s.arr_readonly is False
    assert s.arr_timeout == 15
    assert s.arr_downloads_path is None  # auto-detected
    assert s.arr_lang == "en"


def test_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RADARR_URL", "http://r:1")
    monkeypatch.setenv("RADARR_API_KEY", "abc")
    monkeypatch.setenv("ARR_READONLY", "true")
    monkeypatch.setenv("ARR_TIMEOUT", "30")
    s = Settings(_env_file=None)
    assert s.radarr is not None
    assert s.arr_readonly is True
    assert s.arr_timeout == 30


def test_repr_hides_api_key() -> None:
    s = make_settings()
    assert "sonarr-key" not in repr(s.sonarr)


def test_settings_repr_never_shows_api_keys() -> None:
    s = make_settings(sonarr_api_key="super-secret-sonarr", radarr_api_key="super-secret-radarr")
    text = repr(s) + str(s) + s.model_dump_json()
    assert "super-secret" not in text
    assert s.sonarr is not None and s.sonarr.api_key == "super-secret-sonarr"
