"""
ThermostatRTOS Platform - Root URL Configuration

This module defines the root URL routing for the Django project:
    - /admin/ - Django admin interface
    - /api/ - REST API endpoints
    - /accounts/ - User authentication pages
    - /dashboard/ - User dashboard views
    - /health/ - Health check endpoint

Author:     Gonzalo Patino
Created:    2025
Course:     Southern New Hampshire University
License:    Academic Use Only - See LICENSE file

For URL routing reference:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
"""

from django.contrib import admin
from django.urls import path, include
from .views import health

from django.contrib.auth import views as auth_views
from apps.api import views as api_views
from django.shortcuts import redirect


def root_redirect(request):
    return redirect("login")  # uses the name="login" URL


urlpatterns = [
    
     # Auth HTML views
    path("", root_redirect, name="root-redirect"),
    path("accounts/register/", api_views.register_page, name="register"),
    path("accounts/login/", auth_views.LoginView.as_view( template_name="registration/login.html"),name="login",),
    path("accounts/logout/", api_views.logout_view, name="logout_view",),
    path("dashboard/devices/", api_views.dashboard_devices, name="dashboard_devices",),
    path(
        "dashboard/devices/<int:device_id>/",
        api_views.dashboard_device_detail,
        name="dashboard_device_detail",
    ),
    path(
        "dashboard/devices/register/",
        api_views.dashboard_register_device,
        name="dashboard_register_device",
    ),
    path(
        "dashboard/settings/",
        api_views.user_settings,
        name="user_settings",
    ),
    path(
        "dashboard/data-management/",
        api_views.data_management,
        name="data_management",
    ),
    
    path("about/", api_views.about, name="about"),

     # API auth (for Postman / programmatic)
    path('admin/', admin.site.urls),
    path('api/health/', health),
    path("api/", include("apps.api.urls")),

   


   
    
    

]
