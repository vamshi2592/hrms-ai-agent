# HRMS Intelligent Assistant Agent

A conversational layer over an HRMS. Employees, managers, and HR admins ask
natural-language questions ("what's my leave balance?", "apply 3 days from
Monday", "show my last payslip") and the agent classifies intent, enforces
role-based access, calls the right HRMS tools, confirms any state-changing
action, and escalates grievances to a human. Every step is audited.

## Reasoning flow

```
query -> auth / RBAC -> classify intent -> fetch HR context
      -> execute tools (guarded) -> validate output -> respond / escalate
```

## Tech stack

| Layer         | Choice                                                        |
|---------------|---------------------------------------------------------------|
| LLM client    | Groq via `langchain-groq` (`llama-3.3-70b-versatile`, configurable) |
| Web layer     | FastAPI + Uvicorn (`/login`, `/chat`)                         |
| AI framework  | LangChain — tool calling, memory, RAG                         |
| Vector store  | pgvector (Postgres) for HR-policy semantic search             |
| Embeddings    | fastembed (ONNX, local, no API key) — Voyage AI as a swap     |
| Auth / RBAC   | JWT + OAuth2 password flow, role claims in the token          |
| HRMS adapter  | mock adapter behind an interface (SuccessFactors swap point)  |
| Audit store   | PostgreSQL via SQLAlchemy — every query, role check, tool call |
| Notifications | console by default; SendGrid / Slack backends optional        |

## Role-based access

| Role      | Own data | Direct reports | All employees | Salary bands | Grievances |
|-----------|:--------:|:--------------:|:-------------:|:------------:|:----------:|
| Employee  |   yes    |       no       |      no       |      no      |     no     |
| Manager   |   yes    |      yes       |      no       |      no      |     no     |
| HR Admin  |   yes    |      yes       |      yes      |     yes      |    yes     |

RBAC is enforced in the tool layer (Python), not just the prompt — the system
prompt tells the model the rules, but `enforce()` rejects out-of-scope calls
before any data is read. The acting identity comes from the JWT, never from
model-supplied arguments, so "check Priya's payslip on her behalf" fails.

## Prerequisites

- Python 3.12
- Docker (for Postgres + pgvector)
- A `GROQ_API_KEY` (free at console.groq.com)

## Setup

The virtual environment is already created (Python 3.12 via `uv`) at `.venv`.

```bash
source .venv/bin/activate
uv pip install -r requirements.txt      # or: pip install -r requirements.txt

cp .env.example .env                     # then add your GROQ_API_KEY
docker compose up -d                     # starts Postgres + pgvector
```

## Run

```bash
uvicorn app.main:app --reload            # policies are ingested on startup
```

### Log in (pick a role) and chat

```bash
# get a token (asha=employee, rahul=manager, neha=hr_admin; password: demo)
TOKEN=$(curl -s -X POST localhost:8000/login \
  -d 'username=asha&password=demo' | python -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')

# chat (token carries the role; session_id keeps memory)
curl -s -X POST localhost:8000/chat \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"s1","message":"what is my leave balance?"}'
```

### Scripted demo

```bash
python -m app.main --demo
```

Walks three roles through the flows that matter: an employee reading their own
data and being refused a coworker's payslip (even when reworded), a manager
seeing reports but not salary bands, an HR admin with full access, a
confirm-then-apply leave request, and a grievance that is always escalated to a
human. Audit rows are written for each.

## Project layout

```
app/
  main.py     FastAPI app: /login, /chat, startup ingest, --demo runner
  config.py   env settings
  auth.py     JWT + OAuth2 + Role, Principal, enforce()  (the RBAC guard)
  agent.py    intent classify + system prompt + LangChain tool loop + memory + validate
  tools.py    the 8 HRMS tools + guarded dispatch + confirmation gate + notify
  hrms.py     adapter interface + mock impl (loads data/employees.json)
  policy.py   pgvector ingest + retriever (fastembed embeddings)
  audit.py    SQLAlchemy audit sink
data/
  employees.json   mock HR data
  policies.md      HR policy text (incl. "no casual leave in December")
db/init.sql        vector extension + audit table
docker-compose.yml postgres + pgvector
```

## Guardrails

- Cross-employee PII is blocked at the tool layer and re-checked on output.
- Salary / compensation / headcount is HR-admin only; others get a clear refusal.
- Grievance and harassment reports are always routed to a human HR partner —
  the agent never attempts to resolve them. If escalation fails, the failure is
  audited and the user is given the HR contact rather than a silent drop.
- State-changing actions (apply leave, raise ticket) require an explicit
  confirmation before they execute.
