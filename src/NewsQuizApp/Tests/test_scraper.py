import asyncio
from datetime import datetime, timedelta
from NewsQuizApp.Scrappers.ExpressTribune import TribuneScraper

START_URL = "https://tribune.com.pk/"
MAX_ARTICLES = 2


async def main():
    scraper = TribuneScraper(START_URL)
    scraper.cutoff_date = datetime.now() - timedelta(days=3)   # override, last_scraped.txt untouched

    count = 0
    gen = scraper.crawl()
    async for article in gen:
        count += 1
        print(f"\n[{count}] {article['title']}")
        print("   date:", article["date"], "| paragraphs:", len(article["paragraphs"]))
        print("   url:", article["url"])
        print("   first paragraph:", article["paragraphs"][0][:100])
        if count >= MAX_ARTICLES:
            break
    await gen.aclose()
    print(f"\nGot {count} article(s). Visited {len(scraper.visited)} pages.")

asyncio.run(main())