from unittest.mock import AsyncMock, patch

import httpx
import pytest
import respx

from scholarx.models import Paper, PaperSource, SearchQuery, SourceConfig
from scholarx.providers.arxiv import ARXIV_CATEGORIES, ArxivProvider
from scholarx.providers.base import PaperProvider
from scholarx.providers.biorxiv import BiorxivProvider, MedrxivProvider
from scholarx.providers.osf import OSFProvider, PsyarxivProvider
from scholarx.providers.pmc import PMCProvider
from scholarx.providers.rss import RSSFeedProvider
from scholarx.providers.semantic_scholar import SemanticScholarProvider


# Concrete minimal class for testing base class features
class DummyProvider(PaperProvider):
    source = PaperSource.ARXIV

    async def search(self, query: SearchQuery) -> list[Paper]:
        return []

    async def get_paper(self, paper_id: str) -> Paper | None:
        return None

    async def get_recent(self, categories: list[str] | None = None, days: int = 1) -> list[Paper]:
        return []


# =========================================================================
# 1. Base PaperProvider Tests
# =========================================================================


@pytest.mark.asyncio
async def test_base_provider_api_key_resolution(monkeypatch):
    monkeypatch.setenv("ARXIV_API_KEY", "dummy-arxiv-key")
    # Base URL must be set in config
    config = SourceConfig(
        source=PaperSource.ARXIV,
        base_url="https://export.arxiv.org/api",
        requests_per_second=1.0,
        max_results_per_query=50,
        api_key_env="ARXIV_API_KEY",
    )
    provider = DummyProvider(config)
    assert provider._api_key == "dummy-arxiv-key"

    client = await provider._get_client()
    assert client.headers["Authorization"] == "Bearer dummy-arxiv-key"
    assert await provider.get_categories() == []


@pytest.mark.asyncio
async def test_base_provider_rate_limiting():
    config = SourceConfig(
        source=PaperSource.ARXIV,
        base_url="https://example.com/api",
        requests_per_second=10.0,  # 0.1s interval
        max_results_per_query=50,
    )
    provider = DummyProvider(config)

    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        # First request sets _last_request_time
        await provider._wait_for_rate_limit()
        mock_sleep.assert_not_called()

        # Second request immediate should trigger sleep
        await provider._wait_for_rate_limit()
        mock_sleep.assert_called_once()
        # Verify sleep duration is close to 0.1s
        args, kwargs = mock_sleep.call_args
        assert args[0] > 0
        assert args[0] <= 0.1


@respx.mock
@pytest.mark.asyncio
async def test_base_provider_request_success():
    respx.get("https://example.com/api/test").mock(return_value=httpx.Response(200, json={"status": "ok"}))

    config = SourceConfig(
        source=PaperSource.ARXIV,
        base_url="https://example.com/api",
        requests_per_second=10.0,
        max_results_per_query=50,
    )
    provider = DummyProvider(config)

    # Bypass sleep for rate limits to keep test instant
    with patch("asyncio.sleep", new_callable=AsyncMock):
        response = await provider._get("/test")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


@respx.mock
@pytest.mark.asyncio
async def test_base_provider_429_retry():
    route = respx.get("https://example.com/api/test")
    # First response: 429
    # Second response: 200
    route.side_effect = [
        httpx.Response(429, headers={"Retry-After": "1"}),
        httpx.Response(200, json={"status": "recovered"}),
    ]

    config = SourceConfig(
        source=PaperSource.ARXIV,
        base_url="https://example.com/api",
        requests_per_second=10.0,
        max_results_per_query=50,
    )
    provider = DummyProvider(config)

    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        response = await provider._get("/test")
        assert response.status_code == 200
        assert response.json() == {"status": "recovered"}
        # Should sleep for retry duration (1 second) plus any rate limit wait
        mock_sleep.assert_any_call(1)


@respx.mock
@pytest.mark.asyncio
async def test_base_provider_429_retry_exhausted():
    route = respx.get("https://example.com/api/test")
    route.mock(return_value=httpx.Response(429, headers={"Retry-After": "1"}))

    config = SourceConfig(
        source=PaperSource.ARXIV,
        base_url="https://example.com/api",
        requests_per_second=10.0,
        max_results_per_query=50,
    )
    provider = DummyProvider(config)

    with patch("asyncio.sleep", new_callable=AsyncMock):
        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            await provider._get("/test")
        assert exc_info.value.response.status_code == 429


