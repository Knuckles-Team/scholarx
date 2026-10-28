"""One bounded arXiv provider page for the shared SDK paper contract.

The host supplies the verified EG client, quota policy, egress policy, and
caller authorization. This module does not infer any of those authorities.
"""

from __future__ import annotations

import math
import re
from datetime import date
from typing import Any

from agent_connector_sdk.adapters.paper_models import DocumentOffer, FieldEvidence, PaperQuery, ProviderReference
from agent_connector_sdk.adapters.paper_provider import ProviderFailure, ProviderPage, ProviderPaper
from agent_connector_sdk.adapters.paper_quota import PaperQuotaPolicy, SharedPaperQuota
from agent_connector_sdk.adapters.paper_search import PaperSearchService, ProviderBinding
from agent_connector_sdk.http.bodies import aread_bounded
from agent_connector_sdk.http.client import AirgapViolation, create_async_http_client
from agent_connector_sdk.http.egress import EgressPolicyError, PinnedEgressViolation
from agent_connector_sdk.http.options import HttpClientOptions
from agent_connector_sdk.http.retry import parse_retry_after
from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException

from scholarx.models import PaperSource, SearchQuery
from scholarx.providers.arxiv import ArxivProvider, _build_arxiv_search_page_params

_MAX_RESPONSE = 5 * 1024 * 1024
_ATOM = "{http://www.w3.org/2005/Atom}"
_VERSION = re.compile(r"v([1-9][0-9]*)$")


class ArxivPaperSource:
    """Fetch and parse one arXiv page using host-admitted HTTP options."""

    def __init__(self, options: HttpClientOptions) -> None:
        if options.retry.max_attempts != 1 or not options.pin_egress:
            raise ValueError("paper sources require pinned egress and single HTTP attempts")
        self._options = options
        self._parser = ArxivProvider()

    async def search(self, query: PaperQuery, cursor: str | None) -> ProviderPage:
        offset = _offset(cursor)
        count = min(query.page_bound, self._parser.config.max_results_per_query)
        legacy = SearchQuery(query=query.query, sources=[PaperSource.ARXIV], max_results=count)
        params = _build_arxiv_search_page_params(legacy, self._parser._build_query(legacy), offset, count)
        body = await self._fetch(params)
        records = _parse(body, self._parser)
        return ProviderPage(records=records, cursor=str(offset + len(records)) if len(records) == count else None)

    async def _fetch(self, params: dict[str, Any]) -> bytes:
        try:
            async with create_async_http_client(self._options) as client:
                async with client.stream(
                    "GET", "/query", params=params, headers={"Accept-Encoding": "identity"}
                ) as response:
                    if response.status_code == 429:
                        raise ProviderFailure(
                            "rate_limited", retry_after_seconds=_retry_after(response.headers.get("retry-after"))
                        )
                    if response.status_code in {401, 403}:
                        raise ProviderFailure("unauthorized")
                    content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                    encoding = response.headers.get("content-encoding", "identity").lower()
                    if (
                        response.status_code != 200
                        or encoding not in {"", "identity"}
                        or content_type not in {"application/atom+xml", "application/xml", "text/xml"}
                    ):
                        raise ProviderFailure("provider_failed")
                    return await aread_bounded(response, _MAX_RESPONSE)
        except ProviderFailure:
            raise
        except (AirgapViolation, EgressPolicyError, PinnedEgressViolation):
            raise ProviderFailure("egress_denied") from None
        except Exception:
            raise ProviderFailure("provider_failed") from None


def _retry_after(value: str | None) -> float | None:
    try:
        result = parse_retry_after(value)
        return result if result is not None and math.isfinite(result) else None
    except (OverflowError, ValueError):
        return None


def _offset(cursor: str | None) -> int:
    if cursor is None:
        return 0
    if not cursor.isascii() or not cursor.isdecimal() or len(cursor) > 9:
        raise ProviderFailure("provider_failed")
    return int(cursor)


def _parse(body: bytes, parser: ArxivProvider) -> tuple[ProviderPaper, ...]:
    try:
        root = ElementTree.fromstring(body)
    except (ElementTree.ParseError, DefusedXmlException):
        raise ProviderFailure("provider_failed") from None
    if root.tag != _ATOM + "feed":
        raise ProviderFailure("provider_failed")
    return tuple(_record(entry, parser) for entry in root.findall(_ATOM + "entry"))


