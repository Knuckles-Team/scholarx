#!/usr/bin/python
"""ScholarX Agent Server.

Standard graph agent server following the genius-agent pattern.
Uses create_agent_server from agent-utilities for graph orchestration.
"""

import logging
import os
import sys
import warnings

# Filter warnings early
with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    try:
        from requests.exceptions import RequestsDependencyWarning

        warnings.filterwarnings("ignore", category=RequestsDependencyWarning)
    except ImportError:
        pass

warnings.filterwarnings("ignore", message=".*urllib3.*or chardet.*")
warnings.filterwarnings("ignore", message=".*urllib3.*or charset_normalizer.*")
warnings.filterwarnings("ignore", category=DeprecationWarning, module="fastmcp")


__version__ = "1.0.0"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

DEFAULT_AGENT_NAME = None
DEFAULT_AGENT_DESCRIPTION = None
DEFAULT_AGENT_SYSTEM_PROMPT = None


def agent_server():
    from agent_utilities import (
        build_system_prompt_from_workspace,
        create_agent_parser,
        create_agent_server,
        initialize_workspace,
        load_identity,
    )

    global DEFAULT_AGENT_NAME, DEFAULT_AGENT_DESCRIPTION, DEFAULT_AGENT_SYSTEM_PROMPT
    initialize_workspace()
    meta = load_identity()

    DEFAULT_AGENT_NAME = os.getenv("DEFAULT_AGENT_NAME", meta.get("name", "ScholarX Agent"))
    DEFAULT_AGENT_DESCRIPTION = os.getenv(
        "AGENT_DESCRIPTION",
        meta.get("description", "ScholarX — Universal research paper discovery and analysis."),
    )
    DEFAULT_AGENT_SYSTEM_PROMPT = os.getenv(
        "AGENT_SYSTEM_PROMPT",
        meta.get("content") or build_system_prompt_from_workspace(),
    )

    """Agent server entry point."""
    print(f"{DEFAULT_AGENT_NAME} v{__version__}", file=sys.stderr)
    logger.info("Application startup complete")

    parser = create_agent_parser()
    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.debug("Debug mode enabled")

    create_agent_server(
        mcp_url=args.mcp_url,
        mcp_config=args.mcp_config or "mcp_config.json",
        host=args.host,
        port=args.port,
        provider=args.provider,
        model_id=args.model_id,
        router_model=args.model_id,
        agent_model=args.model_id,
        base_url=args.base_url,
        api_key=args.api_key,
        custom_skills_directory=args.custom_skills_directory,
        enable_web_ui=args.web,
        enable_otel=args.otel,
        otel_endpoint=args.otel_endpoint,
        otel_headers=args.otel_headers,
        otel_public_key=args.otel_public_key,
        otel_secret_key=args.otel_secret_key,
        otel_protocol=args.otel_protocol,
        debug=args.debug,
    )


if __name__ == "__main__":
    agent_server()
