from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum

from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt

from .config import settings
from .hrms import hrms


class Role(str, Enum):
    EMPLOYEE = "employee"
    MANAGER = "manager"
    HR_ADMIN = "hr_admin"


@dataclass
class Principal:
    emp_id: str
    name: str
    role: Role
    reports: list = field(default_factory=list)


class AccessDenied(Exception):
    pass


oauth2 = OAuth2PasswordBearer(tokenUrl="login")


def _principal(emp_id):
    e = hrms.employee(emp_id)
    if not e:
        return None
    return Principal(e["emp_id"], e["name"], Role(e["role"]), e.get("reports", []))


def authenticate(username, password):
    u = hrms.user_by_login(username, password)
    return _principal(u["emp_id"]) if u else None


def make_token(p):
    payload = {"sub": p.emp_id, "role": p.role.value,
               "exp": datetime.now(timezone.utc) + timedelta(hours=8)}
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def current_principal(token: str = Depends(oauth2)) -> Principal:
    try:
        sub = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])["sub"]
    except JWTError:
        raise HTTPException(401, "invalid token")
    p = _principal(sub)
    if not p:
        raise HTTPException(401, "unknown principal")
    return p


def can_view(p, target_id):
    if p.role == Role.HR_ADMIN or target_id == p.emp_id:
        return True
    return p.role == Role.MANAGER and target_id in p.reports


def can_view_salary(p):
    return p.role == Role.HR_ADMIN
