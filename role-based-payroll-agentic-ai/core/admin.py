from django.contrib import admin
from .models import Company, Department, Team, User, Attendance, Leave, Payroll, Task, KnowledgeDocument, Notification, AgentAuditLog

for model in [Company, Department, Team, User, Attendance, Leave, Payroll, Task, KnowledgeDocument, Notification, AgentAuditLog]:
    admin.site.register(model)
