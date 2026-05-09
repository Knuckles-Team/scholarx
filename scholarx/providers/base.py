#!/usr/bin/python
"""Abstract base class for paper providers with per-source rate limiting.

Each provider implements source-specific API logic but exposes a uniform
interface. The base class handles rate limiting via an async semaphore
and token bucket approach.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from abc import ABC, abstractmethod

import httpx

from ..models import Paper, PaperSource, SearchQuery, SourceConfig

logger = logging.getLogger(__name__)


class PaperProvider(ABC):
    """Abstract base for a single paper source.

    Subclasses must implement ``search``, ``get_paper``, and ``get_recent``.
    The base class provides:
    - Per-source rate limiting via token bucket
    - Shared httpx.AsyncClient with configurable timeouts
    - API key resolution from environment variables
    """

    source: PaperSource
    config: SourceConfig

    def __init__(self, config: SourceConfig | None = None):
        from ..models import DEFAULT_SOURCE_CONFIGS

        self.config = config or DEFAULT_SOURCE_CONFIGS[self.source]
        self._api_key: str | None = None
        if self.config.api_key_env:
            self._api_key = os.environ.get(self.config.api_key_env)

        # Token bucket rate limiter
        self._rate_limit = asyncio.Semaphore(1)
        self._last_request_time: float = 0.0
        self._min_interval: float = (
            1.0 / self.config.requests_per_second if self.config.requests_per_second > 0 else 0.0
        )

    async def _wait_for_rate_limit(self) -> None:
        """Enforce per-source rate limiting."""
        async with self._rate_limit:
            now = time.monotonic()
            elapsed = now - self._last_request_time
            if elapsed < self._min_interval:
                await asyncio.sleep(self._min_interval - elapsed)
            self._last_request_time = time.monotonic()

    async def _get_client(self) -> httpx.AsyncClient:
        """Create a configured httpx.AsyncClient."""
        headers: dict[str, str] = {"User-Agent": "ScholarX/0.1.0 (mailto:research@example.com)"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return httpx.AsyncClient(
            base_url=self.config.base_url,
            headers=headers,
            timeout=httpx.Timeout(30.0, connect=10.0),
            follow_redirects=True,
        )

    async def _request(
        self,
        method: str,
        url: str,
        *,
        params: dict | None = None,
        json_data: dict | None = None,
        headers: dict | None = None,
    ) -> httpx.Response:
        """Make a rate-limited HTTP request with retries for 429s."""
        max_retries = 3
        for attempt in range(max_retries):
            await self._wait_for_rate_limit()
            async with await self._get_client() as client:
                response = await client.request(
                    method,
                    url,
                    params=params,
                    json=json_data,
                    headers=headers,
                )
                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", 5 * (attempt + 1)))
                    logger.warning(f"Rate limited (429). Retrying after {retry_after}s...")
                    await asyncio.sleep(retry_after)
                    continue
                response.raise_for_status()
                return response
        # Fallback if we exhaust retries and it's still 429, it will raise or return
        response.raise_for_status()
        return response

    async def _get(self, url: str, params: dict | None = None, **kwargs) -> httpx.Response:
        """Convenience GET wrapper."""
        return await self._request("GET", url, params=params, **kwargs)

    @abstractmethod
    async def search(self, query: SearchQuery) -> list[Paper]:
        """Search for papers matching the query.

        Args:
            query: Unified search query with filters.

        Returns:
            List of Paper objects from this source.
        """

    @abstractmethod
    async def get_paper(self, paper_id: str) -> Paper | None:
        """Retrieve a single paper by its source-specific ID.

        Args:
            paper_id: Source-specific identifier.

        Returns:
            Paper or None if not found.
        """

    @abstractmethod
    async def get_recent(self, categories: list[str] | None = None, days: int = 1) -> list[Paper]:
        """Retrieve recently published papers.

        Args:
            categories: Optional category filters.
            days: Number of days to look back.

        Returns:
            List of recent papers.
        """

    async def get_categories(self) -> list[dict[str, str]]:
        """Return available categories for this source.

        Override in subclasses with source-specific category lists.
        """
        return []
