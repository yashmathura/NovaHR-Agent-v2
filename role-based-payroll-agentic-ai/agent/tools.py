from datetime import date
from decimal import Decimal, InvalidOperation
import secrets
import string
from django.db.models import Sum, Count, Q
from django.utils import timezone
from core.models import User, Attendance, Payroll, Task, KnowledgeDocument, Notification, Leave, Department, Company, Team

def _employees_for(user):
    qs=User.objects.filter(is_active=True).exclude(role__in=[])
    if user.role=="MANAGER": qs=qs.filter(department_id=user.department_id)
    return qs

def get_leave_balance(user, leave_type="ALL"):
    mapping = {
        "CASUAL": "casual_leave_quota",
        "SICK": "sick_leave_quota",
        "ANNUAL": "annual_leave_quota"
    }

    types = [leave_type] if leave_type in mapping else list(mapping)
    out = {}

    for kind in types:
        quota = getattr(user, mapping[kind], 0)

        used_days = sum(
            x.days
            for x in Leave.objects.filter(
                employee=user,
                leave_type=kind,
                status="APPROVED"
            )
        )

        out[kind] = {
            "allocated": quota,
            "used": used_days,
            "remaining": max(0, quota - used_days)
        }

    return {
        "found": True,
        "balances": out
    }

def get_attendance(user,month=None,year=None):
    today=timezone.localdate(); month=month or today.month; year=year or today.year
    qs=Attendance.objects.filter(employee=user,date__year=year,date__month=month).order_by("date")
    return {"month":month,"year":year,"records":[{"date":str(x.date),"status":x.status,"check_in":x.check_in.isoformat() if x.check_in else None,"check_out":x.check_out.isoformat() if x.check_out else None,"hours":x.hours_worked} for x in qs]}

def mark_attendance(user):
    today=timezone.localdate(); now=timezone.localtime(); a,created=Attendance.objects.get_or_create(employee=user,date=today,defaults={"status":"PRESENT","check_in":now})
    if not created and a.check_in: return {"success":False,"message":f"Already checked in at {a.check_in.isoformat()}."}
    if not created: a.check_in=now; a.status="PRESENT"; a.save()
    return {"success":True,"message":"Attendance marked successfully.","date":str(today),"check_in":now.isoformat()}

def check_out(user):
    a=Attendance.objects.filter(employee=user,date=timezone.localdate()).first()
    if not a or not a.check_in: return {"success":False,"message":"Please check in first."}
    if a.check_out: return {"success":False,"message":"Already checked out."}
    a.check_out=timezone.localtime(); a.save(); return {"success":True,"message":"Checked out successfully.","check_out":a.check_out.isoformat(),"hours":a.hours_worked}

def get_team_attendance(user):
    today=timezone.localdate(); qs=User.objects.filter(is_active=True,department_id=user.department_id,role="EMPLOYEE") if user.role=="MANAGER" else User.objects.filter(is_active=True,role="EMPLOYEE")
    rows=[]
    for e in qs.select_related("department"):
        a=Attendance.objects.filter(employee=e,date=today).first(); rows.append({"employee_id":e.employee_id,"name":e.get_full_name() or e.username,"status":a.status if a else "ABSENT","check_in":a.check_in.isoformat() if a and a.check_in else None})
    return {"date":str(today),"count":len(rows),"records":rows}

def get_payroll(user, month=None, year=None, employee_id=None):
    target = user

    if employee_id:
        if user.role not in {"HR", "FINANCE", "ADMIN"}:
            return {"found": False, "message": "You are not authorized to view another employee's payroll."}

        target = User.objects.filter(
            employee_id=employee_id,
            is_active=True
        ).first()

        if not target:
            return {"found": False, "message": "Employee not found."}

    qs = Payroll.objects.filter(employee=target).order_by("-year", "-month")

    if month and year:
        qs = qs.filter(month=month, year=year)

    p = qs.first()

    if not p:
        return {
            "found": False,
            "message": f"No payroll record found for {target.get_full_name() or target.username}."
        }

    return {
        "found": True,
        "employee_id": target.employee_id,
        "employee": target.get_full_name() or target.username,
        "month": p.month,
        "year": p.year,
        "base_salary": str(p.base_salary),
        "present_days": str(p.present_days),
        "absent_days": str(p.absent_days),
        "leave_days": str(p.leave_days),
        "deductions": str(p.deductions),
        "bonus": str(p.bonus),
        "final_salary": str(p.final_salary),
        "last_salary_revision": (
            str(target.last_salary_revision)
            if target.last_salary_revision else None
        ),
    }

