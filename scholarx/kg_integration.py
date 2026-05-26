#!/usr/bin/python
"""ScholarX Knowledge Graph Integration.

Bridges ScholarX papers into the existing KG infrastructure via
KBIngestionEngine. Uses existing node types (ArticleNode, SourceNode,
PersonNode) rather than introducing new types. Large papers auto-route
through RLM (CONCEPT:AU-007) via the KBExtractor pipeline.
"""

from __future__ import annotations

import logging
from pathlib import Path

from .models import Paper
from .paper_storage import PaperStorage

logger = logging.getLogger(__name__)


class ScholarXKGBridge:
    """Bridges ScholarX papers into the Knowledge Graph. (CONCEPT:AU-007)

    Uses the existing KBIngestionEngine pipeline:
    1. Download PDF → store locally
    2. Feed to KBDocumentParser → chunk
    3. KBExtractor → Pydantic AI structured extraction
    4. RLM auto-triggers for papers > 50K chars
    5. Write ArticleNode + KBConceptNode + KBFactNode to graph
    6. Create PersonNode for authors, SourceNode for citations
    """

    def __init__(self, knowledge_engine=None, storage: PaperStorage | None = None):
        """Initialize the KG bridge.

        Args:
            knowledge_engine: IntelligenceGraphEngine instance (from agent-utilities).
            storage: PaperStorage instance for PDF downloads.
        """
        self.engine = knowledge_engine
        self.storage = storage or PaperStorage()
        self._kb_engine = None

    def _get_kb_engine(self):
        """Lazily initialize the KBIngestionEngine."""
        if self._kb_engine is None and self.engine is not None:
            try:
                from agent_utilities.knowledge_graph.kb.ingestion import KBIngestionEngine

                self._kb_engine = KBIngestionEngine(
                    graph=self.engine.graph,
                    backend=getattr(self.engine, "backend", None),
                )
            except ImportError:
                logger.warning("agent_utilities KB ingestion not available")
        return self._kb_engine

    async def ingest_paper(self, paper: Paper, kb_name: str = "scholarx-research") -> dict:
        """Download and ingest a paper into the Knowledge Graph.

        Args:
            paper: Paper to ingest.
            kb_name: Knowledge Base name for grouping.

        Returns:
            Dict with ingestion status and node IDs.
        """
        result = {"paper_id": paper.id, "status": "pending", "nodes_created": []}

        # 1. Download PDF
        local_path = await self.storage.download_paper(paper)
        if not local_path:
            # Fallback: ingest from abstract only
            logger.warning(f"No PDF for {paper.id}, ingesting abstract only")
            return await self._ingest_abstract_only(paper, kb_name)

        # 2. Ingest via KBIngestionEngine (handles PDF parsing, chunking, RLM)
        kb_engine = self._get_kb_engine()
        if kb_engine:
            try:
                pdf_dir = Path(local_path).parent
                meta = await kb_engine.ingest_directory(pdf_dir, kb_name=kb_name, topic=paper.title)
                result["status"] = "ingested"
                result["kb_id"] = meta.id
                result["article_count"] = meta.article_count
            except Exception as e:
                logger.error(f"KG ingestion failed for {paper.id}: {e}")
                result["status"] = "error"
                result["error"] = str(e)
        else:
            result["status"] = "skipped"
            result["reason"] = "KBIngestionEngine not available"

        # 3. Create author PersonNodes and SourceNode
        await self._create_auxiliary_nodes(paper)

        return result

    async def ingest_batch(self, papers: list[Paper], kb_name: str = "scholarx-research") -> dict:
        """Batch ingest papers with dedup against existing KG nodes.

        Args:
            papers: List of papers to ingest.
            kb_name: Knowledge Base name.

        Returns:
            Summary dict with counts.
        """
        ingested = 0
        skipped = 0
        errors = 0

        for paper in papers:
            # Check if already in KG
            if self._paper_exists_in_kg(paper):
                skipped += 1
                continue

            result = await self.ingest_paper(paper, kb_name)
            if result["status"] == "ingested":
                ingested += 1
            elif result["status"] == "error":
                errors += 1
            else:
                skipped += 1

        return {
            "total": len(papers),
            "ingested": ingested,
            "skipped": skipped,
            "errors": errors,
            "kb_name": kb_name,
        }

    def _paper_exists_in_kg(self, paper: Paper) -> bool:
        """Check if a paper already exists in the KG."""
        if not self.engine:
            return False

        graph = self.engine.graph
        # Check by DOI in SourceNode
        if paper.doi:
            for _, data in graph.nodes(data=True):
                if data.get("type") == "source" and data.get("doi") == paper.doi:
                    return True

        # Check by normalized title in ArticleNode
        if paper.normalized_title:
            from .models import normalize_title

            for _, data in graph.nodes(data=True):
                if data.get("type") == "article":
                    existing_title = normalize_title(data.get("name", ""))
                    if existing_title == paper.normalized_title:
                        return True

        return False

    async def _ingest_abstract_only(self, paper: Paper, kb_name: str) -> dict:
        """Fallback: ingest paper using only its abstract."""
        if not self.engine:
            return {"paper_id": paper.id, "status": "skipped", "reason": "No engine"}

        try:
            import time

            from agent_utilities.models.knowledge_graph import (
                ArticleNode,
                RegistryEdgeType,
                SourceNode,
            )

            timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

            # Create ArticleNode from abstract
            article_id = f"article:scholarx:{paper.id.replace(':', '-')}"
            article_node = ArticleNode(
                id=article_id,
                name=paper.title,
                description=paper.abstract[:300],
                summary=paper.abstract[:300],
                content=paper.abstract,
                word_count=len(paper.abstract.split()),
                tags=paper.categories,
                importance_score=0.6,
                timestamp=timestamp,
            )
            self.engine.graph.add_node(article_id, **article_node.model_dump())

            # Create SourceNode for citation info
            source_id = f"source:scholarx:{paper.id.replace(':', '-')}"
            source_node = SourceNode(
                id=source_id,
                source_id=paper.id,
                name=f"Source: {paper.title[:60]}",
                description=f"Research paper from {paper.source.value}",
                doi=paper.doi,
                url=paper.url,
                publication_date=paper.published_date,
                authors=paper.authors,
                importance_score=0.5,
                timestamp=timestamp,
            )
            self.engine.graph.add_node(source_id, **source_node.model_dump())
            self.engine.graph.add_edge(article_id, source_id, type=RegistryEdgeType.CITES)

            await self._create_auxiliary_nodes(paper)

            return {
                "paper_id": paper.id,
                "status": "ingested",
                "article_id": article_id,
                "nodes_created": [article_id, source_id],
            }
        except Exception as e:
            logger.error(f"Abstract-only ingestion failed for {paper.id}: {e}")
            return {"paper_id": paper.id, "status": "error", "error": str(e)}

    async def _create_auxiliary_nodes(self, paper: Paper) -> None:
        """Create PersonNode for authors and link to ArticleNode."""
        if not self.engine:
            return

        try:
            import time

            from agent_utilities.models.knowledge_graph import (
                PersonNode,
                RegistryEdgeType,
            )

            timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            article_id = f"article:scholarx:{paper.id.replace(':', '-')}"

            for author in paper.authors[:10]:  # Cap at 10 authors
                author_id = f"person:{author.lower().replace(' ', '-').replace('.', '')[:40]}"
                if author_id not in self.engine.graph.nodes:
                    person_node = PersonNode(
                        id=author_id,
                        person_id=author_id,
                        name=author,
                        description=f"Author of: {paper.title[:60]}",
                        importance_score=0.4,
                        timestamp=timestamp,
                    )
                    self.engine.graph.add_node(author_id, **person_node.model_dump())

                if not self.engine.graph.has_edge(article_id, author_id):
                    self.engine.graph.add_edge(article_id, author_id, type=RegistryEdgeType.AUTHORED)
        except Exception as e:
            logger.debug(f"Failed to create author nodes for {paper.id}: {e}")