# =========================================================================
# 2. ArxivProvider Tests
# =========================================================================

ARXIV_XML_MOCK = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/2605.12345v1</id>
    <title>   Test arXiv Title
    With Newline </title>
    <summary>  Test summary with
    newline. </summary>
    <published>2026-05-22T00:00:00Z</published>
    <updated>2026-05-22T12:00:00Z</updated>
    <author><name>Alice Smith</name></author>
    <author><name>Bob Jones</name></author>
    <category term="cs.AI"/>
    <category term="cs.MA"/>
    <arxiv:doi>10.1234/testdoi</arxiv:doi>
    <link title="pdf" href="http://arxiv.org/pdf/2605.12345v1" rel="related" type="application/pdf"/>
  </entry>
</feed>
"""


@respx.mock
@pytest.mark.asyncio
async def test_arxiv_provider_search():
    respx.get("https://export.arxiv.org/api/query").mock(return_value=httpx.Response(200, content=ARXIV_XML_MOCK))

    provider = ArxivProvider()
    query = SearchQuery(query="multi-agent", max_results=1)

    with patch("asyncio.sleep", new_callable=AsyncMock):
        papers = await provider.search(query)
        assert len(papers) == 1
        paper = papers[0]
        assert paper.id == "arxiv:2605.12345v1"
        assert paper.title == "Test arXiv Title     With Newline"
        assert paper.abstract == "Test summary with     newline."
        assert paper.authors == ["Alice Smith", "Bob Jones"]
        assert paper.categories == ["cs.AI", "cs.MA"]
        assert paper.published_date == "2026-05-22"
        assert paper.updated_date == "2026-05-22"
        assert paper.doi == "10.1234/testdoi"
        assert paper.url == "https://arxiv.org/abs/2605.12345v1"
        assert paper.pdf_url == "http://arxiv.org/pdf/2605.12345v1"


@respx.mock
@pytest.mark.asyncio
async def test_arxiv_provider_get_paper():
    respx.get("https://export.arxiv.org/api/query").mock(return_value=httpx.Response(200, content=ARXIV_XML_MOCK))

    provider = ArxivProvider()
    with patch("asyncio.sleep", new_callable=AsyncMock):
        paper = await provider.get_paper("arxiv:2605.12345v1")
        assert paper is not None
        assert paper.id == "arxiv:2605.12345v1"


@respx.mock
@pytest.mark.asyncio
async def test_arxiv_provider_get_recent_rss():
    rss_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0" xmlns:arxiv="http://arxiv.org/schemas/atom" xmlns:dc="http://purl.org/dc/elements/1.1/">
      <channel>
        <title>arXiv cs.AI updates</title>
        <pubDate>Fri, 22 May 2026 00:00:00 EST</pubDate>
        <item>
          <title>RSS Test Title</title>
          <link>https://arxiv.org/abs/2605.12345</link>
          <description>arXiv:2605.12345v1 Announce Type: new&#10;Abstract: RSS Abstract Text</description>
          <pubDate>Fri, 22 May 2026 00:00:00 EST</pubDate>
          <arxiv:announce_type>new</arxiv:announce_type>
          <category>cs.AI</category>
          <dc:creator>Author 1, Author 2</dc:creator>
          <arxiv:DOI>10.1234/rssdoi</arxiv:DOI>
        </item>
      </channel>
    </rss>
    """
    respx.get("https://rss.arxiv.org/rss/cs.ai").mock(return_value=httpx.Response(200, content=rss_xml))

    provider = ArxivProvider()
    with patch("asyncio.sleep", new_callable=AsyncMock):
        papers = await provider.get_recent(categories=["cs.AI"], days=1, use_rss=True)
        assert len(papers) == 1
        assert papers[0].title == "RSS Test Title"
        assert papers[0].id == "arxiv:2605.12345"


@respx.mock
@pytest.mark.asyncio
async def test_arxiv_provider_get_recent_fallback():
    # If RSS fails, it should fallback to API query
    respx.get("https://rss.arxiv.org/rss/cs.ai").mock(return_value=httpx.Response(500))
    respx.get("https://export.arxiv.org/api/query").mock(return_value=httpx.Response(200, content=ARXIV_XML_MOCK))

    provider = ArxivProvider()
    with patch("asyncio.sleep", new_callable=AsyncMock):
        papers = await provider.get_recent(categories=["cs.AI"], days=1, use_rss=True)
        assert len(papers) == 1
        assert papers[0].id == "arxiv:2605.12345v1"


