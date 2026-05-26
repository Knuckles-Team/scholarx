import argparse
import asyncio
import json
import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from scholarx.cli import (
    _run_auto_analysis,
    _show_status,
    cli,
    generate_synergy_report,
    run_scan,
    score_paper,
)
from scholarx.models import Paper, PaperSource


def test_score_paper_relevance():
    # Test high relevance
    res = score_paper(
        title="Multi-Agent Planning and Orchestration",
        abstract="This paper introduces structured multi-agent workflow orchestration and planning algorithms.",
    )
    assert res["verdict"] == "relevant"
    assert res["total_score"] >= 3.0
    assert "orchestration" in res["domain_hits"]
    assert "planning_reasoning" in res["domain_hits"]

    # Test marginal relevance
    res = score_paper(
        title="Tool Calling",
        abstract="We discuss simple methods.",
    )
    assert res["verdict"] == "marginal"
    assert 1.0 <= res["total_score"] < 3.0

    # Test irrelevant
    res = score_paper(
        title="Quantum Mechanics in Deep Space",
        abstract="This paper explores high-energy quantum physics phenomena.",
    )
    assert res["verdict"] == "irrelevant"
    assert res["total_score"] < 1.0


def test_generate_synergy_report(tmp_path):
    paper1 = Paper(
        id="arxiv:2605.00001",
        source=PaperSource.ARXIV,
        title="Multi-agent Orchestration Overview",
        abstract="Some agent stuff",
        authors=["Alice", "Bob"],
        categories=["cs.AI"],
        published_date="2026-05-22",
        updated_date="2026-05-22",
        url="https://arxiv.org/abs/2605.00001",
    )
    paper2 = Paper(
        id="arxiv:2605.00002",
        source=PaperSource.ARXIV,
        title="Unrelated Paper",
        abstract="Quantum biology details",
        authors=["Charlie"],
        categories=["quant-ph"],
        published_date="2026-05-22",
        updated_date="2026-05-22",
        url="https://arxiv.org/abs/2605.00002",
    )

    scored = [
        {"paper": paper1, "score": score_paper(paper1.title, paper1.abstract)},
        {"paper": paper2, "score": score_paper(paper2.title, paper2.abstract)},
    ]
    accepted = [scored[0]]  # Only the multi-agent one is accepted/marginal/relevant

    report_path = generate_synergy_report(tmp_path, scored, accepted)
    assert report_path.exists()
    content = report_path.read_text()
    assert "# Research Synergy Report" in content
    assert "Multi-agent Orchestration Overview" in content
    assert "Unrelated Paper" in content  # Irrelevant paper listed under Filtered section


def test_run_auto_analysis_no_extractor():
    args = argparse.Namespace(output_dir="/dummy", target_projects=None)
    with patch("pathlib.Path.exists", return_value=False):
        # Should early exit with warning message and not raise exceptions
        _run_auto_analysis(args)


@patch("subprocess.run")
def test_run_auto_analysis_with_extractor_success(mock_subproc, tmp_path):
    # Setup files in tmp_path to mock globting
    (tmp_path / "paper_01.md").write_text("dummy paper")
    (tmp_path / "paper_02.md").write_text("dummy paper 2")

    # Mock the projects paths
    target_project = tmp_path / "dummy_project"
    target_project.mkdir()

    args = argparse.Namespace(
        output_dir=str(tmp_path),
        target_projects=[str(target_project)],
    )

    # We mock exists to return True only for our target project, the papers, and the extractor
    orig_exists = Path.exists

    def mock_exists(self):
        if "extract_innovations.py" in str(self):
            return True
        return orig_exists(self)

    # Setup subprocess mock
    mock_subproc.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="success")

    with patch("pathlib.Path.exists", mock_exists):
        _run_auto_analysis(args)

    assert mock_subproc.call_count == 2  # 2 papers * 1 target project


def test_show_status_success():
    mock_papers = [
        {
            "id": "arxiv:2605.00001",
            "title": "Mock Title",
            "source": "arxiv",
            "published_date": "2026-05-22",
            "exists": True,
        }
    ]
    mock_stats = {
        "paper_count": 1,
        "total_size_mb": 1.5,
        "storage_dir": "/dummy",
    }

    with (
        patch("scholarx.paper_storage.PaperStorage.list_stored_papers", return_value=mock_papers),
        patch("scholarx.paper_storage.PaperStorage.get_storage_stats", return_value=mock_stats),
        patch("rich.console.Console.print") as mock_print,
    ):
        _show_status()
        assert mock_print.called


@pytest.mark.asyncio
async def test_run_scan_no_papers_found(tmp_path):
    args = argparse.Namespace(
        query="no-papers-found-query",
        categories="cs.AI",
        max_results=5,
        output_dir=str(tmp_path),
        taxonomy=None,
        analyze=False,
    )

    mock_client = MagicMock()
    mock_client.search = AsyncMock(return_value=MagicMock(papers=[], total_count=0, deduplicated_count=0))

    with patch("scholarx.api_client.ScholarXClient", return_value=mock_client):
        res = await run_scan(args)
        assert res["status"] == "no_papers"
        assert res["count"] == 0


