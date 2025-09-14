from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.http import HttpResponseBadRequest
from django.utils import timezone
from django.utils.dateparse import parse_date
from datetime import datetime, time
from django.core.paginator import Paginator
from django.db.models import F, ExpressionWrapper, IntegerField
from .models import MeteringEvent

def _parse_range(request):
    tz = timezone.get_current_timezone()
    s = request.GET.get("start")
    e = request.GET.get("end")
    period = request.GET.get("period")
    if period and len(period) == 7 and period[4] == '-':
        try:
            year = int(period[:4]); month = int(period[5:7])
            ds = timezone.datetime(year, month, 1, tzinfo=tz)
            start = ds
            if month == 12:
                de = timezone.datetime(year+1, 1, 1, tzinfo=tz)
            else:
                de = timezone.datetime(year, month+1, 1, tzinfo=tz)
            end = de
            return start, end
        except Exception:
            pass
    if s:
        try:
            ds = parse_date(s)
            start = datetime.combine(ds, time.min, tzinfo=tz)
        except Exception:
            start = datetime.combine(timezone.localdate().replace(day=1), time.min, tzinfo=tz)
    else:
        start = datetime.combine(timezone.localdate().replace(day=1), time.min, tzinfo=tz)
    if e:
        try:
            de = parse_date(e)
            end = datetime.combine(de, time.max, tzinfo=tz)
        except Exception:
            end = timezone.now()
    else:
        end = timezone.now()
    return start, end


def _fmt_brl(cents: int) -> str:
    try:
        v = (cents or 0) / 100.0
        txt = f"{v:,.2f}"
        return "R$ " + txt.replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return f"R$ {cents/100:.2f}"


@login_required
def events_view(request):
    start, end = _parse_range(request)
    etype = request.GET.get("type") or ""
    page_no = int(request.GET.get("page") or 1)

    qs = MeteringEvent.objects.filter(user=request.user, occurred_at__gte=start, occurred_at__lt=end)
    if etype:
        qs = qs.filter(event_type=etype)
    qs = qs.order_by("-occurred_at")

    paginator = Paginator(qs, 20)
    page = paginator.get_page(page_no)

    subtotal_expr = ExpressionWrapper(F("quantity") * F("unit_price_cents"), output_field=IntegerField())
    rows = []
    for ev in page.object_list:
        rows.append({
            "occurred_at": ev.occurred_at,
            "resource_type": ev.resource_type,
            "event_type": ev.event_type,
            "quantity": ev.quantity,
            "unit_price": _fmt_brl(ev.unit_price_cents or 0),
            "subtotal": _fmt_brl((ev.quantity or 0) * (ev.unit_price_cents or 0)),
        })

    period_str = f"{start.year:04d}-{start.month:02d}"
    return render(request, "metering/_events.html", {
        "rows": rows,
        "page": page,
        "etype": etype,
        "period": period_str,
    })
