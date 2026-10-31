# FIND API

FastAPI service for public water-location reports, comments, aggregate votes, and admin moderation.

## Run locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Set DATABASE_URL to a PostgreSQL database you can use.
uvicorn app.main:app --reload --port 8000
```

The FastAPI lifespan creates the `water_reports` and `comments` tables, renames the legacy report `credibility` column to `votes`, and removes the retired `water_votes` table. Reads use lowercase, parameterized SQL. The API returns at most the 10 nearest reports, with report distance calculated in meters. Reports within 30 feet are returned as possible duplicates when a new report is submitted. Report and comment vote direction stays in browser session storage; the API applies bounded vote deltas without recording voter identity. Comment pages contain 10 comments ordered by vote count descending, then oldest first. A nullable `report_id` identifies the homepage thread; report comments reference their report. Configure `ADMIN_EMAIL`, `ADMIN_NAME`, `ADMIN_PASSWORD`, and `JWT_SECRET` to enable admin login and comment deletion.
