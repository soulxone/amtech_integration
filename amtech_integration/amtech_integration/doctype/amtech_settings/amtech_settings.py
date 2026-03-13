import frappe
from frappe.model.document import Document


class AmtechSettings(Document):
    """Singleton settings for the Amtech Encore ERP / Sign & Drive integration."""

    @frappe.whitelist()
    def test_connection(self):
        """Manually test the API connection and cache a fresh token."""
        from amtech_integration.amtech_integration.client.amtech_client import AmtechClient
        try:
            client = AmtechClient()
            token = client.authenticate(force=True)
            if token:
                return {"status": "success", "message": "Connection successful. Bearer token obtained."}
            return {"status": "error", "message": "Authentication returned no token."}
        except Exception as e:
            frappe.log_error(str(e), "Amtech Connection Test Failed")
            return {"status": "error", "message": str(e)}
