#!/usr/bin/env python3
"""Re-download missing PDFs with proper rate limiting."""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from scholarx.api_client import ScholarXClient
from scholarx.models import Paper, PaperSource

OUTPUT_DIR = Path("/home/apps/workspace/scholarx_papers/batch_30")
DOWNLOAD_DELAY = 3.5  # seconds between downloads
MAX_RETRIES = 3
RETRY_BACKOFF = [5, 10, 20]


async def main():
    # Load metadata for all accepted papers
    meta_path = OUTPUT_DIR / "papers_metadata.json"
    papers_data = json.loads(meta_path.read_text())

    client = ScholarXClient(
        sources=[PaperSource.ARXIV],
        storage_dir=str(OUTPUT_DIR / "pdfs"),
    )

    # Check which PDFs are missing
    missing = []
    for pd in papers_data:
        paper = Paper(**pd)
        local = client.storage.get_local_path(paper.id)
        if not local or not local.exists():
            missing.append(paper)

    if not missing:
        print("✅ All PDFs already downloaded!")
        return

    print(f"📥 Re-downloading {len(missing)} missing PDFs with rate limiting...")
    print(f"   Estimated time: ~{len(missing) * DOWNLOAD_DELAY:.0f}s")
    downloaded = 0
    failed = []

    for i, paper in enumerate(missing, 1):
        for attempt in range(MAX_RETRIES):
            try:
                if i > 1 or attempt > 0:
                    delay = DOWNLOAD_DELAY if attempt == 0 else RETRY_BACKOFF[attempt]
                    print(f"   ⏳ Waiting {delay}s (rate limit)...")
                    await asyncio.sleep(delay)

                path = await client.download_paper(paper)
                if path:
                    downloaded += 1
                    print(f"  ✅ [{i}/{len(missing)}] {paper.title[:60]}...")
                    break
                else:
                    print(f"  ⚠️  [{i}/{len(missing)}] No PDF URL: {paper.id}")
                    break
            except Exception as e:
                if attempt < MAX_RETRIES - 1:
                    print(f"  🔄 [{i}/{len(missing)}] Retry {attempt + 1}: {e}")
                else:
                    print(f"  ❌ [{i}/{len(missing)}] Failed: {e}")
                    failed.append(paper.title)

    total_pdfs = len(list((OUTPUT_DIR / "pdfs").glob("*.pdf")))
    print(f"\n✅ Done! Downloaded {downloaded}/{len(missing)} missing PDFs")
    print(f"   Total PDFs now: {total_pdfs}")
    if failed:
        print(f"   Still missing: {len(failed)}")


if __name__ == "__main__":
    asyncio.run(main())
