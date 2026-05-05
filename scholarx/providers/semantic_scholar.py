#!/usr/bin/python
"""Semantic Scholar Paper Provider.

Uses the Semantic Scholar Academic Graph API (https://api.semanticscholar.org/graph/v1).
Free access; optional S2_API_KEY for higher rate limits (100/5min → 1000/5min).
"""

from __future__ import annotations

import logging

from ..models import Paper, PaperSource, SearchQuery
from .base import PaperProvider

logger = logging.getLogger(__name__)

_FIELDS = "paperId,externalIds,title,abstract,authors,year,citationCount,referenceCount,url,openAccessPdf,fieldsOfStudy,publicationDate"


class SemanticScholarProvider(PaperProvider):
    """Semantic Scholar provider using the Academic Graph API."""

    source = PaperSource.SEMANTIC_SCHOLAR

    async def search(self, query: SearchQuery) -> list[Paper]:
        params: dict = {
            "query": query.query,
            "limit": min(query.max_results, self.config.max_results_per_query),
            "fields": _FIELDS,
        }
        if query.date_from:
            year_from = query.date_from[:4]
            year_to = query.date_to[:4] if query.date_to else "2030"
            params["year"] = f"{year_from}-{year_to}"
        if query.categories:
            params["fieldsOfStudy"] = ",".join(query.categories)

        headers = {"x-api-key": self._api_key} if self._api_key else {}
        try:
            resp = await self._get("/paper/search", params=params, headers=headers)
            data = resp.json()
            return [p for p in (self._parse(i) for i in data.get("data", [])) if p]
        except Exception as e:
            logger.error(f"Semantic Scholar search failed: {e}")
            return []

    async def get_paper(self, paper_id: str) -> Paper | None:
        clean_id = paper_id.replace("s2:", "").replace("S2:", "")
        headers = {"x-api-key": self._api_key} if self._api_key else {}
        try:
            resp = await self._get(f"/paper/{clean_id}", params={"fields": _FIELDS}, headers=headers)
            return self._parse(resp.json())
        except Exception as e:
            logger.error(f"Semantic Scholar get_paper failed for {paper_id}: {e}")
            return None

    async def get_recent(self, categories: list[str] | None = None, days: int = 1) -> list[Paper]:
        query_str = "machine learning OR artificial intelligence OR multi-agent systems"
        params: dict = {"query": query_str, "limit": 50, "fields": _FIELDS}
        if categories:
            params["fieldsOfStudy"] = ",".join(categories)
        headers = {"x-api-key": self._api_key} if self._api_key else {}
        try:
            resp = await self._get("/paper/search", params=params, headers=headers)
            return [p for p in (self._parse(i) for i in resp.json().get("data", [])) if p]
        except Exception as e:
            logger.error(f"Semantic Scholar get_recent failed: {e}")
            return []

    def _parse(self, item: dict) -> Paper | None:
        if not isinstance(item, dict):
            return None
        title = (item.get("title") or "").strip()
        if not title:
            return None
        paper_id = item.get("paperId", "")
        ext_ids = item.get("externalIds", {}) or {}
        authors = [a.get("name", "") for a in (item.get("authors") or []) if a.get("name")]
        fields = item.get("fieldsOfStudy") or []
        oap = item.get("openAccessPdf") or {}
        pub_date = item.get("publicationDate")
        return Paper(
            id=f"s2:{paper_id}",
            source=PaperSource.SEMANTIC_SCHOLAR,
            title=title,
            authors=authors,
            abstract=item.get("abstract") or "",
            categories=fields,
            published_date=pub_date,
            doi=ext_ids.get("DOI"),
            url=item.get("url") or f"https://www.semanticscholar.org/paper/{paper_id}",
            pdf_url=oap.get("url"),
            citation_count=item.get("citationCount"),
            reference_count=item.get("referenceCount"),
            metadata={"s2_id": paper_id, "arxiv_id": ext_ids.get("ArXiv"), "pmid": ext_ids.get("PubMed")},
        )
