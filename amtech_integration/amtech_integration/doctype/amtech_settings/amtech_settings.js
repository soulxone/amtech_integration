// amtech_settings.js — Frappe form JS for Amtech Settings singleton

frappe.ui.form.on("Amtech Settings", {
    refresh(frm) {
        // ── Test Connection button ─────────────────────────────────────────────
        frm.add_custom_button(__("Test Connection"), () => {
            frappe.show_progress(__("Connecting to Amtech..."), 0, 100, __("Please wait"));
            frappe.call({
                method: "amtech_integration.amtech_integration.api.test_connection",
                callback(r) {
                    frappe.hide_progress();
                    const res = r.message || {};
                    if (res.status === "success") {
                        frappe.show_alert({ message: res.message, indicator: "green" }, 7);
                        frm.reload_doc();
                    } else {
                        frappe.msgprint({
                            title: __("Connection Failed"),
                            message: res.message || "Unknown error",
                            indicator: "red",
                        });
                    }
                },
            });
        }, __("Amtech API"));

        // ── Manual Poll button ─────────────────────────────────────────────────
        frm.add_custom_button(__("Poll Completions Now"), () => {
            frappe.prompt(
                [{ label: __("Delivery Date"), fieldname: "delivery_date", fieldtype: "Date",
                   default: frappe.datetime.get_today() }],
                ({ delivery_date }) => {
                    frappe.call({
                        method: "amtech_integration.amtech_integration.api.manual_poll",
                        args:   { delivery_date },
                        callback(r) {
                            const res = r.message || {};
                            frappe.show_alert({
                                message:   res.message || (res.status === "success" ? "Done" : "Error"),
                                indicator: res.status === "success" ? "green" : "red",
                            }, 6);
                            frm.reload_doc();
                        },
                    });
                },
                __("Poll Amtech Completions"), __("Run Poll")
            );
        }, __("Amtech API"));

        // ── View Sync Logs button ──────────────────────────────────────────────
        frm.add_custom_button(__("View Sync Logs"), () => {
            frappe.set_route("List", "Amtech Sync Log", "List");
        }, __("Amtech API"));

        // Show last sync status banner
        if (frm.doc.last_sync_at) {
            const color = { Success: "green", Partial: "orange", Error: "red" }[frm.doc.last_sync_status] || "blue";
            frm.dashboard.add_comment(
                `Last sync: <b>${frm.doc.last_sync_status || "—"}</b> at ${frm.doc.last_sync_at} — ${frm.doc.last_sync_message || ""}`,
                color, true
            );
        }
    },

    test_connection_btn(frm) {
        // Handles the inline Button field click
        frappe.call({
            method: "amtech_integration.amtech_integration.api.test_connection",
            callback(r) {
                const res = r.message || {};
                frappe.show_alert({
                    message:   res.message || "Done",
                    indicator: res.status === "success" ? "green" : "red",
                }, 7);
                if (res.status === "success") frm.reload_doc();
            },
        });
    },
});
