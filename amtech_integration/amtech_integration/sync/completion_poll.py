"""
completion_poll.py
==================
Scheduled job that polls Amtech Sign & Drive for completed/updated delivery trips
and writes results back to ERPNext Delivery Notes (OSD, receipt number, etc.).

Runs every N minutes per the scheduler_events cron in hooks.py.
"""

import json
from datetime import date, timedelta

import frappe
from amtech_integration.amtech_integration.client.amtech_client import AmtechClient, AmtechAPIError


def poll_completed_deliveries():
    """
    Scheduled entry point.
    Fetches today's trips from Amtech and reconciles them with ERPNext.
    """
    settings = frappe.get_single("Amtech Settings")
    if not settings.auto_sync_deliveries:
        return

    today = str(date.today())
    _sync_trips_for_date(today, settings)


def _sync_trips_for_date(delivery_date: str, settings=None):
    """
    Fetch all Amtech trips for a given date and update matching Delivery Notes.

    Args:
        delivery_date: ISO date string YYYY-MM-DD
        settings: Amtech Settings singleton (fetched if not provided)
    """
    if settings is None:
        settings = frappe.get_single("Amtech Settings")

    log = frappe.get_doc({
        "doctype":      "Amtech Sync Log",
        "sync_type":    "Completion Poll",
        "sync_date":    frappe.utils.now_datetime(),
        "status":       "Error",
    })

    try:
        client = AmtechClient()
        trips  = client.get_truck_trips(delivery_date=delivery_date)

        received  = 0
        updated   = 0
        failed    = 0

        for trip in trips:
            try:
                result = _process_completed_trip(trip, settings)
                received += 1
                if result:
                    updated += 1
            except Exception as e:
                failed += 1
                frappe.log_error(str(e), f"Amtech poll: failed processing trip {trip.get('TruckTripID')}")

        log.status           = "Success" if failed == 0 else "Partial"
        log.records_received = received
        log.records_sent     = 0
        log.records_failed   = failed
        log.response_payload = json.dumps(trips[:5], indent=2)  # First 5 for brevity

        _update_settings_last_sync(
            log.status,
            f"Polled {delivery_date}: {received} trips received, {updated} DN updated, {failed} failed"
        )

    except AmtechAPIError as e:
        log.status        = "Error"
        log.error_message = str(e)
        _update_settings_last_sync("Error", str(e))

    finally:
        log.insert(ignore_permissions=True)
        frappe.db.commit()


def _process_completed_trip(trip: dict, settings) -> bool:
    """
    For a single Amtech TruckHdr, find the matching ERPNext Delivery Note
    (by amtech_trip_id or by matching order number in Truck_Dtl) and update it.

    Returns True if a Delivery Note was updated, False otherwise.
    """
    trip_id  = str(trip.get("TruckTripID") or "")
    details  = trip.get("Truck_Dtl") or []
    if not details:
        return False

    # Find order number from first detail line
    order_no = (details[0].get("OrderNo") or details[0].get("OrderID") or "").strip()
    if not order_no:
        return False

    # Try to locate the Delivery Note
    dn_name = None

    # Method 1: match by amtech_trip_id custom field
    if trip_id:
        dn_name = frappe.db.get_value("Delivery Note", {"amtech_trip_id": trip_id}, "name")

    # Method 2: match by name (OrderNo IS the Delivery Note name)
    if not dn_name and frappe.db.exists("Delivery Note", order_no):
        dn_name = order_no

    if not dn_name:
        return False

    dn = frappe.get_doc("Delivery Note", dn_name)

    # Build update notes
    notes_lines = []

    for dtl in details:
        item_no  = dtl.get("ItemNo") or dtl.get("ItemID") or ""
        qty_ship = dtl.get("QTYShipped",   0)
        qty_del  = dtl.get("QTYDelivered", 0)
        qty_adj  = dtl.get("QTYAdjusted",  0)
        osd_type = dtl.get("OSDType",    "").strip()
        osd_note = dtl.get("OSDComment", "").strip()
        dr_no    = dtl.get("DeliveryReceiptNo", "").strip()

        if dr_no:
            notes_lines.append(f"Receipt# {dr_no} | Item {item_no}: Shipped {qty_ship}, Delivered {qty_del}")

        if osd_type and settings.include_osd_notes:
            notes_lines.append(f"  OSD [{osd_type}] {item_no}: Adjusted {qty_adj} — {osd_note}")

    if notes_lines:
        amtech_note = (
            f"\n--- Amtech Sign & Drive Update (TripID {trip_id}) ---\n"
            + "\n".join(notes_lines)
        )
        receiver = trip.get("ReceiverName", "").strip()
        if receiver:
            amtech_note += f"\nSigned by: {receiver}"

        # Append to internal notes / instructions
        current = dn.instructions or ""
        frappe.db.set_value(
            "Delivery Note", dn_name, "instructions",
            (current + "\n" + amtech_note).strip()
        )
        frappe.db.commit()
        return True

    return False


def _update_settings_last_sync(status: str, message: str):
    frappe.db.set_value("Amtech Settings", None, {
        "last_sync_at":      frappe.utils.now_datetime(),
        "last_sync_status":  status,
        "last_sync_message": message[:500],
    })
