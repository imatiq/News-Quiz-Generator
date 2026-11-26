# News Quiz Generator

Scrapes news articles (Express Tribune), picks out the factual paragraphs with a local Llama 3 model, and turns them into multiple-choice quizzes with Gemini.

## Pipeline

| Step | What happens | Tool |
|------|--------------|------|
| 1 | Scrape new articles | `Scrappers/ExpressTribune.py` |
| 2 | Filter junk and low-fact paragraphs (no LLM) | `main.py` |
| 3 | Classify paragraphs into facts | Llama 3 (Ollama) |
| 4 | Generate MCQs | Gemini |
| 5 | Save to `quizzes.jsonl` | `main.py` |

Extras: duplicate protection (`paragraph_hash`), a cache of rejected paragraphs, a per-article quiz cap, and a Gemini rate limiter.

## Setup

```bash
git clone https://github.com/imatiq/News-Quiz-Generator.git
cd News-Quiz-Generator
uv sync
cp .env.example .env     # then add your API keys
```

Install [Ollama](https://ollama.com) and pull the model you use for classification (for example `ollama pull llama3`). For parallel classification, start Ollama with `OLLAMA_NUM_PARALLEL=3`.

## Run

```bash
cd src/NewsQuizApp
python main.py
```

It runs once an hour. Add the sites to scrape in `src/NewsQuizApp/active_urls.txt` (one URL per line).

## Settings (top of `main.py`)

| Setting | Meaning |
|---------|---------|
| `CLASSIFY_WORKERS` | Parallel Ollama calls |
| `MAX_QUIZZES_PER_ARTICLE` | Cap on Gemini calls per article |
| `MIN_FACT_SCORE` | Pre-filter strictness (0 = off) |
| `GEMINI_MIN_INTERVAL` | Seconds between Gemini calls |
| `INTERVAL_MINUTES` | Time between runs |

## Output

One quiz per line in `quizzes.jsonl`, with `title`, `date`, `source_url` and `paragraph_hash` added.

## Notes

- Never commit `.env`. Only `.env.example` belongs in the repo.
- Generated files (`quizzes.jsonl`, `rejected_hashes.txt`) are git-ignored.
