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
            # (e.g. "https://arxiv.org/abs/2603.09022").
            if not paper_ids:
                return {"error": "'paper_ids' required for 'download_url' action"}
            from typing import Any

            results: list[dict[str, Any]] = []
            for raw_id in [i.strip() for i in paper_ids.split(",") if i.strip()]:
                # Extract arXiv ID from URL if provided
                pid = raw_id
                for prefix in ("https://arxiv.org/abs/", "https://arxiv.org/pdf/", "http://arxiv.org/abs/"):
                    if raw_id.startswith(prefix):
                        pid = raw_id.split(prefix)[-1].rstrip("/")
                        break
                # Strip version suffix for filename, keep for URL
                base_id = pid.split("v")[0] if "v" in pid and pid[-1].isdigit() else pid
                pdf_url = f"https://arxiv.org/pdf/{pid}"
                dest = client.storage.storage_dir / f"{base_id}.pdf"
                if dest.exists():
                    results.append({"paper_id": pid, "status": "already_exists", "local_path": str(dest)})
                    continue
                try:
                    import httpx as _httpx

                    async with _httpx.AsyncClient(
                        timeout=_httpx.Timeout(120.0, connect=30.0),
                        follow_redirects=True,
                    ) as http:
                        resp = await http.get(pdf_url)
                        resp.raise_for_status()
                        dest.write_bytes(resp.content)
                        results.append(
                            {
                                "paper_id": pid,
                                "status": "downloaded",
                                "local_path": str(dest),
                                "size_bytes": len(resp.content),
                            }
                        )
                except Exception as e:
                    results.append({"paper_id": pid, "status": "failed", "error": str(e)})
            return {"results": results}

        if action == "bulk_download":
            if not source or not paper_ids:
                return {"error": "'source' and 'paper_ids' required for 'bulk_download' action"}
            ids = [i.strip() for i in paper_ids.split(",") if i.strip()]
            results = []
            stored = await run_blocking(client.storage.list_stored_papers)
            for pid in ids:
                # Check local storage first
                already_exists = False
                for p in stored:
                    if p.get("source") == source and (pid == p.get("id") or pid in p.get("id", "")):
                        local_path = p.get("local_path")
                        if local_path and __import__("pathlib").Path(local_path).exists():
                            results.append({"paper_id": pid, "status": "already_exists", "local_path": local_path})
                            already_exists = True
                            break
                if already_exists:
                    continue

                paper = await client.get_paper(PaperSource(source), pid)
                if not paper:
                    results.append({"paper_id": pid, "status": "failed", "error": "Paper not found"})
                    continue
                jid = await run_blocking(client.queue_download, paper)
                results.append({"paper_id": pid, "status": "queued", "job_id": jid})
            return {"results": results}

        # resolve_action guarantees a valid canonical action above.
        return {"error": f"Unknown action: {action}"}  # pragma: no cover
