app_name = "amtech_integration"
app_title = "Amtech Integration"
app_publisher = "Welch Packaging"
app_description = "Amtech Encore ERP / Sign & Drive integration for ERPNext"
app_email = "soulxone@gmail.com"
app_license = "MIT"

# Fixture adds a Custom Field on Delivery Note; sync hooks target ERPNext docs.
required_apps = ["frappe", "erpnext"]

# ── Document events ────────────────────────────────────────────────────────────
# Sync ERPNext Delivery Notes to Amtech Sign & Drive when submitted
doc_events = {
    "Delivery Note": {
        "on_submit": "amtech_integration.amtech_integration.sync.delivery_sync.on_delivery_submit",
    },
}

# ── Scheduled tasks ────────────────────────────────────────────────────────────
# Poll Amtech for completed deliveries every 15 minutes
scheduler_events = {
    "cron": {
        "*/15 * * * *": [
            "amtech_integration.amtech_integration.sync.completion_poll.poll_completed_deliveries"
        ]
    }
}

# ── Fixtures ───────────────────────────────────────────────────────────────────
fixtures = [
    {"doctype": "Amtech Settings", "filters": []},
    {
        "doctype": "Custom Field",
        "filters": [["name", "in", ["Delivery Note-amtech_trip_id"]]],
    },
]

# ── Delivery Note — "Push to Amtech" button ────────────────────────────────────
doctype_js = {
    "Delivery Note": "public/js/delivery_note_amtech.js",
}
