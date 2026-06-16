#!/usr/bin/python
"""Generic RSS/Atom Feed Provider for academic paper sources.

Parses RSS and Atom feeds into Paper objects with announce_type metadata.
Designed as a reusable base for arXiv, bioRxiv, PubMed, and other feeds.

The arXiv RSS feed (https://rss.arxiv.org/rss/<category>) is the authoritative
source for "papers announced today" and is updated daily at midnight EST.
"""

from __future__ import annotations

import asyncio
import logging
import re
import xml.etree.ElementTree as ET  # nosec B405
from dataclasses import dataclass, field

import httpx

from ..models import Paper, PaperSource

logger = logging.getLogger(__name__)

# ── Feed Configuration ──────────────────────────────────────────────────────

ARXIV_RSS_BASE = "https://rss.arxiv.org/rss"

# arXiv RSS namespaces
_RSS_NS = {
    "arxiv": "http://arxiv.org/schemas/atom",
    "dc": "http://purl.org/dc/elements/1.1/",
    "atom": "http://www.w3.org/2005/Atom",
    "content": "http://purl.org/rss/1.0/modules/content/",
}

# Primary categories that are irrelevant to agentic AI research.
# Papers whose first <category> is one of these are pre-filtered.
IRRELEVANT_PRIMARY_CATEGORIES = frozenset(
    {
        "quant-ph",
        "physics.atm-clus",
        "physics.chem-ph",
        "physics.comp-ph",
        "physics.optics",
        "physics.bio-ph",
        "physics.flu-dyn",
        "math.CO",
        "math.NA",
        "math.PR",
        "math.ST",
        "stat.AP",
        "stat.CO",
        "stat.ME",
        "stat.TH",
        "q-bio.BM",
        "q-bio.CB",
        "q-bio.GN",
        "q-bio.MN",
        "q-bio.PE",
        "q-bio.SC",
        "q-bio.TO",
        "econ.EM",
        "econ.GN",
        "econ.TH",
        "astro-ph",
        "cond-mat",
        "gr-qc",
        "hep-ex",
        "hep-lat",
        "hep-ph",
        "hep-th",
        "nlin",
        "nucl-ex",
        "nucl-th",
    }
)


@dataclass
class RSSFeedResult:
    """Result of parsing an RSS feed."""

    papers: list[Paper] = field(default_factory=list)
    feed_title: str = ""
    feed_date: str = ""
    total_items: int = 0
    new_count: int = 0
    cross_count: int = 0
    replace_count: int = 0