def get_payroll_report(user):
    qs=Payroll.objects.select_related("employee").all()
    if user.role=="FINANCE": pass
    if user.role=="HR" and user.department_id: qs=qs.filter(employee__department_id=user.department_id)
    rows=list(qs.order_by("-year","-month")[:200]); total=qs.aggregate(total=Sum("final_salary"))["total"] or Decimal("0")
    return {"count":len(rows),"total_net_salary":str(total),"records":[{"employee_id":p.employee.employee_id,"employee":p.employee.get_full_name() or p.employee.username,"period":f"{p.month}/{p.year}","net":str(p.final_salary),"deductions":str(p.deductions),"bonus":str(p.bonus)} for p in rows]}

def generate_payroll(user,employee_id=None,month=None,year=None):
    today=timezone.localdate(); month=month or today.month; year=year or today.year
    employees=User.objects.filter(role="EMPLOYEE",is_active=True)
    if employee_id: employees=employees.filter(employee_id=employee_id)
    created=[]
    for e in employees:
        rec=Attendance.objects.filter(employee=e,date__year=year,date__month=month); present=rec.filter(status="PRESENT").count(); absent=rec.filter(status="ABSENT").count()
        approved=sum(x.days for x in Leave.objects.filter(employee=e,status="APPROVED",start_date__year=year,start_date__month=month))
        p,_=Payroll.objects.update_or_create(employee=e,month=month,year=year,defaults={"base_salary":e.salary,"working_days":22,"present_days":present,"absent_days":absent,"leave_days":approved})
        created.append({"employee_id":e.employee_id,"final_salary":str(p.final_salary)})
    return {"success":True,"period":f"{month}/{year}","count":len(created),"records":created}

def get_tasks(user,status="ALL"):
    qs=Task.objects.filter(assigned_to=user) if user.role=="EMPLOYEE" else Task.objects.filter(assigned_to__department_id=user.department_id) if user.role=="MANAGER" else Task.objects.all()
    if status and status!="ALL": qs=qs.filter(status=status)
    return {"count":qs.count(),"tasks":[{"id":x.id,"title":x.title,"status":x.status,"priority":x.priority,"due_date":str(x.due_date) if x.due_date else None,"assigned_to":x.assigned_to.employee_id} for x in qs.order_by("status","due_date")[:50]]}

def assign_task(user,employee_id,title,description="",due_date=None,priority="MEDIUM"):
    emp=User.objects.filter(employee_id=employee_id,role="EMPLOYEE",is_active=True).first()
    if not emp:return {"success":False,"error":"Employee not found."}
    if user.role=="MANAGER" and emp.department_id!=user.department_id:return {"success":False,"error":"Employee is outside your department."}
    task=Task.objects.create(assigned_to=emp,assigned_by=user,title=title,description=description,due_date=date.fromisoformat(due_date) if due_date else None,priority=priority)
    Notification.objects.create(employee=emp,title="New task assigned",message=f"{title} ({priority}) was assigned to you.")
    return {"success":True,"task_id":task.id,"assigned_to":emp.employee_id}

def update_task(user,task_id,status):
    task=Task.objects.filter(id=task_id).first()
    if not task:return {"success":False,"error":"Task not found."}
    if user.role=="EMPLOYEE" and task.assigned_to_id!=user.id:return {"success":False,"error":"You can only update your own tasks."}
    if user.role=="MANAGER" and task.assigned_to.department_id!=user.department_id:return {"success":False,"error":"Outside your department."}
    task.status=status; task.save(); return {"success":True,"task_id":task.id,"status":task.status}

def get_policy(user,query="company policy"):
    words=[w.lower() for w in query.split() if len(w)>2][:10]; scored=[]
    for d in KnowledgeDocument.objects.all():
        text=(d.title+" "+d.category+" "+d.content).lower(); score=sum(text.count(w) for w in words)
        if score: scored.append((score,d))
    scored.sort(key=lambda x:x[0],reverse=True); return {"query":query,"results":[{"title":d.title,"category":d.category,"content":d.content} for _,d in scored[:5]]}

def analyze_performance(user):
    start=timezone.localdate().replace(day=1); r=Attendance.objects.filter(employee=user,date__gte=start); present=r.filter(status="PRESENT").count(); absent=r.filter(status="ABSENT").count(); miss=r.filter(status="MISS_PUNCH").count(); tasks=Task.objects.filter(assigned_to=user); total=tasks.count(); done=tasks.filter(status="DONE").count(); denom=present+absent+miss; ap=round((present+.5*miss)/denom*100,1) if denom else 0; tp=round(done/total*100,1) if total else 0
    return {"attendance_percent":ap,"task_completion_percent":tp,"performance_score":round(ap*.6+tp*.4,1),"present":present,"absent":absent,"tasks_total":total,"tasks_done":done}

