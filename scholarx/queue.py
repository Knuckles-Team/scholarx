"""Background queue for downloading papers with a bounded worker pool.

A pool of worker threads drains a shared :data:`JOB_QUEUE`. Politeness toward
upstream mirrors is enforced by a single shared monotonic min-interval rate
gate (one job *start* every ``_MIN_START_INTERVAL`` seconds across the whole
pool) rather than by serializing a flat sleep per worker. (CONCEPT:SX-OS.config.sx-6)
"""

import asyncio
import datetime
import logging
import queue
import threading
import time

logger = logging.getLogger(__name__)

BACKGROUND_DOWNLOADS: dict[str, dict] = {}
JOB_QUEUE: queue.Queue = queue.Queue()

# Number of worker threads draining JOB_QUEUE in parallel. (CONCEPT:SX-OS.config.sx-6)
POOL_SIZE = 4

# Shared monotonic min-interval rate gate: at most one job *start* per this
# many seconds across the entire pool. Keeps upstream politeness without each
# worker serializing on a flat per-job sleep. (CONCEPT:SX-OS.config.sx-6)
_MIN_START_INTERVAL = 0.5
_rate_lock = threading.Lock()
_last_start_time: float = 0.0


def _rate_gate() -> None:
    """Block until at least ``_MIN_START_INTERVAL`` has elapsed since the last
    job start across the pool, then claim this start slot. (CONCEPT:SX-OS.config.sx-6)"""
    global _last_start_time
    while True:
        with _rate_lock:
            now = time.monotonic()
            wait = _MIN_START_INTERVAL - (now - _last_start_time)
            if wait <= 0:
                _last_start_time = now
                return
        time.sleep(wait)


def _download_worker():
    """Background worker that processes download jobs from the shared queue.

    Multiple instances run concurrently (one per pool thread). (CONCEPT:SX-OS.config.sx-6)
    """
    logger.info("Starting ScholarX background download worker...")
    while True:
        try:
            job = JOB_QUEUE.get()
            job_id = job["job_id"]
            paper = job["paper"]
            client = job["client"]

            if job_id not in BACKGROUND_DOWNLOADS:
                JOB_QUEUE.task_done()
                continue

            BACKGROUND_DOWNLOADS[job_id]["status"] = "running"

            # Enforce the shared rate gate before starting the download.
            _rate_gate()

            # download_paper in PaperStorage spawns its own httpx.AsyncClient,
            # so we can safely wrap it in a new event loop per worker thread.
            try:
                local_path = asyncio.run(client.storage.download_paper(paper))
                if local_path:
                    BACKGROUND_DOWNLOADS[job_id]["status"] = "downloaded"
                    BACKGROUND_DOWNLOADS[job_id]["local_path"] = str(local_path)
                else:
                    BACKGROUND_DOWNLOADS[job_id]["status"] = "failed"
                    BACKGROUND_DOWNLOADS[job_id]["error"] = "Download failed or returned None"
            except Exception as e:
                logger.error(f"Download worker failed for job {job_id}: {e}")
                BACKGROUND_DOWNLOADS[job_id]["status"] = "failed"
                BACKGROUND_DOWNLOADS[job_id]["error"] = str(e)

            BACKGROUND_DOWNLOADS[job_id]["completed_at"] = datetime.datetime.now(datetime.UTC).isoformat()
            JOB_QUEUE.task_done()

        except Exception as e:
            logger.error(f"Critical error in ScholarX download worker: {e}")
            try:
                JOB_QUEUE.task_done()
            except Exception:  # nosec B110
                pass
            time.sleep(5.0)


# Initialize the daemon worker pool globally so it's ready when the module
# loads. (CONCEPT:SX-OS.config.sx-6)
_worker_threads: list[threading.Thread] = []
for _i in range(POOL_SIZE):
    _t = threading.Thread(target=_download_worker, daemon=True, name=f"scholarx-download-{_i}")
    _t.start()
    _worker_threads.append(_t)
