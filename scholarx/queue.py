"""Background queue for downloading papers sequentially to avoid rate limits."""

import asyncio
import datetime
import logging
import queue
import threading
import time

logger = logging.getLogger(__name__)

BACKGROUND_DOWNLOADS: dict[str, dict] = {}
JOB_QUEUE: queue.Queue = queue.Queue()


def _download_worker():
    """Background worker that sequentially processes download jobs. (CONCEPT:SX-1.6)"""
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

            # Enforce rate limit delay before starting
            time.sleep(2.0)

            # download_paper in PaperStorage spawns its own httpx.AsyncClient,
            # so we can safely wrap it in a new event loop.
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


# Initialize the daemon thread globally so it's ready when the module loads
_worker_thread = threading.Thread(target=_download_worker, daemon=True)
_worker_thread.start()
