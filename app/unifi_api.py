import requests
from urllib3.exceptions import InsecureRequestWarning

requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)

class UniFiAPI:
    def __init__(self, base_url, api_key):
        self.base = base_url.rstrip("/") + "/proxy/network/integration/v1"
        self.headers = {"X-API-Key": api_key, "Accept": "application/json"}

    def request(self, method, path, payload=None, params=None):
        try:
            r = requests.request(
                method,
                self.base + path,
                headers={**self.headers, "Content-Type": "application/json"},
                json=payload,
                params=params,
                timeout=20,
                verify=False,
            )
            try:
                data = r.json()
            except Exception:
                data = {"raw": r.text[:5000]}
            return {"ok": 200 <= r.status_code < 300, "status": r.status_code, "data": data}
        except Exception as e:
            return {"ok": False, "status": 0, "error": str(e)}

    def get(self, path, params=None):
        return self.request("GET", path, params=params)

    def put(self, path, payload):
        return self.request("PUT", path, payload=payload)

    @staticmethod
    def items(result):
        if not result or not result.get("ok"):
            return []
        payload = result.get("data")
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            if isinstance(payload.get("data"), list):
                return payload["data"]
            if isinstance(payload.get("items"), list):
                return payload["items"]
        return []

    def site(self):
        items = self.items(self.get("/sites", {"limit": 200}))
        return items[0] if items else None

    def devices(self, site_id):
        return self.items(self.get(f"/sites/{site_id}/devices", {"limit": 200}))

    def device_detail(self, site_id, device_id):
        r = self.get(f"/sites/{site_id}/devices/{device_id}")
        return r.get("data") if r.get("ok") and isinstance(r.get("data"), dict) else None

    def device_stats(self, site_id, device_id):
        r = self.get(f"/sites/{site_id}/devices/{device_id}/statistics/latest")
        return r.get("data") if r.get("ok") and isinstance(r.get("data"), dict) else {}

    def clients(self, site_id):
        return self.items(self.get(f"/sites/{site_id}/clients", {"limit": 200, "offset": 0}))

    def networks(self, site_id):
        basics = self.items(self.get(f"/sites/{site_id}/networks", {"limit": 200, "offset": 0}))
        output = []
        for item in basics:
            network_id=item.get("id")
            if not network_id:
                output.append(item)
                continue
            r=self.get(f"/sites/{site_id}/networks/{network_id}")
            output.append(r.get("data") if r.get("ok") and isinstance(r.get("data"), dict) else item)
        return output

    def wifi_broadcasts(self, site_id):
        basics = self.items(self.get(f"/sites/{site_id}/wifi/broadcasts", {"limit": 200}))
        output = []
        for item in basics:
            r = self.get(f"/sites/{site_id}/wifi/broadcasts/{item.get('id')}")
            output.append(r.get("data") if r.get("ok") and isinstance(r.get("data"), dict) else item)
        return output


    def dpi_categories(self):
        return self.items(self.get("/dpi/categories", {"limit": 200, "offset": 0}))

    def dpi_applications(self):
        return self.items(self.get("/dpi/applications", {"limit": 200, "offset": 0}))


    def firewall_zones(self, site_id):
        return self.items(self.get(f"/sites/{site_id}/firewall/zones", {"limit": 200, "offset": 0}))

    def firewall_policies(self, site_id):
        return self.items(self.get(f"/sites/{site_id}/firewall/policies", {"limit": 200, "offset": 0}))

    def acl_rules(self, site_id):
        return self.items(self.get(f"/sites/{site_id}/acl-rules", {"limit": 200, "offset": 0}))

    def dns_policies(self, site_id):
        return self.items(self.get(f"/sites/{site_id}/dns/policies", {"limit": 200, "offset": 0}))

    def wan_interfaces(self, site_id):
        return self.items(self.get(f"/sites/{site_id}/wans", {"limit": 200, "offset": 0}))
