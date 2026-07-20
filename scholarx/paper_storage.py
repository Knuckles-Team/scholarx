#!/usr/bin/python
"""Paper Storage — Full PDF download and local file management.

Downloaded papers are stored locally and can be fed into the
KBIngestionEngine for Knowledge Graph ingestion. The KBDocumentParser
handles PDF text extraction, and RLM auto-triggers for large papers
(>50K chars) via RLMConfig.trigger_on_large_output.
"""

from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import json
import logging
import re
import socket
import tempfile
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import httpx
from agent_utilities.core.http_client import create_async_http_client

logger = logging.getLogger(__name__)

from agent_utilities.core import paths

from .models import Paper

_OLD_STORAGE_DIR = Path.home() / ".local" / "share" / "scholarx" / "papers"
DEFAULT_STORAGE_DIR = paths.research_dir() / "papers"
_ARXIV_ID_RE = re.compile(
    r"(?:\d{4}\.\d{4,5}|[a-z-]+(?:\.[a-z]{2})?/\d{7})(?:v\d+)?",
    re.IGNORECASE,
)
_MAX_PDF_BYTES = 100 * 1024 * 1024
_MAX_REDIRECTS = 5
_PDF_HEADER_SCAN_BYTES = 1024
_MAX_DOWNLOAD_SECONDS = 180.0
_DNS_TIMEOUT_SECONDS = 10.0

# Migrate old papers and metadata if they exist
if _OLD_STORAGE_DIR.exists() and _OLD_STORAGE_DIR != DEFAULT_STORAGE_DIR:
    try:
        DEFAULT_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        # Migrate all files recursively (including .metadata directory)
        for old_file in _OLD_STORAGE_DIR.rglob("*"):
            if old_file.is_file() and not old_file.is_symlink():
                rel_path = old_file.relative_to(_OLD_STORAGE_DIR)
                new_file = DEFAULT_STORAGE_DIR / rel_path
                new_file.parent.mkdir(parents=True, exist_ok=True)
                if not new_file.exists():
                    new_file.write_bytes(old_file.read_bytes())
    except Exception as e:
        logger.warning(
            "Failed to migrate legacy paper storage: error_type=%s",
            type(e).__name__,
        )


