"""Surface contracts: tool use, links, data locations and business roles."""

from scion_sdk.surface_contracts import (
    BusinessRole,
    DataLocation,
    Refusal,
    SurfaceLink,
    ToolStep,
    ToolUseContract,
)

CONTRACTS = (
    ToolUseContract(
        "search-papers",
        (
            ToolStep(
                "sx_enabled_sources",
                result=("sources",),
            ),
            ToolStep(
                "sx_search_search",
                params=("query", "sources", "categories", "max_results", "sort_by", "title", "paper_id"),
                result=("papers", "total_count", "sources_queried", "deduplicated_count"),
                refusals=(Refusal("SOURCE_UNAVAILABLE", "the paper source is disabled or does not answer"),),
            ),
            ToolStep(
                "scholarx_search",
                params=("query",),
                result=("papers", "total_count"),
                refusals=(Refusal("SOURCE_UNAVAILABLE", "the paper source is disabled or does not answer"),),
            ),
        ),
    ),
    ToolUseContract(
        "read-a-paper",
        (
            ToolStep(
                "sx_search_get",
                params=("sources", "paper_id"),
                result=("id", "title", "authors", "abstract", "pdf_url"),
                refusals=(
                    Refusal("PAPER_NOT_FOUND", "no paper has the id in that source"),
                    Refusal("INVALID_SOURCE", "the source is not one of the enabled paper sources"),
                ),
            ),
            ToolStep(
                "scholarx_get_paper",
                params=("source", "paper_id"),
                result=("id", "title", "authors", "abstract"),
                refusals=(
                    Refusal("PAPER_NOT_FOUND", "no paper has the id in that source"),
                    Refusal("INVALID_SOURCE", "the source is not one of the enabled paper sources"),
                ),
            ),
        ),
    ),
    ToolUseContract(
        "find-papers-by-author",
        (
            ToolStep(
                "sx_search_author",
                params=("author", "max_results"),
                result=("papers", "total_count"),
                refusals=(Refusal("AUTHOR_REQUIRED", "no author name was supplied"),),
            ),
        ),
    ),
    ToolUseContract(
        "track-recent-papers",
        (
            ToolStep(
                "sx_search_recent",
                params=("categories", "days", "sources"),
                result=("papers", "total_count", "sources_queried"),
                refusals=(Refusal("SOURCE_UNAVAILABLE", "the paper source is disabled or does not answer"),),
            ),
            ToolStep(
                "scholarx_get_recent_papers",
                params=("categories", "days", "sources"),
                result=("papers", "total_count"),
                refusals=(Refusal("SOURCE_UNAVAILABLE", "the paper source is disabled or does not answer"),),
            ),
        ),
    ),
    ToolUseContract(
        "explore-sources-and-categories",
        (
            ToolStep(
                "sx_info_sources",
                result=("sources",),
            ),
            ToolStep(
                "sx_info_categories",
                params=("source",),
                result=("categories",),
                refusals=(Refusal("INVALID_SOURCE", "the source is not one of the enabled paper sources"),),
            ),
            ToolStep(
                "scholarx_get_source_status",
                result=("source", "enabled", "status"),
            ),
            ToolStep(
                "scholarx_list_categories",
                params=("source",),
                result=("categories",),
                refusals=(Refusal("INVALID_SOURCE", "the source is not one of the enabled paper sources"),),
            ),
            ToolStep(
                "scholarx_enabled_sources",
                result=("sources",),
            ),
        ),
    ),
    ToolUseContract(
        "download-papers",
        (
            ToolStep(
                "sx_storage_download",
                params=("source", "paper_ids"),
                result=("status", "local_path", "paper_id"),
                refusals=(
                    Refusal("PAPER_NOT_FOUND", "no paper has the id in that source"),
                    Refusal("INVALID_SOURCE", "the source is not one of the enabled paper sources"),
                    Refusal("LIMIT_EXCEEDED", "the id list or input exceeds the documented bound"),
                ),
            ),
            ToolStep(
                "sx_storage_download_url",
                params=("paper_ids",),
                result=("results",),
                refusals=(
                    Refusal("LIMIT_EXCEEDED", "the id list or input exceeds the documented bound"),
                    Refusal("INVALID_ARXIV_ID", "the identifier is not an arXiv id or URL"),
                ),
            ),
            ToolStep(
                "sx_download_papers",
                params=("source", "paper_ids", "concurrency"),
                result=("results",),
                refusals=(
                    Refusal("INVALID_SOURCE", "the source is not one of the enabled paper sources"),
                    Refusal("LIMIT_EXCEEDED", "the id list or input exceeds the documented bound"),
                ),
            ),
            ToolStep(
                "sx_download_urls",
                params=("paper_ids", "concurrency"),
                result=("results",),
                refusals=(Refusal("LIMIT_EXCEEDED", "the id list or input exceeds the documented bound"),),
            ),
            ToolStep(
                "scholarx_download_paper",
                params=("paper",),
                result=("local_path",),
                refusals=(Refusal("SOURCE_UNAVAILABLE", "the paper source is disabled or does not answer"),),
            ),
            ToolStep(
                "scholarx_download_papers",
                params=("papers", "concurrency"),
                result=("results",),
                refusals=(Refusal("SOURCE_UNAVAILABLE", "the paper source is disabled or does not answer"),),
            ),
            ToolStep(
                "scholarx_download_urls",
                params=("raw_ids", "concurrency"),
                result=("results",),
                refusals=(Refusal("LIMIT_EXCEEDED", "the id list or input exceeds the documented bound"),),
            ),
        ),
    ),
    ToolUseContract(
        "queue-background-downloads",
        (
            ToolStep(
                "sx_storage_bulk_download",
                params=("source", "paper_ids"),
                result=("results", "job_id"),
                refusals=(
                    Refusal("INVALID_SOURCE", "the source is not one of the enabled paper sources"),
                    Refusal("LIMIT_EXCEEDED", "the id list or input exceeds the documented bound"),
                ),
            ),
            ToolStep(
                "scholarx_queue_download",
                params=("paper",),
                result=("job_id",),
            ),
            ToolStep(
                "sx_storage_status",
                params=("job_id",),
                result=("status",),
                refusals=(Refusal("JOB_NOT_FOUND", "no queued job has the id"),),
            ),
            ToolStep(
                "scholarx_get_download_status",
                params=("job_id",),
                result=("status",),
                refusals=(Refusal("JOB_NOT_FOUND", "no queued job has the id"),),
            ),
            ToolStep(
                "sx_storage_queue",
                result=("downloads",),
            ),
            ToolStep(
                "scholarx_get_queue_status",
                result=("downloads",),
            ),
        ),
    ),
    ToolUseContract(
        "review-stored-papers",
        (
            ToolStep(
                "sx_storage_stored",
                result=("papers", "stats"),
            ),
        ),
    ),
    ToolUseContract(
        "ingest-papers-to-graph",
        (
            ToolStep(
                "scholarx_ingest_papers",
                params=("query", "sources", "categories", "max_results"),
                result=("fetched", "ingested"),
                refusals=(Refusal("NO_ENGINE", "no knowledge-graph engine is reachable, ingested is null"),),
            ),
        ),
    ),
)

