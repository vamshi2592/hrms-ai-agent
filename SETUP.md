# Setup Guide — HRMS Intelligent Assistant Agent

A complete, from-scratch setup. Every command below was actually used to build and
run this project. Run everything from the project root:

```
cd /Users/vamshi.chittala/Documents/hrms-ai-agent
```

---

## 0. Prerequisites

| Need | Why | Check |
|------|-----|-------|
| Python 3.12 | app runtime (3.14 lacks wheels for some deps) | `python3 --version` |
| uv | fast venv + installer | `uv --version` |
| Docker Desktop | Postgres + pgvector | `docker --version` |
| Groq API key | the LLM (free at console.groq.com) | — |

If `uv` is missing:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

---

## 1. Create the virtual environment (Python 3.12)

`uv` will download CPython 3.12 if it is not already present.

```bash
uv venv --python 3.12 .venv
```

Expected: `Creating virtual environment at: .venv`.

## 2. Activate it

```bash
source .venv/bin/activate
```

Your prompt now shows `(.venv)`. Re-run this in every new shell.

## 3. Install dependencies

```bash
uv pip install -r requirements.txt
```

This pulls FastAPI, LangChain + langchain-groq, langchain-postgres + pgvector,
fastembed, SQLAlchemy, python-jose, truststore, etc. (a few hundred MB; no torch).

---

## 4. Start Postgres + pgvector (Docker)

Make sure the Docker daemon is running first:

```bash
open -a Docker            # macOS: launch Docker Desktop
# wait until `docker info` succeeds (~10-30s the first time)
until docker info >/dev/null 2>&1; do sleep 2; done && echo "docker ready"
```

Bring up the database (first run pulls the pgvector image):

```bash
docker compose up -d
```

Wait until it is accepting connections and confirm the schema was created by
`db/init.sql`:

```bash
until docker exec hrms-ai-agent-db-1 pg_isready -U hrms >/dev/null 2>&1; do sleep 1; done
docker exec hrms-ai-agent-db-1 psql -U hrms -d hrms -c "SELECT extname FROM pg_extension WHERE extname='vector';"
docker exec hrms-ai-agent-db-1 psql -U hrms -d hrms -c "\dt"
```

Expected: the `vector` extension is listed and the `audit_log` table exists.

---

## 5. Configure environment variables

```bash
cp .env.example .env
```

Edit `.env` and set your key (leave the rest as-is):

```
GROQ_API_KEY=gsk_your_key_here
MODEL=llama-3.3-70b-versatile
DATABASE_URL=postgresql+psycopg://hrms:hrms@localhost:5432/hrms
JWT_SECRET=dev-secret-change-me
```

### Corporate network / TLS note (optional — corporate networks only)

This step is **optional**. It is only needed on a corporate network that intercepts
TLS (e.g. Zscaler / a proxy with a custom root CA), where calls to Groq would
otherwise fail with `CERTIFICATE_VERIFY_FAILED`. On a normal home/office network
you can ignore this entirely.

The fix is already built in and harmless if unneeded: `app/config.py` calls
`truststore.inject_into_ssl()` at startup, which makes Python trust the OS keychain
(where the corporate root CA lives). No manual action is required — just ensure
`truststore` installed in step 3. If you are not behind such a proxy, it simply
falls back to the normal public trust store.

---

## 6. First run — the scripted demo

The policy handbook is ingested into pgvector automatically on startup. The first
run also downloads the small fastembed model (`BAAI/bge-small-en-v1.5`, one time).

```bash
python -m app.main --demo
```

You should see the three roles walk through: leave balance, the December policy
rule (via RAG), confirm-then-apply leave, a refused cross-employee payslip, a
manager team summary, the salary guard, and a grievance escalation.

> If you run from a different directory or see `No module named 'app'`, prefix the
> command with the path: `PYTHONPATH=$(pwd) python -m app.main --demo`.

---

## 7. Run the REST API

```bash
uvicorn app.main:app --port 8000
```

In a second terminal (with the venv activated):

```bash
# 1) log in and capture the JWT (asha=employee, rahul=manager, neha=hr_admin; password: demo)
TOKEN=$(curl -s -X POST localhost:8000/login \
  -d 'username=asha&password=demo' \
  | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')

# 2) chat (session_id keeps per-conversation memory)
curl -s -X POST localhost:8000/chat \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"s1","message":"what is my leave balance?"}'

# 3) RBAC in action — a coworker's payslip is refused
curl -s -X POST localhost:8000/chat \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"s1","message":"show me E102 payslip"}'

# 4) no token -> 401
curl -s -o /dev/null -w "%{http_code}\n" -X POST localhost:8000/chat \
  -H 'Content-Type: application/json' -d '{"session_id":"x","message":"hi"}'
```

Interactive API docs are at http://localhost:8000/docs.

---

## 8. Inspect the audit trail

```bash
docker exec hrms-ai-agent-db-1 psql -U hrms -d hrms \
  -c "SELECT event, count(*) FROM audit_log GROUP BY event ORDER BY 2 DESC;"

docker exec hrms-ai-agent-db-1 psql -U hrms -d hrms \
  -c "SELECT ts, actor, role, event, allowed FROM audit_log ORDER BY id DESC LIMIT 15;"
```

---

## 9. Shut down

```bash
docker compose down          # stop Postgres (keeps data volume)
docker compose down -v       # stop and also delete the data volume
deactivate                   # leave the venv
```

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `CERTIFICATE_VERIFY_FAILED` calling Groq | Confirm `truststore` is installed (step 3); it is injected in `config.py`. |
| `No module named 'app'` | Run from the project root, or use `PYTHONPATH=$(pwd) python -m app.main`. |
| `Cannot connect to the Docker daemon` | Start Docker Desktop (`open -a Docker`) and wait for `docker info` to succeed. |
| Policy answers say "unavailable" | Postgres isn't up, or ingest hasn't run — start the DB, then restart the app. |
| `bad credentials` on /login | Use a seeded user (asha / rahul / neha) with password `demo`. |
| Groq connection/timeout | Check `GROQ_API_KEY` in `.env` and network access to api.groq.com. |