@respx.mock
@pytest.mark.asyncio
async def test_rss_fetch_arxiv_daily_concurrent_partial_failure():
    # Multiple category feeds are fetched concurrently; one failing feed (500)
    # must not sink the others — the healthy feeds still aggregate.
    def _feed(arxiv_id: str, title: str, cat: str) -> str:
        return f"""<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0" xmlns:arxiv="http://arxiv.org/schemas/atom" xmlns:dc="http://purl.org/dc/elements/1.1/">
          <channel>
            <title>arXiv {cat} updates</title>
            <pubDate>Fri, 22 May 2026 00:00:00 EST</pubDate>
            <item>
              <title>{title}</title>
              <link>https://arxiv.org/abs/{arxiv_id}</link>
              <description>arXiv:{arxiv_id}v1 Announce Type: new&#10;Abstract: Abs</description>
              <arxiv:announce_type>new</arxiv:announce_type>
              <category>{cat}</category>
              <dc:creator>Author</dc:creator>
            </item>
          </channel>
        </rss>
        """

    respx.get("https://rss.arxiv.org/rss/cs.ai").mock(
        return_value=httpx.Response(200, content=_feed("2605.00001", "AI Paper", "cs.AI"))
    )
    respx.get("https://rss.arxiv.org/rss/cs.lg").mock(return_value=httpx.Response(500))
    respx.get("https://rss.arxiv.org/rss/cs.se").mock(
        return_value=httpx.Response(200, content=_feed("2605.00002", "SE Paper", "cs.SE"))
    )

    provider = RSSFeedProvider(pre_filter_categories=False)
    result = await provider.fetch_arxiv_daily(["cs.AI", "cs.LG", "cs.SE"])

    titles = {p.title for p in result.papers}
    assert titles == {"AI Paper", "SE Paper"}


@pytest.mark.asyncio
async def test_arxiv_provider_get_categories():
    provider = ArxivProvider()
    cats = await provider.get_categories()
    assert len(cats) == len(ARXIV_CATEGORIES)
    assert cats[0]["id"] == "cs.AI"


# =========================================================================
# 3. BiorxivProvider & MedrxivProvider Tests
# =========================================================================

BIORXIV_MOCK_JSON = {
    "collection": [
        {
            "doi": "10.1101/2026.05.123456",
            "title": "Biorxiv Test Paper",
            "authors": "Author A; Author B",
            "category": "Bioinformatics",
            "date": "2026-05-22",
            "abstract": "Biorxiv Abstract Content",
        }
    ]
}


@respx.mock
@pytest.mark.asyncio
async def test_biorxiv_provider_search():
    respx.get("https://api.biorxiv.org/details/biorxiv/2026-04-22/2026-05-22/0/50").mock(
        return_value=httpx.Response(200, json=BIORXIV_MOCK_JSON)
    )

    provider = BiorxivProvider()
    query = SearchQuery(query="Biorxiv", date_from="2026-04-22", date_to="2026-05-22", max_results=5)

    with patch("asyncio.sleep", new_callable=AsyncMock):
        papers = await provider.search(query)
        assert len(papers) == 1
        assert papers[0].id == "biorxiv:10.1101/2026.05.123456"
        assert papers[0].title == "Biorxiv Test Paper"
        assert papers[0].authors == ["Author A", "Author B"]
        assert papers[0].categories == ["Bioinformatics"]
        assert papers[0].published_date == "2026-05-22"
        assert papers[0].abstract == "Biorxiv Abstract Content"


@respx.mock
@pytest.mark.asyncio
async def test_biorxiv_provider_get_paper():
    respx.get("https://api.biorxiv.org/details/biorxiv/10.1101/2026.05.123456").mock(
        return_value=httpx.Response(200, json=BIORXIV_MOCK_JSON)
    )

    provider = BiorxivProvider()
    with patch("asyncio.sleep", new_callable=AsyncMock):
        paper = await provider.get_paper("biorxiv:10.1101/2026.05.123456")
        assert paper is not None
        assert paper.id == "biorxiv:10.1101/2026.05.123456"


