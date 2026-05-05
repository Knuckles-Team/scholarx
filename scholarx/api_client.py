#!/usr/bin/python
"""ScholarX Unified API Client.

The single entry point for all paper operations. Users interact with
ScholarXClient — never with providers directly. The client handles
fan-out to configured providers, cross-source deduplication, and
result aggregation.
"""

from __future__ import annotations

import asyncio
import logging

from .deduplication import deduplicate_papers
from .models import (
    DEFAULT_SOURCE_CONFIGS,
    Paper,
    PaperSource,
    SearchQuery,
    SearchResult,
    SourceConfig,
    SourceStatus,
)
from .paper_storage import PaperStorage
from .providers.base import PaperProvider

logger = logging.getLogger(__name__)


def _create_provider(source: PaperSource, config: SourceConfig) -> PaperProvider:
    """Factory to create a provider instance for a given source."""
    from .providers.arxiv import ArxivProvider
    from .providers.biorxiv import BiorxivProvider, MedrxivProvider
    from .providers.osf import OSFProvider, PsyarxivProvider
    from .providers.pmc import PMCProvider
    from .providers.semantic_scholar import SemanticScholarProvider

    _PROVIDER_MAP: dict[PaperSource, type[PaperProvider]] = {
        PaperSource.ARXIV: ArxivProvider,
        PaperSource.PMC: PMCProvider,
        PaperSource.BIORXIV: BiorxivProvider,
        PaperSource.MEDRXIV: MedrxivProvider,
        PaperSource.PSYARXIV: PsyarxivProvider,
        PaperSource.OSF: OSFProvider,
        PaperSource.SEMANTIC_SCHOLAR: SemanticScholarProvider,
    }

    provider_cls = _PROVIDER_MAP.get(source)
    if not provider_cls:
        raise ValueError(f"Unknown paper source: {source}")
    return provider_cls(config)


