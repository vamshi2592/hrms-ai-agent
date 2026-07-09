import json
import random
from pathlib import Path

_DATA = json.loads((Path(__file__).resolve().parent.parent / "data" / "employees.json").read_text())

_PROFILE_FIELDS = ("emp_id", "name", "title", "department", "manager_id",
                   "location", "date_of_joining", "email")


class HRMS:
    """Mock HRMS. Swap this class for a SuccessFactors/Workday adapter later."""

    def __init__(self, data):
        self.employees = data["employees"]
        self.users = data["users"]
        self.bands = data["salary_bands"]

    def user_by_login(self, username, password):
        for u in self.users:
            if u["username"] == username and u["password"] == password:
                return u
        return None

    def employee(self, emp_id):
        return self.employees.get(emp_id)

    def profile(self, emp_id):
        e = self.employees[emp_id]
        return {k: e[k] for k in _PROFILE_FIELDS}

    def leave_balance(self, emp_id):
        return self.employees[emp_id]["leave_balance"]

    def payslip(self, emp_id, month=None):
        slips = self.employees[emp_id]["payslips"]
        if month:
            slip = slips.get(month)
            return {"month": month, **slip} if slip else {"error": f"no payslip for {month}"}
        latest = sorted(slips)[-1]
        return {"month": latest, **slips[latest]}

    def onboarding(self, emp_id):
        return self.employees[emp_id]["onboarding_tasks"]

    def review(self, emp_id):
        return self.employees[emp_id]["performance_review"]

    def team(self, manager_id):
        reports = []
        for rid in self.employees[manager_id].get("reports", []):
            r = self.employees[rid]
            pending = [t["task"] for t in r["onboarding_tasks"] if t["status"] != "done"]
            reports.append({
                "emp_id": rid,
                "name": r["name"],
                "title": r["title"],
                "leave_balance": r["leave_balance"],
                "pending_onboarding": pending,
                "review_status": r["performance_review"]["status"],
            })
        return {"manager_id": manager_id, "team_size": len(reports), "reports": reports}

    def salary(self, emp_id):
        e = self.employees[emp_id]
        return {"emp_id": emp_id, "name": e["name"], "salary_band": e["salary_band"],
                "annual_ctc": e["annual_ctc"], "band_range": self.bands.get(e["salary_band"])}

    def apply_leave(self, emp_id, leave_type, days, start_date):
        bal = self.employees[emp_id]["leave_balance"]
        if leave_type not in bal:
            return {"ok": False, "error": f"unknown leave type '{leave_type}'"}
        if leave_type == "casual" and start_date[5:7] == "12":
            return {"ok": False, "error": "casual leave is not allowed in December; use earned leave"}
        if bal[leave_type] < days:
            return {"ok": False, "error": f"insufficient {leave_type} balance ({bal[leave_type]} left)"}
        bal[leave_type] -= days
        return {"ok": True, "leave_type": leave_type, "days": days,
                "start_date": start_date, "remaining": bal[leave_type]}

    def create_ticket(self, emp_id, issue, category="general"):
        return {"ok": True, "ticket_id": "HR-%04d" % random.randint(0, 9999),
                "emp_id": emp_id, "category": category, "issue": issue}


hrms = HRMS(_DATA)
