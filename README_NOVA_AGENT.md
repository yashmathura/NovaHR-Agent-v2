# NovaHR Agent v2

This version changes the architecture from **LLM-first tool calling** to an **agent-owned orchestration layer**:

1. Router identifies common HR intents locally.
2. Agent chooses an ERP tool.
3. Tool executes against Django/PostgreSQL using the authenticated user.
4. Permission checks stay in server-side Python.
5. Every tool call is written to `AgentAuditLog`.
6. Gemini is used only as an optional fallback for open-ended questions, so Gemini quota outages do not break core HR actions.

## New agent actions

- `mark_attendance`
- `checkout_attendance`
- `get_leave_balance`
- `apply_leave`
- `get_attendance`
- `get_payroll`
- `get_tasks`
- `get_policy`
- `analyze_performance`
- `assign_task`
- `send_notification`
- `list_team_attendance`

## Run

```powershell
.venv\Scripts\activate
python manage.py migrate
python manage.py seed_demo
python manage.py runserver
```

Open `http://127.0.0.1:8000/agent/`.

## Important security note

The uploaded project contained a Gemini API key in `.env`. The deliverable intentionally does **not** include that `.env`. If that key was ever exposed or committed, rotate/revoke it and create a new key. Put the new key only in your local `.env`.
