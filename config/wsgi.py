"""
ThermostatRTOS Platform - WSGI Configuration

WSGI (Web Server Gateway Interface) configuration for production deployment.
Exposes the WSGI callable as a module-level variable named 'application'.

Author:     Gonzalo Patino
Created:    2025
Course:     Southern New Hampshire University
License:    Academic Use Only - See LICENSE file

For WSGI deployment reference:
    https://docs.djangoproject.com/en/5.2/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

application = get_wsgi_application()
