import hashlib
import json
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from news_quiz_app.classifier.paragraph_classifier import paragraphClassifier
from news_quiz_app.generator.quiz_generator import AllModelsExhausted, quizGenerator
from news_quiz_app.scrapers.express_tribune import TribuneScraper
from news_quiz_app.scrapers.scrape_news import NewsRunner
from news_quiz_app.utils import log

QUIZ_FILE = "data/quizzes.jsonl"
REJECTED_FILE = "data/rejected_hashes.txt"   # paragraphs the classifier called irrelevant
INTERVAL_MINUTES = 60

# ---- speed settings (tune these) ----
CLASSIFY_WORKERS = 3             # parallel Ollama calls (also set OLLAMA_NUM_PARALLEL=3)
MAX_QUIZZES_PER_ARTICLE = 4      # cap Gemini calls per article
MIN_FACT_SCORE = 2               # pre-filter strictness (0 = off)
GEMINI_MIN_INTERVAL = 4.0        # seconds between Gemini calls (15 RPM -> 4.0)

# Create heavy objects once and reuse them on every run
clf = paragraphClassifier()
qg = quizGenerator()
runner = NewsRunner(
    scrapers={"tribune.com.pk": TribuneScraper},   # domain -> scraper class
    active_urls_file="config/active_urls.txt",
)


# ---------------- caches ----------------
def paragraph_hash(paragraph: str) -> str:
    return hashlib.md5(paragraph.strip().encode("utf-8")).hexdigest()


def load_seen() -> set:
    # (source_url, paragraph_hash) of quizzes already saved
    seen = set()
    if os.path.exists(QUIZ_FILE):
        with open(QUIZ_FILE, encoding="utf-8") as f:
            for line in f:
                try:
                    q = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if q.get("source_url") and q.get("paragraph_hash"):
                    seen.add((q["source_url"], q["paragraph_hash"]))
    return seen


def load_rejected() -> set:
    if not os.path.exists(REJECTED_FILE):
        return set()
    with open(REJECTED_FILE, encoding="utf-8") as f:
        return {line.strip() for line in f if line.strip()}


SEEN = load_seen()
REJECTED = load_rejected()
_reject_lock = threading.Lock()


def mark_rejected(h: str):
    with _reject_lock:
        if h in REJECTED:
            return
        REJECTED.add(h)
        with open(REJECTED_FILE, "a", encoding="utf-8") as f:
            f.write(h + "\n")


def save_quiz(quiz: dict):
    # Append one quiz per line (JSON Lines)
    with open(QUIZ_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(quiz, ensure_ascii=False) + "\n")


# ---------------- cheap filters (no LLM) ----------------
FACT_WORDS = re.compile(
    r"\b(said|announced|approved|signed|launched|declared|ordered|confirmed|"
    r"agreed|rejected|appointed|elected|killed|arrested|reported|according to|"
    r"billion|million|percent|per cent|minister|court|government|police|"
    r"parliament|bank|budget|president|prime minister)\b",
    re.IGNORECASE,
)


def fact_score(paragraph: str) -> int:
    # Rough "how factual is this paragraph" score
    score = 0
    if re.search(r"\d", paragraph):
        score += 1
    if re.search(r"\b(?:Rs|\$|USD|PKR)\s?\d|\d+\s?(?:%|percent|per cent|million|billion)", paragraph):
        score += 1
    score += min(len(FACT_WORDS.findall(paragraph)), 2)
    # proper nouns in the middle of sentences
    score += min(len(re.findall(r"(?<=[a-z,] )[A-Z][a-z]{2,}", paragraph)), 2)
    return score


def is_junk(paragraph: str) -> bool:
    # Skip headlines, "Read:" links, tweet embeds and mostly non-English text
    if len(paragraph.split()) < 10:
        return True
    if paragraph.lower().startswith("read:") or "pic.twitter.com" in paragraph:
        return True
    letters = [c for c in paragraph if c.isalpha()]
    return not letters or sum(c.isascii() for c in letters) / len(letters) < 0.8


# ---------------- Gemini rate limiter ----------------
class RateLimiter:
    # Sleeps only as long as needed, instead of a fixed time.sleep(2)
    def __init__(self, min_interval: float):
        self.min_interval = min_interval
        self._last = 0.0

    def wait(self):
        gap = time.monotonic() - self._last
        if gap < self.min_interval:
            time.sleep(self.min_interval - gap)
        self._last = time.monotonic()


gemini_limiter = RateLimiter(GEMINI_MIN_INTERVAL)


# ---------------- pipeline ----------------
def classify_one(item: tuple):
    # item = (paragraph, hash). Returns (paragraph, hash, result, ok)
    paragraph, h = item
    try:
        return paragraph, h, clf.classify(paragraph), True
    except Exception as e:
        log(f"⚠️ Classification failed: {e}")
        return paragraph, h, None, False


def process_article(article: dict) -> int:
    log(f"📰 Processing: {article['title']}")
    url = article["url"]

    # Step 1: cheap filters (junk, already done, already rejected, low fact score)
    candidates = []
    for paragraph in article["paragraphs"]:
        if is_junk(paragraph):
            continue
        h = paragraph_hash(paragraph)
        if (url, h) in SEEN or h in REJECTED:
            continue
        if fact_score(paragraph) < MIN_FACT_SCORE:
            continue
        candidates.append((paragraph, h))

    if not candidates:
        return 0

    # Most factual paragraphs first, so the cap keeps the best ones
    candidates.sort(key=lambda x: fact_score(x[0]), reverse=True)

    # Step 2: classify in parallel (Ollama)
    with ThreadPoolExecutor(max_workers=CLASSIFY_WORKERS) as pool:
        classified = list(pool.map(classify_one, candidates))

    relevant = []
    for _paragraph, h, result, ok in classified:
        if not ok:
            continue                 # failed: retry next run
        if not result:
            mark_rejected(h)         # irrelevant: never classify again
            continue
        relevant.append((h, result))

    # Step 3: generate quizzes (Gemini), capped and rate-limited
    saved = 0
    for h, result in relevant[:MAX_QUIZZES_PER_ARTICLE]:
        gemini_limiter.wait()
        try:
            quiz = qg.generate(result)
        except AllModelsExhausted:
            raise                    # quota finished: stop the whole run
        except Exception as e:
            log(f"⚠️ Quiz generation failed: {e}")
            continue

        if quiz:
            quiz["title"] = article["title"]
            quiz["date"] = article["date"]
            quiz["source_url"] = url
            quiz["paragraph_hash"] = h
            save_quiz(quiz)
            SEEN.add((url, h))
            saved += 1

    log(f"   ✅ {saved} quizzes | {len(candidates)} classified | {len(relevant)} relevant")
    return saved


def job():
    # One full run: scrape -> classify -> generate -> save -> commit
    try:
        log("🕷️ Starting run...")
        total = runner.run(on_article=process_article)
        log(f"🎯 Done: {total} quizzes saved")
        runner.commit()
    except AllModelsExhausted as e:
        log(f"⛔ Quota finished, last_scraped NOT updated: {e}")
    except Exception as e:
        log(f"❌ Job failed: {e}")


if __name__ == "__main__":
    log(f"⏳ Running every {INTERVAL_MINUTES} minute(s)")
    while True:
        job()
        log(f"😴 Next run in {INTERVAL_MINUTES} minute(s)")
        time.sleep(INTERVAL_MINUTES * 60)