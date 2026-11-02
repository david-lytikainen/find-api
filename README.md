# FIND API

FastAPI service for findable things, their locations, comments, aggregate votes, and admin management.

## Run locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Set DATABASE_URL to a PostgreSQL database you can use.
uvicorn app.main:app --reload --port 8000
```

The FastAPI lifespan creates `things`, `things_locations`, and `comments`. On the first startup after this schema change, it drops the old `water_reports` and `comments` tables; existing location and comment data is intentionally cleared. It removes the retired `water_votes` table and seeds Water as the first thing. Reads use lowercase, parameterized SQL. Public thing lists sort by Find clicks descending; locations return the 10 nearest entries for the selected thing. Locations within 30 feet are returned as possible duplicates when a new location is submitted. Location and comment vote direction stays in browser session storage; the API applies bounded vote deltas without recording voter identity. Comment pages contain 10 comments ordered by vote count descending, then oldest first. A nullable `report_id` identifies homepage comments; other comments reference a row in `things_locations`. Configure `ADMIN_EMAIL`, `ADMIN_NAME`, `ADMIN_PASSWORD`, and `JWT_SECRET` to enable admin sign-in, thing management, and comment deletion.