LINKS = (
    SurfaceLink(
        "search-papers",
        tools=("sx_enabled_sources", "sx_search_search", "scholarx_search"),
        prompts=(
            "scholarx-operator",
            "scholarx-research-scout",
            "scion_sdk_enhancement_scan",
            "biomimicry_innovation_scan",
        ),
        skills=("scholarx-paper-search",),
    ),
    SurfaceLink(
        "read-a-paper",
        tools=("sx_search_get", "scholarx_get_paper"),
        prompts=("scholarx-operator", "scholarx-research-scout"),
        skills=("scholarx-paper-search",),
    ),
    SurfaceLink(
        "find-papers-by-author",
        tools=("sx_search_author",),
        prompts=("scholarx-operator", "scholarx-research-scout"),
        skills=("scholarx-paper-search",),
    ),
    SurfaceLink(
        "track-recent-papers",
        tools=("sx_search_recent", "scholarx_get_recent_papers"),
        prompts=("scholarx-operator", "scholarx-research-scout", "scion_sdk_enhancement_scan"),
        skills=("scholarx-paper-search",),
    ),
    SurfaceLink(
        "explore-sources-and-categories",
        tools=(
            "sx_info_sources",
            "sx_info_categories",
            "scholarx_get_source_status",
            "scholarx_list_categories",
            "scholarx_enabled_sources",
        ),
        prompts=("scholarx-operator", "scholarx-research-scout"),
        skills=("scholarx-paper-search",),
    ),
    SurfaceLink(
        "download-papers",
        tools=(
            "sx_storage_download",
            "sx_storage_download_url",
            "sx_download_papers",
            "sx_download_urls",
            "scholarx_download_paper",
            "scholarx_download_papers",
            "scholarx_download_urls",
        ),
        prompts=("scholarx-operator", "scholarx-librarian"),
        skills=("scholarx-paper-library",),
    ),
    SurfaceLink(
        "queue-background-downloads",
        tools=(
            "sx_storage_bulk_download",
            "scholarx_queue_download",
            "sx_storage_status",
            "scholarx_get_download_status",
            "sx_storage_queue",
            "scholarx_get_queue_status",
        ),
        prompts=("scholarx-operator", "scholarx-librarian"),
        skills=("scholarx-paper-library",),
    ),
    SurfaceLink(
        "review-stored-papers",
        tools=("sx_storage_stored",),
        prompts=("scholarx-operator", "scholarx-librarian"),
        skills=("scholarx-paper-library",),
    ),
    SurfaceLink(
        "ingest-papers-to-graph",
        tools=("scholarx_ingest_papers",),
        prompts=("scholarx-operator", "scholarx-librarian"),
        skills=("scholarx-kg-ingestion",),
    ),
    SurfaceLink(
        "scholarx-operations",
        tools=("sx_search_search", "sx_storage_download", "scholarx_search"),
        skills=("scholarx-operations",),
    ),
)

LOCATIONS = (
    DataLocation(
        "scholarx-paper-sources",
        ("Paper", "PaperSource", "ResearchCategory"),
        "SCHOLARX_SOURCES",
        "sx_search_search",
        route_param="sources",
        federation_key="paper_id",
    ),
    DataLocation(
        "scholarx-paper-store",
        ("Paper",),
        "SCHOLARX_OUTPUT_DIR",
        "sx_storage_stored",
        federation_key="paper_id",
    ),
)

ROLES = (
    BusinessRole(
        "research-scout",
        tasks=(
            "search-papers",
            "read-a-paper",
            "find-papers-by-author",
            "track-recent-papers",
            "explore-sources-and-categories",
        ),
    ),
    BusinessRole("enhancement-analyst", tasks=("search-papers", "track-recent-papers")),
    BusinessRole("biomimicry-analyst", tasks=("search-papers",)),
    BusinessRole(
        "librarian",
        tasks=("download-papers", "queue-background-downloads", "review-stored-papers", "ingest-papers-to-graph"),
    ),
)
