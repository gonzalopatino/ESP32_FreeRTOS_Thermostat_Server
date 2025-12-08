"""
Dashboard HTML views - device management, data management, and settings pages.
"""

from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_http_methods

from ..models import (
    Device,
    DeviceAlertSettings,
    DeviceApiKey,
    StoragePlan,
    TelemetrySnapshot,
    UserStorageProfile,
)
from .helpers import _recent_telemetry_qs_for_device


@login_required
@require_http_methods(["GET", "POST"])
def data_management(request):
    """
    Data management page for users to view storage usage and delete telemetry.
    
    GET: Display storage gauge and deletion options
    POST: Handle data deletion requests
    """
    user = request.user
    
    # Get or create storage profile
    try:
        storage_profile = user.storage_profile
    except UserStorageProfile.DoesNotExist:
        storage_profile = UserStorageProfile.objects.create(user=user)
    
    # Get user's devices with telemetry counts
    devices = Device.objects.filter(owner=user).order_by('name', 'serial_number')
    
    device_stats = []
    for device in devices:
        count = TelemetrySnapshot.objects.filter(device_id=device.serial_number).count()
        
        # Get date range
        first_snapshot = TelemetrySnapshot.objects.filter(
            device_id=device.serial_number
        ).order_by('server_ts').first()
        
        last_snapshot = TelemetrySnapshot.objects.filter(
            device_id=device.serial_number
        ).order_by('-server_ts').first()
        
        device_stats.append({
            'device': device,
            'count': count,
            'first_date': first_snapshot.server_ts if first_snapshot else None,
            'last_date': last_snapshot.server_ts if last_snapshot else None,
        })
    
    # Calculate total telemetry count
    total_count = sum(d['count'] for d in device_stats)
    
    if request.method == "POST":
        action = request.POST.get("action")
        
        if action == "refresh_usage":
            # Recalculate storage usage
            storage_profile.refresh_usage_cache()
            messages.success(request, "Storage usage has been recalculated.")
            return redirect("data_management")
        
        elif action == "delete_device_data":
            device_serial = request.POST.get("device_serial")
            
            if device_serial:
                # Verify device belongs to user
                device = Device.objects.filter(
                    owner=user, 
                    serial_number=device_serial
                ).first()
                
                if device:
                    deleted_count, _ = TelemetrySnapshot.objects.filter(
                        device_id=device_serial
                    ).delete()
                    
                    # Refresh storage cache
                    storage_profile.refresh_usage_cache()
                    
                    messages.success(
                        request, 
                        f"Deleted {deleted_count:,} telemetry records from {device.name or device.serial_number}."
                    )
                else:
                    messages.error(request, "Device not found or access denied.")
            
            return redirect("data_management")
        
        elif action == "delete_date_range":
            device_serial = request.POST.get("device_serial")
            from_date = request.POST.get("from_date")
            to_date = request.POST.get("to_date")
            
            if device_serial and from_date and to_date:
                # Verify device belongs to user
                device = Device.objects.filter(
                    owner=user,
                    serial_number=device_serial
                ).first()
                
                if device:
                    try:
                        from_dt = parse_datetime(from_date + "T00:00:00Z")
                        to_dt = parse_datetime(to_date + "T23:59:59Z")
                        
                        if from_dt and to_dt:
                            deleted_count, _ = TelemetrySnapshot.objects.filter(
                                device_id=device_serial,
                                server_ts__gte=from_dt,
                                server_ts__lte=to_dt
                            ).delete()
                            
                            # Refresh storage cache
                            storage_profile.refresh_usage_cache()
                            
                            messages.success(
                                request,
                                f"Deleted {deleted_count:,} telemetry records from {from_date} to {to_date}."
                            )
                        else:
                            messages.error(request, "Invalid date format.")
                    except Exception as e:
                        messages.error(request, f"Error parsing dates: {e}")
                else:
                    messages.error(request, "Device not found or access denied.")
            else:
                messages.error(request, "Please provide device, from date, and to date.")
            
            return redirect("data_management")
        
        elif action == "delete_all_data":
            # Delete ALL telemetry for ALL user's devices
            confirm = request.POST.get("confirm_delete_all")
            
            if confirm == "DELETE ALL MY DATA":
                device_serials = list(devices.values_list('serial_number', flat=True))
                
                deleted_count, _ = TelemetrySnapshot.objects.filter(
                    device_id__in=device_serials
                ).delete()
                
                # Refresh storage cache
                storage_profile.refresh_usage_cache()
                
                messages.success(
                    request,
                    f"Deleted all {deleted_count:,} telemetry records from all devices."
                )
            else:
                messages.error(
                    request, 
                    "Please type 'DELETE ALL MY DATA' to confirm deletion."
                )
            
            return redirect("data_management")
    
    # Refresh usage cache if stale (older than 1 hour)
    if (not storage_profile.usage_last_calculated or 
        timezone.now() - storage_profile.usage_last_calculated > timedelta(hours=1)):
        storage_profile.refresh_usage_cache()
    
    context = {
        "user": user,
        "storage_profile": storage_profile,
        "device_stats": device_stats,
        "total_count": total_count,
        "plan_choices": StoragePlan.CHOICES,
    }
    
    return render(request, "dashboard/data_management.html", context)


# ---------------------------------------------------------------------------
# Dashboard HTML views
# ---------------------------------------------------------------------------

