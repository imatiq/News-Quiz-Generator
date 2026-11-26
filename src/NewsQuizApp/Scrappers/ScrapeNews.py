import asyncio
import os
import socket
from urllib.parse import urlparse
from Generator.QuizGenerator import AllModelsExhausted
from utils import log

class NewsRunner:
    def __init__(self, scrapers: dict, active_urls_file: str = "active_urls.txt"):
        self.scrapers = scrapers  # {"domain": ScraperClass}
        self.active_urls_file = active_urls_file
        self._active = []  # scrapers created in the current run
        self._failed = set()  # ids of scrapers that failed mid-crawl

    # ---------- public API ----------
    def run(self, on_article) -> int:
        # Sync entry point used by main.py
        return asyncio.run(self._run_all(on_article))

    def commit(self):
        # Save last-scraped dates only for scrapers that finished cleanly
        for scraper in self._active:
            if id(scraper) in self._failed:
                log(f"⏭️ Skipping commit for failed scraper: {type(scraper).__name__}")
                continue
            scraper.commit()

    # ---------- helpers ----------
    @staticmethod
    async def wait_for_internet(retry_delay: int = 10):
        # Block until an internet connection is available (without freezing the loop)
        while True:
            try:
                conn = await asyncio.to_thread(
                    socket.create_connection, ("8.8.8.8", 53), 3
                )
                conn.close()
                return
            except OSError:
                log(f"⚠️ No internet... retrying in {retry_delay} seconds")
                await asyncio.sleep(retry_delay)

    def fetch_active_urls(self) -> list[str]:
        # Read the list of site URLs to scrape (one per line)
        if not os.path.exists(self.active_urls_file):
            log(f"❌ {self.active_urls_file} not found.")
            return []
        with open(self.active_urls_file, "r", encoding="utf-8") as f:
            urls = [line.strip() for line in f if line.strip()]
        log(f"✅ Loaded {len(urls)} active URLs.")
        return urls

    @staticmethod
    def get_domain(url: str) -> str:
        # Domain without "www." (key of the scrapers dict)
        return urlparse(url).netloc.replace("www.", "")

    # ---------- internals ----------
    async def _run_one(self, scraper, domain: str, on_article) -> int:
        # Crawl one site; pass every article to on_article as soon as it is found
        total = 0
        try:
            async for article in scraper.crawl():
                # Blocking work (Ollama + Gemini) runs in a thread; we wait for it,
                # so the next article is scraped only after this one is done
                total += await asyncio.to_thread(on_article, article) or 0
            log(f"✅ {domain} finished")
        except AllModelsExhausted:
            raise  # let main.py stop the run and skip commit
        except Exception as e:
            self._failed.add(id(scraper))  # do NOT commit this scraper
            log(f"❌ Error in {domain}: {e}")
        return total

    async def _run_all(self, on_article) -> int:
        await self.wait_for_internet()
        self._active = []
        self._failed = set()
        total = 0
        # Sites run one after another so only one article is processed at a time
        for url in self.fetch_active_urls():
            domain = self.get_domain(url)
            scraper_cls = self.scrapers.get(domain)
            if not scraper_cls:
                log(f"⚠️ No scraper available for domain: {domain}")
                continue
            scraper = scraper_cls(url)  # new scraper on every run
            self._active.append(scraper)
            total += await self._run_one(scraper, domain, on_article)
        return total
