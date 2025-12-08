#!/usr/bin/env python
"""
ThermostatRTOS Platform - Django Management Script

Django's command-line utility for administrative tasks such as
running the development server, database migrations, and shell access.

Author:     Gonzalo Patino
Created:    2025
Course:     Southern New Hampshire University
License:    Academic Use Only - See LICENSE file

Usage:
    python manage.py runserver
    python manage.py migrate
    python manage.py createsuperuser
"""
import os
import sys


def main():
    """Run administrative tasks."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
