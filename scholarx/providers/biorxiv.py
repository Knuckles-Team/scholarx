#!/usr/bin/python
"""bioRxiv / medRxiv Paper Provider.

Uses the bioRxiv API (https://api.biorxiv.org) for searching preprints
from both bioRxiv and medRxiv. Free access, no authentication required.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from ..models import Paper, PaperSource, SearchQuery
from .base import PaperProvider

logger = logging.getLogger(__name__)


class BiorxivProvider(PaperProvider):
    """bioRxiv / medRxiv provider using the bioRxiv API."""

    source = PaperSource.BIORXIV

    def __init__(self, config=None, *, server: str = "biorxiv"):
        """Initialize provider.

        Args:
            config: Optional SourceConfig override.
            server: Either 'biorxiv' or 'medrxiv'.
        """
        super().__init__(config)
        self._server = server

    async def search(self, query: SearchQuery) -> list[Paper]:
        """Search bioRxiv/medRxiv for papers.

        The bioRxiv API doesn't support full-text search directly.
        We use the /details endpoint with date range and filter client-side.
        """
        date_from = query.date_from or (datetime.now(tz=UTC) - timedelta(days=30)).strftime("%Y-%m-%d")
        date_to = query.date_to or datetime.now(tz=UTC).strftime("%Y-%m-%d")

        try:
            response = await self._get(f"/details/{self._server}/{date_from}/{date_to}/0/50")
            data = response.json()
            collection = data.get("collection", [])

            parsed_papers = [self._parse_paper(item) for item in collection]
            valid_papers: list[Paper] = [p for p in parsed_papers if p is not None]

            # Client-side filtering by query terms
            if query.query:
                query_lower = query.query.lower()
                valid_papers = [
                    p for p in valid_papers if query_lower in p.title.lower() or query_lower in p.abstract.lower()
                ]

            return valid_papers[: query.max_results]
        except Exception as e:
            logger.error(f"bioRxiv search failed: {e}")
            return []

    async def get_paper(self, paper_id: str) -> Paper | None:
        """Retrieve a single paper by DOI."""
        clean_id = paper_id.replace("biorxiv:", "").replace("medrxiv:", "")

        try:
            response = await self._get(f"/details/{self._server}/{clean_id}")
            data = response.json()
            collection = data.get("collection", [])
            if collection:
                return self._parse_paper(collection[-1])  # Latest version
            return None
        except Exception as e:
            logger.error(f"bioRxiv get_paper failed for {paper_id}: {e}")
            return None

    async def get_recent(self, categories: list[str] | None = None, days: int = 1) -> list[Paper]:
        """Retrieve recently published preprints."""
        date_from = (datetime.now(tz=UTC) - timedelta(days=days)).strftime("%Y-%m-%d")
        date_to = datetime.now(tz=UTC).strftime("%Y-%m-%d")

        try:
            response = await self._get(f"/details/{self._server}/{date_from}/{date_to}/0/50")
            data = response.json()
            collection = data.get("collection", [])

            parsed_papers = [self._parse_paper(item) for item in collection]
            valid_papers: list[Paper] = [p for p in parsed_papers if p is not None]

            # Filter by category if specified
            if categories:
                cat_lower = [c.lower() for c in categories]
                valid_papers = [p for p in valid_papers if any(c.lower() in cat_lower for c in p.categories)]

            return valid_papers
        except Exception as e:
            logger.error(f"bioRxiv get_recent failed: {e}")
            return []

    # ── Private Helpers ──────────────────────────────────────────────────

    def _parse_paper(self, item: dict) -> Paper | None:
        """Parse a bioRxiv API response item into a Paper."""
        doi = item.get("doi", "")
        if not doi:
            return None

        title = item.get("title", "").strip()
        if not title:
            return None

        # Authors come as a semicolon-separated string
        authors_str = item.get("authors", "")
        authors = [a.strip() for a in authors_str.split(";") if a.strip()]

        category = item.get("category", "")
        pub_date = item.get("date", "")

        source = PaperSource.MEDRXIV if self._server == "medrxiv" else PaperSource.BIORXIV

        return Paper(
            id=f"{self._server}:{doi}",
            source=source,
            title=title,
            authors=authors,
            abstract=item.get("abstract", ""),
            categories=[category] if category else [],
            published_date=pub_date if pub_date else None,
            doi=f"10.1101/{doi}" if not doi.startswith("10.") else doi,
            url=f"https://www.{self._server}.org/content/{doi}",
            pdf_url=f"https://www.{self._server}.org/content/{doi}.full.pdf",
        )


class MedrxivProvider(BiorxivProvider):
    """medRxiv provider — same API as bioRxiv with server='medrxiv'."""

    source = PaperSource.MEDRXIV

    def __init__(self, config=None):
        from ..models import DEFAULT_SOURCE_CONFIGS

        super().__init__(
            config=config or DEFAULT_SOURCE_CONFIGS[PaperSource.MEDRXIV],
            server="medrxiv",
        )
