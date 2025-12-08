"""
ThermostatRTOS Platform - ASGI Configuration

ASGI (Asynchronous Server Gateway Interface) configuration for async deployment.
Exposes the ASGI callable as a module-level variable named 'application'.

Author:     Gonzalo Patino
Created:    2025
Course:     Southern New Hampshire University
License:    Academic Use Only - See LICENSE file

For ASGI deployment reference:
    https://docs.djangoproject.com/en/5.2/howto/deployment/asgi/
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

application = get_asgi_application()
