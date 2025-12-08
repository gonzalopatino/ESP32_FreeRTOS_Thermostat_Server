"""
Authentication views - both HTML pages and JSON API endpoints.
"""

import json

from django.contrib import messages
from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.http import HttpResponseBadRequest, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST, require_http_methods

from ..ratelimits import ratelimit_login, ratelimit_register

User = get_user_model()


# ---------------------------------------------------------------------------
# HTML auth views
# ---------------------------------------------------------------------------

def register_page(request):
    """
    Simple HTML registration view using Django's UserCreationForm.
    After successful registration, redirect to login page.
    """
    if request.method == "POST":
        form = UserCreationForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect("login")  # name of the login URL
    else:
        form = UserCreationForm()

    return render(request, "registration/register.html", {"form": form})


@login_required
def logout_view(request):
    """
    HTML logout for dashboard users.

    Logs out the current user and redirects to the login page.
    """
    logout(request)
    return redirect("login")


@login_required
@require_http_methods(["GET", "POST"])
def user_settings(request):
    """
    User account settings page.
    
    Allows users to update their profile information:
    - Username
    - Email address
    - First name
    - Last name
    - Password (optional)
    """
    user = request.user
    
    if request.method == "POST":
        # Get form data
        username = request.POST.get("username", "").strip()
        email = request.POST.get("email", "").strip()
        first_name = request.POST.get("first_name", "").strip()
        last_name = request.POST.get("last_name", "").strip()
        current_password = request.POST.get("current_password", "")
        new_password = request.POST.get("new_password", "")
        confirm_password = request.POST.get("confirm_password", "")
        
        errors = []
        
        # Validate username
        if not username:
            errors.append("Username is required.")
        elif username != user.username:
            # Check if username is already taken
            if User.objects.filter(username=username).exclude(pk=user.pk).exists():
                errors.append("This username is already taken.")
        
        # Validate email
        if not email:
            errors.append("Email address is required.")
        elif email != user.email:
            # Check if email is already taken
            if User.objects.filter(email=email).exclude(pk=user.pk).exists():
                errors.append("This email address is already in use.")
        
        # Validate password change (if attempting)
        if new_password or confirm_password:
            if not current_password:
                errors.append("Current password is required to set a new password.")
            elif not user.check_password(current_password):
                errors.append("Current password is incorrect.")
            elif new_password != confirm_password:
                errors.append("New passwords do not match.")
            elif len(new_password) < 8:
                errors.append("New password must be at least 8 characters long.")
        
        if errors:
            for error in errors:
                messages.error(request, error)
        else:
            # Update user fields
            user.username = username
            user.email = email
            user.first_name = first_name
            user.last_name = last_name
            
            # Update password if provided
            if new_password:
                user.set_password(new_password)
                user.save()
                # Re-authenticate to maintain session
                login(request, user)
                messages.success(request, "Your password has been updated. You have been re-authenticated.")
            else:
                user.save()
                messages.success(request, "Your account settings have been updated.")
            
            return redirect("user_settings")
    
    return render(request, "dashboard/settings.html", {"user": user})


# ---------------------------------------------------------------------------
# JSON auth endpoints
# ---------------------------------------------------------------------------

@require_POST
@ratelimit_register
def register_user(request):
    """
    Simple JSON registration endpoint.

    Body:
    {
        "username": "gonzalo",
        "password": "secret123",
        "email": "optional@example.com"
    }

    On success:
    - Creates a new user
    - Logs them in (session cookie)
    - Returns basic user info
    """
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return HttpResponseBadRequest("Invalid JSON")

    username = (payload.get("username") or "").strip()
    password = payload.get("password") or ""
    email = (payload.get("email") or "").strip()

    if not username or not password:
        return HttpResponseBadRequest("Fields 'username' and 'password' are required")

    if User.objects.filter(username=username).exists():
        return JsonResponse(
            {"detail": "Username already taken"},
            status=400,
        )

    user = User.objects.create_user(
        username=username,
        password=password,
        email=email or None,
    )

    # Log the user in so Postman gets a session cookie
    login(request, user)

    return JsonResponse(
        {
            "id": user.id,
            "username": user.username,
            "email": user.email,
        },
        status=201,
    )


@ratelimit_login
@require_POST
def login_user(request):
    """
    JSON login endpoint.

    Body:
    {
        "username": "gonzalo",
        "password": "secret123"
    }

    On success:
    - Logs in the user (session cookie)
    - Returns basic user info
    """
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return HttpResponseBadRequest("Invalid JSON")

    username = (payload.get("username") or "").strip()
    password = payload.get("password") or ""

    if not username or not password:
        return HttpResponseBadRequest("Fields 'username' and 'password' are required")

    user = authenticate(request, username=username, password=password)
    if user is None:
        return JsonResponse(
            {"detail": "Invalid credentials"},
            status=400,
        )

    login(request, user)

    return JsonResponse(
        {
            "id": user.id,
            "username": user.username,
            "email": user.email,
        }
    )


@require_POST
def logout_user(request):
    """
    Log out the current user (session-based).
    """
    logout(request)
    return JsonResponse({"status": "ok"})
