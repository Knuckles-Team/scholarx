"""MCP tools for storage operations.

Auto-generated from mcp_server.py during ecosystem standardization.
"""

from agent_utilities.mcp_utilities import resolve_action, run_blocking
from fastmcp import Context
from pydantic import Field

from scholarx.mcp_server import STORAGE_ACTIONS, _get_client


def register_storage_tools(mcp):
    """Register paper storage tools."""

    @mcp.tool(tags={"storage"})
    async def sx_storage(
        action: str = Field(
            default="stored",
            description=(
                "Action: 'download', 'download_url', 'bulk_download', 'stored', "
                "'status', 'queue'. Use 'list_actions' to discover all."
            ),
        ),
        source: str = Field(default="", description="Paper source (arxiv, pmc, etc.)"),
        paper_ids: str = Field(default="", description="Comma-separated list of paper IDs to download"),
        job_id: str = Field(default="", description="The job_id to check status for"),
        ctx: Context | None = Field(description="MCP context for progress reporting", default=None),
    ) -> dict:
        """Manage offline PDF storage and background downloads."""
        from scholarx.models import PaperSource

        resolved = resolve_action(action, STORAGE_ACTIONS, service="scholarx")
        if isinstance(resolved, dict):
            return resolved
        action = resolved

        client = _get_client()
        if action == "stored":
            papers = await run_blocking(client.storage.list_stored_papers)
            stats = await run_blocking(client.storage.get_storage_stats)
            return {"papers": papers, "stats": stats}

        if action == "status":
            if not job_id:
                return {"error": "'job_id' required for 'status' action"}
            status = await run_blocking(client.get_download_status, job_id)
            return status if status else {"error": f"Job {job_id} not found."}

        if action == "queue":
            return {"downloads": await run_blocking(client.get_queue_status)}

        if action == "download":
            if not source or not paper_ids:
                return {"error": "'source' and 'paper_ids' required for 'download' action"}
            pid = paper_ids.split(",")[0].strip()

            # Check local storage first
            stored = await run_blocking(client.storage.list_stored_papers)
            for p in stored:
                if p.get("source") == source and (pid == p.get("id") or pid in p.get("id", "")):
                    local_path = p.get("local_path")
                    if local_path and __import__("pathlib").Path(local_path).exists():
                        return {"status": "already_exists", "local_path": local_path, "paper_id": p.get("id")}

            paper = await client.get_paper(PaperSource(source), pid)
            if not paper:
                return {"error": "Paper not found"}
            if ctx:
                await ctx.report_progress(10, 100)
            path = await client.download_paper(paper)
            if ctx:
                await ctx.report_progress(100, 100)
            return {
                "status": "downloaded" if path else "failed",
                "local_path": str(path) if path else None,
                "paper_id": paper.id,
            }

        if action == "download_url":
            # Direct URL-based download — bypasses the arXiv API entirely.
            # Accepts paper_ids as arXiv IDs (e.g. "2603.09022") or full URLs
            # (e.g. "https://arxiv.org/abs/2603.09022"). Downloads run in
            # parallel with bounded concurrency inside the client.
            if not paper_ids:
                return {"error": "'paper_ids' required for 'download_url' action"}
            raw_ids = [i.strip() for i in paper_ids.split(",") if i.strip()]
            results = await client.download_urls(raw_ids)
            return {"results": results}

        if action == "bulk_download":
            if not source or not paper_ids:
                return {"error": "'source' and 'paper_ids' required for 'bulk_download' action"}
            ids = [i.strip() for i in paper_ids.split(",") if i.strip()]

            # Build the stored-paper index ONCE (set of ids + id→path map)
            # to avoid an O(N×stored) inner scan per requested id.
            stored = await run_blocking(client.storage.list_stored_papers)
            stored_paths: dict[str, str] = {}
            for p in stored:
                if p.get("source") != source:
                    continue
                local_path = p.get("local_path")
                if local_path and __import__("pathlib").Path(local_path).exists():
                    stored_paths[p.get("id", "")] = local_path

            def _cached_path(pid: str) -> str | None:
                if pid in stored_paths:
                    return stored_paths[pid]
                # Fall back to substring match (some ids are stored with prefixes).
                for sid, path in stored_paths.items():
                    if pid in sid:
                        return path
                return None

            results = []
            uncached_ids: list[str] = []
            for pid in ids:
                cached = _cached_path(pid)
                if cached:
                    results.append({"paper_id": pid, "status": "cached", "local_path": cached})
                else:
                    uncached_ids.append(pid)

            # Resolve uncached papers' metadata concurrently.
            import asyncio

            resolved_pairs = await asyncio.gather(
                *[client.get_paper(PaperSource(source), pid) for pid in uncached_ids],
                return_exceptions=True,
            )

            to_download = []
            for pid, paper in zip(uncached_ids, resolved_pairs, strict=True):
                if isinstance(paper, Exception):
                    results.append({"paper_id": pid, "status": "failed", "error": str(paper)})
                elif paper is None:
                    results.append({"paper_id": pid, "status": "failed", "error": "Paper not found"})
                else:
                    to_download.append(paper)

            if to_download:
                results.extend(await client.download_papers(to_download))
            return {"results": results}

        # resolve_action guarantees a valid canonical action above.
        return {"error": f"Unknown action: {action}"}  # pragma: no cover
