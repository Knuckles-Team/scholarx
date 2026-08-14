#!/usr/bin/python
"""PubMed Central (PMC) Paper Provider.

Uses the NCBI E-utilities API (https://eutils.ncbi.nlm.nih.gov/entrez/eutils)
for searching PubMed/PMC. Free access; optional API key for higher rate limits.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from ..models import Paper, PaperSource, SearchQuery
from .base import PaperProvider

logger = logging.getLogger(__name__)


class PMCProvider(PaperProvider):
    """PubMed Central provider using NCBI E-utilities."""

    source = PaperSource.PMC

    async def search(self, query: SearchQuery) -> list[Paper]:
        """Search PubMed/PMC for papers."""
        params = self._build_search_params(query)

        try:
            # Step 1: esearch to get PMIDs
            response = await self._get("/esearch.fcgi", params=params)
            data = response.json()
            id_list = data.get("esearchresult", {}).get("idlist", [])

            if not id_list:
                return []

            # Step 2: efetch to get full metadata
            return await self._fetch_details(id_list)
        except Exception as e:
            logger.error("PMC search failed: error_type=%s", type(e).__name__)
            return []

    async def get_paper(self, paper_id: str) -> Paper | None:
        """Retrieve a single paper by PMID or PMC ID."""
        clean_id = paper_id.replace("pmid:", "").replace("pmc:", "").replace("PMC", "")

        try:
            papers = await self._fetch_details([clean_id])
            return papers[0] if papers else None
        except Exception as e:
            logger.error("PMC paper retrieval failed: error_type=%s", type(e).__name__)
            return None

    async def get_recent(self, categories: list[str] | None = None, days: int = 1) -> list[Paper]:
        """Retrieve recently published papers from PubMed."""
        date_from = (datetime.now(tz=UTC) - timedelta(days=days)).strftime("%Y/%m/%d")
        date_to = datetime.now(tz=UTC).strftime("%Y/%m/%d")

        term = f"({date_from}[PDAT] : {date_to}[PDAT])"
        if categories:
            mesh_terms = " OR ".join(f'"{cat}"[MeSH]' for cat in categories)
            term = f"({mesh_terms}) AND {term}"

        params = {
            "db": "pubmed",
            "term": term,
            "retmax": 50,
            "retmode": "json",
            "sort": "pub_date",
        }
        if self._api_key:
            params["api_key"] = self._api_key

        try:
            response = await self._get("/esearch.fcgi", params=params)
            data = response.json()
            id_list = data.get("esearchresult", {}).get("idlist", [])
            if not id_list:
                return []
            return await self._fetch_details(id_list)
        except Exception as e:
            logger.error("Operation failed: error_type=%s", type(e).__name__)
            return []

    # ── Private Helpers ──────────────────────────────────────────────────

    def _build_search_params(self, query: SearchQuery) -> dict:
        """Build esearch parameters."""
        term = query.query
        if query.categories:
            mesh = " OR ".join(f'"{c}"[MeSH]' for c in query.categories)
            term = f"({term}) AND ({mesh})"
        if query.author:
            term = f"({term}) AND {query.author}[Author]"

        params = {
            "db": "pubmed",
            "term": term,
            "retmax": min(query.max_results, self.config.max_results_per_query),
            "retmode": "json",
            "sort": "relevance" if query.sort_by == "relevance" else "pub_date",
        }

        if query.date_from:
            params["mindate"] = query.date_from.replace("-", "/")
        if query.date_to:
            params["maxdate"] = query.date_to.replace("-", "/")
        if query.date_from or query.date_to:
            params["datetype"] = "pdat"

        if self._api_key:
            params["api_key"] = self._api_key

        return params

    async def _fetch_details(self, id_list: list[str]) -> list[Paper]:
        """Fetch full paper details using efetch + esummary."""
        ids = ",".join(id_list[:50])  # Cap at 50 per request
        params = {
            "db": "pubmed",
            "id": ids,
            "retmode": "json",
        }
        if self._api_key:
            params["api_key"] = self._api_key

        try:
            response = await self._get("/esummary.fcgi", params=params)
            data = response.json()
            result = data.get("result", {})

            papers = []
            for pmid in id_list:
                article = result.get(pmid, {})
                if not article or not isinstance(article, dict):
                    continue

                title = article.get("title", "").strip()
                if not title:
                    continue

                # Extract authors
                authors = []
                for author in article.get("authors", []):
                    name = author.get("name", "")
                    if name:
                        authors.append(name)

                # Extract DOI from article IDs
                doi = None
                for aid in article.get("articleids", []):
                    if aid.get("idtype") == "doi":
                        doi = aid.get("value")
                        break

                # PMC ID
                pmc_id = None
                for aid in article.get("articleids", []):
                    if aid.get("idtype") == "pmc":
                        pmc_id = aid.get("value")
                        break

                pub_date = article.get("pubdate", "")
                pub_date_clean = pub_date[:10] if pub_date else None

                pdf_url = None
                if pmc_id:
                    pdf_url = f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmc_id}/pdf/"

                papers.append(
                    Paper(
                        id=f"pmid:{pmid}",
                        source=PaperSource.PMC,
                        title=title,
                        authors=authors,
                        abstract="",  # esummary doesn't include abstract
                        categories=[],
                        published_date=pub_date_clean,
                        doi=doi,
                        url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                        pdf_url=pdf_url,
                        metadata={"pmid": pmid, "pmc_id": pmc_id},
                    )
                )

            return papers
        except Exception as e:
            logger.error("PMC detail retrieval failed: error_type=%s", type(e).__name__)
            return []
