# Contributing to Job Scout

Thanks for your interest. This is primarily a personal-use tool, but contributions that improve reliability, add real job sources, or fix bugs are welcome.

## Local setup

```bash
git clone https://github.com/sakshi-suryawanshi/job-scout
cd job-scout

# Copy environment template and fill in your keys
cp .env.example .env

# Install dependencies
pip install -r requirements.txt

# Install Playwright browser (required for auto-apply)
playwright install chromium

# Run the UI
streamlit run app/main.py
```

## Running tests

```bash
# Unit tests only (no DB required)
pytest tests/unit/ -v

# Integration tests (requires live Supabase)
RUN_INTEGRATION_TESTS=1 pytest tests/integration/ -v

# Network smoke tests (hits real job boards)
RUN_NETWORK_TESTS=1 pytest tests/integration/ -v -k "network"
```

## Lint and type-check

```bash
ruff check job_scout/ tests/
mypy job_scout/core/ job_scout/enrichment/ --ignore-missing-imports
```

## Database migrations

```bash
python scripts/migrate.py --list    # show pending
python scripts/migrate.py           # apply all pending
python scripts/migrate.py --dry-run # print SQL without running
```

## How the pipeline works

```
Discovery (stage 1) → Scrape (2) → Enrich (3) → Classify (4)
→ Score (5) → Auto-apply (6) → Follow-ups (7) → Digest (8)
```

Run a single stage manually:

```bash
python -m job_scout.pipeline.daily_run --stages 2,5
```

## Adding a new job board

1. Create `job_scout/scraping/boards/my_board.py` with a `MyScraper` class that has `get_jobs() -> List[Dict]`.
2. Register it in `job_scout/scraping/boards/_orchestrator.py` → `_all_boards_registry()`.
3. Add it to `_DEFAULT_BOARDS` if it should be on by default.
4. Add a smoke test in `tests/integration/test_pipeline_e2e.py`.

## Adding a new ATS scraper

1. Create `job_scout/scraping/ats/my_ats.py` — model after `greenhouse.py`.
2. Export from `job_scout/scraping/ats/__init__.py`.
3. Add to `scrapers` dict and `url_patterns` in `job_scout/scraping/ats/_pipeline.py`.

## Pull requests

- Keep PRs small and focused — one feature or fix per PR.
- Add or update tests for anything that was broken before.
- Run `ruff check` and `pytest tests/unit/` before opening.
- Write a clear commit message following the existing `type(scope): description` convention.
