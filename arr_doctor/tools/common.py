"""Shared plumbing for the tool modules: service registry and title resolution."""

from __future__ import annotations

import asyncio
import difflib
import functools
import re
import unicodedata
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Annotated, Any, Literal, ParamSpec, TypeVar, Union

from pydantic import Field

from arr_doctor.clients import ArrError, ProwlarrClient, RadarrClient, SonarrClient
from arr_doctor.config import Settings
from arr_doctor.guards import IndexerBudget
from arr_doctor.i18n import t

ArrService = Literal["sonarr", "radarr"]
ServiceOpt = Annotated[ArrService | None, Field(description="'sonarr' or 'radarr'; omit to query both")]
ServiceReq = Annotated[ArrService, Field(description="'sonarr' (series) or 'radarr' (movies)")]

READ_ONLY = {"readOnlyHint": True, "openWorldHint": False}
WRITE = {"readOnlyHint": False, "destructiveHint": False, "openWorldHint": False}
DESTRUCTIVE = {"readOnlyHint": False, "destructiveHint": True, "openWorldHint": False}

P = ParamSpec("P")
R = TypeVar("R")


@dataclass
class Services:
    settings: Settings
    sonarr: SonarrClient | None = None
    radarr: RadarrClient | None = None
    prowlarr: ProwlarrClient | None = None
    budget: IndexerBudget = field(default_factory=lambda: IndexerBudget(30))
    #: (service, item id) -> (monotonic time, approved releases) of recent explain_search runs.
    interactive: dict[tuple[str, int], tuple[float, int]] = field(default_factory=dict)

    @classmethod
    def from_settings(cls, settings: Settings) -> Services:
        t = settings.arr_timeout
        return cls(
            settings=settings,
            sonarr=SonarrClient(settings.sonarr, t) if settings.sonarr else None,
            radarr=RadarrClient(settings.radarr, t) if settings.radarr else None,
            prowlarr=ProwlarrClient(settings.prowlarr, t) if settings.prowlarr else None,
            budget=IndexerBudget(settings.arr_indexer_budget_per_hour),
        )

    @property
    def has_arr(self) -> bool:
        return bool(self.sonarr or self.radarr)

    def require_sonarr(self) -> SonarrClient:
        if not self.sonarr:
            raise ArrError(t("not_configured", svc="Sonarr", env="SONARR"))
        return self.sonarr

    def require_radarr(self) -> RadarrClient:
        if not self.radarr:
            raise ArrError(t("not_configured", svc="Radarr", env="RADARR"))
        return self.radarr

    def arrs(self, service: ArrService | None) -> list[tuple[str, SonarrClient | RadarrClient]]:
        """Clients selected by ``service`` (None = every configured one)."""
        if service == "sonarr":
            return [("sonarr", self.require_sonarr())]
        if service == "radarr":
            return [("radarr", self.require_radarr())]
        out: list[tuple[str, SonarrClient | RadarrClient]] = []
        if self.sonarr:
            out.append(("sonarr", self.sonarr))
        if self.radarr:
            out.append(("radarr", self.radarr))
        return out


ArrClientT = Union[SonarrClient, RadarrClient]  # noqa: UP007


async def per_service(
    svc: Services,
    service: ArrService | None,
    fn: Callable[[str, ArrClientT], Awaitable[Any]],
) -> dict[str, Any]:
    """Run ``fn`` for each selected service concurrently.

    When several services are queried, one failing service does not hide the
    others: its entry becomes ``{"error": "..."}``. It only raises when every
    service fails, or when a single service was requested.
    """
    targets = svc.arrs(service)
    results = await asyncio.gather(*(fn(n, c) for n, c in targets), return_exceptions=True)
    out: dict[str, Any] = {}
    errors: list[str] = []
    for (name, _), res in zip(targets, results, strict=True):
        if isinstance(res, BaseException):
            if not isinstance(res, ArrError) or len(targets) == 1:
                raise res
            out[name] = {"error": str(res)}
            errors.append(str(res))
        else:
            out[name] = res
    if errors and len(errors) == len(targets):
        raise ArrError(" | ".join(errors))
    return out


async def ask_user(ctx: Any, message: str) -> bool | None:
    """Ask the user directly through the MCP client (elicitation), not through the model.

    True = the user accepted, False = declined or cancelled, None = the client does not
    support elicitation (callers then fall back to the preview-token flow).
    """
    session = getattr(ctx, "session", None)
    params = getattr(session, "client_params", None) if session else None
    if params is None or getattr(params.capabilities, "elicitation", None) is None:
        return None
    try:
        answer = await ctx.elicit(message, response_type=None)
    except Exception:  # noqa: BLE001 - a client that advertises but fails: fall back
        return None
    return getattr(answer, "action", None) == "accept"


# ------------------------------------------------------------ ambiguity


class AmbiguousMatch(Exception):
    """Raised by resolvers when a title matches more than one item."""

    def __init__(self, kind: str, query: str, candidates: list[dict[str, Any]]) -> None:
        super().__init__(f"'{query}' is ambiguous ({kind})")
        self.kind = kind
        self.query = query
        self.candidates = candidates