def _record(entry: Any, parser: ArxivProvider) -> ProviderPaper:
    try:
        paper = parser._parse_entry(entry)
        if paper is None or not paper.id:
            raise ValueError("missing paper identity")
        source_id = paper.id
        reference = ProviderReference(provider_id="arxiv", record_id=source_id, original_id=paper.url or None)
        revision_match = _VERSION.search(source_id)
        revision = "v" + revision_match.group(1) if revision_match else None
        publication = date.fromisoformat(paper.published_date) if paper.published_date else None
        offers = (
            ()
            if not paper.pdf_url
            else (DocumentOffer(provider_id="arxiv", url=paper.pdf_url, media_type="application/pdf"),)
        )
        values = {
            "title": paper.title or None,
            "authors": tuple(paper.authors),
            "abstract": paper.abstract or None,
            "publication_date": publication,
        }
        evidence = {
            key: (FieldEvidence(provider_id="arxiv", source_id=source_id, location="atom:" + key),)
            for key, value in values.items()
            if value
        }
        return ProviderPaper(
            reference=reference,
            doi=paper.doi,
            revision=revision,
            document_offers=offers,
            field_provenance=evidence,
            **values,
        )
    except (TypeError, ValueError):
        raise ProviderFailure("provider_failed") from None


def create_paper_service(
    *,
    engine_client: Any,
    authorize: Any,
    arxiv_http: HttpClientOptions,
    arxiv_quota: PaperQuotaPolicy,
    semantic_http: HttpClientOptions | None = None,
    semantic_quota: PaperQuotaPolicy | None = None,
    osf_providers: dict[str, tuple[HttpClientOptions, PaperQuotaPolicy]] | None = None,
    biorxiv_providers: dict[str, tuple[HttpClientOptions, PaperQuotaPolicy]] | None = None,
    pmc_provider: tuple[HttpClientOptions, PaperQuotaPolicy] | None = None,
) -> PaperSearchService:
    """Compose arXiv with host-owned authentication, egress and quota policy."""
    if arxiv_quota.provider_id != "arxiv":
        raise ValueError("arXiv quota names another provider")
    binding = ProviderBinding(provider=ArxivPaperSource(arxiv_http), quota=arxiv_quota)
    providers = {"arxiv": binding}
    if (semantic_http is None) != (semantic_quota is None):
        raise ValueError("Semantic Scholar HTTP and quota must be supplied together")
    if semantic_http is not None and semantic_quota is not None:
        if semantic_quota.provider_id != "semantic_scholar":
            raise ValueError("Semantic Scholar quota names another provider")
        providers["semantic_scholar"] = ProviderBinding(
            provider=SemanticScholarPaperSource(semantic_http), quota=semantic_quota
        )
    for name, (options, quota) in (osf_providers or {}).items():
        if name not in {"osf", "psyarxiv"} or quota.provider_id != name:
            raise ValueError("invalid OSF quota identity")
        providers[name] = ProviderBinding(provider=OsfPaperSource(options, name), quota=quota)
    for name, (options, quota) in (biorxiv_providers or {}).items():
        if name not in {"biorxiv", "medrxiv"} or quota.provider_id != name:
            raise ValueError("invalid bioRxiv quota identity")
        providers[name] = ProviderBinding(provider=BiorxivPaperSource(options, name), quota=quota)
    if pmc_provider is not None:
        options, quota = pmc_provider
        providers["pmc"] = ProviderBinding(provider=PmcPaperSource(options, quota), quota=quota)
    return PaperSearchService(providers, quota=SharedPaperQuota(engine_client), authorize=authorize)


