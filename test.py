import asyncio
from datetime import UTC

from scholarx.api_client import ScholarXClient
from scholarx.models import PaperSource, SearchQuery


async def main():
    client = ScholarXClient(sources=[PaperSource.ARXIV])
    sq = SearchQuery(
        query="artificial intelligence",
        sources=[PaperSource.ARXIV],
        categories=["cs.AI"],
        max_results=50,
        sort_by="date",
    )
    result = await client.search(sq)
    print(f"Found {len(result.papers)} papers")
    # let's count how many are from the last 24 hours
    from datetime import datetime, timedelta

    now = datetime.now(UTC)
    last_24h = 0
    for p in result.papers:
        # p.published_date is a string or datetime
        if isinstance(p.published_date, str):
            pd = datetime.fromisoformat(p.published_date.replace("Z", "+00:00"))
        else:
            pd = p.published_date
        if now - pd < timedelta(hours=24):
            last_24h += 1
    print(f"Last 24h papers: {last_24h}")


if __name__ == "__main__":
    asyncio.run(main())
