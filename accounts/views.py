from django.shortcuts import render, redirect
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .forms import RegisterForm, LoginForm


def register_view(request):
    if request.user.is_authenticated:
        return redirect('movies:home')
    form = RegisterForm()
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, 'Welcome! Account created successfully.')
            return redirect('movies:home')
    return render(request, 'accounts/register.html', {'form': form})


def login_view(request):
    if request.user.is_authenticated:
        return redirect('movies:home')
    form = LoginForm(request)
    if request.method == 'POST':
        form = LoginForm(request, request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            next_url = request.GET.get('next', 'movies:home')
            return redirect(next_url)
    return render(request, 'accounts/login.html', {'form': form})


def logout_view(request):
    logout(request)
    return redirect('movies:home')


@login_required
def profile_view(request):
    from movies.models import Booking
    bookings = Booking.objects.filter(user=request.user).select_related(
        'show__movie', 'show__screen__theater'
    ).prefetch_related('seats').order_by('-created_at')
    return render(request, 'accounts/profile.html', {'bookings': bookings})
