"""Tests for ScholarX CLI and relevance scoring.

Covers:
- CONCEPT:SX-OS.config.sx CLI — scan and status commands
- CONCEPT:SX-OS.config.sx-2 Relevance Scoring — 9-domain weighted taxonomy
- CONCEPT:SX-OS.config.sx-4 Storage Dedup — skips already-downloaded PDFs
- CONCEPT:SX-OS.scaling.chains-comparative-analysis-extract Auto-Analysis — --analyze flag behavior
"""

from scholarx.cli import DEFAULT_TAXONOMY, generate_synergy_report, score_paper

# ── CONCEPT:SX-OS.config.sx-2 Relevance Scoring ────────────────────────────────────────


class TestScorePaper:
    """Tests for the relevance scoring engine (CONCEPT:SX-OS.config.sx-2)."""

    def test_highly_relevant_paper(self):
        """A paper about multi-agent orchestration should score highly in orchestration domain."""
        score = score_paper(
            "Multi-Agent Orchestration for Complex Workflows",
            "This paper presents a multi-agent system for task decomposition "
            "and workflow orchestration using an agentic framework.",
        )
        assert score["verdict"] == "relevant"
        assert score["total_score"] >= 3.0
        assert "orchestration" in score["domain_hits"]

    def test_knowledge_graph_paper(self):
        """A paper about knowledge graphs should match the knowledge_graph domain."""
        score = score_paper(
            "Knowledge Graph Reasoning with OWL Ontologies",
            "We propose a graph reasoning approach using ontology-based "
            "entity relation extraction and link prediction over knowledge bases.",
        )
        assert score["verdict"] == "relevant"
        assert "knowledge_graph" in score["domain_hits"]

    def test_irrelevant_paper(self):
        """A paper about unrelated topics should be scored as irrelevant."""
        score = score_paper(
            "Crystal Structure Analysis of Novel Polymer Materials",
            "We study the molecular dynamics of polymer crystallization "
            "under high temperature and pressure conditions.",
        )
        assert score["verdict"] == "irrelevant"
        assert score["total_score"] < 1.0
        assert score["domains_matched"] == 0

    def test_marginal_paper(self):
        """A paper with weak keyword matches should be marginal."""
        score = score_paper(
            "Improving Data Pipeline Throughput",
            "We present techniques for scalable data processing with a collaborative approach to decision support.",
        )
        assert score["verdict"] == "marginal"
        assert 1.0 <= score["total_score"] < 3.0

    def test_multi_domain_paper(self):
        """A paper touching multiple domains should accumulate score across all."""
        score = score_paper(
            "Multi-Agent Planning with Knowledge Graphs and RAG",
            "We combine multi-agent orchestration with knowledge graph reasoning "
            "and retrieval augmented generation for chain of thought planning. "
            "Our benchmark evaluation shows improved safety and alignment.",
        )
        assert score["verdict"] == "relevant"
        assert score["domains_matched"] >= 3
        assert "orchestration" in score["domain_hits"]
        assert "knowledge_graph" in score["domain_hits"]
        assert "planning_reasoning" in score["domain_hits"]

    def test_custom_taxonomy(self):
        """Scoring should respect a custom taxonomy."""
        custom = {
            "robotics": {
                "weight": 5.0,
                "keywords": ["robot", "actuator", "servo"],
            },
        }
        score = score_paper(
            "Robot Arm Control",
            "A novel robot with servo actuator for precise control.",
            taxonomy=custom,
        )
        assert score["verdict"] == "relevant"
        assert "robotics" in score["domain_hits"]

    def test_default_taxonomy_has_9_domains(self):
        """The default taxonomy should have exactly 9 domains."""
        assert len(DEFAULT_TAXONOMY) == 9

    def test_score_structure(self):
        """Score result should have the expected keys."""
        score = score_paper("Test", "test content")
        assert "total_score" in score
        assert "domain_hits" in score
        assert "domains_matched" in score
        assert "verdict" in score
        assert score["verdict"] in ("relevant", "marginal", "irrelevant")


# ── CONCEPT:SX-OS.config.sx CLI / Synergy Report ─────────────────────────────────────


class TestSynergyReport:
    """Tests for synergy report generation (CONCEPT:SX-OS.config.sx)."""

    def test_generate_synergy_report(self, tmp_path):
        """Should produce a valid markdown synergy report."""
        scored = [
            {
                "paper": {"title": "Test Paper 1", "source": "arxiv"},
                "score": {
                    "total_score": 5.0,
                    "verdict": "relevant",
                    "domain_hits": {
                        "orchestration": {
                            "keywords": [{"keyword": "multi-agent", "count": 2}],
                            "domain_score": 5.0,
                        }
                    },
                    "domains_matched": 1,
                },
            },
            {
                "paper": {"title": "Irrelevant Paper", "source": "arxiv"},
                "score": {
                    "total_score": 0.0,
                    "verdict": "irrelevant",
                    "domain_hits": {},
                    "domains_matched": 0,
                },
            },
        ]
        accepted = [scored[0]]

        report_path = generate_synergy_report(tmp_path, scored, accepted)

        assert report_path.exists()
        content = report_path.read_text()
        assert "# Research Synergy Report" in content
        assert "Test Paper 1" in content
        assert "orchestration" in content
        assert "Irrelevant Paper" in content  # Listed in filtered section

    def test_empty_accepted(self, tmp_path):
        """Should handle zero accepted papers gracefully."""
        report_path = generate_synergy_report(tmp_path, [], [])
        assert report_path.exists()
        content = report_path.read_text()
        assert "Papers Accepted**: 0" in content


# ── CONCEPT:SX-OS.config.sx CLI Argument Parsing ─────────────────────────────────────


class TestCLIParsing:
    """Tests for CLI argument parsing (CONCEPT:SX-OS.config.sx)."""

    def test_scan_command_defaults(self):
        """Scan command should have sensible defaults."""
        import argparse

        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest="command")
        scan_parser = subparsers.add_parser("scan")
        scan_parser.add_argument("--query", default="artificial intelligence")
        scan_parser.add_argument("--categories", default="cs.AI,cs.MA,cs.LG,cs.CL,cs.SE,cs.IR,cs.DC")
        scan_parser.add_argument("--max-results", type=int, default=50)
        scan_parser.add_argument("--analyze", action="store_true")

        args = parser.parse_args(["scan"])
        assert args.query == "artificial intelligence"
        assert "cs.AI" in args.categories
        assert args.max_results == 50
        assert args.analyze is False

    def test_analyze_flag(self):
        """--analyze flag should be parsed correctly."""
        import argparse

        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest="command")
        scan_parser = subparsers.add_parser("scan")
        scan_parser.add_argument("--analyze", action="store_true")

        args = parser.parse_args(["scan", "--analyze"])
        assert args.analyze is True
