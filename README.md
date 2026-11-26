# News Quiz Generator

Generates MCQ quizzes from the latest Pakistani and world news.

## Pipeline

Scrape → Classify (Llama 3) → Verify and generate MCQs (Gemini) → Save

| Stage | Tool | Output |
|---|---|---|
| Scrape | aiohttp, BeautifulSoup | Paragraphs from Express Tribune (Pakistan and World tabs, under 24 hours old) |
| Classify | Llama 3 via Ollama (local) | Political, Current Affairs, International (others skipped) |
| Quiz | Gemini | Facts and MCQs (invalid or illogical ones skipped) |
| Save | JSONL | `data/quizzes.jsonl` |

## Project structure

| Path | Purpose |
|---|---|
| `src/news_quiz_app/scrapers/` | News scrapers |
| `src/news_quiz_app/classifier/` | Paragraph classifier (Ollama) |
| `src/news_quiz_app/generator/` | Quiz generator (Gemini) |
| `src/news_quiz_app/processing/` | Cleaning and deduplication (planned) |
| `src/news_quiz_app/storage/` | Database storage (planned) |
| `config/` | `active_urls.txt` (sites to scrape) |
| `data/` | Generated files (git-ignored) |
| `scripts/` | Manual try-out scripts |
| `tests/` | Automated tests |

## Setup

| Step | Command |
|---|---|
| 1. Install [uv](https://docs.astral.sh/uv/) and [Ollama](https://ollama.com/) | |
| 2. Pull the model | `ollama pull llama3` |
| 3. Clone | `git clone https://github.com/imatiq/News-Quiz-Generator` |
| 4. Install dependencies | `cd News-Quiz-Generator && uv sync` |
| 5. Configure | `cp .env.example .env`, then add your Gemini API key |

## Run

Run from the project root:

```bash
PYTHONPATH=src uv run python -m news_quiz_app.main
```

## Development

| Command | Purpose |
|---|---|
| `uv run ruff check .` | Lint |
| `uv run pytest` | Tests |
| `uv run mypy src` | Type check |

## Roadmap

- [x] Phase 1: Repo hygiene
- [ ] Phase 2: Core pipeline (processing, storage)
- [ ] Phase 3: Tests
- [ ] Phase 4: CI (GitHub Actions)
- [ ] Phase 5: API and UI
- [ ] Phase 6: Docker
- [ ] Phase 7: Deployment