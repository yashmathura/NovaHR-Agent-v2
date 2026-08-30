import json
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import ensure_csrf_cookie
from django.http import JsonResponse
from django.shortcuts import render
from .service import run_agent

@login_required
@ensure_csrf_cookie
def chat_page(request): return render(request,"agent.html")

@login_required
@ensure_csrf_cookie
def chat_api(request):
    if request.method != "POST": return JsonResponse({"ok":False,"message":"POST required"},status=405)
    try: data=json.loads(request.body); message=(data.get("message") or "").strip()
    except Exception: return JsonResponse({"ok":False,"message":"Invalid JSON"},status=400)
    if not message: return JsonResponse({"ok":False,"message":"Message is required"},status=400)
    return JsonResponse(run_agent(request.user,message))
