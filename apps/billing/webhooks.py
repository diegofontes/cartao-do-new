import json
from django.conf import settings
from django.http import HttpResponse, HttpResponseBadRequest
from django.urls import path
from django.views.decorators.csrf import csrf_exempt
import stripe
from .models import Invoice

@csrf_exempt
def webhook(request):
    payload = request.body
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE")
    try:
        event = stripe.Webhook.construct_event(
            payload=payload, sig_header=sig_header, secret=settings.STRIPE_WEBHOOK_SECRET
        )
    except Exception as e:
        return HttpResponseBadRequest(str(e))

    if event["type"] in {"invoice.payment_succeeded", "invoice.finalized", "invoice.payment_failed"}:
        inv_obj = event["data"]["object"]
        inv_id = inv_obj.get("id")
        status = inv_obj.get("status")
        hosted_url = inv_obj.get("hosted_invoice_url")
        try:
            inv = Invoice.objects.get(stripe_invoice_id=inv_id)
            inv.status = status or inv.status
            if hosted_url:
                inv.hosted_invoice_url = hosted_url
            inv.save(update_fields=["status", "hosted_invoice_url"])
        except Invoice.DoesNotExist:
            pass

    return HttpResponse("ok")

urlpatterns = [
    path("webhook/", webhook, name="stripe_webhook"),
]
