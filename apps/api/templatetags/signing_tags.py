# apps/api/templatetags/signing_tags.py
"""
Template tags for URL signing.
"""
from django import template
from apps.api.signing import encode_serial

register = template.Library()


@register.filter
def signed_serial(serial: str) -> str:
    """
    Template filter to encode a serial number.
    
    Usage in templates:
        {{ device.serial_number|signed_serial }}
    """
    if not serial:
        return ""
    return encode_serial(serial)