class PaperStorage:
    """Manages local storage of downloaded research papers. (CONCEPT:SX-OS.config.sx-4)"""

    def __init__(self, storage_dir: str | Path | None = None):
        selected_dir = Path(storage_dir) if storage_dir else DEFAULT_STORAGE_DIR
        self.storage_dir = selected_dir.expanduser().resolve()
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._metadata_dir = self.storage_dir / ".metadata"
        self._metadata_dir.mkdir(exist_ok=True)

    async def download_paper(self, paper: Paper) -> Path | None:
        """Download the full PDF for a paper. (CONCEPT:SX-OS.config.sx-4)

        Args:
            paper: Paper with a pdf_url to download.

        Returns:
            Path to the downloaded PDF, or None if download failed.
        """
        if not paper.pdf_url:
            logger.warning("No PDF URL was available for a paper")
            return None

        # Check if already downloaded
        existing = self.get_local_path(paper.id)
        if existing and existing.exists():
            logger.debug("Paper is already stored")
            return existing

        # Sanitize filename
        safe_name = self._safe_filename(paper)
        pdf_path = self.storage_dir / f"{safe_name}.pdf"

        try:
            pdf_path, content_bytes = await self._download_pdf(
                paper.pdf_url, pdf_path
            )
            logger.info("Downloaded paper: content_bytes=%d", content_bytes)

            # Store metadata alongside PDF
            self._save_metadata(paper, pdf_path)
            return pdf_path

        except Exception as e:
            logger.error("Operation failed: error_type=%s", type(e).__name__)
            return None

    def get_local_path(self, paper_id: str) -> Path | None:
        """Check if a paper is already stored locally. (CONCEPT:SX-OS.config.sx-4)

        Args:
            paper_id: Source-specific paper ID.

        Returns:
            Path to the local PDF, or None if not stored.
        """
        meta_file = self._metadata_dir / f"{self._id_hash(paper_id)}.json"
        if meta_file.exists():
            try:
                meta = json.loads(meta_file.read_text())
                pdf_path = self._resolve_stored_path(meta.get("local_path"))
                if pdf_path is not None and pdf_path.exists():
                    return pdf_path
            except Exception:  # nosec B110 B112
                pass
        return None

    def list_stored_papers(self) -> list[dict]:
        """List all locally stored papers with their metadata. (CONCEPT:SX-OS.config.sx-4)

        Returns:
            List of dicts with paper metadata and local paths.
        """
        results = []
        for meta_file in self._metadata_dir.glob("*.json"):
            try:
                meta = json.loads(meta_file.read_text())
                local_path = self._resolve_stored_path(meta.get("local_path"))
                meta["local_path"] = str(local_path) if local_path else None
                meta["exists"] = bool(local_path and local_path.exists())
                if local_path and local_path.exists():
                    meta["file_size"] = local_path.stat().st_size
                results.append(meta)
            except Exception:  # nosec B110 B112
                continue
        return sorted(results, key=lambda x: x.get("title", ""))

    def get_storage_stats(self) -> dict:
        """Get storage statistics. (CONCEPT:SX-OS.config.sx-4)"""
        pdfs = list(self.storage_dir.glob("*.pdf"))
        total_size = sum(f.stat().st_size for f in pdfs)
        return {
            "storage_dir": str(self.storage_dir),
            "paper_count": len(pdfs),
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
        }

    # ── Private Helpers ──────────────────────────────────────────────────

    def _safe_filename(self, paper: Paper) -> str:
        """Generate a safe filename from paper metadata."""
        # Use ID hash + truncated title
        id_hash = self._id_hash(paper.id)
        title_slug = re.sub(r"[^a-z0-9._-]+", "_", paper.normalized_title[:60])
        title_slug = title_slug.strip("._-") or "paper"
        return f"{id_hash}_{title_slug}"

    def _id_hash(self, paper_id: str) -> str:
        """Generate a short hash from paper ID."""
        return hashlib.sha256(paper_id.encode()).hexdigest()[:12]

    def _save_metadata(self, paper: Paper, pdf_path: Path) -> None:
        """Save paper metadata alongside the PDF."""
        resolved_pdf = self._resolve_stored_path(pdf_path)
        if resolved_pdf is None:
            raise ValueError("PDF path must remain inside the storage directory")
        meta = {
            "id": paper.id,
            "source": paper.source.value,
            "title": paper.title,
            "authors": paper.authors,
            "doi": paper.doi,
            "url": paper.url,
            "pdf_url": paper.pdf_url,
            "published_date": paper.published_date,
            "local_path": str(resolved_pdf),
            "categories": paper.categories,
        }
        meta_file = self._metadata_dir / f"{self._id_hash(paper.id)}.json"
        meta_file.write_text(json.dumps(meta, indent=2))

    def _resolve_stored_path(self, value: object) -> Path | None:
        """Resolve a metadata path only when it remains under ``storage_dir``."""
        if not isinstance(value, (str, Path)) or not str(value):
            return None
        candidate = Path(value).expanduser()
        if not candidate.is_absolute():
            candidate = self.storage_dir / candidate
        try:
            resolved = candidate.resolve()
            resolved.relative_to(self.storage_dir)
        except (OSError, ValueError):
            return None
        return resolved

    async def download_arxiv_id(self, value: str) -> tuple[Path, int, bool]:
        """Download one validated arXiv identifier into the storage root.

        Returns ``(path, size_bytes, created)``. Identifiers, including legacy
        category-prefixed IDs, are converted to a single safe filename component.
        """
        arxiv_id = normalize_arxiv_id(value)
        destination = self.storage_dir / f"{arxiv_id.replace('/', '_')}.pdf"
        if destination.is_symlink():
            raise ValueError("Download destination must not be a symbolic link")
        if destination.exists():
            return destination, destination.stat().st_size, False
        path, size = await self._download_pdf(
            f"https://arxiv.org/pdf/{arxiv_id}", destination
        )
        return path, size, True

    async def _download_pdf(self, url: str, destination: Path) -> tuple[Path, int]:
        """Stream a public HTTPS PDF to an atomic, size-bounded destination."""
        async with asyncio.timeout(_MAX_DOWNLOAD_SECONDS):
            return await self._download_pdf_bounded(url, destination)

    async def _download_pdf_bounded(
        self, url: str, destination: Path
    ) -> tuple[Path, int]:
        """Perform one download under the caller's absolute wall deadline."""
        if destination.is_symlink():
            raise ValueError("Download destination must not be a symbolic link")
        destination = destination.resolve()
        try:
            destination.relative_to(self.storage_dir)
        except ValueError as exc:
            raise ValueError("Download destination escapes the storage directory") from exc

        current_url = url
        async with create_async_http_client(
            timeout=httpx.Timeout(120.0, connect=30.0),
            follow_redirects=False,
            pin_egress=True,
            allow_loopback=False,
            trust_env=False,
        ) as client:
            for _ in range(_MAX_REDIRECTS + 1):
                await _validate_download_url(current_url)
                async with client.stream("GET", current_url) as response:
                    if response.status_code in {301, 302, 303, 307, 308}:
                        location = response.headers.get("location")
                        if not location:
                            raise ValueError("PDF redirect omitted its destination")
                        current_url = urljoin(current_url, location)
                        continue

                    response.raise_for_status()
                    declared = response.headers.get("content-length")
                    if declared:
                        try:
                            declared_size = int(declared)
                        except ValueError as exc:
                            raise ValueError("Invalid PDF content length") from exc
                        if declared_size < 0 or declared_size > _MAX_PDF_BYTES:
                            raise ValueError("PDF size limit exceeded")

                    part_path: Path | None = None
                    try:
                        total = 0
                        header = bytearray()
                        with tempfile.NamedTemporaryFile(
                            mode="wb",
                            dir=self.storage_dir,
                            prefix=".download-",
                            suffix=".part",
                            delete=False,
                        ) as output:
                            part_path = Path(output.name)
                            async for chunk in response.aiter_bytes():
                                if not chunk:
                                    continue
                                total += len(chunk)
                                if total > _MAX_PDF_BYTES:
                                    raise ValueError("PDF size limit exceeded")
                                if len(header) < _PDF_HEADER_SCAN_BYTES:
                                    remaining = _PDF_HEADER_SCAN_BYTES - len(header)
                                    header.extend(chunk[:remaining])
                                output.write(chunk)
                        if b"%PDF-" not in header:
                            raise ValueError("Downloaded content is not a PDF")
                        part_path.replace(destination)
                        return destination, total
                    finally:
                        if part_path is not None and part_path.exists():
                            part_path.unlink()

        raise ValueError("PDF redirect limit exceeded")


