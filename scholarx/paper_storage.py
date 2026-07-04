#!/usr/bin/python
"""Paper Storage — Full PDF download and local file management.

Downloaded papers are stored locally and can be fed into the
KBIngestionEngine for Knowledge Graph ingestion. The KBDocumentParser
handles PDF text extraction, and RLM auto-triggers for large papers
(>50K chars) via RLMConfig.trigger_on_large_output.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

from agent_utilities.core import paths

from .models import Paper

_OLD_STORAGE_DIR = Path.home() / ".local" / "share" / "scholarx" / "papers"
DEFAULT_STORAGE_DIR = paths.research_dir() / "papers"

# Migrate old papers and metadata if they exist
if _OLD_STORAGE_DIR.exists() and _OLD_STORAGE_DIR != DEFAULT_STORAGE_DIR:
    try:
        DEFAULT_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        # Migrate all files recursively (including .metadata directory)
        for old_file in _OLD_STORAGE_DIR.rglob("*"):
            if old_file.is_file():
                rel_path = old_file.relative_to(_OLD_STORAGE_DIR)
                new_file = DEFAULT_STORAGE_DIR / rel_path
                new_file.parent.mkdir(parents=True, exist_ok=True)
                if not new_file.exists():
                    new_file.write_bytes(old_file.read_bytes())
    except Exception as e:
        logger.warning(f"Failed to migrate old scholarx papers: {e}")


class PaperStorage:
    """Manages local storage of downloaded research papers. (CONCEPT:SX-OS.config.sx-4)"""

    def __init__(self, storage_dir: str | Path | None = None):
        self.storage_dir = Path(storage_dir) if storage_dir else DEFAULT_STORAGE_DIR
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
            logger.warning(f"No PDF URL for paper: {paper.id}")
            return None

        # Check if already downloaded
        existing = self.get_local_path(paper.id)
        if existing and existing.exists():
            logger.debug(f"Paper already stored: {paper.id}")
            return existing

        # Sanitize filename
        safe_name = self._safe_filename(paper)
        pdf_path = self.storage_dir / f"{safe_name}.pdf"

        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(120.0, connect=30.0),
                follow_redirects=True,
            ) as client:
                response = await client.get(paper.pdf_url)
                response.raise_for_status()

                pdf_path.write_bytes(response.content)
                logger.info(f"Downloaded paper: {paper.id} → {pdf_path} ({len(response.content):,} bytes)")

                # Store metadata alongside PDF
                self._save_metadata(paper, pdf_path)
                return pdf_path

        except Exception as e:
            logger.error(f"Failed to download paper {paper.id}: {e}")
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
                pdf_path = Path(meta.get("local_path", ""))
                if pdf_path.exists():
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
                local_path = Path(meta.get("local_path", ""))
                meta["exists"] = local_path.exists()
                if local_path.exists():
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
        title_slug = paper.normalized_title[:60].replace(" ", "_").replace("/", "_")
        return f"{id_hash}_{title_slug}"

    def _id_hash(self, paper_id: str) -> str:
        """Generate a short hash from paper ID."""
        return hashlib.sha256(paper_id.encode()).hexdigest()[:12]

    def _save_metadata(self, paper: Paper, pdf_path: Path) -> None:
        """Save paper metadata alongside the PDF."""
        meta = {
            "id": paper.id,
            "source": paper.source.value,
            "title": paper.title,
            "authors": paper.authors,
            "doi": paper.doi,
            "url": paper.url,
            "pdf_url": paper.pdf_url,
            "published_date": paper.published_date,
            "local_path": str(pdf_path),
            "categories": paper.categories,
        }
        meta_file = self._metadata_dir / f"{self._id_hash(paper.id)}.json"
        meta_file.write_text(json.dumps(meta, indent=2))