def team_performance(user):
    qs=User.objects.filter(role="EMPLOYEE",is_active=True); 
    if user.role=="MANAGER": qs=qs.filter(department_id=user.department_id)
    return {"employees":[{"employee_id":e.employee_id,"name":e.get_full_name() or e.username,**analyze_performance(e)} for e in qs]}

def list_employees(user):
    qs=User.objects.filter(is_active=True,role="EMPLOYEE");
    if user.role=="MANAGER": qs=qs.filter(department_id=user.department_id)
    return {"count":qs.count(),"employees":[{"employee_id":e.employee_id,"name":e.get_full_name() or e.username,"email":e.email,"job_title":e.job_title,"department":e.department.name if e.department else None,"manager":e.manager.get_full_name() if e.manager else None} for e in qs.order_by("employee_id")[:200]]}

def get_employee(user,employee_id):
    e=User.objects.filter(employee_id=employee_id,is_active=True).first()
    if not e:return {"found":False,"message":"Employee not found."}
    if user.role=="MANAGER" and e.department_id!=user.department_id:return {"found":False,"message":"Employee is outside your department."}
    return {"found":True,"employee_id":e.employee_id,"name":e.get_full_name() or e.username,"email":e.email,"phone":e.phone,"job_title":e.job_title,"role":e.role,"department":e.department.name if e.department else None,"joining_date":str(e.joining_date) if e.joining_date else None,"salary":str(e.salary) if user.role in {"HR","FINANCE","ADMIN"} else "RESTRICTED"}

def _temporary_password(length=12):
    alphabet=string.ascii_letters+string.digits+"@#$%"
    while True:
        p="".join(secrets.choice(alphabet) for _ in range(length))
        if any(c.islower() for c in p) and any(c.isupper() for c in p) and any(c.isdigit() for c in p): return p

def create_employee(user,name,email,password=None,role="EMPLOYEE",employee_id=None,department=None,salary="0",job_title="",phone=""):
    if not name or not email:return {"success":False,"error":"name and email are required."}
    email=email.strip().lower()
    if role not in {"EMPLOYEE","MANAGER","HR","FINANCE"}: role="EMPLOYEE"
    if User.objects.filter(email__iexact=email).exists():return {"success":False,"error":"Email already exists."}
    employee_id=employee_id or f"E{User.objects.count()+1001}"
    if User.objects.filter(employee_id=employee_id).exists():return {"success":False,"error":"Employee ID already exists."}
    dept=None
    if department: dept=Department.objects.filter(name__iexact=department).first()
    if not dept: dept=Department.objects.first()
    try: salary=Decimal(str(salary))
    except InvalidOperation: return {"success":False,"error":"Invalid salary."}
    password=password or _temporary_password()
    first,*rest=name.split(); e=User(username=email,email=email,employee_id=employee_id,role=role,department=dept,salary=salary,job_title=job_title,phone=phone,first_name=first,last_name=" ".join(rest),must_change_password=True)
    e.set_password(password); e.save()
    Notification.objects.create(employee=e,title="Welcome to NovaHR",message=f"Your login ID is your email address: {email}. Temporary password: {password}. Please change it after first login.")
    return {"success":True,"employee_id":e.employee_id,"name":name,"email":email,"role":role,"login_id":email,"temporary_password":password,"must_change_password":True}

def update_employee(user,employee_id,**fields):
    e=User.objects.filter(employee_id=employee_id,is_active=True).first()
    if not e:return {"success":False,"error":"Employee not found."}
    if fields.get("email") is not None:
        new_email=str(fields["email"]).strip().lower()
        if User.objects.exclude(pk=e.pk).filter(email__iexact=new_email).exists(): return {"success":False,"error":"Email already exists."}
        e.email=new_email; e.username=new_email
    for k in ("phone","job_title","first_name","last_name"):
        if fields.get(k) is not None:setattr(e,k,fields[k])
    if fields.get("salary") is not None:
        try:e.salary=Decimal(str(fields["salary"]))
        except InvalidOperation:return {"success":False,"error":"Invalid salary."}
    if fields.get("department"): e.department=Department.objects.filter(name__iexact=fields["department"]).first() or e.department
    e.save(); return {"success":True,"employee_id":e.employee_id,"message":"Employee updated."}

def delete_employee(user,employee_id):
    e=User.objects.filter(employee_id=employee_id,is_active=True).first()
    if not e:return {"success":False,"error":"Employee not found."}
    e.is_active=False; e.save(update_fields=["is_active"]); return {"success":True,"employee_id":employee_id,"message":"Employee deactivated."}

