import asyncio
import pytest
import threading
import time
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path
from scholarx.models import Paper, PaperSource
from scholarx.queue import JOB_QUEUE, BACKGROUND_DOWNLOADS, POOL_SIZE


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


@pytest.mark.concept("SX-1.6")
def test_queue_pool_drains_many_jobs_with_bounded_concurrency(monkeypatch):
    """Enqueue many jobs; assert ALL reach a terminal status, the queue
    drains via join(), and the in-flight count never exceeds POOL_SIZE.
    (CONCEPT:SX-1.6)"""
    import scholarx.queue as q

    # Make the shared rate gate permissive so we exercise pool concurrency
    # rather than the 0.5s start-interval politeness throttle (covered
    # separately by test_rate_gate_throttles_starts).
    monkeypatch.setattr(q, "_MIN_START_INTERVAL", 0.0)

    n_jobs = POOL_SIZE * 5

    lock = threading.Lock()
    state = {"in_flight": 0, "max_in_flight": 0}

    async def counting_download(paper):
        with lock:
            state["in_flight"] += 1
            state["max_in_flight"] = max(state["max_in_flight"], state["in_flight"])
        try:
            # Hold the slot long enough for workers to overlap.
            await asyncio.sleep(0.1)
            return Path(f"/tmp/{paper.id}.pdf")
        finally:
            with lock:
                state["in_flight"] -= 1

    mock_client = MagicMock()
    mock_client.storage = MagicMock()
    mock_client.storage.download_paper = counting_download

    job_ids = []
    for i in range(n_jobs):
        paper = Paper(
            id=f"arxiv:pool-{i}", title=f"Pool Paper {i}", authors=["Z"], source=PaperSource.ARXIV
        )
        job_id = f"job-pool-{i}"
        job_ids.append(job_id)
        BACKGROUND_DOWNLOADS[job_id] = {"status": "queued", "paper_id": paper.id}
        JOB_QUEUE.put({"job_id": job_id, "paper": paper, "client": mock_client})

    JOB_QUEUE.join()

    # Every job reached a terminal status.
    for job_id in job_ids:
        assert BACKGROUND_DOWNLOADS[job_id]["status"] == "downloaded"
        assert "completed_at" in BACKGROUND_DOWNLOADS[job_id]

    # Concurrency was actually exploited but never exceeded the pool size.
    assert state["max_in_flight"] <= POOL_SIZE
    assert state["max_in_flight"] >= 2  # proves true parallelism, not serial


@pytest.mark.concept("SX-1.6")
def test_rate_gate_throttles_starts(monkeypatch):
    """The shared monotonic rate gate enforces a minimum interval between
    job starts across the pool. (CONCEPT:SX-1.6)"""
    import scholarx.queue as q

    # Use real time.sleep (the autouse fixture stubs scholarx.queue.time.sleep).
    monkeypatch.setattr(q.time, "sleep", time.sleep)
    monkeypatch.setattr(q, "_MIN_START_INTERVAL", 0.05)
    monkeypatch.setattr(q, "_last_start_time", 0.0)

    starts: list[float] = []
    gate_lock = threading.Lock()

    def record():
        for _ in range(5):
            q._rate_gate()
            with gate_lock:
                starts.append(time.monotonic())

    threads = [threading.Thread(target=record) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    starts.sort()
    gaps = [b - a for a, b in zip(starts, starts[1:])]
    # Every consecutive pair of starts is separated by ~>= the min interval.
    assert all(g >= q._MIN_START_INTERVAL - 0.01 for g in gaps)
