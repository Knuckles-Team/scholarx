#!/usr/bin/python
"""OSF / PsyArXiv Paper Provider.

Uses the OSF API v2 for searching OSF preprints and PsyArXiv.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from ..models import Paper, PaperSource, SearchQuery
from .base import PaperProvider

logger = logging.getLogger(__name__)


class OSFProvider(PaperProvider):
    """OSF preprint provider."""

    source = PaperSource.OSF

    def __init__(self, config=None, *, provider_id: str = "osf"):
        super().__init__(config)
        self._provider_id = provider_id

    async def search(self, query: SearchQuery) -> list[Paper]:
        params: dict = {
            "filter[title,description]": query.query,
            "page[size]": min(query.max_results, self.config.max_results_per_query),
        }
        if self._provider_id != "osf":
            params["filter[provider]"] = self._provider_id
        if query.date_from:
            params["filter[date_created][gte]"] = query.date_from
        if query.date_to:
            params["filter[date_created][lte]"] = query.date_to

        headers = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        try:
            resp = await self._get("/preprints/", params=params, headers=headers)
            return [p for p in (self._parse(i) for i in resp.json().get("data", [])) if p]
        except Exception as e:
            logger.error("OSF search failed: error_type=%s", type(e).__name__)
            return []

    async def get_paper(self, paper_id: str) -> Paper | None:
        clean_id = paper_id.replace("osf:", "").replace("psyarxiv:", "")
        headers = {"Authorization": f"Bearer {self._api_key}"} if self._api_key else {}
        try:
            resp = await self._get(f"/preprints/{clean_id}/", headers=headers)
            data = resp.json().get("data", {})
            return self._parse(data) if data else None
        except Exception as e:
            logger.error("OSF paper retrieval failed: error_type=%s", type(e).__name__)
            return None

    async def get_recent(self, categories: list[str] | None = None, days: int = 1) -> list[Paper]:
        date_from = (datetime.now(tz=UTC) - timedelta(days=days)).strftime("%Y-%m-%dT00:00:00")
        params: dict = {"filter[date_created][gte]": date_from, "page[size]": 50, "sort": "-date_created"}
        if self._provider_id != "osf":
            params["filter[provider]"] = self._provider_id
        headers = {"Authorization": f"Bearer {self._api_key}"} if self._api_key else {}
        try:
            resp = await self._get("/preprints/", params=params, headers=headers)
            return [p for p in (self._parse(i) for i in resp.json().get("data", [])) if p]
        except Exception as e:
            logger.error("Operation failed: error_type=%s", type(e).__name__)
            return []

    def _parse(self, item: dict) -> Paper | None:
        if not isinstance(item, dict):
            return None
        attrs = item.get("attributes", {})
        pid = item.get("id", "")
        title = attrs.get("title", "").strip()
        if not title:
            return None
        provider = attrs.get("provider", self._provider_id)
        source = PaperSource.PSYARXIV if provider == "psyarxiv" else PaperSource.OSF
        prefix = "psyarxiv" if provider == "psyarxiv" else "osf"
        dc = attrs.get("date_created", "")
        dm = attrs.get("date_modified", "")
        return Paper(
            id=f"{prefix}:{pid}",
            source=source,
            title=title,
            authors=[],
            abstract=attrs.get("description", "") or "",
            categories=attrs.get("tags", []),
            published_date=dc[:10] if dc else None,
            updated_date=dm[:10] if dm else None,
            doi=attrs.get("doi"),
            url=f"https://osf.io/{pid}/",
            metadata={"osf_id": pid, "provider": provider},
        )


class PsyarxivProvider(OSFProvider):
    """PsyArXiv — OSF API filtered to psyarxiv preprints."""

    source = PaperSource.PSYARXIV

    def __init__(self, config=None):
        from ..models import DEFAULT_SOURCE_CONFIGS

        super().__init__(config=config or DEFAULT_SOURCE_CONFIGS[PaperSource.PSYARXIV], provider_id="psyarxiv")
