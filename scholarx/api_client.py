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
from .paper_storage import PaperStorage, normalize_arxiv_id
from .providers.base import PaperProvider

logger = logging.getLogger(__name__)

# Default bounded concurrency for parallel arXiv PDF downloads. Sized to
# overlap I/O without overwhelming the arXiv mirrors; politeness for the
# background queue is enforced separately in queue.py.
ARXIV_DOWNLOAD_CONCURRENCY = 5
_MAX_DOWNLOAD_CONCURRENCY = 16
_MAX_PAPER_DOWNLOAD_BATCH = 100
_MAX_DIRECT_DOWNLOAD_BATCH = 20
_MAX_DOWNLOAD_BATCH_SECONDS = 300.0

def _download_concurrency(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("Download concurrency must be an integer")
    if value < 0 or value > _MAX_DOWNLOAD_CONCURRENCY:
        raise ValueError("Download concurrency exceeds its limit")
    return value or ARXIV_DOWNLOAD_CONCURRENCY


async def _wait_for_download_tasks(tasks: list[asyncio.Task]) -> None:
    """Apply one wall budget and never orphan work when the caller is cancelled."""
    try:
        _, pending = await asyncio.wait(
            tasks, timeout=_MAX_DOWNLOAD_BATCH_SECONDS
        )
    except BaseException:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise
    for task in pending:
        task.cancel()
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)


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
                    logger.warning("Operation failed: error_type=%s", type(e).__name__)

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
                logger.error(
                    "Provider search failed: error_type=%s", type(e).__name__
                )
                sources_failed.append(f"{source.value}: {type(e).__name__}")
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
                logger.error("Operation failed: error_type=%s", type(e).__name__)
                sources_failed.append(f"{source.value}: {type(e).__name__}")
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
        if path:
            # Best-effort native blob ingestion: store the raw PDF as a :AssetOccurrence in
            # the knowledge graph. No-ops instantly when no engine is reachable.
            try:
                from .kg_media import ingest_pdf

                ingest_pdf(str(path), paper=paper)
            except Exception as e:  # noqa: BLE001 — KG ingestion is never fatal to a download
                logger.debug("Operation failed: error_type=%s", type(e).__name__)
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
        if len(papers) > _MAX_PAPER_DOWNLOAD_BATCH:
            raise ValueError("Paper download batch exceeds its limit")
        if not papers:
            return []
        limit = _download_concurrency(concurrency)
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

        tasks = [asyncio.create_task(_one(p)) for p in papers]
        await _wait_for_download_tasks(tasks)

        results: list[dict] = []
        for paper, task in zip(papers, tasks, strict=True):
            if task.cancelled():
                results.append(
                    {
                        "paper_id": paper.id,
                        "status": "failed",
                        "error": "Download batch time limit exceeded",
                    }
                )
                continue
            try:
                results.append(task.result())
            except Exception:
                results.append(
                    {
                        "paper_id": paper.id,
                        "status": "failed",
                        "error": "Download failed",
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

        Bypasses the arXiv metadata API while retaining the same validated,
        streamed, atomic storage path as metadata-backed paper downloads.

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
        ids = [r.strip() for r in raw_ids if r and r.strip()]
        if len(ids) > _MAX_DIRECT_DOWNLOAD_BATCH:
            raise ValueError("Direct download batch exceeds its limit")
        if not ids:
            return []
        limit = _download_concurrency(concurrency)
        semaphore = asyncio.Semaphore(limit)

        normalized: list[str | None] = []
        for raw_id in ids:
            try:
                normalized.append(normalize_arxiv_id(raw_id))
            except ValueError:
                normalized.append(None)

        async def _one(pid: str) -> dict:
            async with semaphore:
                path, size_bytes, created = await self.storage.download_arxiv_id(pid)
            return {
                "paper_id": pid,
                "status": "downloaded" if created else "cached",
                "local_path": str(path),
                "size_bytes": size_bytes,
            }

        tasks = [
            asyncio.create_task(_one(pid)) if pid is not None else None
            for pid in normalized
        ]
        valid_tasks = [task for task in tasks if task is not None]
        if valid_tasks:
            await _wait_for_download_tasks(valid_tasks)

        results: list[dict] = []
        for pid, task in zip(normalized, tasks, strict=True):
            if pid is None or task is None:
                results.append(
                    {
                        "paper_id": "invalid",
                        "status": "rejected",
                        "error": "Invalid arXiv identifier",
                    }
                )
            elif task.cancelled():
                results.append(
                    {
                        "paper_id": pid,
                        "status": "failed",
                        "error": "Download batch time limit exceeded",
                    }
                )
            else:
                try:
                    results.append(task.result())
                except Exception:
                    results.append(
                        {
                            "paper_id": pid,
                            "status": "failed",
                            "error": "Download failed",
                        }
                    )
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
                logger.warning(
                    "Failed to get provider categories: error_type=%s",
                    type(e).__name__,
                )
                result[s.value] = []
        return result