@respx.mock
@pytest.mark.asyncio
async def test_biorxiv_provider_get_recent():
    respx.get(url__regex=r"https://api.biorxiv.org/details/biorxiv/.*").mock(
        return_value=httpx.Response(200, json=BIORXIV_MOCK_JSON)
    )

    provider = BiorxivProvider()
    with patch("asyncio.sleep", new_callable=AsyncMock):
        papers = await provider.get_recent(categories=["Bioinformatics"], days=1)
        assert len(papers) == 1
        assert papers[0].title == "Biorxiv Test Paper"


@respx.mock
@pytest.mark.asyncio
async def test_medrxiv_provider():
    respx.get("https://api.biorxiv.org/details/medrxiv/2026-04-22/2026-05-22/0/50").mock(
        return_value=httpx.Response(
            200,
            json={
                "collection": [
                    {
                        "doi": "10.1101/2026.05.654321",
                        "title": "Medrxiv Test Paper",
                        "authors": "Dr. House",
                        "category": "Epidemiology",
                        "date": "2026-05-22",
                        "abstract": "Medrxiv Abstract",
                    }
                ]
            },
        )
    )

    provider = MedrxivProvider()
    query = SearchQuery(
        query="Medrxiv",
        date_from="2026-04-22",
        date_to="2026-05-22",
    )

    with patch("asyncio.sleep", new_callable=AsyncMock):
        papers = await provider.search(query)
        assert len(papers) == 1
        assert papers[0].id == "medrxiv:10.1101/2026.05.654321"
        assert papers[0].source == PaperSource.MEDRXIV


# =========================================================================
# 4. OSFProvider & PsyarxivProvider Tests
# =========================================================================

OSF_MOCK_JSON = {
    "data": [
        {
            "id": "osf123",
            "attributes": {
                "title": "OSF Preprint Title",
                "provider": "osf",
                "date_created": "2026-05-22T00:00:00.000000Z",
                "date_modified": "2026-05-22T12:00:00.000000Z",
                "description": "OSF Description text",
                "tags": ["AI", "Psychology"],
                "doi": "10.31219/osf.io/osf123",
            },
        }
    ]
}


@respx.mock
@pytest.mark.asyncio
async def test_osf_provider_search():
    respx.get("https://api.osf.io/v2/preprints/").mock(return_value=httpx.Response(200, json=OSF_MOCK_JSON))

    provider = OSFProvider()
    query = SearchQuery(query="Preprint", max_results=5)

    with patch("asyncio.sleep", new_callable=AsyncMock):
        papers = await provider.search(query)
        assert len(papers) == 1
        assert papers[0].id == "osf:osf123"
        assert papers[0].title == "OSF Preprint Title"
        assert papers[0].abstract == "OSF Description text"
        assert papers[0].categories == ["AI", "Psychology"]
        assert papers[0].published_date == "2026-05-22"
        assert papers[0].updated_date == "2026-05-22"
        assert papers[0].doi == "10.31219/osf.io/osf123"


@respx.mock
@pytest.mark.asyncio
async def test_osf_provider_get_paper():
    respx.get("https://api.osf.io/v2/preprints/osf123/").mock(
        return_value=httpx.Response(200, json={"data": OSF_MOCK_JSON["data"][0]})
    )

    provider = OSFProvider()
    with patch("asyncio.sleep", new_callable=AsyncMock):
        paper = await provider.get_paper("osf:osf123")
        assert paper is not None
        assert paper.id == "osf:osf123"


@respx.mock
@pytest.mark.asyncio
async def test_osf_provider_get_recent():
    respx.get("https://api.osf.io/v2/preprints/").mock(return_value=httpx.Response(200, json=OSF_MOCK_JSON))

    provider = OSFProvider()
    with patch("asyncio.sleep", new_callable=AsyncMock):
        papers = await provider.get_recent(days=1)
        assert len(papers) == 1
        assert papers[0].title == "OSF Preprint Title"


@respx.mock
@pytest.mark.asyncio
async def test_psyarxiv_provider():
    respx.get("https://api.osf.io/v2/preprints/").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "psy123",
                        "attributes": {
                            "title": "PsyArXiv Paper",
                            "provider": "psyarxiv",
                            "date_created": "2026-05-22T00:00:00Z",
                            "description": "Psy Description",
                        },
                    }
                ]
            },
        )
    )

    provider = PsyarxivProvider()
    query = SearchQuery(query="Psy")

    with patch("asyncio.sleep", new_callable=AsyncMock):
        papers = await provider.search(query)
        assert len(papers) == 1
        assert papers[0].id == "psyarxiv:psy123"
        assert papers[0].source == PaperSource.PSYARXIV


