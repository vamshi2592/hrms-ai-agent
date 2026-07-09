from dataclasses import dataclass, field

from langchain_core.messages import SystemMessage


@dataclass
class Session:
    id: str
    principal: object
    messages: list = field(default_factory=list)
    pending: dict = None


class SessionStore:
    def __init__(self):
        self._sessions = {}

    def get(self, sid, principal, system_prompt):
        s = self._sessions.get(sid)
        if s is None:
            s = Session(sid, principal, [SystemMessage(system_prompt)])
            self._sessions[sid] = s
        return s


store = SessionStore()
