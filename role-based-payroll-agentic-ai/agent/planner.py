import re
from agent.router import resolve_intent, extract_employee_id, extract_leave_type, extract_dates, extract_status, extract_priority, extract_kv
from agent.permissions import check_permission
from agent import tools
from core.models import AgentAuditLog, Leave, Task

def _role(user): return getattr(user,"role","EMPLOYEE").upper()

def _missing_message(intent):
    return {"create_employee":"To add an employee, provide name and email. Example: add employee name: Rahul Kumar, email: rahul@company.com, salary: 45000, department: Engineering, job_title: Developer",
            "apply_leave":"To apply leave, provide dates and reason. Example: apply sick leave from 2026-08-28 to 2026-08-29, reason: fever",
            "assign_task":"To assign a task, provide employee ID, title and optionally due date/priority. Example: assign task to E1005 title: Prepare report, due_date: 2026-09-01, priority: HIGH"}.get(intent,"I need a little more information to complete that request.")

def _pretty(intent,data):
    
    if intent=="get_leave_balance":
        return "Leave balance:\n"+"\n".join(f"• {k.title()}: {v['remaining']} remaining ({v['used']} used / {v['allocated']} allocated)" for k,v in data["balances"].items())
    if intent=="salary_revision":
        revision = data.get("last_salary_revision")

        if not revision:
            return "No salary revision date is recorded for your profile."

        return f"Your last salary revision was on {revision}."
    if intent in {"get_attendance","get_team_attendance"}: return f"Attendance checked for {data.get('month','today')}/{data.get('year','')}. {len(data.get('records',[]))} record(s) found." if "records" in data else f"Today's attendance: {data['count']} employee(s)."
    if intent in {"get_payroll", "get_payroll_report"}:
        if intent == "get_payroll":
            return (
                f"Payroll for {data['employee']} "
                f"({data['month']}/{data['year']}): "
                f"net ₹{data['final_salary']}, "
                f"deductions ₹{data['deductions']}, "
                f"bonus ₹{data['bonus']}."
            )

        return (
            f"Payroll report: {data['count']} records, "
            f"total net ₹{data['total_net_salary']}."
        )
    if intent=="generate_payroll": return f"Payroll generated for {data['count']} employee(s) for {data['period']}."
    if intent=="get_tasks": return f"You have/accessed {data['count']} task(s)."
    if intent=="list_employees": return f"There are {data['count']} active employees in your permitted scope."
    if intent=="get_employee": return f"Employee {data['employee_id']}: {data['name']}, {data['job_title'] or 'No title'}, {data['department'] or 'No department'}."
    
    if intent in {"analyze_performance"}: return f"Performance score: {data['performance_score']}%. Attendance: {data['attendance_percent']}%. Task completion: {data['task_completion_percent']}%."
    if intent=="team_performance": return f"Performance report generated for {len(data['employees'])} employee(s)."
    if intent=="get_policy": return f"Found {len(data['results'])} matching policy document(s)."
    if intent=="get_notifications": return f"You have {data['count']} unread notification(s)."
    if data.get("last_salary_revision"):
        return (
        f"Your latest salary revision was on "
        f"{data['last_salary_revision']}. "
        f"Your current/latest net salary is ₹{data['final_salary']}."
    )
    return data.get("message") if isinstance(data,dict) and data.get("message") else "Done successfully."

