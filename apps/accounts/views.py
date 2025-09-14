from django.contrib.auth import login
from .forms import SignupForm
from django.shortcuts import render, redirect
from apps.billing.services import get_or_create_stripe_customer

def signup(request):
    if request.method == "POST":
        form = SignupForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            # Cria Customer no Stripe ao cadastrar
            get_or_create_stripe_customer(user)
            return redirect("dashboard:index")
    else:
        form = SignupForm()
    return render(request, "accounts/signup.html", {"form": form})
