// delivery_note_amtech.js
// Adds "Push to Amtech" button on submitted Delivery Notes

frappe.ui.form.on("Delivery Note", {
    refresh(frm) {
        if (frm.doc.docstatus !== 1) return;  // Only on submitted DNs

        frm.add_custom_button(__("Push to Amtech Sign & Drive"), () => {
            frappe.confirm(
                __("Push <b>{0}</b> to Amtech Sign & Drive?", [frm.doc.name]),
                () => {
                    frappe.show_progress(__("Syncing to Amtech..."), 0, 100);
                    frappe.call({
                        method: "amtech_integration.amtech_integration.api.manual_push_delivery",
                        args: { delivery_note_name: frm.doc.name },
                        callback(r) {
                            frappe.hide_progress();
                            const res = r.message || {};
                            if (res.status === "success") {
                                frappe.show_alert({
                                    message: __("Synced to Amtech! Trip ID: {0}", [res.trip_id || "—"]),
                                    indicator: "green",
                                }, 7);
                                frm.reload_doc();
                            } else {
                                frappe.msgprint({
                                    title: __("Amtech Sync Failed"),
                                    message: res.message || "Unknown error",
                                    indicator: "red",
                                });
                            }
                        },
                    });
                }
            );
        }, __("Amtech"));

        // Show Amtech Trip ID badge if already synced
        if (frm.doc.amtech_trip_id) {
            frm.dashboard.add_comment(
                `✓ Amtech Trip ID: <b>${frm.doc.amtech_trip_id}</b>`,
                "green", true
            );
        }
    },
});
