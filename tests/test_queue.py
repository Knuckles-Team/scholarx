import pytest
import time
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path
from scholarx.models import Paper, PaperSource
from scholarx.queue import JOB_QUEUE, BACKGROUND_DOWNLOADS


@pytest.fixture(autouse=True)
def mock_rate_limit_delay():
    # Patch time.sleep inside scholarx.queue to avoid waiting 5 seconds in worker critical exception path
    with patch("scholarx.queue.time.sleep") as mock_sleep:
        yield mock_sleep


@pytest.mark.concept("SX-1.6")
def test_queue_lifecycle_success():
    mock_paper = Paper(
        id="arxiv:test-queue-1", title="Queue Success Paper", authors=["Alice"], source=PaperSource.ARXIV
    )

    mock_client = MagicMock()
    mock_client.storage = MagicMock()
    mock_client.storage.download_paper = AsyncMock(return_value=Path("/tmp/stored-queue.pdf"))

    job_id = "job-success"
    BACKGROUND_DOWNLOADS[job_id] = {"status": "queued", "paper_id": mock_paper.id}

    # Queue the job
    JOB_QUEUE.put({"job_id": job_id, "paper": mock_paper, "client": mock_client})

    # Wait for the background worker to finish processing this job
    JOB_QUEUE.join()

    # Assert success states with robust schema assertions
    job_status = BACKGROUND_DOWNLOADS[job_id]
    assert job_status["status"] == "downloaded"
    assert job_status["local_path"] == "/tmp/stored-queue.pdf"
    assert "completed_at" in job_status
    assert job_status["paper_id"] == "arxiv:test-queue-1"


@pytest.mark.concept("SX-1.6")
def test_queue_lifecycle_failure():
    mock_paper = Paper(id="arxiv:test-queue-2", title="Queue Failure Paper", authors=["Bob"], source=PaperSource.ARXIV)

    mock_client = MagicMock()
    mock_client.storage = MagicMock()
    mock_client.storage.download_paper = AsyncMock(return_value=None)

    job_id = "job-fail"
    BACKGROUND_DOWNLOADS[job_id] = {"status": "queued", "paper_id": mock_paper.id}

    JOB_QUEUE.put({"job_id": job_id, "paper": mock_paper, "client": mock_client})

    JOB_QUEUE.join()

    # Assert failure states
    job_status = BACKGROUND_DOWNLOADS[job_id]
    assert job_status["status"] == "failed"
    assert "Download failed" in job_status["error"]
    assert "completed_at" in job_status
    assert job_status["paper_id"] == "arxiv:test-queue-2"


@pytest.mark.concept("SX-1.6")
def test_queue_lifecycle_exception():
    mock_paper = Paper(
        id="arxiv:test-queue-3", title="Queue Exception Paper", authors=["Charlie"], source=PaperSource.ARXIV
    )

    mock_client = MagicMock()
    mock_client.storage = MagicMock()
    mock_client.storage.download_paper = AsyncMock(side_effect=RuntimeError("Disk is full!"))

    job_id = "job-exception"
    BACKGROUND_DOWNLOADS[job_id] = {"status": "queued", "paper_id": mock_paper.id}

    JOB_QUEUE.put({"job_id": job_id, "paper": mock_paper, "client": mock_client})

    JOB_QUEUE.join()

    # Assert exception states
    job_status = BACKGROUND_DOWNLOADS[job_id]
    assert job_status["status"] == "failed"
    assert job_status["error"] == "Disk is full!"
    assert "completed_at" in job_status
    assert job_status["paper_id"] == "arxiv:test-queue-3"


@pytest.mark.concept("SX-1.6")
def test_queue_job_not_found():
    # If a job is put in the queue but is not registered in BACKGROUND_DOWNLOADS,
    # it should just skip and proceed.
    mock_paper = Paper(
        id="arxiv:test-queue-4", title="Queue Untracked Paper", authors=["David"], source=PaperSource.ARXIV
    )
    mock_client = MagicMock()

    job_id = "untracked-job"

    JOB_QUEUE.put({"job_id": job_id, "paper": mock_paper, "client": mock_client})

    JOB_QUEUE.join()
    # Should complete without throwing and just ignore
    assert job_id not in BACKGROUND_DOWNLOADS