@login_required
def dashboard_devices(request):
    """
    Dashboard landing page: list devices for the logged-in user.
    """
    devices = (
        Device.objects
        .filter(owner=request.user)
        .annotate(
            active_key_count=Count(
                "api_keys",
                filter=Q(api_keys__is_active=True),
            )
        )
        .prefetch_related("api_keys")
        .order_by("id")
    )

    context = {
        "devices": devices,
    }
    return render(request, "dashboard/devices.html", context)


@login_required
def dashboard_register_device(request):
    """
    HTML form to register or claim a device for the logged-in user.

    This is the view behind the 'Register New Device' navbar tab.
    """
    if request.method == "POST":
        serial = request.POST.get("serial_number", "").strip()
        name = request.POST.get("name", "").strip()

        if not serial:
            messages.error(request, "Serial number is required.")
            return redirect("dashboard_register_device")

        # Try to find an existing device with this serial
        try:
            device = Device.objects.get(serial_number=serial)
            if device.owner != request.user:
                messages.error(
                    request,
                    "This device serial is already registered to another user.",
                )
                return redirect("dashboard_register_device")
            # Device is already owned by this user, optional rename
            if name:
                device.name = name
                device.save()
        except Device.DoesNotExist:
            # Create a new device and assign to this user
            device = Device.objects.create(
                owner=request.user,
                serial_number=serial,
                name=name,
            )

        # Rotate keys: deactivate all previous keys
        device.api_keys.update(is_active=False)

        # Create a fresh API key and get the raw value once
        api_key_obj, raw_key = DeviceApiKey.create_for_device(device, ttl_days=365)

        # Show the QR code page with the API key
        # The QR code contains the raw API key for the phone camera to scan
        qr_content = raw_key  # Just the raw key for scanning
        
        return render(
            request,
            "dashboard/device_api_key_qr.html",
            {
                "device": device,
                "api_key": raw_key,
                "qr_url": qr_content,
            },
        )

    # GET – show the registration form
    return render(request, "dashboard/register_device.html")


@login_required
def dashboard_device_detail(request, device_id: int):
    """
    Device detail page for the dashboard, including API key management
    and recent telemetry preview.
    """
    # Ensure the device belongs to the logged-in user
    device = get_object_or_404(Device, id=device_id, owner=request.user)

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "rotate":
            # Deactivate all existing keys
            device.api_keys.update(is_active=False)
            # Create a new key with 1-year TTL
            api_key_obj, raw_key = DeviceApiKey.create_for_device(
                device, ttl_days=365
            )
            # Show the QR code page with the new API key (raw key for scanning)
            qr_content = raw_key
            return render(
                request,
                "dashboard/device_api_key_qr.html",
                {
                    "device": device,
                    "api_key": raw_key,
                    "qr_url": qr_content,
                },
            )

        elif action == "revoke":
            key_id = request.POST.get("key_id")
            try:
                key = device.api_keys.get(id=key_id)
            except DeviceApiKey.DoesNotExist:
                messages.error(request, "API key not found for this device.")
            else:
                if not key.is_active:
                    messages.info(request, "This API key is already inactive.")
                else:
                    key.is_active = False
                    key.save()
                    messages.success(request, "API key revoked.")
            return redirect("dashboard_device_detail", device_id=device.id)

        elif action == "update_device":
            new_name = (request.POST.get("name") or "").strip()
            if not new_name:
                messages.error(request, "Device name cannot be empty.")
            else:
                device.name = new_name
                device.save(update_fields=["name"])
                messages.success(request, "Device name updated.")
            return redirect("dashboard_device_detail", device_id=device.id)

        elif action == "delete_device":
            serial = device.serial_number

            # Delete related API keys
            device.api_keys.all().delete()

            # Delete telemetry snapshots for this device (because not FK)
            TelemetrySnapshot.objects.filter(device_id=serial).delete()

            # Finally delete the device itself
            device.delete()

            messages.success(
                request,
                f"Device '{serial}' and all its telemetry have been deleted.",
            )
            return redirect("dashboard_devices")

        elif action == "update_alerts":
            # Get or create alert settings for this device
            alert_settings, created = DeviceAlertSettings.objects.get_or_create(
                device=device
            )
            
            # Update settings from form
            alert_settings.alerts_enabled = request.POST.get("alerts_enabled") == "on"
            alert_settings.high_temp_enabled = request.POST.get("high_temp_enabled") == "on"
            alert_settings.low_temp_enabled = request.POST.get("low_temp_enabled") == "on"
            
            try:
                alert_settings.high_temp_threshold = float(request.POST.get("high_temp_threshold", 30))
                alert_settings.low_temp_threshold = float(request.POST.get("low_temp_threshold", 10))
                alert_settings.min_alert_interval_minutes = int(request.POST.get("alert_interval", 30))
            except (ValueError, TypeError):
                messages.error(request, "Invalid threshold values provided.")
                return redirect("dashboard_device_detail", device_id=device.id)
            
            custom_email = request.POST.get("custom_email", "").strip()
            alert_settings.custom_email = custom_email if custom_email else None
            
            alert_settings.save()
            messages.success(request, "Email alert settings updated.")
            return redirect("dashboard_device_detail", device_id=device.id)

    # GET (or fallthrough after POST handling) – show device info and telemetry
    snapshots = _recent_telemetry_qs_for_device(device)
    keys = device.api_keys.order_by("-created_at")
    
    # Get or create alert settings
    alert_settings, _ = DeviceAlertSettings.objects.get_or_create(device=device)

    context = {
        "device": device,
        "snapshots": snapshots,
        "keys": keys,
        "alert_settings": alert_settings,
    }
    return render(request, "dashboard/device_detail.html", context)


@login_required
def about(request):
    """Simple About / metadata page."""
    return render(request, "about.html")
