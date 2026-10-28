"""Controlled provider responses exercise ScholarX's governed paper adapters."""

from __future__ import annotations

import asyncio
import json

import pytest
from agent_connector_sdk.adapters.paper_models import PaperQuery
from agent_connector_sdk.adapters.paper_provider import ProviderFailure
from agent_connector_sdk.adapters.paper_quota import PaperQuotaPolicy
from agent_connector_sdk.http.options import HttpClientOptions
from agent_connector_sdk.http.retry import RetryPolicy
from agent_connector_sdk.testing.http_server import ScriptedHttpServer, ScriptedResponse

from scholarx.paper_source import (
    ArxivPaperSource,
    BiorxivPaperSource,
    OsfPaperSource,
    PmcPaperSource,
    SemanticScholarPaperSource,
)


def options(url: str) -> HttpClientOptions:
    return HttpClientOptions(base_url=url, pin_egress=True, allow_loopback=True, retry=RetryPolicy(max_attempts=1))


def query(provider: str, page_bound: int = 100) -> PaperQuery:
    return PaperQuery(
        tenant="tenant", query="graph", provider_ids=(provider,), schema_revision="v1", page_bound=page_bound
    )


def test_arxiv_atom_and_malformed_response():
    atom = b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>http://arxiv.org/abs/1234.5678v1</id><title>Graph paper</title></entry></feed>'
    with ScriptedHttpServer(
        ScriptedResponse(body=atom, headers={"Content-Type": "application/atom+xml"}),
        ScriptedResponse(body=b"<bad>", headers={"Content-Type": "application/atom+xml"}),
    ) as server:
        provider = ArxivPaperSource(options(server.base_url))
        page = asyncio.run(provider.search(query("arxiv"), None))
        assert page.records[0].reference.record_id == "arxiv:1234.5678v1"
        with pytest.raises(ProviderFailure):
            asyncio.run(provider.search(query("arxiv"), None))


@pytest.mark.parametrize("name", ["osf", "psyarxiv"])
def test_osf_provider_page(name):
    body = json.dumps(
        {"data": [{"id": "abc", "attributes": {"title": "Graph paper"}}], "links": {"next": "next"}}
    ).encode()
    with ScriptedHttpServer(
        ScriptedResponse(body=body, headers={"Content-Type": "application/vnd.api+json"})
    ) as server:
        page = asyncio.run(OsfPaperSource(options(server.base_url), name).search(query(name), None))
        assert page.records[0].reference.provider_id == name
        assert page.cursor == "2"


def test_semantic_scholar_and_retry_after():
    body = json.dumps({"data": [{"paperId": "123", "title": "Graph paper"}], "next": 1}).encode()
    with ScriptedHttpServer(
        ScriptedResponse(body=body, headers={"Content-Type": "application/json"}),
        ScriptedResponse(status=429, headers={"Retry-After": "5"}),
    ) as server:
        provider = SemanticScholarPaperSource(options(server.base_url))
        page = asyncio.run(provider.search(query("semantic_scholar"), None))
        assert page.cursor == "1"
        with pytest.raises(ProviderFailure) as failure:
            asyncio.run(provider.search(query("semantic_scholar"), None))
        assert failure.value.reason == "rate_limited"
        assert failure.value.retry_after_seconds == 5


@pytest.mark.parametrize("name", ["biorxiv", "medrxiv"])
def test_biorxiv_bounded_page(name):
    records = [
        {"doi": "10.1101/123", "title": "Graph first", "version": "1"},
        {"doi": "10.1101/456", "title": "Graph second", "version": "2"},
    ]
    first = json.dumps({"messages": [{"total": "2"}], "collection": records}).encode()
    second = json.dumps({"messages": [{"total": "2"}], "collection": records[1:]}).encode()
    headers = {"Content-Type": "application/json"}
    with ScriptedHttpServer(
        ScriptedResponse(body=first, headers=headers), ScriptedResponse(body=second, headers=headers)
    ) as server:
        provider = BiorxivPaperSource(options(server.base_url), name)
        page = asyncio.run(provider.search(query(name, 1), None))
        following = asyncio.run(provider.search(query(name, 1), page.cursor))
        assert [page.records[0].doi, following.records[0].doi] == ["10.1101/123", "10.1101/456"]
        assert following.cursor is None


def test_pmc_two_requests_require_matching_summaries():
    first = json.dumps({"esearchresult": {"idlist": ["123"], "count": "1"}}).encode()
    second = json.dumps({"result": {"uids": ["123"], "123": {"title": "Graph paper"}}}).encode()
    headers = {"Content-Type": "application/json"}
    with ScriptedHttpServer(
        ScriptedResponse(body=first, headers=headers), ScriptedResponse(body=second, headers=headers)
    ) as server:
        quota = PaperQuotaPolicy(
            provider_id="pmc", credential_group="pmc-public", policy_revision="v1", minimum_spacing_ns=1
        )
        page = asyncio.run(PmcPaperSource(options(server.base_url), quota).search(query("pmc"), None))
        assert page.records[0].reference.record_id == "pmid:123"
        assert len(server.requests) == 2
