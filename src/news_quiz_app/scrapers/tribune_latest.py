import asyncio
from urllib.parse import urljoin

import aiohttp
from bs4 import BeautifulSoup

from news_quiz_app.scrapers.express_tribune import TribuneScraper


class TribuneLatestNewsScrapper(TribuneScraper):
    # Reuses date/title/paragraph extraction and last-scraped logic from TribuneScraper.
    # Only the crawl strategy differs: read the "latest" listing page, then open each story.

    LISTING_SELECTOR = "div.horiz-news3-caption a[href]"

    async def fetch(self, session, url) -> str | None:
        # Download one page; return its HTML or None on failure
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status != 200:
                    return None
                return await response.text()
        except Exception as e:
            print(f"⚠️ Error fetching {url}: {e}")
            return None

    def get_story_links(self, soup) -> list[str]:
        # Collect story links from the listing, keeping page order and removing duplicates
        links = []
        for a in soup.select(self.LISTING_SELECTOR):
            full_url = urljoin(self.base_url, a["href"]).split("#")[0]
            if "/story/" in full_url:
                links.append(full_url)
        return list(dict.fromkeys(links))

    async def crawl(self):
        # Async generator: yields each article as soon as it is scraped
        print("Latest news URL:", self.base_url, "| CUTOFF DATE:", self.cutoff_date)

        async with aiohttp.ClientSession() as session:
            html = await self.fetch(session, self.base_url)
            if not html:
                return

            links = self.get_story_links(BeautifulSoup(html, "html.parser"))
            print(f"Found {len(links)} story links")
            if not links:
                print("⚠️ No links found: check LISTING_SELECTOR")

            for url in links:
                if url in self.visited:
                    continue
                self.visited.add(url)

                story_html = await self.fetch(session, url)
                if story_html:
                    article = self.extract_article_data(BeautifulSoup(story_html, "html.parser"), url)
                    if article:
                        yield article          # caller processes it before we continue

                await asyncio.sleep(1)         # be polite to the server