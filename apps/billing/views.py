import json
import random
from django.contrib.auth.decorators import login_required
import logging
from django.views.decorators.csrf import ensure_csrf_cookie
from django.http import JsonResponse, HttpResponse, HttpResponseBadRequest
from django.shortcuts import render, redirect
from django.views.decorators.csrf import csrf_exempt

from django.conf import settings
from .services import create_setup_intent, attach_payment_method, get_or_create_stripe_customer
from .models import UsageEvent, CustomerProfile

log = logging.getLogger(__name__)

@ensure_csrf_cookie
@login_required
def payment_method(request):
    prof = CustomerProfile.objects.filter(user=request.user).first()
    publishable = settings.STRIPE_PUBLISHABLE_KEY
    return render(request, "billing/payment_method.html", {"profile": prof, "pk": publishable})

@login_required
def create_setup_intent_view(request):
    si = create_setup_intent(request.user)
    log.info("[billing] API create_setup_intent user_id=%s si_id=%s", request.user.id, si.get("id"))
    return JsonResponse({"clientSecret": si["client_secret"]})

@login_required
def attach_payment_method_view(request):
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")
    pm = request.POST.get("payment_method_id")
    log.info("[billing] API attach_payment_method user_id=%s pm_id=%s", request.user.id, pm)
    if not pm:
        return HttpResponseBadRequest("missing payment_method_id")
    prof = attach_payment_method(request.user, pm)
    return render(request, "billing/_card_info.html", {"profile": prof})

@login_required
def cancel_view(request):
    prof = CustomerProfile.objects.get(user=request.user)
    prof.is_active = False
    prof.save(update_fields=["is_active"])
    return redirect("dashboard:index")

@login_required
def simulate_usage(request):
    units = int(request.POST.get("units") or random.randint(1, 5))
    UsageEvent.objects.create(user=request.user, units=units)
    # retorna parcial para HTMX atualizar contador
    month_units = UsageEvent.objects.filter(user=request.user).count()
    return render(request, "dashboard/_usage_stats.html", {"month_units": month_units})