# =========================================================================
# 5. PMCProvider Tests
# =========================================================================

PMC_SEARCH_MOCK = {"esearchresult": {"idlist": ["98765432"]}}

PMC_SUMMARY_MOCK = {
    "result": {
        "98765432": {
            "title": "PMC Test Article",
            "authors": [{"name": "Dr. Watson"}, {"name": "Sherlock Holmes"}],
            "articleids": [
                {"idtype": "doi", "value": "10.1093/pmc/98765432"},
                {"idtype": "pmc", "value": "PMC9876543"},
            ],
            "pubdate": "2026-05-22",
        }
    }
}


@respx.mock
@pytest.mark.asyncio
async def test_pmc_provider_search():
    respx.get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi").mock(
        return_value=httpx.Response(200, json=PMC_SEARCH_MOCK)
    )
    respx.get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi").mock(
        return_value=httpx.Response(200, json=PMC_SUMMARY_MOCK)
    )

    provider = PMCProvider()
    query = SearchQuery(query="Agent", max_results=5)

    with patch("asyncio.sleep", new_callable=AsyncMock):
        papers = await provider.search(query)
        assert len(papers) == 1
        assert papers[0].id == "pmid:98765432"
        assert papers[0].title == "PMC Test Article"
        assert papers[0].authors == ["Dr. Watson", "Sherlock Holmes"]
        assert papers[0].published_date == "2026-05-22"
        assert papers[0].doi == "10.1093/pmc/98765432"
        assert papers[0].pdf_url == "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC9876543/pdf/"


@respx.mock
@pytest.mark.asyncio
async def test_pmc_provider_get_paper():
    respx.get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi").mock(
        return_value=httpx.Response(200, json=PMC_SUMMARY_MOCK)
    )

    provider = PMCProvider()
    with patch("asyncio.sleep", new_callable=AsyncMock):
        paper = await provider.get_paper("pmid:98765432")
        assert paper is not None
        assert paper.id == "pmid:98765432"


@respx.mock
@pytest.mark.asyncio
async def test_pmc_provider_get_recent():
    respx.get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi").mock(
        return_value=httpx.Response(200, json=PMC_SEARCH_MOCK)
    )
    respx.get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi").mock(
        return_value=httpx.Response(200, json=PMC_SUMMARY_MOCK)
    )

    provider = PMCProvider()
    with patch("asyncio.sleep", new_callable=AsyncMock):
        papers = await provider.get_recent(days=1)
        assert len(papers) == 1
        assert papers[0].title == "PMC Test Article"


# =========================================================================
# 6. SemanticScholarProvider Tests
# =========================================================================

S2_MOCK_JSON = {
    "data": [
        {
            "paperId": "s2id123",
            "externalIds": {"DOI": "10.1145/3308558.3313411", "ArXiv": "2605.55555", "PubMed": "999999"},
            "title": "Semantic Scholar Paper",
            "abstract": "S2 Abstract Text",
            "authors": [{"name": "Alice Cooper"}, {"name": "Bob Dylan"}],
            "fieldsOfStudy": ["Computer Science"],
            "openAccessPdf": {"url": "https://s2.com/openaccess.pdf"},
            "publicationDate": "2026-05-22",
            "url": "https://www.semanticscholar.org/paper/s2id123",
            "citationCount": 42,
            "referenceCount": 100,
        }
    ]
}


@respx.mock
@pytest.mark.asyncio
async def test_s2_provider_search():
    respx.get("https://api.semanticscholar.org/graph/v1/paper/search").mock(
        return_value=httpx.Response(200, json=S2_MOCK_JSON)
    )

    provider = SemanticScholarProvider()
    query = SearchQuery(query="Machine learning", date_from="2026-01-01", max_results=5)

    with patch("asyncio.sleep", new_callable=AsyncMock):
        papers = await provider.search(query)
        assert len(papers) == 1
        assert papers[0].id == "s2:s2id123"
        assert papers[0].title == "Semantic Scholar Paper"
        assert papers[0].abstract == "S2 Abstract Text"
        assert papers[0].authors == ["Alice Cooper", "Bob Dylan"]
        assert papers[0].categories == ["Computer Science"]
        assert papers[0].published_date == "2026-05-22"
        assert papers[0].doi == "10.1145/3308558.3313411"
        assert papers[0].pdf_url == "https://s2.com/openaccess.pdf"
        assert papers[0].citation_count == 42
        assert papers[0].reference_count == 100


