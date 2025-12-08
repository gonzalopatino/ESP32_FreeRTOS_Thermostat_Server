"""
ThermostatRTOS Platform - API Application Configuration

Django application configuration for the API app.

Author:     Gonzalo Patino
Created:    2025
Course:     Southern New Hampshire University
License:    Academic Use Only - See LICENSE file
"""

from django.apps import AppConfig


class ApiConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.api'
