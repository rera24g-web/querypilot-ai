# QueryPilot AI (Day 1 core)
Autonomous product-analytics agent: ask a business question, it runs several safe SQL queries and returns evidence-backed findings.

## Run locally
```
cd backend
pip install -r requirements.txt
cp ../.env.example .env   # add OPENAI_API_KEY, then: export $(cat .env | xargs)
python -m app.seed        # builds sample data (planted drop: Oct-2026 paid_social cohort)
uvicorn app.main:app --reload
curl -X POST localhost:8000/api/ask -H 'content-type: application/json' \
  -d '{"question":"Why did retention drop for users who signed up in October?"}'
python -m pytest          # 15 tests: SQL guard + API
```
## Safety layers
1. SQLGlot guard: one statement, SELECT only, table allow-list, blocked functions, forced row limit
2. Read-only DB connection (SQLite query_only / Postgres READ ONLY + statement timeout)
3. For Supabase: connect with a dedicated read-only role (real protection, do not skip)

## Frontend (Next.js)
```
cd frontend && cp .env.example .env.local && npm install && npm run dev   # http://localhost:3000
```
## Benchmark
`python evaluations/run_benchmark.py` runs 10 questions with gold SQL; strict result match, agent never sees the gold answer.
Report the number you actually get. Do not quote targets as results.

## Deploy
Backend on Render (`render.yaml`; set OPENAI_API_KEY, DATABASE_URL (read-only role), ALLOWED_ORIGINS = your Vercel URL).
Frontend on Vercel: root directory `frontend`, env NEXT_PUBLIC_API_URL = your Render URL.

## Saved history and export
Every investigation is saved (app DB, separate from the read-only analytics DB) with its SQL, results and duration.
`GET /api/investigations`, `GET /api/investigations/{id}`, `GET /api/investigations/{id}/export` (Markdown report).
On Supabase, point APP_DATABASE_URL at a separate writable schema or project; keep DATABASE_URL read-only.

## Metrics, findings and limits
- `backend/app/metrics.py`: formal metric definitions (retention, conversion, churn, revenue, AOV) injected into the agent prompt.
- Findings are structured (`fact` / `hypothesis` / `recommendation`). `verify.py` checks deterministically that facts cite real successful queries and that their numbers appear in that evidence; unsupported facts are downgraded. This is NOT an LLM reviewer.
- `Limits` in `agent.py`: max steps, queries, seconds and tokens per investigation.
- `tests/test_agent.py` runs the full agent loop offline with a scripted fake client.
