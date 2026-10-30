# FIND API

FastAPI service for public water-location reports and per-browser-session votes.

## Run locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Set DATABASE_URL to a PostgreSQL database you can use.
uvicorn app.main:app --reload --port 8000
```

The FastAPI lifespan creates the `water_reports` and `water_votes` tables. Reads use lowercase, parameterized SQL. The API returns at most the 10 nearest reports, with report distance calculated in meters. Reports within 30 feet are returned as possible duplicates when a new report is submitted.