class ScholarXClient:
    """Universal research paper client.

    Fan-out queries to all configured sources, deduplicate results,
    and present a unified view. Users never need to know about
    individual provider implementations.

    Usage::

        client = ScholarXClient()
        result = await client.search(SearchQuery(query="multi-agent systems"))
        for paper in result.papers:
            print(f"{paper.title} ({paper.source})")
    """

    def __init__(
        self,
        sources: list[PaperSource] | None = None,
        configs: dict[PaperSource, SourceConfig] | None = None,
        storage_dir: str | None = None,
    ):
        """Initialize the client.

        Args:
            sources: List of sources to enable (default: all).
            configs: Optional per-source configuration overrides.
            storage_dir: Optional custom paper storage directory.
        """
        self._configs = configs or dict(DEFAULT_SOURCE_CONFIGS)
        enabled_sources = sources or list(PaperSource)

        self._providers: dict[PaperSource, PaperProvider] = {}
        for source in enabled_sources:
            config = self._configs.get(source, DEFAULT_SOURCE_CONFIGS.get(source))
            if config and config.enabled:
                try:
                    self._providers[source] = _create_provider(source, config)
                except Exception as e:
                    logger.warning(f"Failed to initialize provider {source}: {e}")

        self.storage = PaperStorage(storage_dir)
        logger.info(
            f"ScholarX initialized with {len(self._providers)} sources: {', '.join(s.value for s in self._providers)}"
        )

    @property
    def enabled_sources(self) -> list[PaperSource]:
        """List of currently enabled sources."""
        return list(self._providers.keys())

    async def search(self, query: SearchQuery) -> SearchResult:
        """Search across all configured sources with deduplication.

        Args:
            query: Unified search query.

        Returns:
            Aggregated, deduplicated SearchResult.
        """
        # Filter to requested sources
        target_sources = [s for s in query.sources if s in self._providers]
        if not target_sources:
            target_sources = list(self._providers.keys())

        # Fan out to all providers concurrently
        all_papers: list[Paper] = []
        sources_failed: list[str] = []

        async def _query_source(source: PaperSource) -> list[Paper]:
            try:
                return await self._providers[source].search(query)
            except Exception as e:
                logger.error(f"Search failed for {source.value}: {e}")
                sources_failed.append(f"{source.value}: {e}")
                return []

        results = await asyncio.gather(
            *[_query_source(s) for s in target_sources],
            return_exceptions=True,
        )

        for i, result in enumerate(results):
            if isinstance(result, list):
                all_papers.extend(result)
            elif isinstance(result, Exception):
                sources_failed.append(f"{target_sources[i].value}: {result}")

        # Deduplicate
        deduped, dup_count = deduplicate_papers(all_papers)

        # Sort
        if query.sort_by == "date":
            deduped.sort(key=lambda p: p.published_date or "", reverse=True)

        return SearchResult(
            papers=deduped[: query.max_results],
            total_count=len(deduped),
            sources_queried=[s for s in target_sources],
            sources_failed=sources_failed,
            deduplicated_count=dup_count,
            query=query.query,
        )

    async def get_paper(self, source: PaperSource, paper_id: str) -> Paper | None:
        """Retrieve a single paper from a specific source.

        Args:
            source: The paper source to query.
            paper_id: Source-specific paper identifier.

        Returns:
            Paper or None if not found.
        """
        provider = self._providers.get(source)
        if not provider:
            logger.error(f"Source not configured: {source}")
            return None
        return await provider.get_paper(paper_id)

    async def get_recent_papers(
        self,
        categories: list[str] | None = None,
        days: int = 1,
        sources: list[PaperSource] | None = None,
    ) -> SearchResult:
        """Retrieve recently published papers.

        Args:
            categories: Optional category filters.
            days: Number of days to look back.
            sources: Optional source filter (default: all).

        Returns:
            Aggregated, deduplicated SearchResult.
        """
        target_sources = [s for s in (sources or list(self._providers.keys())) if s in self._providers]

        all_papers: list[Paper] = []
        sources_failed: list[str] = []

        async def _fetch(source: PaperSource) -> list[Paper]:
            try:
                return await self._providers[source].get_recent(categories, days)
            except Exception as e:
                logger.error(f"get_recent failed for {source.value}: {e}")
                sources_failed.append(f"{source.value}: {e}")
                return []

        results = await asyncio.gather(
            *[_fetch(s) for s in target_sources],
            return_exceptions=True,
        )

        for i, result in enumerate(results):
            if isinstance(result, list):
                all_papers.extend(result)
            elif isinstance(result, Exception):
                sources_failed.append(f"{target_sources[i].value}: {result}")

        deduped, dup_count = deduplicate_papers(all_papers)
        deduped.sort(key=lambda p: p.published_date or "", reverse=True)

        return SearchResult(
            papers=deduped,
            total_count=len(deduped),
            sources_queried=target_sources,
            sources_failed=sources_failed,
            deduplicated_count=dup_count,
            query="recent papers",
        )

    async def download_paper(self, paper: Paper) -> str | None:
        """Download a paper's full PDF.

        Args:
            paper: Paper to download.

        Returns:
            Local file path string, or None on failure.
        """
        path = await self.storage.download_paper(paper)
        return str(path) if path else None

    async def get_source_status(self) -> list[SourceStatus]:
        """Get the status of all configured sources."""
        return [SourceStatus(source=source, available=True) for source in self._providers]

    async def list_categories(self, source: PaperSource | None = None) -> dict[str, list[dict]]:
        """List available categories for each source."""
        result: dict[str, list[dict]] = {}
        targets = [source] if source and source in self._providers else list(self._providers.keys())
        for s in targets:
            try:
                cats = await self._providers[s].get_categories()
                result[s.value] = cats
            except Exception as e:
                logger.warning(f"Failed to get categories for {s.value}: {e}")
                result[s.value] = []
        return result
