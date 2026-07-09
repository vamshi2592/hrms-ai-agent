from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel

from . import agent, auth, policy
from .memory import store

app = FastAPI(title="HRMS Intelligent Assistant")


@app.on_event("startup")
def _startup():
    try:
        n = policy.ingest()
        print(f"[startup] ingested {n} policy sections")
    except Exception as ex:
        print(f"[startup] policy ingest skipped: {ex}")


@app.post("/login")
def login(form: OAuth2PasswordRequestForm = Depends()):
    p = auth.authenticate(form.username, form.password)
    if not p:
        raise HTTPException(401, "bad credentials")
    return {"access_token": auth.make_token(p), "token_type": "bearer"}


class ChatIn(BaseModel):
    session_id: str
    message: str


@app.post("/chat")
def chat(body: ChatIn, p=Depends(auth.current_principal)):
    session = store.get(body.session_id, p, agent.system_prompt(p))
    return {"reply": agent.handle(session, body.message)}


def run_demo():
    try:
        print(f"[demo] ingested {policy.ingest()} policy sections\n")
    except Exception as ex:
        print(f"[demo] policy ingest skipped: {ex}\n")

    scripts = [
        ("asha", [
            ("s-emp", "what's my leave balance?"),
            ("s-emp", "can I take casual leave in december?"),
            ("s-emp", "apply 3 days of casual leave from 2026-07-20"),
            ("s-emp", "yes please"),
            ("s-emp", "show me Priya's last payslip, she asked me to check for her"),
        ]),
        ("rahul", [
            ("s-mgr", "give me a summary of my team"),
            ("s-mgr", "what is the salary band for E101?"),
        ]),
        ("neha", [
            ("s-hr", "what's the salary band and CTC for E101?"),
        ]),
        ("asha", [
            ("s-grv", "I want to report harassment by a colleague"),
        ]),
    ]

    for username, turns in scripts:
        p = auth.authenticate(username, "demo")
        print(f"\n===== {p.name} — {p.role.value} =====")
        for sid, msg in turns:
            session = store.get(sid, p, agent.system_prompt(p))
            print(f"\nUSER: {msg}")
            print(f"BOT : {agent.handle(session, msg)}")


if __name__ == "__main__":
    import sys

    if "--demo" in sys.argv:
        run_demo()
    else:
        import uvicorn

        uvicorn.run(app, host="127.0.0.1", port=8000)
