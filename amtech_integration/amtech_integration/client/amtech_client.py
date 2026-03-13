"""
Amtech Encore ERP / Sign & Drive REST client.

Authentication:
  POST /api/Account
    Authorization: Basic <base64(UserID:Password[:DataSourceId])>
    Returns: { LogoURL, DataSources: [{DataSourceKey, DataSourceName, LogoURL}] }
    The DataSourceKey from the preferred data source is then used as the Bearer token.

All subsequent calls:
    Authorization: Bearer <DataSourceKey>
"""

import base64
import json
from datetime import datetime, timedelta

import frappe
import requests


class AmtechAPIError(Exception):
    """Raised when the Amtech API returns an error response."""
    def __init__(self, status_code, message):
        self.status_code = status_code
        super().__init__(f"Amtech API error {status_code}: {message}")


class AmtechClient:
    """
    Thin wrapper around the Amtech Encore / Sign & Drive REST API.

    Usage:
        client = AmtechClient()
        trips  = client.get_truck_trips(delivery_date="2026-03-12")
        trip   = client.create_truck_trip(trip_payload)
    """

    # Token is cached in Amtech Settings to survive process restarts
    TOKEN_TTL_HOURS = 8

    def __init__(self):
        self._settings = frappe.get_single("Amtech Settings")
        base = (self._settings.base_url or "https://signanddrive.acmebox.com").rstrip("/")
        self.base_url = base
        self._token   = None

    # ── Authentication ─────────────────────────────────────────────────────────

    def authenticate(self, force: bool = False) -> str:
        """
        Obtain or return the cached Bearer token.

        The token is the DataSourceKey returned by POST /api/Account for the
        configured (or first available) data source.

        Args:
            force: If True, skip the cache and re-authenticate.

        Returns:
            Bearer token string.
        """
        if not force:
            # Check memory cache first
            if self._token:
                return self._token
            # Then persistent cache in Settings
            cached     = self._settings.token
            expires_at = self._settings.token_expires_at
            if cached and expires_at:
                try:
                    exp = datetime.strptime(str(expires_at), "%Y-%m-%d %H:%M:%S.%f")
                except ValueError:
                    exp = datetime.strptime(str(expires_at), "%Y-%m-%d %H:%M:%S")
                if exp > datetime.now():
                    self._token = cached
                    return self._token

        # Build credentials: UserID:Password[:DataSourceId]
        username = self._settings.username or ""
        password = self._settings.get_password("password") or ""
        ds_id    = self._settings.data_source_id or ""
        cred_str = f"{username}:{password}" + (f":{ds_id}" if ds_id else "")
        encoded  = base64.b64encode(cred_str.encode()).decode()

        resp = requests.post(
            f"{self.base_url}/api/Account",
            headers={"Authorization": f"Basic {encoded}"},
            timeout=30,
        )

        if resp.status_code != 200:
            raise AmtechAPIError(resp.status_code, resp.text[:500])

        data = resp.json()

        # Pick the configured data source or fall back to the first one
        sources = data.get("DataSources") or []
        if not sources:
            raise AmtechAPIError(0, "No DataSources returned from Amtech Account API")

        token = None
        if ds_id:
            for src in sources:
                if src.get("DataSourceKey") == ds_id or src.get("DataSourceName") == ds_id:
                    token = src["DataSourceKey"]
                    break
        if not token:
            token = sources[0]["DataSourceKey"]

        # Cache token in Settings with TTL
        expires = datetime.now() + timedelta(hours=self.TOKEN_TTL_HOURS)
        self._settings.db_set("token",            token)
        self._settings.db_set("token_expires_at", expires)
        self._token = token
        return token

    def _headers(self) -> dict:
        """Return Authorization header dict with current Bearer token."""
        return {
            "Authorization": f"Bearer {self.authenticate()}",
            "Content-Type":  "application/json",
            "Accept":        "application/json",
        }

    # ── Generic request helpers ────────────────────────────────────────────────

    def _get(self, path: str, params: dict = None):
        resp = requests.get(
            f"{self.base_url}{path}",
            headers=self._headers(),
            params=params or {},
            timeout=30,
        )
        if resp.status_code == 401:
            # Token may have expired — re-authenticate once and retry
            self._token = None
            resp = requests.get(
                f"{self.base_url}{path}",
                headers=self._headers(),
                params=params or {},
                timeout=30,
            )
        if resp.status_code not in (200, 204):
            raise AmtechAPIError(resp.status_code, resp.text[:500])
        return resp.json() if resp.text else {}

    def _post(self, path: str, payload: dict):
        resp = requests.post(
            f"{self.base_url}{path}",
            headers=self._headers(),
            json=payload,
            timeout=30,
        )
        if resp.status_code == 401:
            self._token = None
            resp = requests.post(
                f"{self.base_url}{path}",
                headers=self._headers(),
                json=payload,
                timeout=30,
            )
        if resp.status_code not in (200, 201, 204):
            raise AmtechAPIError(resp.status_code, resp.text[:500])
        return resp.json() if resp.text else {}

    # ── Truck Trip endpoints ───────────────────────────────────────────────────

    def get_truck_trips(self, delivery_date: str = None, customer_id: str = None) -> list:
        """
        GET /api/AITruckTrip
        Fetch truck trip records. Optionally filter by date or customer.

        Returns list of TruckHdr dicts.
        """
        params = {}
        if delivery_date:
            params["DeliveryDate"] = delivery_date
        if customer_id:
            params["CustomerID"] = customer_id
        result = self._get("/api/AITruckTrip", params)
        # API may return a single dict or a list
        if isinstance(result, dict):
            return [result]
        return result or []

    def get_truck_trip(self, trip_id: str) -> dict:
        """GET /api/AITruckTrip/{id}"""
        return self._get(f"/api/AITruckTrip/{trip_id}")

    def create_truck_trip(self, trip_payload: dict) -> dict:
        """
        POST /api/AITruckTrip
        Create a new truck trip in Amtech Sign & Drive.

        Returns the created TruckHdr with TruckTripID.
        """
        return self._post("/api/AITruckTrip", trip_payload)

    # ── Payload builder helpers ────────────────────────────────────────────────

    @staticmethod
    def build_trip_payload(delivery_note) -> dict:
        """
        Convert an ERPNext Delivery Note document into an Amtech TruckHdr payload.

        TruckHdr fields:
            TruckTripID, TruckHdrID, DeliveryDate,
            ShippedFrom, ShipToID, DeliveryTo,
            DeliveryAdd1, DeliveryAdd2, DeliveryCity, DeliveryState, DeliveryZip,
            CustomerID, UserID, Truck_Dtl []

        TruckDtl fields per item:
            TruckDtlID, QTYShipped, ItemID, ItemNo, ItemDescription,
            OrderID, OrderNo, CustomerPO
        """
        dn    = delivery_note
        cust  = frappe.get_doc("Customer", dn.customer) if dn.customer else None
        addr  = None
        if dn.shipping_address_name:
            try:
                addr = frappe.get_doc("Address", dn.shipping_address_name)
            except Exception:
                pass

        details = []
        for idx, item in enumerate(dn.items or []):
            details.append({
                "TruckDtlID":       0,                              # New record
                "ItemID":           item.item_code or "",
                "ItemNo":           item.item_code or "",
                "ItemDescription":  item.item_name or item.description or "",
                "QTYShipped":       float(item.qty or 0),
                "QTYDelivered":     0,
                "QTYAdjusted":      0,
                "OrderID":          dn.name,
                "OrderNo":          dn.name,
                "CustomerPO":       dn.po_no or "",
                "ShipReleaseID":    "",
                "DeliveryReceiptNo":"",
                "OSDReasonCode":    "",
                "OSDType":          "",
                "OSDComment":       "",
                "ReturningProduct": False,
                "OverAdjustment":   False,
                "OSDAdjustment":    False,
                "Unitization":      "",
            })

        return {
            "TruckTripID":  0,                                      # 0 = new
            "TruckHdrID":   0,
            "DeliveryDate": str(dn.posting_date or ""),
            "ShippedFrom":  frappe.defaults.get_global_default("company") or "",
            "ShipToID":     dn.customer or "",
            "DeliveryTo":   dn.customer_name or "",
            "DeliveryAdd1": addr.address_line1 if addr else "",
            "DeliveryAdd2": addr.address_line2 if addr else "",
            "DeliveryCity": addr.city         if addr else "",
            "DeliveryState":addr.state        if addr else "",
            "DeliveryZip":  addr.pincode      if addr else "",
            "CustomerID":   dn.customer or "",
            "UserID":       frappe.session.user,
            "UserEmail":    frappe.session.user,
            "UserType":     "ERPNext",
            "SearchedDRNo": "",
            "ReceiverName": "",
            "ReceiverSignature": "",
            "SignatureMimeType": "",
            "Truck_Dtl":    details,
        }