def _decide(user,leave_id,decision):
    leave=Leave.objects.filter(id=leave_id).first()
    if not leave:return {"success":False,"error":"Leave request not found."}
    if user.role=="MANAGER" and leave.employee.department_id!=user.department_id:return {"success":False,"error":"Outside your department."}
    leave.status=decision; leave.approved_by=user; leave.decision_at=timezone.now(); leave.save(); Notification.objects.create(employee=leave.employee,title=f"Leave {decision.lower()}",message=f"Your leave request was {decision.lower()}."); return {"success":True,"leave_id":leave.id,"status":decision}
def approve_leave(user,leave_id):return _decide(user,leave_id,"APPROVED")
def reject_leave(user,leave_id):return _decide(user,leave_id,"REJECTED")

def apply_leave(user,leave_type,start_date,end_date,reason):
    a=date.fromisoformat(start_date); b=date.fromisoformat(end_date)
    if b<a:return {"success":False,"error":"End date cannot be before start date."}
    if Leave.objects.filter(employee=user,status__in=["PENDING","APPROVED"],start_date__lte=b,end_date__gte=a).exists():return {"success":False,"error":"Overlapping leave exists."}
    leave=Leave.objects.create(employee=user,leave_type=leave_type,start_date=a,end_date=b,reason=reason)
    return {"success":True,"leave_id":leave.id,"days":leave.days,"status":"PENDING"}

def cancel_leave(user,leave_id):
    leave=Leave.objects.filter(id=leave_id,employee=user).first()
    if not leave:return {"success":False,"error":"Leave not found."}
    if leave.status!="PENDING":return {"success":False,"error":"Only pending leave can be cancelled."}
    leave.status="REJECTED"; leave.save(); return {"success":True,"message":"Leave request cancelled."}

def send_notification(user,employee_id,title,message):
    e=User.objects.filter(employee_id=employee_id,is_active=True).first()
    if not e:return {"success":False,"error":"Employee not found."}
    if user.role=="MANAGER" and e.department_id!=user.department_id:return {"success":False,"error":"Outside your department."}
    n=Notification.objects.create(employee=e,title=title,message=message); return {"success":True,"notification_id":n.id}

def get_notifications(user):return {"count":user.notifications.filter(read=False).count(),"notifications":[{"id":n.id,"title":n.title,"message":n.message,"created_at":n.created_at.isoformat()} for n in user.notifications.order_by("-created_at")[:20]]}
def mark_notifications_read(user): user.notifications.filter(read=False).update(read=True); return {"success":True,"message":"Notifications marked as read."}
def profile(user):return {"employee_id":user.employee_id,"name":user.get_full_name() or user.username,"email":user.email,"role":user.role,"job_title":user.job_title,"department":user.department.name if user.department else None,"joining_date":str(user.joining_date) if user.joining_date else None}
def department_summary(user):
    qs=User.objects.filter(role="EMPLOYEE",is_active=True); 
    if user.role=="MANAGER":qs=qs.filter(department_id=user.department_id)
    return {"employees":qs.count(),"pending_leaves":Leave.objects.filter(employee__in=qs,status="PENDING").count(),"open_tasks":Task.objects.filter(assigned_to__in=qs).exclude(status="DONE").count(),"payroll":str(Payroll.objects.filter(employee__in=qs).aggregate(s=Sum("final_salary"))["s"] or 0)}
def explain_salary_change(user):
    qs = Payroll.objects.filter(
        employee=user
    ).order_by("-year", "-month")[:2]

    records = list(qs)

    if not records:
        return {
            "found": False,
            "message": "No payroll records found."
        }

    current = records[0]

    if len(records) < 2:
        return {
            "found": True,
            "message": "Only one payroll record is available, so I cannot compare it with a previous month.",
            "current_salary": str(current.final_salary),
            "current_period": f"{current.month}/{current.year}"
        }

    previous = records[1]

    current_salary = Decimal(str(current.final_salary))
    previous_salary = Decimal(str(previous.final_salary))
    difference = current_salary - previous_salary

    reasons = []

    if current.deductions > previous.deductions:
        reasons.append(
            f"deductions increased from ₹{previous.deductions} to ₹{current.deductions}"
        )

    if current.present_days < previous.present_days:
        reasons.append(
            f"present days decreased from {previous.present_days} to {current.present_days}"
        )

    if current.leave_days > previous.leave_days:
        reasons.append(
            f"leave days increased from {previous.leave_days} to {current.leave_days}"
        )

    if current.bonus < previous.bonus:
        reasons.append(
            f"bonus decreased from ₹{previous.bonus} to ₹{current.bonus}"
        )

    if not reasons:
        reasons.append(
            "the payroll calculation changed for reasons not captured by the available payroll fields"
        )

    return {
        "found": True,
        "current_period": f"{current.month}/{current.year}",
        "previous_period": f"{previous.month}/{previous.year}",
        "current_salary": str(current.final_salary),
        "previous_salary": str(previous.final_salary),
        "difference": str(difference),
        "reasons": reasons
    }