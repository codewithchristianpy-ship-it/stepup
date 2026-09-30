from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required


def home(request):
    if request.user.is_authenticated:
        return redirect('core:dashboard')
    return render(request, 'core/home.html')


@login_required
def dashboard(request):
    wallet = request.user.wallet
    recent_tx = wallet.transactions.all()[:5]
    return render(request, 'core/dashboard.html', {
        'wallet': wallet,
        'recent_tx': recent_tx,
    })