@respx.mock
@pytest.mark.asyncio
async def test_s2_provider_get_paper():
    respx.get("https://api.semanticscholar.org/graph/v1/paper/s2id123").mock(
        return_value=httpx.Response(200, json=S2_MOCK_JSON["data"][0])
    )

    provider = SemanticScholarProvider()
    with patch("asyncio.sleep", new_callable=AsyncMock):
        paper = await provider.get_paper("s2:s2id123")
        assert paper is not None
        assert paper.id == "s2:s2id123"


@respx.mock
@pytest.mark.asyncio
async def test_s2_provider_get_recent():
    respx.get("https://api.semanticscholar.org/graph/v1/paper/search").mock(
        return_value=httpx.Response(200, json=S2_MOCK_JSON)
    )

    provider = SemanticScholarProvider()
    with patch("asyncio.sleep", new_callable=AsyncMock):
        papers = await provider.get_recent(days=1)
        assert len(papers) == 1
        assert papers[0].title == "Semantic Scholar Paper"


# =========================================================================
# 7. RSSFeedProvider & Generic RSS Parsing Tests
# =========================================================================


@respx.mock
@pytest.mark.asyncio
async def test_rss_feed_provider_full_feed():
    rss_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0" xmlns:arxiv="http://arxiv.org/schemas/atom" xmlns:dc="http://purl.org/dc/elements/1.1/">
      <channel>
        <title>arXiv cs.MA updates</title>
        <pubDate>Fri, 22 May 2026 00:00:00 EST</pubDate>
        <item>
          <title>Multi-Agent Systems</title>
          <link>https://arxiv.org/abs/2605.98765</link>
          <description>arXiv:2605.98765v1 Announce Type: new&#10;Abstract: Abstract CS.MA text</description>
          <pubDate>Fri, 22 May 2026 00:00:00 EST</pubDate>
          <arxiv:announce_type>new</arxiv:announce_type>
          <category>cs.MA</category>
          <dc:creator>John Doe, Jane Doe</dc:creator>
          <arxiv:DOI>10.1234/csma</arxiv:DOI>
        </item>
        <item>
          <title>Irrelevant Quantum Physics</title>
          <link>https://arxiv.org/abs/2605.11111</link>
          <description>arXiv:2605.11111v1 Announce Type: new&#10;Abstract: Abstract Quant text</description>
          <pubDate>Fri, 22 May 2026 00:00:00 EST</pubDate>
          <arxiv:announce_type>new</arxiv:announce_type>
          <category>quant-ph</category>
          <dc:creator>Quantum Physicist</dc:creator>
        </item>
        <item>
          <title>Announce Type Replace Paper</title>
          <link>https://arxiv.org/abs/2605.22222</link>
          <description>arXiv:2605.22222v2 Announce Type: replace&#10;Abstract: Abstract Replace text</description>
          <pubDate>Fri, 22 May 2026 00:00:00 EST</pubDate>
          <arxiv:announce_type>replace</arxiv:announce_type>
          <category>cs.AI</category>
          <dc:creator>Updater Person</dc:creator>
        </item>
      </channel>
    </rss>
    """
    respx.get("https://rss.arxiv.org/rss/cs.ma").mock(return_value=httpx.Response(200, content=rss_xml))

    provider = RSSFeedProvider(pre_filter_categories=True)
    result = await provider.fetch_arxiv_daily(categories=["cs.MA"])

    assert len(result.papers) == 1
    paper = result.papers[0]
    assert paper.title == "Multi-Agent Systems"
    assert paper.id == "arxiv:2605.98765"
    assert paper.authors == ["John Doe", "Jane Doe"]
    assert paper.abstract == "Abstract CS.MA text"
    assert paper.announce_type == "new"

    # Verify counts
    assert result.total_items == 3
    assert result.new_count == 2
    assert result.replace_count == 1
    assert result.cross_count == 0


@pytest.mark.asyncio
async def test_rss_feed_provider_malformed_xml():
    provider = RSSFeedProvider()
    result = provider._parse_rss_feed("this is not XML", "cs.AI")
    assert len(result.papers) == 0
    assert result.total_items == 0


@pytest.mark.asyncio
async def test_rss_feed_provider_empty_channel():
    xml = "<?xml version='1.0'?><rss></rss>"
    provider = RSSFeedProvider()
    result = provider._parse_rss_feed(xml, "cs.AI")
    assert len(result.papers) == 0
