import asyncio
import os
from datetime import datetime, timedelta
from urllib.parse import urljoin

import aiohttp
from bs4 import BeautifulSoup


class TribuneScraper:
    LAST_SCRAPED_FILE = "data/last_scraped.txt"

    def __init__(self, start_url: str):
        self.base_url = start_url
        self.cutoff_date = self.last_scraped_date()
        self.latest_date = None
        self.visited = set()
        self.articles = []   # crawl ke articles yahan jama honge

    # ---------- Last scraped date ----------
    def last_scraped_date(self) -> datetime:
        # last_scraped.txt format: link|YYYY-MM-DD  (ek line per site)
        if os.path.exists(self.LAST_SCRAPED_FILE):
            with open(self.LAST_SCRAPED_FILE, encoding="utf-8") as f:
                for line in f:
                    if "|" not in line:
                        continue
                    link, date_str = line.strip().split("|", 1)
                    if link == self.base_url:
                        try:
                            return datetime.strptime(date_str, "%Y-%m-%d")
                        except ValueError:
                            break
        return datetime.now() - timedelta(days=1)

    def save_last_scraped_date(self, date: datetime):
        lines, found = [], False
        if os.path.exists(self.LAST_SCRAPED_FILE):
            with open(self.LAST_SCRAPED_FILE, encoding="utf-8") as f:
                for line in f:
                    if line.strip().startswith(self.base_url + "|"):
                        lines.append(f"{self.base_url}|{date.strftime('%Y-%m-%d')}\n")
                        found = True
                    else:
                        lines.append(line if line.endswith("\n") else line + "\n")
        if not found:
            lines.append(f"{self.base_url}|{date.strftime('%Y-%m-%d')}\n")

        with open(self.LAST_SCRAPED_FILE, "w", encoding="utf-8") as f:
            f.writelines(lines)

    def commit(self):
        """Quizzes ban jane ke baad main/runner isay call karta hai."""
        if self.latest_date:
            self.save_last_scraped_date(self.latest_date)

    # ---------- Helpers ----------
    def get_links(self, soup, current_url) -> set:
        links = set()
        for a in soup.find_all("a", href=True):
            full_url = urljoin(current_url, a["href"]).split("#")[0]
            if full_url.startswith(self.base_url):
                links.add(full_url)
        return links

    def is_valid(self, url: str) -> bool:
        return url.startswith(self.base_url) and "/story/" in url

    @staticmethod
    def parse_date(date_text: str):
        try:
            return datetime.strptime(date_text, "%B %d, %Y")
        except ValueError:
            return None

    # ---------- Article ----------
    def extract_article_data(self, soup, url) -> dict | None:
        try:
            # -------- DATE --------
            publish_date = None
            author_box = soup.find("div", class_="left-authorbox")
            if author_box:
                for span in reversed(author_box.find_all("span")):
                    text = span.get_text(strip=True)
                    if "," in text:
                        parsed = self.parse_date(text)
                        if parsed:
                            publish_date = datetime.combine(parsed.date(), datetime.min.time())
                        break

            if not publish_date or publish_date < self.cutoff_date:
                return None

            # -------- TITLE --------
            h1 = soup.find("h1")
            title = h1.get_text(strip=True) if h1 else ""

            # -------- CONTENT --------
            story_text = soup.find("span", class_="story-text")
            if not story_text:
                return None

            paragraphs = [p.get_text(strip=True) for p in story_text.find_all("p")]
            paragraphs = [p for p in paragraphs if p]
            if not paragraphs:
                return None

            if self.latest_date is None or publish_date > self.latest_date:
                self.latest_date = publish_date

            return {
                "title": title,
                "date": publish_date.strftime("%Y-%m-%d"),
                "url": url,
                "paragraphs": paragraphs,
            }

        except Exception as e:
            print(f"❌ Error extracting article: {e}")
            return None

    # ---------- Crawl ----------
    async def scrape_page(self, session, url) -> tuple[dict | None, set]:
        # Fetch one page; return (article or None, links found on the page)
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status != 200:
                    return None, set()

                html = await response.text()
                soup = BeautifulSoup(html, "html.parser")

                article = self.extract_article_data(soup, url) if self.is_valid(url) else None
                return article, self.get_links(soup, url)

        except Exception as e:
            print(f"⚠️ Error scraping {url}: {e}")
            return None, set()

    async def crawl(self):
        # Async generator: yields each article as soon as it is scraped
        print("Start URL:", self.base_url, "| CUTOFF DATE:", self.cutoff_date)

        queue = [self.base_url]
        async with aiohttp.ClientSession() as session:
            while queue:
                url = queue.pop(0)
                if url in self.visited:
                    continue
                self.visited.add(url)

                article, new_links = await self.scrape_page(session, url)
                queue.extend(new_links - self.visited)

                if article:
                    yield article          # caller processes it before we continue

                await asyncio.sleep(1)     # be polite to the server