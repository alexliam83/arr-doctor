"""Prowlarr tools (``/api/v1``)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastmcp import FastMCP
from pydantic import Field

from arr_doctor import formatting as fmt
from arr_doctor.clients.base import ArrError
from arr_doctor.i18n import t
from arr_doctor.tools.common import READ_ONLY, WRITE, Services, normalize_title


def _indexer_summary(i: dict[str, Any], status: dict[int, dict[str, Any]]) -> dict[str, Any]:
    st = status.get(i.get("id") or -1) or {}
    until = st.get("disabledTill")
    if not i.get("enable"):
        state = "disabled"
    elif until and until > datetime.now(UTC).isoformat():
        state = "failing"  # enabled, but Prowlarr paused it after repeated failures
    else:
        state = "ok"
    failing_info = (
        {"last_failure": st.get("mostRecentFailure"), "note": t("indexer_disabled_was_failing")}
        if state == "disabled" and (until or st.get("mostRecentFailure"))
        else {"disabled_until": until, "most_recent_failure": st.get("mostRecentFailure")}
        if state == "failing"
        else {}
    )
    return fmt.drop_none(
        {
            # Prowlarr's own ids: Sonarr/Radarr number the same indexers differently.
            "prowlarr_id": i.get("id"),
            "name": i.get("name"),
            "state": state,
            "enabled": i.get("enable"),
            "priority": i.get("priority"),
            "protocol": i.get("protocol"),
            "privacy": i.get("privacy"),
            "definition": i.get("definitionName") or i.get("implementationName"),
            **failing_info,
        }
    )


async def _resolve_indexer(prowlarr: Any, ident: str | int) -> dict[str, Any]:
    if isinstance(ident, int) or (isinstance(ident, str) and ident.strip().isdigit()):
        return await prowlarr.get_indexer(int(ident))
    q = normalize_title(ident)
    indexers = await prowlarr.list_indexers()
    exact = [i for i in indexers if normalize_title(i.get("name")) == q]
    partial = exact or [i for i in indexers if q in normalize_title(i.get("name"))]
    if len(partial) == 1:
        return await prowlarr.get_indexer(partial[0]["id"])
    if not partial:
        names = ", ".join(sorted(str(i.get("name")) for i in indexers))
        raise ArrError(t("indexer_not_found", query=ident, names=names))
    raise ArrError(
        t("indexer_ambiguous", query=ident, names=", ".join(f"{i.get('name')} (id {i.get('id')})" for i in partial))
    )


def register(mcp: FastMCP, svc: Services, readonly: bool) -> None:
    assert svc.prowlarr is not None
    prowlarr = svc.prowlarr

    @mcp.tool(annotations=READ_ONLY)
    async def list_indexers() -> dict[str, Any]:
        """Indexers configured in Prowlarr: state (ok / failing = paused by Prowlarr after
        repeated failures / disabled), priority, protocol and privacy.

        Examples: "Which indexers do I have?", "Is LimeTorrents disabled?"
        """
        indexers = await prowlarr.list_indexers()
        try:
            status = {s["indexerId"]: s for s in await prowlarr.indexer_status() if "indexerId" in s}
        except ArrError:
            status = {}
        items = sorted(
            (_indexer_summary(i, status) for i in indexers), key=lambda i: (i.get("priority", 25), i.get("name", ""))
        )
        return fmt.limited(items, 500)

    @mcp.tool(annotations=READ_ONLY)
    async def get_indexer_stats(
        days: Annotated[int, Field(ge=1, le=365, description="Look back N days (ignored if start_date is set)")] = 30,
        start_date: Annotated[str | None, Field(description="ISO date, e.g. 2026-10-01")] = None,
        end_date: Annotated[str | None, Field(description="ISO date; default now")] = None,
    ) -> dict[str, Any]:
        """Per-indexer statistics from Prowlarr: queries, RSS, grabs, failures and response
        times, sorted by failure rate (searches + RSS + grabs).

        Examples: "Which indexer fails the most this month?", "How many grabs did each indexer give me?"
        """
        end = end_date or datetime.now(UTC).isoformat()
        start = start_date or (datetime.now(UTC) - timedelta(days=days)).isoformat()
        stats = await prowlarr.indexer_stats(start, end)
        rows = []
        for s in stats.get("indexers") or []:
            queries = s.get("numberOfQueries") or 0
            failed_q = s.get("numberOfFailedQueries") or 0
            grabs = s.get("numberOfGrabs") or 0
            failed_g = s.get("numberOfFailedGrabs") or 0
            rss = s.get("numberOfRssQueries") or 0
            failed_rss = s.get("numberOfFailedRssQueries") or 0
            failed_auth = s.get("numberOfFailedAuthQueries") or 0
            # RSS is most of an indexer's traffic: an indexer that is down shows up
            # as failed RSS long before it fails a search or a grab.
            requests = queries + rss + grabs
            failures = failed_q + failed_rss + failed_g + failed_auth
            rows.append(
                {
                    "prowlarr_id": s.get("indexerId"),
                    "name": s.get("indexerName"),
                    "failure_rate": round(100 * failures / requests, 1) if requests else None,
                    "failures": failures,
                    "queries": queries,
                    "failed_queries": failed_q,
                    "rss_queries": rss,
                    "failed_rss": failed_rss,
                    "grabs": grabs,
                    "failed_grabs": failed_g,
                    "failed_auth": failed_auth,
                    "avg_response_ms": s.get("averageResponseTime"),
                }
            )
        rows.sort(key=lambda r: (r["failure_rate"] or 0, r["failures"]), reverse=True)
        return {"start": start, "end": end, "indexers": [fmt.drop_none(r) for r in rows]}

    if readonly:
        return

    @mcp.tool(annotations={**WRITE, "idempotentHint": True})
    async def set_indexer_enabled(
        indexer: Annotated[str | int, Field(description="Indexer ID or name")],
        enabled: bool,
    ) -> dict[str, Any]:
        """Enable or disable an indexer in Prowlarr.

        Examples: "Disable LimeTorrents", "Turn TheRARBG back on"
        """
        current = await _resolve_indexer(prowlarr, indexer)
        if current.get("enable") == enabled:
            return {"changed": False, "indexer": current.get("name"), "enabled": enabled}
        current["enable"] = enabled
        updated = await prowlarr.update_indexer(current)
        return {"changed": True, "indexer": updated.get("name", current.get("name")), "enabled": updated.get("enable", enabled)}

    @mcp.tool(annotations=WRITE)
    async def test_indexers() -> dict[str, Any]:
        """Run Prowlarr's connectivity test on every indexer and report which ones fail and why.
        It can take a minute.

        Examples: "Test all my indexers", "Which indexers are broken right now?"
        """
        svc.budget.consume(1)
        names = {i["id"]: i.get("name") for i in await prowlarr.list_indexers() if "id" in i}
        results = await prowlarr.test_all() or []
        rows = []
        for r in results:
            failures = [
                f.get("errorMessage") for f in r.get("validationFailures") or [] if f.get("errorMessage")
            ]
            rows.append(
                fmt.drop_none(
                    {"prowlarr_id": r.get("id"), "name": names.get(r.get("id")), "ok": r.get("isValid"), "errors": failures or None}
                )
            )
        rows.sort(key=lambda r: (r.get("ok", False), r.get("name") or ""))
        return {"tested": len(rows), "failing": sum(1 for r in rows if not r.get("ok")), "results": rows}