def returns_candidates(fn: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R | dict[str, Any]]]:
    """Turn :class:`AmbiguousMatch` into a normal result listing the candidates."""

    @functools.wraps(fn)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R | dict[str, Any]:
        try:
            return await fn(*args, **kwargs)
        except AmbiguousMatch as amb:
            return {
                "ambiguous": True,
                "message": t("ambiguous", query=amb.query, kind=t(f"kind_{amb.kind}")),
                "candidates": amb.candidates,
            }

    return wrapper


def normalize_title(text: str | None) -> str:
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^\w\s]", " ", text.casefold())
    return " ".join(text.split())


_SINGULAR = {"series": "series", "movies": "movie"}

_YEAR_SUFFIX = re.compile(r"^(.*?)[\s(\[]+((?:19|20)\d{2})[)\]]?\s*$")


def _match_by_title(
    items: list[dict[str, Any]], query: str, kind: str, candidate: Callable[[dict[str, Any]], dict[str, Any]]
) -> dict[str, Any]:
    query = query.strip()
    year: int | None = None
    m = _YEAR_SUFFIX.match(query)
    if m:
        query_title, year = m.group(1), int(m.group(2))
    else:
        query_title = query
    q = normalize_title(query_title)
    if not q:
        raise ArrError(t("need_title_or_id"))

    def titles(it: dict[str, Any]) -> list[str]:
        alts = [a.get("title") for a in it.get("alternateTitles") or [] if isinstance(a, dict)]
        return [normalize_title(t) for t in [it.get("title"), it.get("originalTitle"), *alts] if t]

    pool = [it for it in items if year is None or it.get("year") == year]
    exact = [it for it in pool if q in titles(it)]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        raise AmbiguousMatch(kind, query, [candidate(it) for it in exact])

    # Partial match by whole words (the last one may be cut short), so "the" does
    # not match every title that happens to contain those letters.
    q_words = q.split()

    def word_match(title: str) -> bool:
        words = title.split()
        return all(w in words for w in q_words[:-1]) and any(w.startswith(q_words[-1]) for w in words)

    partial = [it for it in pool if any(word_match(t) for t in titles(it))]
    if len(partial) == 1:
        return partial[0]
    if len(partial) > 1:
        raise AmbiguousMatch(kind, query, [candidate(it) for it in partial[:20]])

    # Suggestions ignore leading articles: otherwise "The Office" ~ "The Curse".
    names = {_strip_article(normalize_title(it.get("title"))): it for it in items}
    close = difflib.get_close_matches(_strip_article(q), list(names), n=5, cutoff=0.75)
    hint = ""
    if close:
        options = ", ".join(f"{names[c].get('title')} (id {names[c].get('id')})" for c in close)
        hint = t("did_you_mean", options=options)
    raise ArrError(t(f"{_SINGULAR[kind]}_not_found", query=query, hint=hint))


_ARTICLES = ("the ", "a ", "an ", "el ", "la ", "los ", "las ", "le ", "les ", "der ", "die ", "das ")


def _strip_article(title: str) -> str:
    for art in _ARTICLES:
        if title.startswith(art):
            return title[len(art):]
    return title


def _candidate(it: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in {"id": it.get("id"), "title": it.get("title"), "year": it.get("year")}.items() if v}


async def _resolve(
    ident: str | int,
    get_one: Callable[[int], Awaitable[dict[str, Any]]],
    get_all: Callable[[], Awaitable[list[dict[str, Any]]]],
    kind: str,
) -> dict[str, Any]:
    # An int is always an ID. A digit-only string may also be a title ("1917",
    # "24"), so an exact title match wins over the ID interpretation.
    if isinstance(ident, int):
        return await get_one(ident)
    text = ident.strip()
    if text.isdigit():
        items = await get_all()
        exact = [it for it in items if normalize_title(it.get("title")) == text]
        if len(exact) == 1:
            return exact[0]
        if len(exact) > 1:
            raise AmbiguousMatch(kind, text, [_candidate(it) for it in exact])
        return await get_one(int(text))
    return _match_by_title(await get_all(), text, kind, _candidate)


async def resolve_in(items: list[dict[str, Any]], ident: str | int, kind: Literal["series", "movies"]) -> dict[str, Any]:
    """Resolve an ID or title against an already loaded list (no extra requests)."""

    async def get_one(item_id: int) -> dict[str, Any]:
        for it in items:
            if it.get("id") == item_id:
                return it
        raise ArrError(t("id_not_found", kind=t(f"kind_{kind}"), id=item_id))

    async def get_all() -> list[dict[str, Any]]:
        return items

    return await _resolve(ident, get_one, get_all, kind)


async def resolve_series(sonarr: SonarrClient, ident: str | int) -> dict[str, Any]:
    """Return the full series resource for an ID or a title."""
    return await _resolve(ident, sonarr.get_series, sonarr.list_series, "series")


async def resolve_movie(radarr: RadarrClient, ident: str | int) -> dict[str, Any]:
    """Return the full movie resource for an ID or a title."""
    return await _resolve(ident, radarr.get_movie, radarr.list_movies, "movies")
