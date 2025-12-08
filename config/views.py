"""
ThermostatRTOS Platform - Root Views

This module provides root-level views for the Django project.

Author:     Gonzalo Patino
Created:    2025
Course:     Southern New Hampshire University
License:    Academic Use Only - See LICENSE file
"""

from django.http import JsonResponse


def health(request):
    """
    Health check endpoint for load balancers and monitoring.
    
    Returns:
        JsonResponse: Status OK with message.
    """
    return JsonResponse( 

        {
            "status" : "ok",
            "message": "backend alive"
        }
    )