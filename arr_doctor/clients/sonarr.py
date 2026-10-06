"""Sonarr v4 API client (``/api/v3``)."""

from __future__ import annotations

from typing import Any

from arr_doctor.clients.base import ArrClient

# EpisodeHistoryEventType (NzbDrone.Core/History/EpisodeHistory.cs).
HISTORY_EVENT_TYPES: dict[str, int] = {
    "grabbed": 1,
    "seriesFolderImported": 2,
    "downloadFolderImported": 3,
    "downloadFailed": 4,
    "episodeFileDeleted": 5,
    "episodeFileRenamed": 6,
    "downloadIgnored": 7,
}


class SonarrClient(ArrClient):
    display_name = "Sonarr"
    api_prefix = "/api/v3"

    # ----------------------------------------------------------------- library

    async def list_series(self) -> list[dict[str, Any]]:
        return await self.get("/series")

    async def get_series(self, series_id: int) -> dict[str, Any]:
        return await self.get(f"/series/{series_id}")

    async def update_series(self, series: dict[str, Any]) -> dict[str, Any]:
        return await self.put(f"/series/{series['id']}", json=series)

    async def lookup_series(self, term: str) -> list[dict[str, Any]]:
        return await self.get("/series/lookup", term=term)

    async def add_series(self, series: dict[str, Any]) -> dict[str, Any]:
        return await self.post("/series", json=series)

    async def get_episodes(
        self, series_id: int, season_number: int | None = None, include_file: bool = False
    ) -> list[dict[str, Any]]:
        return await self.get(
            "/episode", seriesId=series_id, seasonNumber=season_number, includeEpisodeFile=include_file
        )

    async def get_episodes_by_id(self, episode_ids: list[int], include_file: bool = False) -> list[dict[str, Any]]:
        return await self.get("/episode", episodeIds=episode_ids, includeEpisodeFile=include_file or None)

    async def set_episodes_monitored(self, episode_ids: list[int], monitored: bool) -> Any:
        return await self.put("/episode/monitor", json={"episodeIds": episode_ids, "monitored": monitored})

    async def missing(self, page_size: int, monitored: bool = True) -> dict[str, Any]:
        return await self.get(
            "/wanted/missing",
            page=1,
            pageSize=page_size,
            sortKey="episodes.airDateUtc",
            sortDirection="descending",
            includeSeries=True,
            monitored=monitored,
        )

    async def cutoff_unmet(self, page_size: int, monitored: bool = True) -> dict[str, Any]:
        return await self.get(
            "/wanted/cutoff",
            page=1,
            pageSize=page_size,
            sortKey="episodes.airDateUtc",
            sortDirection="descending",
            includeSeries=True,
            includeEpisodeFile=True,
            monitored=monitored,
        )

    async def calendar(self, start: str, end: str, unmonitored: bool = False) -> list[dict[str, Any]]:
        return await self.get(
            "/calendar", start=start, end=end, unmonitored=unmonitored, includeSeries=True
        )

    async def quality_profiles(self) -> list[dict[str, Any]]:
        return await self.get("/qualityprofile")

    async def root_folders(self) -> list[dict[str, Any]]:
        return await self.get("/rootfolder")

    # ------------------------------------------------------------- diagnostics

    async def queue(self, page_size: int = 1000, include_unknown: bool = False) -> dict[str, Any]:
        """Queue items. Unknown items (downloads in the client that Sonarr did not grab)
        are left out by default, like in the web UI."""
        return await self.get(
            "/queue",
            page=1,
            pageSize=page_size,
            includeSeries=True,
            includeEpisode=True,
            includeUnknownSeriesItems=include_unknown,
        )

    async def history(
        self,
        page_size: int,
        series_id: int | None = None,
        event_type: int | None = None,
    ) -> dict[str, Any]:
        return await self.get(
            "/history",
            page=1,
            pageSize=page_size,
            sortKey="date",
            sortDirection="descending",
            includeSeries=True,
            includeEpisode=True,
            seriesIds=[series_id] if series_id else None,
            eventType=[event_type] if event_type else None,
        )

    async def history_since(self, date: str, event_type: int | None = None) -> list[dict[str, Any]]:
        return await self.get(
            "/history/since", date=date, eventType=event_type, includeSeries=True, includeEpisode=True
        )

    async def blocklist(self, page_size: int) -> dict[str, Any]:
        return await self.get(
            "/blocklist", page=1, pageSize=page_size, sortKey="date", sortDirection="descending"
        )

    async def logs(self, page_size: int, level: str = "error") -> dict[str, Any]:
        params = {"page": 1, "pageSize": page_size, "sortKey": "time", "sortDirection": "descending", "level": level}
        # Filtering the log database by level is slow on a NAS.
        return await self.request("GET", "/log", params=params, timeout=max(self.timeout, 60))

    async def disk_space(self) -> list[dict[str, Any]]:
        return await self.get("/diskspace")

    async def manual_import_scan(
        self, folder: str, filter_existing: bool = True, timeout: float | None = None
    ) -> list[dict[str, Any]]:
        return await self.request(
            "GET",
            "/manualimport",
            params={"folder": folder, "filterExistingFiles": filter_existing},
            timeout=timeout,
        )


    # ------------------------------------------------------------ troubleshooting

    async def parse(self, title: str) -> dict[str, Any]:
        return await self.get("/parse", title=title)

    async def grab_release(self, guid: str, indexer_id: int) -> dict[str, Any]:
        return await self.post("/release", json={"guid": guid, "indexerId": indexer_id})

    async def remote_path_mappings(self) -> list[dict[str, Any]]:
        return await self.get("/remotepathmapping")

    async def download_clients(self) -> list[dict[str, Any]]:
        return await self.get("/downloadclient")

    async def manual_import_for_download(self, download_id: str, timeout: float | None = None) -> list[dict[str, Any]]:
        return await self.request("GET", "/manualimport", params={"downloadId": download_id}, timeout=timeout)

    async def releases(
        self, episode_id: int | None = None, series_id: int | None = None, season: int | None = None,
        timeout: float | None = None,
    ) -> list[dict[str, Any]]:
        """Interactive search: every release found with Sonarr's decision (approved/rejections)."""
        params = {"episodeId": episode_id} if episode_id else {"seriesId": series_id, "seasonNumber": season}
        return await self.request("GET", "/release", params=params, timeout=timeout)


    # ------------------------------------------------------------ maintenance

    async def tags(self) -> list[dict[str, Any]]:
        return await self.get("/tag")

    async def create_tag(self, label: str) -> dict[str, Any]:
        return await self.post("/tag", json={"label": label})

    async def test_download_clients(self) -> list[dict[str, Any]]:
        # Like Prowlarr's testall: 400 with the same per-client body when one fails.
        return await self.request(
            "POST", "/downloadclient/testall", timeout=max(self.timeout, 60), accept_status=(400,)
        )

    async def rename_preview(self, series_id: int, season: int | None = None) -> list[dict[str, Any]]:
        return await self.get("/rename", seriesId=series_id, seasonNumber=season)

    async def edit_series(self, body: dict[str, Any]) -> Any:
        return await self.put("/series/editor", json=body)

    # ----------------------------------------------------------------- actions

    async def manual_import_reprocess(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Re-evaluate files with a manual assignment; returns them with fresh rejections."""
        return await self.post("/manualimport", json=items)

    async def remove_from_queue(
        self, queue_id: int, remove_from_client: bool, blocklist: bool, skip_redownload: bool
    ) -> Any:
        return await self.delete(
            f"/queue/{queue_id}",
            removeFromClient=remove_from_client,
            blocklist=blocklist,
            skipRedownload=skip_redownload,
        )