@pytest.mark.asyncio
async def test_run_scan_success_flow(tmp_path):
    # Setup custom taxonomy JSON to cover taxonomy file loading
    taxonomy_file = tmp_path / "custom_taxonomy.json"
    taxonomy_file.write_text(
        json.dumps(
            {
                "custom_domain": {
                    "weight": 5.0,
                    "keywords": ["highlyrelevant"],
                }
            }
        )
    )

    args = argparse.Namespace(
        query="highlyrelevant agent search",
        categories="cs.AI",
        max_results=2,
        output_dir=str(tmp_path),
        taxonomy=str(taxonomy_file),
        analyze=True,
    )

    paper = Paper(
        id="arxiv:2605.99999",
        source=PaperSource.ARXIV,
        title="A highlyrelevant workflow",
        abstract="Abstract detail highlyrelevant.",
        authors=["Author One"],
        categories=["cs.AI"],
        published_date="2026-05-22",
        updated_date="2026-05-22",
        url="https://arxiv.org/abs/2605.99999",
        pdf_url="https://arxiv.org/pdf/2605.99999",
    )

    mock_result = MagicMock(papers=[paper], total_count=1, deduplicated_count=0)
    mock_client = MagicMock()
    mock_client.search = AsyncMock(return_value=mock_result)
    mock_client.download_paper = AsyncMock(return_value=tmp_path / "dummy.pdf")
    mock_client.storage = MagicMock()
    # First time get_local_path returns None so it downloads, second time it exists to test dedup skip branch
    mock_client.storage.get_local_path.side_effect = [None, tmp_path / "dummy.pdf"]

    with patch("scholarx.api_client.ScholarXClient", return_value=mock_client):
        # We run the scan once
        res = await run_scan(args)
        assert res["status"] == "success"
        assert res["total_fetched"] == 1
        assert res["relevant"] == 1

        # Touch the dummy.pdf file so existing.exists() returns True
        (tmp_path / "dummy.pdf").touch()

        # We run again to verify the duplicate/skipped download logic branch
        res2 = await run_scan(args)
        assert res2["skipped_dedup"] == 1


def test_cli_help_dispatch():
    # Test when no arguments or print_help is dispatched
    with (
        patch("argparse.ArgumentParser.parse_args") as mock_args,
        patch("argparse.ArgumentParser.print_help") as mock_help,
    ):
        mock_args.return_value = argparse.Namespace(command=None)
        cli()
        mock_help.assert_called_once()


def test_cli_scan_command_dispatch():
    # Test scan command execution dispatching
    args = argparse.Namespace(command="scan", analyze=True)
    with (
        patch("argparse.ArgumentParser.parse_args", return_value=args),
        patch("asyncio.run", return_value={"relevant": 2}) as mock_run,
        patch("scholarx.cli._run_auto_analysis") as mock_analyze,
    ):
        cli()
        mock_run.assert_called_once()
        mock_analyze.assert_called_once()


def test_cli_status_command_dispatch():
    # Test status command execution dispatching
    args = argparse.Namespace(command="status")
    with (
        patch("argparse.ArgumentParser.parse_args", return_value=args),
        patch("scholarx.cli._show_status") as mock_status,
    ):
        cli()
        mock_status.assert_called_once()


@pytest.mark.asyncio
async def test_run_scan_rate_limiting_and_failed_downloads(tmp_path):
    args = argparse.Namespace(
        query="orchestration OR planning",
        categories="cs.AI",
        max_results=5,
        output_dir=str(tmp_path),
        taxonomy=None,
        analyze=False,
    )

    paper1 = Paper(
        id="arxiv:2605.00001",
        source=PaperSource.ARXIV,
        title="Multi-agent Orchestration Overview",
        abstract="Some agent stuff with planning orchestration.",
        authors=["Alice"],
        categories=["cs.AI"],
        published_date="2026-05-22",
        updated_date="2026-05-22",
        url="https://arxiv.org/abs/2605.00001",
        pdf_url="https://arxiv.org/pdf/2605.00001",
    )
    paper2 = Paper(
        id="arxiv:2605.00002",
        source=PaperSource.ARXIV,
        title="Multi-agent Planning Overview",
        abstract="Some agent stuff with planning orchestration.",
        authors=["Bob"],
        categories=["cs.AI"],
        published_date="2026-05-22",
        updated_date="2026-05-22",
        url="https://arxiv.org/abs/2605.00002",
        pdf_url="https://arxiv.org/pdf/2605.00002",
    )
    paper3 = Paper(
        id="arxiv:2605.00003",
        source=PaperSource.ARXIV,
        title="No PDF paper planning",
        abstract="Some paper with no pdf.",
        authors=["Charlie"],
        categories=["cs.AI"],
        published_date="2026-05-22",
        updated_date="2026-05-22",
        url="https://arxiv.org/abs/2605.00003",
        pdf_url="https://arxiv.org/pdf/2605.00003",
    )

    mock_result = MagicMock(papers=[paper1, paper2, paper3], total_count=3, deduplicated_count=0)
    mock_client = MagicMock()
    mock_client.search = AsyncMock(return_value=mock_result)
    mock_client.storage = MagicMock()
    mock_client.storage.get_local_path.return_value = None

    async def mock_download(paper):
        if paper.id == "arxiv:2605.00001":
            return tmp_path / "dummy1.pdf"
        elif paper.id == "arxiv:2605.00002":
            raise Exception("Network failure")
        else:
            return None

    mock_client.download_paper = AsyncMock(side_effect=mock_download)

    with (
        patch("scholarx.api_client.ScholarXClient", return_value=mock_client),
        patch("asyncio.sleep", AsyncMock()) as mock_sleep,
    ):
        res = await run_scan(args)
        assert res["status"] == "success"
        assert res["downloaded"] == 1
        assert res["failed"] == 1
        assert mock_sleep.called


