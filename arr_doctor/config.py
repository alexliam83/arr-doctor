"""Settings loaded from environment variables (and an optional `.env` file)."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# `.env` is looked up in the current directory and in the repository root, so it
# works both from a checkout and when Claude Desktop launches the entry point
# with an arbitrary working directory.
_REPO_ROOT = Path(__file__).resolve().parent.parent
_ENV_FILES = (str(_REPO_ROOT / ".env"), ".env")


class ServiceConfig:
    """URL + API key for one *arr service."""

    def __init__(self, name: str, url: str, api_key: str) -> None:
        self.name = name
        self.url = url.rstrip("/")
        self.api_key = api_key

    def __repr__(self) -> str:  # never leak the key in logs
        return f"ServiceConfig(name={self.name!r}, url={self.url!r})"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_FILES,
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    sonarr_url: str | None = None
    # SecretStr: the keys never show up if the settings are printed or logged.
    sonarr_api_key: SecretStr | None = None
    radarr_url: str | None = None
    radarr_api_key: SecretStr | None = None
    prowlarr_url: str | None = None
    prowlarr_api_key: SecretStr | None = None

    arr_readonly: bool = False
    arr_timeout: float = Field(default=15.0, gt=0)
    #: Download folder as Sonarr/Radarr see it. None = detect it from the queue/history.
    arr_downloads_path: str | None = None
    #: Guardrails (see docs/GOOD_PRACTICES.md).
    #: Searches touching more items than this need confirm=true.
    arr_search_confirm_above: int = Field(default=10, ge=1)
    #: Skip items Sonarr/Radarr searched less than N minutes ago (force=true overrides). 0 = off.
    arr_search_cooldown_minutes: int = Field(default=60, ge=0)
    #: Max operations that query the indexers per hour (searches, grabs, tests). 0 = unlimited.
    arr_indexer_budget_per_hour: int = Field(default=30, ge=0)
    #: Language of error messages and notes returned by the tools ("en" or "es").
    arr_lang: Literal["en", "es"] = "en"

    @field_validator(
        "sonarr_url",
        "sonarr_api_key",
        "radarr_url",
        "radarr_api_key",
        "prowlarr_url",
        "prowlarr_api_key",
        "arr_downloads_path",
        mode="before",
    )
    @classmethod
    def _blank_is_none(cls, v: object) -> object:
        if isinstance(v, str) and not v.strip():
            return None
        return v.strip() if isinstance(v, str) else v

    @field_validator("arr_lang", mode="before")
    @classmethod
    def _lang(cls, v: object) -> object:
        return v.strip().lower()[:2] if isinstance(v, str) and v.strip() else "en"

    def _service(self, name: str) -> ServiceConfig | None:
        url = getattr(self, f"{name}_url")
        key: SecretStr | None = getattr(self, f"{name}_api_key")
        if url and key and key.get_secret_value():
            return ServiceConfig(name, url, key.get_secret_value())
        return None

    @property
    def sonarr(self) -> ServiceConfig | None:
        return self._service("sonarr")

    @property
    def radarr(self) -> ServiceConfig | None:
        return self._service("radarr")

    @property
    def prowlarr(self) -> ServiceConfig | None:
        return self._service("prowlarr")

    def incomplete_services(self) -> list[str]:
        """Services with only one of URL / API key set (likely a typo)."""
        out = []
        for name in ("sonarr", "radarr", "prowlarr"):
            url = getattr(self, f"{name}_url")
            key = getattr(self, f"{name}_api_key")
            if bool(url) != bool(key):
                out.append(name)
        return out
