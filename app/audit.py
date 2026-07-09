import json

from sqlalchemy import create_engine, text

from .config import settings

_engine = create_engine(settings.database_url, pool_pre_ping=True)

_INSERT = text(
    "INSERT INTO audit_log (session_id, actor, role, event, allowed, detail) "
    "VALUES (:s, :a, :r, :e, :al, CAST(:d AS JSONB))"
)


def log(event, session_id=None, actor=None, role=None, allowed=None, **detail):
    payload = json.dumps(detail, default=str) if detail else None
    try:
        with _engine.begin() as c:
            c.execute(_INSERT, {"s": session_id, "a": actor, "r": role,
                                "e": event, "al": allowed, "d": payload})
    except Exception as ex:
        # never let the audit store take down a request; still surface on console
        print(f"[audit-error] {ex}")
    print(f"[audit] {event} actor={actor} role={role} allowed={allowed} {payload or ''}")
