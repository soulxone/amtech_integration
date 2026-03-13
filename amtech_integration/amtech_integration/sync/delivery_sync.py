"""
delivery_sync.py
================
Pushes ERPNext Delivery Notes to Amtech Sign & Drive when submitted.

Hook target:
    doc_events → Delivery Note → on_submit
"""

import json
import frappe
from amtech_integration.amtech_integration.client.amtech_client import AmtechClient, AmtechAPIError


def on_delivery_submit(doc, method=None):
    """
    Called automatically when a Delivery Note is submitted.
    Checks whether auto-sync is enabled, then pushes the trip to Amtech.
    """
    settings = frappe.get_single("Amtech Settings")
    if not settings.auto_sync_deliveries or not settings.sync_on_submit:
        return

    try:
        push_delivery_note(doc)
    except Exception as e:
        # Don't block the submit — just log the error
        frappe.log_error(frappe.get_traceback(), f"Amtech: Failed to sync {doc.name}")
        frappe.msgprint(
            f"Amtech sync warning: {e}. The delivery note was submitted, "
            "but could not be pushed to Amtech Sign & Drive. Check Amtech Sync Logs.",
            alert=True,
            indicator="orange",
        )


def push_delivery_note(delivery_note_doc_or_name) -> dict:
    """
    Push a single ERPNext Delivery Note to Amtech Sign & Drive.

    Args:
        delivery_note_doc_or_name: Delivery Note document or name string.

    Returns:
        Amtech API response dict (TruckHdr with TruckTripID).
    """
    if isinstance(delivery_note_doc_or_name, str):
        dn = frappe.get_doc("Delivery Note", delivery_note_doc_or_name)
    else:
        dn = delivery_note_doc_or_name

    client  = AmtechClient()
    payload = AmtechClient.build_trip_payload(dn)

    log = frappe.get_doc({
        "doctype":           "Amtech Sync Log",
        "sync_type":         "Delivery Push",
        "sync_date":         frappe.utils.now_datetime(),
        "reference_doctype": "Delivery Note",
        "reference_name":    dn.name,
        "request_payload":   json.dumps(payload, indent=2),
        "status":            "Error",  # Assume error until success confirmed
    })

    try:
        response      = client.create_truck_trip(payload)
        trip_id       = response.get("TruckTripID") or response.get("TruckHdrID") or ""
        log.status            = "Success"
        log.records_sent      = 1
        log.amtech_trip_id    = str(trip_id)
        log.response_payload  = json.dumps(response, indent=2)

        # Store Amtech trip ID back on the Delivery Note for future reference
        if trip_id:
            frappe.db.set_value("Delivery Note", dn.name, "amtech_trip_id", str(trip_id))

        # Update last sync in Settings
        _update_settings_last_sync("Success", f"Pushed {dn.name} → Amtech TripID {trip_id}")

    except AmtechAPIError as e:
        log.status        = "Error"
        log.error_message = str(e)
        _update_settings_last_sync("Error", str(e))
        raise

    finally:
        log.insert(ignore_permissions=True)
        frappe.db.commit()

    return response


def _update_settings_last_sync(status: str, message: str):
    """Update the last sync status fields on Amtech Settings."""
    frappe.db.set_value("Amtech Settings", None, {
        "last_sync_at":      frappe.utils.now_datetime(),
        "last_sync_status":  status,
        "last_sync_message": message[:500],
    })