def normalize_arxiv_id(value: str) -> str:
    """Return a canonical arXiv ID or reject URL/path-shaped input."""
    raw = str(value or "").strip()
    if not raw or len(raw) > 128 or any(char in raw for char in "\x00\r\n"):
        raise ValueError("Invalid arXiv identifier")
    if raw.lower().startswith("arxiv:") and "://" not in raw:
        raw = raw[6:]

    parsed = urlsplit(raw)
    if parsed.scheme or parsed.netloc:
        if (
            parsed.scheme.lower() != "https"
            or (parsed.hostname or "").lower() not in {"arxiv.org", "www.arxiv.org"}
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("Only canonical HTTPS arXiv URLs are accepted")
        path = parsed.path.lstrip("/")
        prefix, separator, identifier = path.partition("/")
        if not separator or prefix.lower() not in {"abs", "pdf"}:
            raise ValueError("Invalid arXiv URL path")
        raw = identifier

    if raw.lower().endswith(".pdf"):
        raw = raw[:-4]
    if not _ARXIV_ID_RE.fullmatch(raw):
        raise ValueError("Invalid arXiv identifier")
    return raw


async def _validate_download_url(url: str) -> None:
    """Reject local/private destinations before each outbound PDF request."""
    try:
        parsed = urlsplit(url)
        port = parsed.port or 443
    except ValueError as exc:
        raise ValueError("Invalid PDF URL") from exc
    hostname = parsed.hostname
    if (
        parsed.scheme.lower() != "https"
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ValueError("PDF URL must be an unauthenticated HTTPS URL")
    lowered = hostname.rstrip(".").lower()
    if lowered == "localhost" or lowered.endswith((".localhost", ".local", ".internal")):
        raise ValueError("PDF URL resolves to a local address")

    try:
        addresses = await asyncio.wait_for(
            asyncio.to_thread(
                socket.getaddrinfo,
                hostname,
                port,
                type=socket.SOCK_STREAM,
            ),
            timeout=_DNS_TIMEOUT_SECONDS,
        )
    except (OSError, TimeoutError) as exc:
        raise ValueError("PDF URL host could not be resolved") from exc
    if not addresses:
        raise ValueError("PDF URL host could not be resolved")
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0].split("%", 1)[0])
        if not ip.is_global:
            raise ValueError("PDF URL resolves to a non-public address")
