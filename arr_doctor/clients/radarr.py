"""Radarr API client (``/api/v3``)."""

from __future__ import annotations

from typing import Any

from arr_doctor.clients.base import ArrClient

# MovieHistoryEventType (NzbDrone.Core/History/MovieHistory.cs).
HISTORY_EVENT_TYPES: dict[str, int] = {
    "grabbed": 1,
    "downloadFolderImported": 3,
    "downloadFailed": 4,
    "movieFileDeleted": 6,
    "movieFolderImported": 7,
    "movieFileRenamed": 8,
    "downloadIgnored": 9,
}


class RadarrClient(ArrClient):
    display_name = "Radarr"
    api_prefix = "/api/v3"

    # ----------------------------------------------------------------- library

    async def list_movies(self) -> list[dict[str, Any]]:
        return await self.get("/movie")

    async def get_movie(self, movie_id: int) -> dict[str, Any]:
        return await self.get(f"/movie/{movie_id}")

    async def lookup_movie(self, term: str) -> list[dict[str, Any]]:
        return await self.get("/movie/lookup", term=term)

    async def add_movie(self, movie: dict[str, Any]) -> dict[str, Any]:
        return await self.post("/movie", json=movie)

    async def set_movies_monitored(self, movie_ids: list[int], monitored: bool) -> Any:
        return await self.put("/movie/editor", json={"movieIds": movie_ids, "monitored": monitored})

    async def missing(self, page_size: int, monitored: bool = True) -> dict[str, Any]:
        return await self.get("/wanted/missing", page=1, pageSize=page_size, monitored=monitored)

    async def cutoff_unmet(self, page_size: int, monitored: bool = True) -> dict[str, Any]:
        return await self.get("/wanted/cutoff", page=1, pageSize=page_size, monitored=monitored)

    async def calendar(self, start: str, end: str, unmonitored: bool = False) -> list[dict[str, Any]]:
        return await self.get("/calendar", start=start, end=end, unmonitored=unmonitored)

    async def quality_profiles(self) -> list[dict[str, Any]]:
        return await self.get("/qualityprofile")

    async def root_folders(self) -> list[dict[str, Any]]:
        return await self.get("/rootfolder")

    # ------------------------------------------------------------- diagnostics

    async def queue(self, page_size: int = 1000, include_unknown: bool = False) -> dict[str, Any]:
        """Queue items. Unknown items (downloads in the client that Radarr did not grab)
        are left out by default, like in the web UI."""
        return await self.get(
            "/queue", page=1, pageSize=page_size, includeMovie=True, includeUnknownMovieItems=include_unknown
        )

    async def history(
        self,
        page_size: int,
        movie_id: int | None = None,
        event_type: int | None = None,
    ) -> dict[str, Any]:
        return await self.get(
            "/history",
            page=1,
            pageSize=page_size,
            sortKey="date",
            sortDirection="descending",
            includeMovie=True,
            movieIds=[movie_id] if movie_id else None,
            eventType=[event_type] if event_type else None,
        )

    async def history_since(self, date: str, event_type: int | None = None) -> list[dict[str, Any]]:
        return await self.get("/history/since", date=date, eventType=event_type, includeMovie=True)

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

    async def releases(self, movie_id: int, timeout: float | None = None) -> list[dict[str, Any]]:
        """Interactive search: every release found with Radarr's decision (approved/rejections)."""
        return await self.request("GET", "/release", params={"movieId": movie_id}, timeout=timeout)


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

    async def rename_preview(self, movie_id: int) -> list[dict[str, Any]]:
        return await self.get("/rename", movieId=movie_id)

    async def edit_movies(self, body: dict[str, Any]) -> Any:
        return await self.put("/movie/editor", json=body)

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