def test_run_auto_analysis_no_targets_or_papers(tmp_path):
    # Case 1: no targets found
    args1 = argparse.Namespace(output_dir=str(tmp_path), target_projects=[str(tmp_path / "nonexistent")])
    with patch("scholarx.cli.console.print") as mock_print:

        def mock_exists(self):
            if "extract_innovations.py" in str(self):
                return True
            return False

        with patch("pathlib.Path.exists", mock_exists):
            _run_auto_analysis(args1)
            any_no_targets = any(
                "No target projects found" in str(call[0][0]) for call in mock_print.call_args_list if call[0]
            )
            assert any_no_targets

    # Case 2: no papers found
    target_dir = tmp_path / "some_target"
    target_dir.mkdir()
    args2 = argparse.Namespace(output_dir=str(tmp_path), target_projects=[str(target_dir)])
    with patch("scholarx.cli.console.print") as mock_print:

        def mock_exists2(self):
            if "extract_innovations.py" in str(self):
                return True
            if "some_target" in str(self):
                return True
            return False

        with patch("pathlib.Path.exists", mock_exists2):
            _run_auto_analysis(args2)
            any_no_papers = any(
                "No paper markdowns found" in str(call[0][0]) for call in mock_print.call_args_list if call[0]
            )
            assert any_no_papers


@patch("subprocess.run")
def test_run_auto_analysis_success_details(mock_subproc, tmp_path):
    (tmp_path / "paper_01.md").write_text("dummy paper")
    target_project = tmp_path / "dummy_project"
    target_project.mkdir()

    args = argparse.Namespace(
        output_dir=str(tmp_path),
        target_projects=[str(target_project)],
    )

    innovations_dir = tmp_path / "innovations"
    innovations_dir.mkdir(exist_ok=True)
    out_file = innovations_dir / "paper_01_dummy_project_innovations.json"

    innov_data = {
        "innovations": [
            {
                "concept": "Self-Supervised Planning",
                "description": "Uses self-play to generate optimal plan graphs.",
                "domain": "planning",
                "analogy": "Like alpha-zero but for software APIs.",
            }
        ]
    }
    out_file.write_text(json.dumps(innov_data))

    def mock_exists(self):
        if "extract_innovations.py" in str(self):
            return True
        if "dummy_project" in str(self):
            return True
        if "paper_01.md" in str(self):
            return True
        return False

    mock_subproc.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="success")

    with patch("pathlib.Path.exists", mock_exists):
        _run_auto_analysis(args)

    report_file = tmp_path / "innovations_report.md"
    assert report_file.exists()
    content = report_file.read_text()
    assert "Self-Supervised Planning" in content
    assert "Domain: `planning`" in content
    assert "Analogy: Like alpha-zero" in content

    # Test Exception in subprocess run to cover error log
    mock_subproc.side_effect = Exception("Subprocess failure")
    with patch("pathlib.Path.exists", mock_exists), patch("scholarx.cli.console.print") as mock_print:
        _run_auto_analysis(args)
        any_err = any("Subprocess failure" in str(call[0][0]) for call in mock_print.call_args_list if call[0])
        assert any_err


@patch("subprocess.run")
def test_run_auto_analysis_default_targets(mock_subproc, tmp_path):
    (tmp_path / "paper_01.md").write_text("dummy paper")
    args = argparse.Namespace(
        output_dir=str(tmp_path),
        target_projects=None,
    )

    def mock_exists(self):
        if "extract_innovations.py" in str(self):
            return True
        if "agent-packages" in str(self):
            return True
        if "paper_01.md" in str(self):
            return True
        return False

    mock_subproc.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="success")

    with patch("pathlib.Path.exists", mock_exists):
        _run_auto_analysis(args)


def test_main_module():
    with patch("scholarx.cli.cli") as mock_cli:
        import runpy

        runpy.run_module("scholarx.__main__", run_name="__main__")
        mock_cli.assert_called_once()
