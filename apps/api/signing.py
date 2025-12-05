# apps/api/signing.py
"""
URL signing utilities for obfuscating sensitive identifiers in URLs.
Uses Django's built-in signing module for tamper-proof, opaque tokens.
"""
from django.core import signing

# Salt ensures tokens for different purposes can't be swapped
DEVICE_SERIAL_SALT = "device-serial-token"


def encode_serial(serial: str) -> str:
    """
    Encode a device serial number into an opaque, signed token.
    
    Example:
        "SN-123456" -> "eyJzZXJpYWwiOiJTTi0xMjM0NTYifQ:1tK2Xm:abc123..."
    """
    return signing.dumps({"serial": serial}, salt=DEVICE_SERIAL_SALT)


def decode_serial(token: str) -> str | None:
    """
    Decode a signed token back to the original serial number.
    
    Returns None if the token is invalid or tampered with.
    """
    try:
        data = signing.loads(token, salt=DEVICE_SERIAL_SALT)
        return data.get("serial")
    except signing.BadSignature:
        return None