class SemanticScholarPaperSource:
    """Fetch a single Semantic Scholar search page with a governed request."""

    def __init__(self, options: HttpClientOptions) -> None:
        if options.retry.max_attempts != 1 or not options.pin_egress:
            raise ValueError("paper sources require pinned egress and single HTTP attempts")
        self._options = options

    async def search(self, query: PaperQuery, cursor: str | None) -> ProviderPage:
        from scholarx.providers.semantic_scholar import _FIELDS, SemanticScholarProvider

        offset = _offset(cursor)
        count = min(query.page_bound, 100)
        try:
            data = await _json_page(
                self._options,
                "/paper/search",
                {"query": query.query, "offset": offset, "limit": count, "fields": _FIELDS},
            )
            if not isinstance(data, dict) or not isinstance(data.get("data"), list) or len(data["data"]) > count:
                raise ValueError("invalid search page")
            parser = SemanticScholarProvider()
            records = tuple(_semantic_record(item, parser) for item in data["data"])
            next_offset = data.get("next")
            if next_offset is not None and (
                type(next_offset) is not int or next_offset <= offset or next_offset > 999_999_999
            ):
                raise ValueError("invalid continuation")
            return ProviderPage(records=records, cursor=str(next_offset) if next_offset is not None else None)
        except ProviderFailure:
            raise
        except (AirgapViolation, EgressPolicyError, PinnedEgressViolation):
            raise ProviderFailure("egress_denied") from None
        except Exception:
            raise ProviderFailure("provider_failed") from None


def _semantic_record(item: Any, parser: Any) -> ProviderPaper:
    paper = parser._parse(item)
    if paper is None or paper.id == "s2:":
        raise ValueError("missing paper identity")
    reference = ProviderReference(provider_id="semantic_scholar", record_id=paper.id, original_id=paper.url or None)
    publication = date.fromisoformat(paper.published_date) if paper.published_date else None
    offers = (
        ()
        if not paper.pdf_url
        else (DocumentOffer(provider_id="semantic_scholar", url=paper.pdf_url, media_type="application/pdf"),)
    )
    values = {
        "title": paper.title or None,
        "authors": tuple(paper.authors),
        "abstract": paper.abstract or None,
        "publication_date": publication,
    }
    evidence = {
        key: (FieldEvidence(provider_id="semantic_scholar", source_id=paper.id, location="json:" + key),)
        for key, value in values.items()
        if value
    }
    return ProviderPaper(
        reference=reference, doi=paper.doi, document_offers=offers, field_provenance=evidence, **values
    )


async def _json_page(options: HttpClientOptions, path: str, params: dict[str, Any]) -> Any:
    import json

    async with create_async_http_client(options) as client:
        async with client.stream("GET", path, params=params, headers={"Accept-Encoding": "identity"}) as response:
            if response.status_code == 429:
                raise ProviderFailure(
                    "rate_limited", retry_after_seconds=_retry_after(response.headers.get("retry-after"))
                )
            if response.status_code in {401, 403}:
                raise ProviderFailure("unauthorized")
            content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
            if (
                response.status_code != 200
                or response.headers.get("content-encoding", "identity").lower() not in {"", "identity"}
                or content_type not in {"application/json", "application/vnd.api+json"}
            ):
                raise ProviderFailure("provider_failed")
            return json.loads(await aread_bounded(response, _MAX_RESPONSE))


class OsfPaperSource:
    """Fetch one OSF or PsyArXiv page under the host's declared quota."""

    def __init__(self, options: HttpClientOptions, provider: str) -> None:
        if provider not in {"osf", "psyarxiv"} or options.retry.max_attempts != 1 or not options.pin_egress:
            raise ValueError("invalid OSF provider or governed HTTP policy")
        self._options = options
        self._provider = provider

    async def search(self, query: PaperQuery, cursor: str | None) -> ProviderPage:
        from scholarx.providers.osf import OSFProvider

        page = 1 if cursor is None else _offset(cursor)
        if page < 1:
            raise ProviderFailure("provider_failed")
        count = min(query.page_bound, 100)
        params = {"filter[title,description]": query.query, "page[size]": count, "page": page}
        if self._provider == "psyarxiv":
            params["filter[provider]"] = "psyarxiv"
        try:
            data = await _json_page(self._options, "/preprints/", params)
            if not isinstance(data, dict) or not isinstance(data.get("data"), list) or len(data["data"]) > count:
                raise ValueError("invalid OSF page")
            links = data.get("links")
            if not isinstance(links, dict) or "next" not in links:
                raise ValueError("missing OSF pagination")
            parser = OSFProvider(provider_id=self._provider)
            records = tuple(_osf_record(item, parser, self._provider) for item in data["data"])
            continuation = str(page + 1) if links["next"] else None
            return ProviderPage(records=records, cursor=continuation)
        except ProviderFailure:
            raise
        except (AirgapViolation, EgressPolicyError, PinnedEgressViolation):
            raise ProviderFailure("egress_denied") from None
        except Exception:
            raise ProviderFailure("provider_failed") from None


