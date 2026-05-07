#!/usr/bin/python
"""arXiv Paper Provider.

Uses the arXiv API (https://export.arxiv.org/api) for searching and
retrieving papers. The API is free and requires no authentication.
Rate limit: 1 request per 3 seconds.
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET  # nosec B405
from datetime import UTC, datetime, timedelta

from ..models import Paper, PaperSource, SearchQuery
from .base import PaperProvider

logger = logging.getLogger(__name__)

# arXiv Atom namespace
_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
    "opensearch": "http://a9.com/-/spec/opensearch/1.1/",
}

# arXiv category taxonomy (major groups)
ARXIV_CATEGORIES = {
    "cs.AI": "Artificial Intelligence",
    "cs.MA": "Multi-Agent Systems",
    "cs.SE": "Software Engineering",
    "cs.LG": "Machine Learning",
    "cs.CL": "Computation and Language",
    "cs.CV": "Computer Vision",
    "cs.RO": "Robotics",
    "cs.DC": "Distributed Computing",
    "cs.CR": "Cryptography and Security",
    "cs.IR": "Information Retrieval",
    "q-bio.BM": "Biomolecules",
    "q-bio.NC": "Neurons and Cognition",
    "stat.ML": "Machine Learning (Statistics)",
    "math.OC": "Optimization and Control",
    "eess.SP": "Signal Processing",
}


class ArxivProvider(PaperProvider):
    """arXiv paper provider using the Atom/OpenSearch API."""

    source = PaperSource.ARXIV

    async def search(self, query: SearchQuery) -> list[Paper]:
        """Search arXiv for papers."""
        search_query = self._build_query(query)
        params = {
            "search_query": search_query,
            "start": 0,
            "max_results": min(query.max_results, self.config.max_results_per_query),
            "sortBy": "relevance" if query.sort_by == "relevance" else "submittedDate",
            "sortOrder": "descending",
        }

        try:
            response = await self._get("/query", params=params)
            return self._parse_atom_feed(response.text)
        except Exception as e:
            logger.error(f"arXiv search failed: {e}")
            return []

    async def get_paper(self, paper_id: str) -> Paper | None:
        """Retrieve a single paper by arXiv ID."""
        clean_id = paper_id.replace("arXiv:", "").replace("arxiv:", "")
        params = {"id_list": clean_id, "max_results": 1}

        try:
            response = await self._get("/query", params=params)
            papers = self._parse_atom_feed(response.text)
            return papers[0] if papers else None
        except Exception as e:
            logger.error(f"arXiv get_paper failed for {paper_id}: {e}")
            return None

    async def get_recent(self, categories: list[str] | None = None, days: int = 1) -> list[Paper]:
        """Retrieve recently submitted papers from arXiv."""
        if not categories:
            categories = ["cs.AI", "cs.MA", "cs.SE", "cs.LG"]

        cat_query = " OR ".join(f"cat:{cat}" for cat in categories)
        date_from = (datetime.now(tz=UTC) - timedelta(days=days)).strftime("%Y%m%d")
        date_to = datetime.now(tz=UTC).strftime("%Y%m%d")

        search_query = f"({cat_query}) AND submittedDate:[{date_from} TO {date_to}]"
        params = {
            "search_query": search_query,
            "start": 0,
            "max_results": 50,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }

        try:
            response = await self._get("/query", params=params)
            return self._parse_atom_feed(response.text)
        except Exception as e:
            logger.error(f"arXiv get_recent failed: {e}")
            return []

    async def get_categories(self) -> list[dict[str, str]]:
        """Return arXiv category taxonomy."""
        return [{"id": cat_id, "name": name} for cat_id, name in ARXIV_CATEGORIES.items()]

    # ── Private Helpers ──────────────────────────────────────────────────

    def _build_query(self, query: SearchQuery) -> str:
        """Build an arXiv API search query string.

        Categories are OR-joined (paper matches ANY category), then
        AND-joined with the main query and author filter.
        """
        parts = []

        # Main query across title, abstract, all fields
        if query.query:
            parts.append(f'all:"{query.query}"')

        # Category filter — OR-joined so a paper in ANY listed category matches
        cat_terms = [
            f"cat:{cat}" for cat in query.categories if cat.startswith("cs.") or cat.startswith("q-bio.") or "." in cat
        ]
        if cat_terms:
            parts.append(f"({' OR '.join(cat_terms)})")

        # Author filter
        if query.author:
            parts.append(f'au:"{query.author}"')

        return " AND ".join(parts) if parts else f"all:{query.query}"

    def _parse_atom_feed(self, xml_text: str) -> list[Paper]:
        """Parse arXiv Atom XML response into Paper objects."""
        papers = []
        try:
            root = ET.fromstring(xml_text)  # nosec B314
        except ET.ParseError as e:
            logger.error(f"Failed to parse arXiv XML: {e}")
            return []

        for entry in root.findall("atom:entry", _NS):
            try:
                paper = self._parse_entry(entry)
                if paper:
                    papers.append(paper)
            except Exception as e:
                logger.warning(f"Failed to parse arXiv entry: {e}")

        return papers

    def _parse_entry(self, entry: ET.Element) -> Paper | None:
        """Parse a single Atom entry into a Paper."""
        entry_id = entry.findtext("atom:id", "", _NS)
        if not entry_id:
            return None

        # Extract arXiv ID from URL
        arxiv_id = entry_id.rstrip("/").split("/")[-1]

        title = entry.findtext("atom:title", "", _NS).strip().replace("\n", " ")
        abstract = entry.findtext("atom:summary", "", _NS).strip().replace("\n", " ")

        # Authors
        authors = []
        for author_elem in entry.findall("atom:author", _NS):
            name = author_elem.findtext("atom:name", "", _NS)
            if name:
                authors.append(name.strip())

        # Categories
        categories = []
        for cat_elem in entry.findall("atom:category", _NS):
            term = cat_elem.get("term", "")
            if term:
                categories.append(term)

        # Dates
        published = entry.findtext("atom:published", "", _NS)
        updated = entry.findtext("atom:updated", "", _NS)

        # DOI
        doi = None
        doi_elem = entry.find("arxiv:doi", _NS)
        if doi_elem is not None and doi_elem.text:
            doi = doi_elem.text.strip()

        # PDF URL
        pdf_url = None
        for link in entry.findall("atom:link", _NS):
            if link.get("title") == "pdf":
                pdf_url = link.get("href")
                break

        return Paper(
            id=f"arxiv:{arxiv_id}",
            source=PaperSource.ARXIV,
            title=title,
            authors=authors,
            abstract=abstract,
            categories=categories,
            published_date=published[:10] if published else None,
            updated_date=updated[:10] if updated else None,
            doi=doi,
            url=f"https://arxiv.org/abs/{arxiv_id}",
            pdf_url=pdf_url or f"https://arxiv.org/pdf/{arxiv_id}",
        )
