"""
api.py — Whitelisted endpoints callable from the Frappe client.
"""
import json
import frappe
from amtech_integration.amtech_integration.client.amtech_client import AmtechClient, AmtechAPIError
from amtech_integration.amtech_integration.sync.delivery_sync  import push_delivery_note
from amtech_integration.amtech_integration.sync.completion_poll import _sync_trips_for_date


@frappe.whitelist()
def test_connection():
    """Test the Amtech API connection and cache a fresh token."""
    try:
        client = AmtechClient()
        token  = client.authenticate(force=True)
        return {"status": "success", "message": f"Connected. Token obtained ({len(token)} chars)."}
    except AmtechAPIError as e:
        return {"status": "error", "message": str(e)}
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Amtech test_connection error")
        return {"status": "error", "message": str(e)}


@frappe.whitelist()
def manual_push_delivery(delivery_note_name: str):
    """Manually push a single Delivery Note to Amtech Sign & Drive."""
    frappe.only_for("System Manager")
    try:
        resp = push_delivery_note(delivery_note_name)
        return {"status": "success", "trip_id": resp.get("TruckTripID"), "response": resp}
    except AmtechAPIError as e:
        return {"status": "error", "message": str(e)}
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Amtech manual_push_delivery error")
        return {"status": "error", "message": str(e)}


@frappe.whitelist()
def manual_poll(delivery_date: str = None):
    """Manually trigger a completion poll for the given date (default: today)."""
    frappe.only_for("System Manager")
    if not delivery_date:
        delivery_date = str(frappe.utils.today())
    try:
        _sync_trips_for_date(delivery_date)
        return {"status": "success", "message": f"Poll completed for {delivery_date}"}
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Amtech manual_poll error")
        return {"status": "error", "message": str(e)}


@frappe.whitelist()
def get_sync_logs(limit: int = 20):
    """Return the most recent Amtech Sync Log entries."""
    logs = frappe.get_list(
        "Amtech Sync Log",
        fields=["name", "sync_type", "sync_date", "status", "records_sent",
                "records_received", "records_failed", "reference_name",
                "amtech_trip_id", "error_message"],
        order_by="sync_date desc",
        limit_page_length=int(limit),
    )
    return logs
