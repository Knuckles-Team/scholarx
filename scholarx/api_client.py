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

# Default bounded concurrency for parallel arXiv PDF downloads. Sized to
# overlap I/O without overwhelming the arXiv mirrors; politeness for the
# background queue is enforced separately in queue.py.
ARXIV_DOWNLOAD_CONCURRENCY = 5

_ARXIV_URL_PREFIXES = (
    "https://arxiv.org/abs/",
    "https://arxiv.org/pdf/",
    "http://arxiv.org/abs/",
    "http://arxiv.org/pdf/",
)


def _normalize_arxiv_id(raw_id: str) -> tuple[str, str, str]:
    """Normalize an arXiv id or URL into (pid, base_id, pdf_url).

    Args:
        raw_id: An arXiv id (``2603.09022``), a versioned id
            (``2603.09022v2``) or a full abs/pdf URL.

    Returns:
        Tuple of (pid with any version suffix, base_id without version
        suffix for the filename, the canonical pdf URL).
    """
    pid = raw_id.strip()
    for prefix in _ARXIV_URL_PREFIXES:
        if pid.startswith(prefix):
            pid = pid.split(prefix)[-1].rstrip("/")
            break
    if pid.endswith(".pdf"):
        pid = pid[: -len(".pdf")]
    # Strip version suffix for filename, keep it for the URL.
    base_id = pid.split("v")[0] if "v" in pid and pid[-1].isdigit() else pid
    pdf_url = f"https://arxiv.org/pdf/{pid}"
    return pid, base_id, pdf_url


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
        """Download a paper's full PDF synchronously.

        Args:
            paper: Paper to download.

        Returns:
            Local file path string, or None on failure.
        """
        path = await self.storage.download_paper(paper)
        return str(path) if path else None

    async def download_papers(
        self,
        papers: list[Paper],
        *,
        concurrency: int = 0,
    ) -> list[dict]:
        """Download many papers in parallel with bounded concurrency.

        Mirrors the ``asyncio.gather`` fan-out used by ``search``/``get_recent``.
        Each ``PaperStorage.download_paper`` call opens its own httpx client and
        writes to a distinct destination path, so concurrent calls are safe.

        Args:
            papers: Papers to download.
            concurrency: Max simultaneous downloads. ``0`` auto-sizes to
                :data:`ARXIV_DOWNLOAD_CONCURRENCY`.

        Returns:
            One result dict per paper, preserving input order, with keys
            ``paper_id``, ``status`` ('downloaded' | 'cached' | 'failed') and
            either ``local_path`` or ``error``.
        """
        limit = concurrency if concurrency > 0 else ARXIV_DOWNLOAD_CONCURRENCY
        semaphore = asyncio.Semaphore(limit)

        async def _one(paper: Paper) -> dict:
            async with semaphore:
                # Detect a pre-existing local copy so we can report 'cached'
                # rather than 'downloaded' without re-fetching.
                cached = self.storage.get_local_path(paper.id)
                if cached and cached.exists():
                    return {
                        "paper_id": paper.id,
                        "status": "cached",
                        "local_path": str(cached),
                    }
                path = await self.storage.download_paper(paper)
                if path:
                    return {
                        "paper_id": paper.id,
                        "status": "downloaded",
                        "local_path": str(path),
                    }
                return {
                    "paper_id": paper.id,
                    "status": "failed",
                    "error": "Download failed or returned None",
                }

        raw = await asyncio.gather(
            *[_one(p) for p in papers],
            return_exceptions=True,
        )

        results: list[dict] = []
        for paper, item in zip(papers, raw, strict=True):
            if isinstance(item, dict):
                results.append(item)
            else:
                results.append(
                    {
                        "paper_id": paper.id,
                        "status": "failed",
                        "error": str(item),
                    }
                )
        return results

    async def download_urls(
        self,
        raw_ids: list[str],
        *,
        concurrency: int = 0,
    ) -> list[dict]:
        """Download arXiv PDFs directly by id/URL with bounded concurrency.

        Bypasses the arXiv metadata API entirely. A single shared
        ``httpx.AsyncClient`` is used across the whole batch. Already-stored
        PDFs are skipped via ``dest.exists()``.

        Args:
            raw_ids: arXiv ids (``2603.09022``), versioned ids or full
                abs/pdf URLs.
            concurrency: Max simultaneous downloads. ``0`` auto-sizes to
                :data:`ARXIV_DOWNLOAD_CONCURRENCY`.

        Returns:
            One result dict per id, preserving input order, with keys
            ``paper_id``, ``status`` ('downloaded' | 'cached' | 'failed') and
            either ``local_path`` (+ ``size_bytes``) or ``error``.
        """
        import httpx

        ids = [r.strip() for r in raw_ids if r and r.strip()]
        limit = concurrency if concurrency > 0 else ARXIV_DOWNLOAD_CONCURRENCY
        semaphore = asyncio.Semaphore(limit)

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(120.0, connect=30.0),
            follow_redirects=True,
        ) as http:

            async def _one(raw_id: str) -> dict:
                pid, base_id, pdf_url = _normalize_arxiv_id(raw_id)
                dest = self.storage.storage_dir / f"{base_id}.pdf"
                if dest.exists():
                    return {"paper_id": pid, "status": "cached", "local_path": str(dest)}
                async with semaphore:
                    resp = await http.get(pdf_url)
                    resp.raise_for_status()
                    dest.write_bytes(resp.content)
                    return {
                        "paper_id": pid,
                        "status": "downloaded",
                        "local_path": str(dest),
                        "size_bytes": len(resp.content),
                    }

            raw = await asyncio.gather(
                *[_one(r) for r in ids],
                return_exceptions=True,
            )

        results: list[dict] = []
        for raw_id, item in zip(ids, raw, strict=True):
            if isinstance(item, dict):
                results.append(item)
            else:
                pid, _, _ = _normalize_arxiv_id(raw_id)
                results.append({"paper_id": pid, "status": "failed", "error": str(item)})
        return results

    def queue_download(self, paper: Paper) -> str:
        """Queue a paper for background downloading.

        Args:
            paper: Paper to download.

        Returns:
            job_id string.
        """
        import datetime
        import uuid

        from .queue import BACKGROUND_DOWNLOADS, JOB_QUEUE

        job_id = f"job-{uuid.uuid4().hex[:8]}"
        BACKGROUND_DOWNLOADS[job_id] = {
            "status": "pending",
            "paper_id": paper.id,
            "title": paper.title,
            "created_at": datetime.datetime.now(datetime.UTC).isoformat(),
        }

        JOB_QUEUE.put(
            {
                "job_id": job_id,
                "paper": paper,
                "client": self,
            }
        )

        return job_id

    def get_download_status(self, job_id: str) -> dict | None:
        """Get the status of a queued download job."""
        from .queue import BACKGROUND_DOWNLOADS

        return BACKGROUND_DOWNLOADS.get(job_id)

    def get_queue_status(self) -> dict:
        """Get the status of all queued downloads."""
        from .queue import BACKGROUND_DOWNLOADS

        return dict(BACKGROUND_DOWNLOADS)

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