def _osf_record(item: Any, parser: Any, provider: str) -> ProviderPaper:
    paper = parser._parse(item)
    if paper is None or paper.id.endswith(":"):
        raise ValueError("missing paper identity")
    reference = ProviderReference(provider_id=provider, record_id=paper.id, original_id=paper.url or None)
    publication = date.fromisoformat(paper.published_date) if paper.published_date else None
    values = {
        "title": paper.title or None,
        "authors": tuple(paper.authors),
        "abstract": paper.abstract or None,
        "publication_date": publication,
    }
    evidence = {
        key: (FieldEvidence(provider_id=provider, source_id=paper.id, location="json:" + key),)
        for key, value in values.items()
        if value
    }
    return ProviderPaper(reference=reference, doi=paper.doi, field_provenance=evidence, **values)


class BiorxivPaperSource:
    """Search one stable 30-day bioRxiv or medRxiv interval page at a time."""

    def __init__(self, options: HttpClientOptions, provider: str) -> None:
        if provider not in {"biorxiv", "medrxiv"} or options.retry.max_attempts != 1 or not options.pin_egress:
            raise ValueError("invalid bioRxiv provider or governed HTTP policy")
        self._options = options
        self._provider = provider

    async def search(self, query: PaperQuery, cursor: str | None) -> ProviderPage:
        from datetime import UTC, datetime, timedelta

        from scholarx.providers.biorxiv import BiorxivProvider

        if cursor is None:
            end = datetime.now(UTC).date()
            start = end - timedelta(days=30)
            offset = 0
        else:
            try:
                start_text, end_text, position = cursor.split("|")
                start, end, offset = date.fromisoformat(start_text), date.fromisoformat(end_text), _offset(position)
                if end - start != timedelta(days=30) or end > datetime.now(UTC).date():
                    raise ValueError("invalid date interval")
            except ValueError:
                raise ProviderFailure("provider_failed") from None
        try:
            data = await _json_page(self._options, f"/details/{self._provider}/{start}/{end}/{offset}/json", {})
            if (
                not isinstance(data, dict)
                or not isinstance(data.get("collection"), list)
                or len(data["collection"]) > 100
            ):
                raise ValueError("invalid preprint page")
            messages = data.get("messages")
            if not isinstance(messages, list) or len(messages) != 1 or not isinstance(messages[0], dict):
                raise ValueError("missing preprint count")
            total = int(messages[0]["total"])
            if total < offset or total > 999_999_999:
                raise ValueError("invalid preprint count")
            parser = BiorxivProvider(server=self._provider)
            records = []
            scanned = 0
            for item in data["collection"]:
                record = _biorxiv_record(item, parser, self._provider)
                scanned += 1
                if (
                    query.query.casefold() in (record.title or "").casefold()
                    or query.query.casefold() in (record.abstract or "").casefold()
                ):
                    records.append(record)
                if len(records) == query.page_bound:
                    break
            next_offset = offset + scanned
            if next_offset > total:
                raise ValueError("preprint count is inconsistent")
            if next_offset < total and scanned == 0:
                raise ValueError("preprint cursor did not advance")
            continuation = f"{start}|{end}|{next_offset}" if next_offset < total else None
            return ProviderPage(records=tuple(records), cursor=continuation)
        except ProviderFailure:
            raise
        except (AirgapViolation, EgressPolicyError, PinnedEgressViolation):
            raise ProviderFailure("egress_denied") from None
        except Exception:
            raise ProviderFailure("provider_failed") from None


