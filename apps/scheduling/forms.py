from decimal import Decimal
from django import forms
from django.conf import settings
from .models import SchedulingService, ServiceAvailability, ServiceOption


class SchedulingServiceForm(forms.ModelForm):
    price_cents = forms.DecimalField(
        label="Preço base (R$)",
        max_digits=9,
        decimal_places=2,
        min_value=Decimal("0.00"),
        widget=forms.NumberInput(attrs={"class": "input", "step": "0.01"}),
    )

    class Meta:
        model = SchedulingService
        fields = [
            "name",
            "price_cents",
            "description",
            "timezone",
            "duration_minutes",
            "type",
            "video_link_template",
            "buffer_before",
            "buffer_after",
            "lead_time_min",
            "cancel_min",
            "resched_min",
            "is_active",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "input"}),
            "description": forms.Textarea(attrs={"rows": 3, "class": "textarea"}),
            "timezone": forms.Select(attrs={"class": "select"}),
            "duration_minutes": forms.NumberInput(attrs={"class": "input"}),
            "type": forms.Select(attrs={"class": "select"}),
            "video_link_template": forms.TextInput(attrs={"class": "input"}),
            "buffer_before": forms.NumberInput(attrs={"class": "input"}),
            "buffer_after": forms.NumberInput(attrs={"class": "input"}),
            "lead_time_min": forms.NumberInput(attrs={"class": "input"}),
            "cancel_min": forms.NumberInput(attrs={"class": "input"}),
            "resched_min": forms.NumberInput(attrs={"class": "input"}),
            "is_active": forms.CheckboxInput(attrs={"class": "checkbox"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        common_tzs = [
            "UTC",
            getattr(settings, "TIME_ZONE", "UTC"),
            "America/Sao_Paulo",
            "America/New_York",
            "Europe/London",
            "Europe/Lisbon",
            "Europe/Berlin",
        ]
        # ensure current value is present
        inst_tz = getattr(getattr(self, "instance", None), "timezone", None)
        if inst_tz and inst_tz not in common_tzs:
            common_tzs.append(inst_tz)
        choices = sorted({(tz, tz) for tz in common_tzs}, key=lambda x: x[0])
        self.fields["timezone"] = forms.ChoiceField(choices=choices, initial=inst_tz or getattr(settings, "TIME_ZONE", "UTC"))
        price = getattr(getattr(self, "instance", None), "price_cents", 0) or 0
        self.fields["price_cents"].initial = Decimal(price) / Decimal(100)

    def clean_price_cents(self):
        value = self.cleaned_data.get("price_cents") or Decimal("0.00")
        return int((value * 100).quantize(Decimal("1")))


class ServiceAvailabilityForm(forms.ModelForm):
    class Meta:
        model = ServiceAvailability
        fields = [
            "rule_type",
            "weekday",
            "start_time",
            "end_time",
            "date",
            "timezone",
        ]
        widgets = {
            "rule_type": forms.Select(attrs={"class": "select"}),
            "weekday": forms.NumberInput(attrs={"class": "input", "min": 0, "max": 6, "placeholder": "0=Seg..6=Dom"}),
            "start_time": forms.TimeInput(attrs={"class": "input", "placeholder": "HH:MM"}),
            "end_time": forms.TimeInput(attrs={"class": "input", "placeholder": "HH:MM"}),
            "date": forms.DateInput(attrs={"class": "input", "placeholder": "YYYY-MM-DD"}),
        }

    def clean(self):
        cleaned = super().clean()
        rtype = cleaned.get("rule_type")
        weekday = cleaned.get("weekday")
        start_time = cleaned.get("start_time")
        end_time = cleaned.get("end_time")
        date = cleaned.get("date")

        if rtype == "weekly":
            if weekday is None:
                self.add_error("weekday", "Obrigatório para regra semanal")
            if not start_time or not end_time:
                self.add_error("start_time", "Obrigatório")
                self.add_error("end_time", "Obrigatório")
        elif rtype == "date_override":
            if not date:
                self.add_error("date", "Data obrigatória")
            if not start_time or not end_time:
                self.add_error("start_time", "Obrigatório")
                self.add_error("end_time", "Obrigatório")
        elif rtype == "holiday":
            if not date:
                self.add_error("date", "Data obrigatória")
        return cleaned

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        common_tzs = [
            "",
            "UTC",
            getattr(settings, "TIME_ZONE", "UTC"),
            "America/Sao_Paulo",
            "America/New_York",
            "Europe/London",
            "Europe/Lisbon",
            "Europe/Berlin",
        ]
        inst_tz = getattr(getattr(self, "instance", None), "timezone", None)
        if inst_tz and inst_tz not in common_tzs:
            common_tzs.append(inst_tz)
        choices = [(tz, tz) for tz in common_tzs]
        self.fields["timezone"] = forms.ChoiceField(choices=choices, required=False, initial=inst_tz)


class ServiceOptionForm(forms.ModelForm):
    price_delta_cents = forms.DecimalField(
        label="Variação de preço (R$)",
        max_digits=9,
        decimal_places=2,
        min_value=Decimal("0.00"),
        widget=forms.NumberInput(attrs={"class": "input", "step": "0.01"}),
        required=False,
    )

    class Meta:
        model = ServiceOption
        fields = [
            "name",
            "description",
            "price_delta_cents",
            "extra_duration_minutes",
            "order",
            "is_active",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "input"}),
            "description": forms.Textarea(attrs={"rows": 2, "class": "textarea"}),
            "extra_duration_minutes": forms.NumberInput(attrs={"class": "input", "min": 0}),
            "order": forms.NumberInput(attrs={"class": "input", "min": 0}),
            "is_active": forms.CheckboxInput(attrs={"class": "checkbox"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        price = getattr(getattr(self, "instance", None), "price_delta_cents", 0) or 0
        self.fields["price_delta_cents"].initial = Decimal(price) / Decimal(100)

    def clean_price_delta_cents(self):
        value = self.cleaned_data.get("price_delta_cents")
        if value is None:
            return 0
        return int((Decimal(value) * 100).quantize(Decimal("1")))
