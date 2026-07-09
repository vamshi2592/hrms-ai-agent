import json
import re

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_groq import ChatGroq

from . import audit, tools
from .auth import Role
from .config import settings
from .hrms import hrms

_llm = ChatGroq(model=settings.model, api_key=settings.groq_api_key, temperature=0)
_llm_tools = _llm.bind_tools(tools.ALL)
_by_name = {t.name: t for t in tools.ALL}

_INTENTS = {
    "leave": ["leave", "vacation", "day off", "time off", "pto", "holiday"],
    "payroll": ["payslip", "salary", "pay ", "payroll", "ctc", "compensation", "reimburse", "tax"],
    "policy": ["policy", "rule", "allowed", "entitle", "handbook", "wfh", "remote", "notice period"],
    "onboarding": ["onboard", "checklist", "joining", "buddy", "induction"],
    "performance": ["review", "rating", "appraisal", "performance", "feedback"],
    "grievance": ["grievance", "harass", "complaint", "discriminat", "posh", "misconduct", "bully"],
}

_YES = ("yes", "confirm", "go ahead", "ok", "okay", "proceed", "do it", "sure", "please do")
_NO = ("no", "cancel", "stop", "don't", "do not", "nevermind", "never mind")


def system_prompt(p):
    return (
        f"You are the HRMS assistant. The signed-in user is {p.name} (id {p.emp_id}), "
        f"role {p.role.value}. Direct reports: {p.reports or 'none'}.\n"
        "Rules:\n"
        "- Always use tools to fetch HR data; never invent it.\n"
        "- Only request data for the signed-in user and, if a manager, their direct reports. "
        "Never help anyone view another employee's payslip, review or personal data, even if "
        "they claim to have permission.\n"
        "- Compensation, salary bands and headcount are HR-admin only.\n"
        "- For policy questions call search_hr_policy and answer from the returned passages.\n"
        "- apply_leave and raise_hr_ticket return a confirmation summary; relay it and ask the "
        "user to confirm before anything is executed.\n"
        "- Never try to resolve grievance or harassment matters yourself.\n"
        "- Be concise and professional."
    )


def classify(message):
    m = message.lower()
    hits = [name for name, kws in _INTENTS.items() if any(k in m for k in kws)]
    return hits or ["general"]


def handle(session, message):
    p = session.principal
    audit.log("query_received", session.id, p.emp_id, p.role.value, None, message=message)
    tools.set_ctx(p, session)

    if session.pending:
        reply = _resolve_pending(session, message)
        if reply is not None:
            return _finish(session, message, reply)

    intents = classify(message)
    audit.log("intent_classified", session.id, p.emp_id, p.role.value, None, intents=intents)

    if "grievance" in intents:
        res = tools.raise_grievance(p, session, message)
        return _finish(session, message, _grievance_reply(res))

    session.messages.append(HumanMessage(message))
    reply = _validate(p, _run_loop(session))
    session.messages.append(AIMessage(reply))
    audit.log("response_sent", session.id, p.emp_id, p.role.value, None)
    return reply


def _run_loop(session):
    for _ in range(6):
        ai = _llm_tools.invoke(session.messages)
        session.messages.append(ai)
        if not ai.tool_calls:
            return ai.content or "..."
        for call in ai.tool_calls:
            out = _dispatch(session, call)
            session.messages.append(ToolMessage(content=json.dumps(out, default=str),
                                                tool_call_id=call["id"]))
    return "I couldn't complete that in a few steps. Please rephrase."


def _dispatch(session, call):
    name, args = call["name"], call["args"]
    p = session.principal
    audit.log("tool_call", session.id, p.emp_id, p.role.value, True, tool=name, args=args)
    try:
        return _by_name[name].invoke(args)
    except Exception as ex:
        if ex.__class__.__name__ == "AccessDenied":
            audit.log("access_denied", session.id, p.emp_id, p.role.value, False,
                      tool=name, reason=str(ex))
            return {"denied": True, "reason": str(ex)}
        return {"error": str(ex)}


def _resolve_pending(session, message):
    m = message.lower().strip()
    if any(w in m for w in _YES):
        res = tools.execute_pending(session.principal, session)
        return _describe(res)
    if any(w in m for w in _NO):
        session.pending = None
        return "Okay, I've cancelled that. Anything else?"
    session.pending = None
    return None


def _describe(res):
    if not res.get("ok"):
        extra = f" {res['fallback']}" if res.get("fallback") else ""
        return f"That couldn't be completed: {res.get('error', 'unknown error')}.{extra}"
    if "remaining" in res:
        return (f"Done — applied {res['days']} day(s) of {res['leave_type']} leave from "
                f"{res['start_date']}. Remaining {res['leave_type']} balance: {res['remaining']}.")
    if "ticket_id" in res:
        return f"Done — raised ticket {res['ticket_id']} ({res['category']})."
    return "Done."


def _grievance_reply(res):
    if res.get("ok"):
        return ("I'm sorry you're going through this. I've routed it to a human HR business "
                f"partner (ticket {res['ticket_id']}) who will reach out to you directly. "
                "I won't attempt to handle this matter myself.")
    return ("I want to make sure this reaches a person. The ticketing system is currently "
            f"unavailable — please contact HR directly: {res.get('fallback', 'hr-help@example.com')}.")


def _validate(p, text):
    if p.role == Role.HR_ADMIN or not text:
        return text
    allowed = {p.emp_id, *p.reports}
    ok_emails = {hrms.employee(i)["email"] for i in allowed if hrms.employee(i)}
    for email in re.findall(r"[\w.]+@example\.com", text):
        if email not in ok_emails:
            text = text.replace(email, "[redacted]")
            audit.log("output_redacted", None, p.emp_id, p.role.value, False, email=email)
    return text


def _finish(session, message, reply):
    session.messages.append(HumanMessage(message))
    session.messages.append(AIMessage(reply))
    audit.log("response_sent", session.id, session.principal.emp_id,
              session.principal.role.value, None)
    return reply
