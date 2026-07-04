"""Tests for ScholarX models and deduplication.

Covers:
- CONCEPT:SX-OS.config.sx-3 3-Tier Deduplication — DOI, cross-ID, and fuzzy title+author matching
- CONCEPT:SX-OS.config.sx-4 Storage Dedup — Paper model normalization for dedup support
"""

from scholarx.deduplication import deduplicate_papers
from scholarx.models import Paper, PaperSource, SearchQuery, normalize_author, normalize_title


class TestNormalization:
    def test_normalize_title_basic(self):
        assert normalize_title("  Hello, World!  ") == "hello world"

    def test_normalize_title_diacritics(self):
        assert normalize_title("Über Naïve Résumé") == "uber naive resume"

    def test_normalize_title_punctuation(self):
        assert normalize_title("Multi-Agent Systems: A Survey") == "multiagent systems a survey"

    def test_normalize_author(self):
        assert normalize_author("José García-López") == "jose garcialopez"


class TestPaperModel:
    def test_auto_normalization(self):
        p = Paper(
            id="test:1",
            source=PaperSource.ARXIV,
            title="Attention Is All You Need",
            authors=["Ashish Vaswani", "Noam Shazeer"],
        )
        assert p.normalized_title == "attention is all you need"
        assert len(p.normalized_authors) == 2

    def test_search_query_defaults(self):
        q = SearchQuery(query="test")
        assert len(q.sources) == len(PaperSource)
        assert q.max_results == 20


class TestDeduplication:
    def _make_paper(
        self, id_: str, source: PaperSource, title: str, doi: str | None = None, authors: list[str] | None = None
    ):
        return Paper(
            id=id_,
            source=source,
            title=title,
            authors=authors or ["Author One"],
            doi=doi,
        )

    def test_doi_dedup(self):
        p1 = self._make_paper("arxiv:1", PaperSource.ARXIV, "Paper A", doi="10.1234/test")
        p2 = self._make_paper("s2:2", PaperSource.SEMANTIC_SCHOLAR, "Paper A", doi="10.1234/test")
        result, removed = deduplicate_papers([p1, p2])
        assert len(result) == 1
        assert removed == 1

    def test_title_dedup(self):
        p1 = self._make_paper("arxiv:1", PaperSource.ARXIV, "Attention Is All You Need", authors=["Vaswani"])
        p2 = self._make_paper("s2:2", PaperSource.SEMANTIC_SCHOLAR, "Attention is All You Need", authors=["Vaswani"])
        result, removed = deduplicate_papers([p1, p2])
        assert len(result) == 1
        assert removed == 1

    def test_no_false_positives(self):
        p1 = self._make_paper("arxiv:1", PaperSource.ARXIV, "Paper About Cats", authors=["Smith"])
        p2 = self._make_paper("arxiv:2", PaperSource.ARXIV, "Paper About Dogs", authors=["Jones"])
        result, removed = deduplicate_papers([p1, p2])
        assert len(result) == 2
        assert removed == 0

    def test_empty_list(self):
        result, removed = deduplicate_papers([])
        assert len(result) == 0
        assert removed == 0

    def test_merge_metadata(self):
        p1 = self._make_paper("arxiv:1", PaperSource.ARXIV, "Paper A", doi="10.1234/test")
        p2 = self._make_paper("s2:2", PaperSource.SEMANTIC_SCHOLAR, "Paper A", doi="10.1234/test")
        p2.abstract = "This is the abstract"
        p2.citation_count = 42
        result, _ = deduplicate_papers([p1, p2])
        assert result[0].abstract == "This is the abstract"
        assert result[0].citation_count == 42