class RSSFeedProvider:
    """Generic RSS/Atom feed parser for academic paper sources.

    Currently supports arXiv RSS format. Extensible for bioRxiv, PubMed, etc.

    Usage::

        provider = RSSFeedProvider()
        result = await provider.fetch_arxiv_daily(["cs.AI", "cs.MA"])
        for paper in result.papers:
            print(f"[{paper.announce_type}] {paper.title}")
    """

    def __init__(
        self,
        *,
        timeout: float = 30.0,
        include_announce_types: frozenset[str] | None = None,
        pre_filter_categories: bool = True,
    ):
        """Initialize the RSS feed provider.

        Args:
            timeout: HTTP request timeout in seconds.
            include_announce_types: Set of announce types to include.
                Defaults to {"new", "cross"} — excludes "replace" (updates).
            pre_filter_categories: If True, skip papers whose primary category
                is in IRRELEVANT_PRIMARY_CATEGORIES.
        """
        self._timeout = timeout
        self._include_types = include_announce_types or frozenset({"new", "cross"})
        self._pre_filter = pre_filter_categories

    async def fetch_arxiv_daily(
        self,
        categories: list[str] | None = None,
    ) -> RSSFeedResult:
        """Fetch today's papers from arXiv RSS feeds.

        Args:
            categories: arXiv categories to fetch (e.g., ["cs.AI", "cs.MA"]).
                Defaults to ["cs.AI"].

        Returns:
            RSSFeedResult with parsed papers and feed metadata.
        """
        if not categories:
            categories = ["cs.AI"]

        all_papers: dict[str, Paper] = {}  # keyed by arXiv ID for dedup
        result = RSSFeedResult()

        # Fetch every category feed concurrently over one shared client. Fetching
        # serially opened a new client per category and let a slow arXiv RSS host
        # stack into N x timeout — the cause of `recent` hanging. The connect
        # timeout mirrors providers/base.py.
        timeout = httpx.Timeout(self._timeout, connect=10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:

            async def _fetch(category: str) -> tuple[str, str | None]:
                feed_url = f"{ARXIV_RSS_BASE}/{category.lower()}"
                logger.info(f"Fetching RSS feed: {feed_url}")
                try:
                    response = await client.get(feed_url)
                    response.raise_for_status()
                    return category, response.text
                except Exception as e:
                    logger.error(f"Failed to fetch RSS feed {feed_url}: {e}")
                    return category, None

            responses = await asyncio.gather(*(_fetch(c) for c in categories))

        # Parse and aggregate sequentially so dedup ordering stays deterministic.
        for category, text in responses:
            if text is None:
                continue

            feed_result = self._parse_rss_feed(text, category)
            result.feed_title = feed_result.feed_title or result.feed_title
            result.feed_date = feed_result.feed_date or result.feed_date

            for paper in feed_result.papers:
                arxiv_id = paper.id.replace("arxiv:", "")
                if arxiv_id not in all_papers:
                    all_papers[arxiv_id] = paper

            result.total_items += feed_result.total_items
            result.new_count += feed_result.new_count
            result.cross_count += feed_result.cross_count
            result.replace_count += feed_result.replace_count

        result.papers = list(all_papers.values())
        return result

    def _parse_rss_feed(self, xml_text: str, category: str) -> RSSFeedResult:
        """Parse an arXiv RSS XML feed into Paper objects."""
        result = RSSFeedResult()

        try:
            root = ET.fromstring(xml_text)  # nosec B314
        except ET.ParseError as e:
            logger.error(f"Failed to parse RSS XML: {e}")
            return result

        channel = root.find("channel")
        if channel is None:
            logger.error("No <channel> element found in RSS feed")
            return result

        result.feed_title = channel.findtext("title", "")
        result.feed_date = channel.findtext("pubDate", "")

        for item in channel.findall("item"):
            result.total_items += 1
            paper = self._parse_rss_item(item)

            if paper is None:
                continue

            # Count by type
            if paper.announce_type == "new":
                result.new_count += 1
            elif paper.announce_type == "cross":
                result.cross_count += 1
            elif paper.announce_type == "replace":
                result.replace_count += 1

            # Filter by announce type
            if paper.announce_type and paper.announce_type not in self._include_types:
                continue

            # Pre-filter irrelevant primary categories
            if self._pre_filter and paper.categories:
                primary_cat = paper.categories[0]
                # Check if primary category (or its prefix) is irrelevant
                if primary_cat in IRRELEVANT_PRIMARY_CATEGORIES or any(
                    primary_cat.startswith(prefix) for prefix in ("astro-ph.", "cond-mat.", "hep-", "nucl-", "nlin.")
                ):
                    continue

            result.papers.append(paper)

        return result

    def _parse_rss_item(self, item: ET.Element) -> Paper | None:
        """Parse a single RSS <item> into a Paper object."""
        title = item.findtext("title", "").strip()
        link = item.findtext("link", "").strip()
        description = item.findtext("description", "").strip()
        pub_date = item.findtext("pubDate", "").strip()

        if not title or not link:
            return None

        # Extract arXiv ID from link
        arxiv_id = link.rstrip("/").split("/")[-1]

        # Extract announce_type from the arxiv namespace
        announce_type_elem = item.find("arxiv:announce_type", _RSS_NS)
        announce_type = (
            announce_type_elem.text.strip()
            if announce_type_elem is not None and announce_type_elem.text is not None
            else None
        )

        # Extract abstract from description (strip arXiv ID prefix)
        abstract = self._extract_abstract(description)

        # Extract categories
        categories = []
        for cat_elem in item.findall("category"):
            cat_text = cat_elem.text
            if cat_text:
                categories.append(cat_text.strip())

        # Extract authors from dc:creator
        creator_elem = item.find("dc:creator", _RSS_NS)
        authors = []
        if creator_elem is not None and creator_elem.text:
            # dc:creator contains comma-separated author names
            raw_authors = creator_elem.text
            # Split on comma, but be careful with names like "O'Brien, Jr."
            authors = [a.strip() for a in raw_authors.split(",") if a.strip()]
            # Re-join pairs that look like "Last, First" -> leave as individual names
            # arXiv RSS typically uses "First Last, First Last" format

        # Extract DOI if present
        doi_elem = item.find("arxiv:DOI", _RSS_NS)
        doi = doi_elem.text.strip() if doi_elem is not None and doi_elem.text else None

        return Paper(
            id=f"arxiv:{arxiv_id}",
            source=PaperSource.ARXIV,
            title=title,
            authors=authors,
            abstract=abstract,
            categories=categories,
            published_date=pub_date[:10] if pub_date else None,
            doi=doi,
            url=link,
            pdf_url=f"https://arxiv.org/pdf/{arxiv_id}",
            announce_type=announce_type,
        )

    @staticmethod
    def _extract_abstract(description: str) -> str:
        """Extract clean abstract text from RSS description field.

        arXiv RSS descriptions look like:
        'arXiv:2605.04050v1 Announce Type: new\\nAbstract: We introduce...'
        """
        # Remove the arXiv ID and announce type prefix
        abstract = re.sub(
            r"arXiv:\d+\.\d+v\d+\s+Announce Type:\s*\w+\s*",
            "",
            description,
        ).strip()

        # Remove "Abstract: " prefix if present
        if abstract.lower().startswith("abstract:"):
            abstract = abstract[9:].strip()

        # Clean up whitespace
        abstract = re.sub(r"\s+", " ", abstract)

        return abstract