def _biorxiv_record(item: Any, parser: Any, provider: str) -> ProviderPaper:
    if not isinstance(item, dict):
        raise ValueError("invalid preprint")
    paper = parser._parse_paper(item)
    if paper is None or not paper.id:
        raise ValueError("missing paper identity")
    reference = ProviderReference(provider_id=provider, record_id=paper.id, original_id=paper.url or None)
    publication = date.fromisoformat(paper.published_date) if paper.published_date else None
    version = item.get("version")
    if version is not None and (not isinstance(version, str) or not version.isascii() or not version.isdecimal()):
        raise ValueError("invalid preprint version")
    offers = (
        ()
        if not paper.pdf_url
        else (DocumentOffer(provider_id=provider, url=paper.pdf_url, media_type="application/pdf"),)
    )
    values = {
        "title": paper.title or None,
        "authors": tuple(paper.authors),
        "abstract": paper.abstract or None,
        "publication_date": publication,
    }
    evidence = {
        key: (FieldEvidence(provider_id=provider, source_id=paper.id, location="json:" + key),)
        for key, value in values.items()
        if value
    }
    return ProviderPaper(
        reference=reference,
        doi=paper.doi,
        revision="v" + version if version else None,
        document_offers=offers,
        field_provenance=evidence,
        **values,
    )


class PmcPaperSource:
    """One PubMed search page and its summaries under one held quota slot."""

    def __init__(self, options: HttpClientOptions, quota: PaperQuotaPolicy) -> None:
        if quota.provider_id != "pmc" or options.retry.max_attempts != 1 or not options.pin_egress:
            raise ValueError("invalid PMC quota or governed HTTP policy")
        self._options = options
        self.quota_policy = quota
        self._spacing = quota.minimum_spacing_ns / 1_000_000_000

    async def search(self, query: PaperQuery, cursor: str | None) -> ProviderPage:
        import anyio

        from scholarx.providers.pmc import _parse_pmc_article

        offset = _offset(cursor)
        count = min(query.page_bound, 50)
        try:
            search = await _json_page(
                self._options,
                "/esearch.fcgi",
                {
                    "db": "pubmed",
                    "term": query.query,
                    "retmode": "json",
                    "retstart": offset,
                    "retmax": count,
                    "sort": "relevance",
                },
            )
            found = search["esearchresult"]
            ids = found["idlist"]
            total = int(found["count"])
            if (
                not isinstance(ids, list)
                or len(ids) > count
                or any(not isinstance(i, str) or not i.isascii() or not i.isdecimal() for i in ids)
                or total < offset + len(ids)
                or (not ids and offset < total)
            ):
                raise ValueError("invalid PubMed search page")
            if not ids:
                return ProviderPage()
            await anyio.sleep(self._spacing)
            detail = await _json_page(
                self._options, "/esummary.fcgi", {"db": "pubmed", "id": ",".join(ids), "retmode": "json"}
            )
            result = detail["result"]
            if result.get("uids") != ids:
                raise ValueError("incomplete PubMed summaries")
            records = tuple(_pmc_record(_parse_pmc_article(pmid, result[pmid])) for pmid in ids)
            next_offset = offset + len(ids)
            return ProviderPage(records=records, cursor=str(next_offset) if next_offset < total else None)
        except ProviderFailure:
            raise
        except (AirgapViolation, EgressPolicyError, PinnedEgressViolation):
            raise ProviderFailure("egress_denied") from None
        except Exception:
            raise ProviderFailure("provider_failed") from None


def _pmc_record(paper: Any) -> ProviderPaper:
    if paper is None or not paper.id:
        raise ValueError("missing PubMed identity")
    reference = ProviderReference(provider_id="pmc", record_id=paper.id, original_id=paper.url or None)
    try:
        publication = date.fromisoformat(paper.published_date) if paper.published_date else None
    except ValueError:
        publication = None
    offers = (
        ()
        if not paper.pdf_url
        else (DocumentOffer(provider_id="pmc", url=paper.pdf_url, media_type="application/pdf"),)
    )
    values = {
        "title": paper.title or None,
        "authors": tuple(paper.authors),
        "abstract": paper.abstract or None,
        "publication_date": publication,
    }
    evidence = {
        key: (FieldEvidence(provider_id="pmc", source_id=paper.id, location="json:" + key),)
        for key, value in values.items()
        if value
    }
    return ProviderPaper(
        reference=reference, doi=paper.doi, document_offers=offers, field_provenance=evidence, **values
    )
