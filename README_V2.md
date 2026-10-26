# AI Tech Trend Archive v2
This is a **staged migration**, preserving the existing Threads version in `src/main.py`.
RSS and GitHub collection now use `src/archive_v2.py`. Threads is never collected.
The new workflow is manual-only: **no schedule, no Notion writes, no Telegram sends**.

For local tests:
```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python -m src.archive_v2
ARCHIVE_V2_MODE=live DRY_RUN=true python -m src.archive_v2
```
Data sources: `config/rss_sources.json`. The feeds are public Google News RSS searches, and the GitHub search API uses the Actions-provided `GITHUB_TOKEN`.

Deployment phases: sample dry run; live read-only dry run; approved manual Notion/Telegram run; repeat dedup test; *separately approved* daily 08:00 KST scheduler.
Existing integration test workflows can still write if manually started; do not run them inadvertently.
Notion IDs are derived from canonical URLs plus source type. Duplicate prevention is query-before-save and workflow concurrency, not an atomic Notion transaction.
