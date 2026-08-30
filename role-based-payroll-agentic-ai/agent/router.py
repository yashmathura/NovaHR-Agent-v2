import re
from datetime import date, timedelta
from agent.novalm import predict_intent

INTENTS = {
    "create_employee": [r"\b(add|create|onboard|hire)\b.*\b(employee|staff)\b", r"new employee"],
    "delete_employee": [r"\b(remove|delete|deactivate|terminate)\b.*\b(employee|staff)\b"],
    "update_employee": [r"\b(update|edit|change)\b.*\b(employee|staff|profile)\b"],
    "assign_task": [r"\b(assign|create)\b.*\b(task|work)\b"],
    "update_task": [r"\b(update|complete|finish|change)\b.*\b(task|work)\b", r"mark.*task.*done"],
    "generate_payroll": [r"\b(generate|process|run)\b.*\b(payroll|payslip)\b"],
    "get_payroll_report": [r"\b(payroll|salary)\b.*\b(report|summary|total|department)\b", r"payroll.*team"],
    "approve_leave": [r"\b(approve|accept)\b.*\bleave\b"],
    "reject_leave": [r"\b(reject|deny)\b.*\bleave\b"],
    "apply_leave": [r"\b(apply|request|take)\b.*\b(leave|vacation|time off)\b", r"need.*leave"],
    "cancel_leave": [r"\b(cancel|withdraw)\b.*\bleave\b"],
    "mark_attendance": [r"\b(mark|check|punch|log)\b.*\b(attendance|in)\b", r"check[- ]?in today", r"check in"],
    "check_out": [r"check[- ]?out", r"punch out", r"log out"],
    "get_team_attendance": [r"\b(team|department)\b.*\b(attendance|absent|present)\b", r"who.*\b(absent|present)\b.*today"],
    "get_leave_balance": [r"\b(leaves?|vacation|time off)\b.*\b(balance|left|remaining|available)\b", r"how many (leaves?|days)"],
    "get_payroll": [r"\b(salary|payroll|payslip|pay)\b", r"earning", r"salary revision", r"salary lower"],
    "get_attendance": [r"\b(attendance|attendance history|attendance report)\b", r"how many days.*present", r"am i absent"],
    "get_tasks": [r"\b(task|tasks|todo|to-do|work)\b", r"assigned work", r"pending task"],
    "get_policy": [r"\b(policy|policies|rule|rules)\b", r"company policy"],
    "analyze_performance": [r"\bperformance\b", r"performance score"],
    "team_performance": [r"\b(team|department)\b.*\bperformance\b"],
    "list_employees": [r"\b(list|show|find|search)\b.*\b(employee|employees|staff|people)\b", r"who works"],
    "get_employee": [r"\b(employee|staff)\b.*\b(profile|details|info|information)\b"],
    "send_notification": [r"\b(send|notify|message)\b.*\b(notification|employee|staff)\b"],
    "get_notifications": [r"\b(notification|notifications|alerts?)\b"],
    "mark_notifications_read": [r"\b(mark|clear)\b.*\b(notification|notifications)\b.*\bread"],
    "profile": [r"\b(my profile|my details|my information|who am i)\b"],
    "department_summary": [r"\b(department|team)\b.*\b(summary|overview|workload)\b"],
}

def resolve_intent(text):
    t=(text or "").lower().strip()
    # NovaLM is the learned language layer; deterministic rules remain the safety fallback.
    learned=predict_intent(t)
    if learned and learned["confidence"] >= 0.58:
        return learned["intent"]
    for intent, patterns in INTENTS.items():
        if any(re.search(p,t) for p in patterns): return intent
    return "UNKNOWN"

def extract_employee_id(text):
    m=re.search(r"\bE\d{3,}\b", text or "", re.I)
    return m.group(0).upper() if m else None

def extract_leave_type(text):
    t=(text or "").upper()
    for x in ("CASUAL","SICK","ANNUAL"):
        if x in t: return x
    return "CASUAL"

def extract_status(text):
    t=(text or "").upper()
    for x in ("TODO","IN_PROGRESS","DONE"):
        if x in t or (x=="IN_PROGRESS" and "IN PROGRESS" in t): return x
    return None

def extract_priority(text):
    t=(text or "").upper()
    for x in ("LOW","MEDIUM","HIGH","URGENT"):
        if x in t: return x
    return "MEDIUM"

def extract_dates(text):
    t=(text or "").lower(); today=date.today()
    if "tomorrow" in t: return today+timedelta(days=1), today+timedelta(days=1)
    if "today" in t: return today,today
    m=re.search(r"(\d{4}-\d{2}-\d{2})(?:\s*(?:to|-|until)\s*(\d{4}-\d{2}-\d{2}))?",t)
    if m:
        a=date.fromisoformat(m.group(1)); b=date.fromisoformat(m.group(2)) if m.group(2) else a; return a,b
    return None,None

def extract_kv(text):
    pairs={}
    for key in ("name","email","phone","job_title","employee_id","department","salary","title","description","due_date","message","reason","role"):
        m=re.search(rf"\b{key}\s*[:=]\s*([^,;\n]+)", text or "", re.I)
        if m: pairs[key]=m.group(1).strip()
    return pairs