def execute_agent_pipeline(user,message):
    intent=resolve_intent(message); role=_role(user)
    if intent=="UNKNOWN": return {"status":"error","message":"I couldn't identify that request. Try leave, attendance, salary, payroll, tasks, policies, performance, employees, or notifications."}
    if not check_permission(role,intent): return {"status":"denied","intent":intent,"message":f"Security Alert: {role} is not authorized to perform '{intent}'."}
    kv=extract_kv(message); emp_id=extract_employee_id(message); a,b=extract_dates(message); lt=extract_leave_type(message); status=extract_status(message); priority=extract_priority(message)
    try:
        if intent=="get_leave_balance": data=tools.get_leave_balance(user,lt if lt in {"CASUAL","SICK","ANNUAL"} and lt in message.upper() else "ALL")
        elif intent=="apply_leave":
            if not a:return {"status":"need_input","message":_missing_message(intent)}
            data=tools.apply_leave(user,lt,str(a),str(b),kv.get("reason") or "Requested through NovaHR Agent")
        elif intent=="cancel_leave":
            lid=int(recover_id(message) or 0); data=tools.cancel_leave(user,lid) if lid else {"success":False,"error":"Provide the leave ID to cancel."}
        elif intent=="get_attendance": data=tools.get_attendance(user)
        elif intent=="mark_attendance": data=tools.mark_attendance(user)
        elif intent=="check_out": data=tools.check_out(user)
        elif intent=="get_team_attendance": data=tools.get_team_attendance(user)
        elif intent=="get_payroll": data=tools.get_payroll(user,employee_id=emp_id)
        elif intent=="salary_revision": data=tools.get_payroll(user)
        elif intent=="get_payroll_report": data=tools.get_payroll_report(user)
        elif intent=="generate_payroll": data=tools.generate_payroll(user,employee_id=emp_id)
        elif intent=="get_tasks": data=tools.get_tasks(user, status or "ALL")
        elif intent=="assign_task":
            if not emp_id or not kv.get("title"): return {"status":"need_input","message":_missing_message(intent)}
            data=tools.assign_task(user,emp_id,kv["title"],kv.get("description", ""),kv.get("due_date"),priority)
        elif intent=="update_task":
            tid=int(recover_id(message) or 0); data=tools.update_task(user,tid,status or "DONE") if tid else {"success":False,"error":"Provide task ID, e.g. task 12 done."}
        elif intent=="get_policy": data=tools.get_policy(user,message)
        elif intent=="analyze_performance": data=tools.analyze_performance(user)
        elif intent=="team_performance": data=tools.team_performance(user)
        elif intent=="list_employees": data=tools.list_employees(user)
        elif intent=="get_employee": data=tools.get_employee(user,emp_id) if emp_id else {"found":False,"message":"Provide employee ID such as E1005."}
        elif intent=="create_employee":
            if not kv.get("name") or not kv.get("email"): return {"status":"need_input","message":_missing_message(intent)}
            data=tools.create_employee(user,kv["name"],kv["email"],kv.get("password","Employee@123"),kv.get("role","EMPLOYEE").upper(),kv.get("employee_id"),kv.get("department"),kv.get("salary","0"),kv.get("job_title",""),kv.get("phone",""))
        elif intent=="update_employee":
            if not emp_id:return {"status":"need_input","message":"Provide employee ID, e.g. update employee E1005 salary: 50000, job_title: Senior Developer"}
            data=tools.update_employee(user,emp_id,**kv)
        elif intent=="delete_employee": data=tools.delete_employee(user,emp_id) if emp_id else {"success":False,"error":"Provide employee ID."}
        elif intent in {"approve_leave","reject_leave"}:
            lid=int(recover_id(message) or 0)
            if not lid:
                leave=Leave.objects.filter(status="PENDING",employee__department_id=user.department_id if role=="MANAGER" else None).order_by("applied_at").first() if role=="MANAGER" else Leave.objects.filter(status="PENDING").order_by("applied_at").first(); lid=leave.id if leave else 0
            data=(tools.approve_leave if intent=="approve_leave" else tools.reject_leave)(user,lid) if lid else {"success":False,"error":"No pending leave request found."}
        elif intent=="send_notification":
            if not emp_id or not kv.get("title") or not kv.get("message"): return {"status":"need_input","message":"Provide employee ID plus title and message. Example: notify E1005 title: Meeting, message: Meeting at 3 PM."}
            data=tools.send_notification(user,emp_id,kv["title"],kv["message"])
        elif intent=="get_notifications": data=tools.get_notifications(user)
        elif intent=="mark_notifications_read": data=tools.mark_notifications_read(user)
        elif intent=="profile": data=tools.profile(user)
        elif intent=="department_summary": data=tools.department_summary(user)
        else: return {"status":"error","message":"Tool not implemented."}
        ok=not (isinstance(data,dict) and (data.get("success") is False or data.get("found") is False))
        AgentAuditLog.objects.create(user=user,tool_name=intent,arguments={"message":message},result=data,success=ok)
        return {"status":"success" if ok else "error","intent":intent,"data":data,"message":_pretty(intent,data) if ok else data.get("error") or data.get("message") or "Request could not be completed."}
    except Exception as exc:
        AgentAuditLog.objects.create(user=user,tool_name=intent,arguments={"message":message},result={"error":str(exc)},success=False)
        return {"status":"error","intent":intent,"message":f"I could not complete that safely: {exc}"}

def recover_id(text):
    import re
    m=re.search(r"\b(?:leave|task|id)\s*#?\s*(\d+)\b",text or "",re.I)
    return m.group(1) if m else None
