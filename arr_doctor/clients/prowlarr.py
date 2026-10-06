"""Prowlarr API client (``/api/v1``)."""

from __future__ import annotations

from typing import Any

from arr_doctor.clients.base import ArrClient


class ProwlarrClient(ArrClient):
    display_name = "Prowlarr"
    api_prefix = "/api/v1"

    async def list_indexers(self) -> list[dict[str, Any]]:
        return await self.get("/indexer")

    async def get_indexer(self, indexer_id: int) -> dict[str, Any]:
        return await self.get(f"/indexer/{indexer_id}")

    async def update_indexer(self, indexer: dict[str, Any]) -> dict[str, Any]:
        return await self.put(f"/indexer/{indexer['id']}", json=indexer)

    async def indexer_status(self) -> list[dict[str, Any]]:
        return await self.get("/indexerstatus")

    async def indexer_stats(self, start_date: str, end_date: str) -> dict[str, Any]:
        return await self.get("/indexerstats", startDate=start_date, endDate=end_date)

    async def test_all(self) -> list[dict[str, Any]]:
        # Testing every indexer can take a while. Prowlarr answers 400 (with the
        # same per-indexer body) when at least one indexer fails.
        return await self.request(
            "POST", "/indexer/testall", timeout=max(self.timeout, 120), accept_status=(400,)
        )
