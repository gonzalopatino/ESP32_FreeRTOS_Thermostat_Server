"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
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
