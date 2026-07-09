import contextvars
from dataclasses import dataclass

from langchain_core.tools import tool

from . import audit, policy
from .auth import AccessDenied, Principal, Role, can_view, can_view_salary
from .hrms import hrms

CONFIRM_TOOLS = {"apply_leave", "raise_hr_ticket"}


@dataclass
class Ctx:
    principal: Principal
    session: object


_CTX = contextvars.ContextVar("ctx")


def set_ctx(principal, session):
    _CTX.set(Ctx(principal, session))


def _c():
    return _CTX.get()


def _check(allowed, tool_name, target, reason):
    c = _c()
    audit.log("access_check", c.session.id, c.principal.emp_id, c.principal.role.value,
              allowed, tool=tool_name, target=target)
    if not allowed:
        raise AccessDenied(reason)


def _scope(emp_id, tool_name):
    _check(can_view(_c().principal, emp_id), tool_name, emp_id,
           f"You may only access your own data (id {_c().principal.emp_id}); {emp_id} is out of scope.")


# --- read tools -----------------------------------------------------------

@tool
def get_employee_profile(emp_id: str) -> dict:
    "Get an employee's basic profile: title, department, manager and joining date."
    _scope(emp_id, "get_employee_profile")
    return hrms.profile(emp_id)


@tool
def get_payslip_summary(emp_id: str, month: str = "") -> dict:
    "Get an employee's payslip (gross, deductions, net) for a month (YYYY-MM). Defaults to latest."
    _scope(emp_id, "get_payslip_summary")
    return hrms.payslip(emp_id, month or None)


@tool
def get_leave_balance(emp_id: str) -> dict:
    "Get an employee's current leave balance by type (casual, sick, earned)."
    _scope(emp_id, "get_leave_balance")
    return {"emp_id": emp_id, "leave_balance": hrms.leave_balance(emp_id)}


@tool
def get_onboarding_tasks(emp_id: str) -> dict:
    "List an employee's onboarding checklist and the status of each task."
    _scope(emp_id, "get_onboarding_tasks")
    return {"emp_id": emp_id, "tasks": hrms.onboarding(emp_id)}


@tool
def get_performance_review(emp_id: str) -> dict:
    "Get an employee's latest performance review, rating and next review date."
    _scope(emp_id, "get_performance_review")
    return hrms.review(emp_id)


@tool
def get_team_summary(manager_id: str) -> dict:
    "Summarize a manager's direct reports: leave balances, pending onboarding and review status."
    p = _c().principal
    ok = p.role == Role.HR_ADMIN or (p.role == Role.MANAGER and p.emp_id == manager_id)
    _check(ok, "get_team_summary", manager_id, "Only the manager themselves or HR can view a team.")
    return hrms.team(manager_id)


@tool
def get_salary_info(emp_id: str) -> dict:
    "Get an employee's compensation band and CTC. Restricted to HR administrators."
    _check(can_view_salary(_c().principal), "get_salary_info", emp_id,
           "Compensation and salary-band data is restricted to HR administrators.")
    return hrms.salary(emp_id)


@tool
def search_hr_policy(query: str) -> dict:
    "Search the HR policy handbook and return the most relevant passages."
    c = _c()
    audit.log("tool_call", c.session.id, c.principal.emp_id, c.principal.role.value,
              True, tool="search_hr_policy", query=query)
    return {"passages": policy.search(query)}


# --- state-changing tools (confirmation required) -------------------------

@tool
def apply_leave(emp_id: str, leave_type: str, days: int, start_date: str) -> dict:
    "Apply leave (casual|sick|earned) for an employee. Presents a confirmation before it runs."
    _scope(emp_id, "apply_leave")
    return _register_pending(
        "apply_leave",
        {"emp_id": emp_id, "leave_type": leave_type, "days": days, "start_date": start_date},
        f"Apply {days} day(s) of {leave_type} leave for {emp_id} starting {start_date}.",
    )


@tool
def raise_hr_ticket(emp_id: str, issue: str, category: str = "general") -> dict:
    "Raise an HR ticket. Presents a confirmation before it runs. Grievances are routed to a human."
    _scope(emp_id, "raise_hr_ticket")
    return _register_pending(
        "raise_hr_ticket",
        {"emp_id": emp_id, "issue": issue, "category": category},
        f'Raise a "{category}" HR ticket for {emp_id}: "{issue}".',
    )


@tool
def send_notification(target: str, message: str) -> dict:
    "Send a notification to an employee or channel (mocked to console)."
    c = _c()
    audit.log("tool_call", c.session.id, c.principal.emp_id, c.principal.role.value,
              True, tool="send_notification", target=target)
    _notify(target, message)
    return {"ok": True, "target": target}


# --- confirmation + execution (driven by the agent, not the model) --------

def _register_pending(name, args, summary):
    c = _c()
    c.session.pending = {"name": name, "args": args, "summary": summary}
    audit.log("confirmation_requested", c.session.id, c.principal.emp_id,
              c.principal.role.value, None, action=name, args=args)
    return {"status": "needs_confirmation", "summary": summary}


def execute_pending(principal, session):
    name, args = session.pending["name"], session.pending["args"]
    session.pending = None
    if name == "apply_leave":
        res = hrms.apply_leave(**args)
    else:
        res = _raise_ticket(principal, session, args)
    audit.log("action_executed", session.id, principal.emp_id, principal.role.value,
              res.get("ok"), action=name, result=res)
    return res


def _raise_ticket(principal, session, args):
    cat = args.get("category", "general")
    try:
        res = hrms.create_ticket(args["emp_id"], args["issue"], cat)
    except Exception as ex:
        audit.log("escalation_failed", session.id, principal.emp_id, principal.role.value,
                  False, error=str(ex))
        return {"ok": False, "error": "ticketing system unavailable",
                "fallback": "Please email hr-help@example.com or call HR at ext. 4000."}
    if cat in ("grievance", "harassment"):
        res["routed_to"] = "Human HR Business Partner"
        audit.log("escalation", session.id, principal.emp_id, principal.role.value,
                  True, ticket=res["ticket_id"], category=cat)
        _notify("hr-business-partner", f"[{cat}] from {args['emp_id']}: {args['issue']}")
    return res


def raise_grievance(principal, session, issue):
    """Deterministic escalation path used when a grievance intent is detected."""
    return _raise_ticket(principal, session, {"emp_id": principal.emp_id,
                                              "issue": issue, "category": "grievance"})


def _notify(target, message):
    print(f"[notify] to={target} :: {message}")


ALL = [get_employee_profile, get_leave_balance, get_payslip_summary,
       get_onboarding_tasks, get_performance_review, get_team_summary,
       get_salary_info, search_hr_policy, apply_leave, raise_hr_ticket,
       send_notification]
