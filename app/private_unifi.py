import base64
import json
import threading
import time
import requests
from copy import deepcopy
from urllib3.exceptions import InsecureRequestWarning

requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)


class PrivateUniFiAPI:
    """Cookie/CSRF client for UniFi's classic local API.

    This is intentionally separate from the supported Integration API.
    It is used only for experimental RF discovery and gated radio writes.
    """

    def __init__(self, base_url, username="", password="", site="default"):
        self.base_url=base_url.rstrip("/")
        self.username=username or ""
        self.password=password or ""
        self.site=site or "default"
        self.session=requests.Session()
        self.session.verify=False
        self.csrf=None
        self.logged_in=False
        self.last_login=None
        self.lock=threading.Lock()

    @property
    def configured(self):
        return bool(self.username and self.password)

    def _jwt_csrf(self):
        try:
            token=self.session.cookies.get("TOKEN")
            if not token:
                return None
            parts=token.split(".")
            if len(parts)<2:
                return None
            payload=parts[1]
            payload += "=" * (-len(payload) % 4)
            data=json.loads(base64.urlsafe_b64decode(payload.encode()).decode())
            return data.get("csrfToken") or data.get("csrf_token")
        except Exception:
            return None

    def _capture_csrf(self, response):
        if response is None:
            return
        token=(response.headers.get("X-CSRF-Token")
               or response.headers.get("X-Csrf-Token")
               or response.headers.get("X-Updated-CSRF-Token")
               or response.headers.get("X-Updated-Csrf-Token"))
        if not token:
            token=self._jwt_csrf()
        if token:
            self.csrf=token

    def login(self, force=False):
        with self.lock:
            if not self.configured:
                return {"ok":False,"status":0,"error":"Private API credentials are not configured"}
            if self.logged_in and not force:
                return {"ok":True,"status":200}

            try:
                # Some UniFi OS builds provide the first CSRF token on the root response.
                root=self.session.get(self.base_url+"/",timeout=15,verify=False)
                self._capture_csrf(root)

                headers={"Accept":"application/json","Content-Type":"application/json"}
                if self.csrf:
                    headers["X-CSRF-Token"]=self.csrf
                payload={
                    "username":self.username,
                    "password":self.password,
                    "remember":True,
                    "rememberMe":True,
                }
                r=self.session.post(
                    self.base_url+"/api/auth/login",
                    headers=headers,
                    json=payload,
                    timeout=20,
                    verify=False,
                )
                self._capture_csrf(r)
                if 200 <= r.status_code < 300:
                    self.logged_in=True
                    self.last_login=time.time()
                    return {"ok":True,"status":r.status_code}
                self.logged_in=False
                return {"ok":False,"status":r.status_code,"error":"Private API login failed"}
            except Exception as e:
                self.logged_in=False
                return {"ok":False,"status":0,"error":str(e)}

    def _request(self, method, path, payload=None, retry_auth=True):
        auth=self.login()
        if not auth.get("ok"):
            return auth

        headers={"Accept":"application/json"}
        if method.upper() in ("POST","PUT","PATCH","DELETE"):
            headers["Content-Type"]="application/json"
            if self.csrf:
                headers["X-CSRF-Token"]=self.csrf

        try:
            r=self.session.request(
                method,
                self.base_url+path,
                headers=headers,
                json=payload,
                timeout=25,
                verify=False,
            )
            self._capture_csrf(r)
            if r.status_code in (401,403) and retry_auth:
                self.logged_in=False
                auth=self.login(force=True)
                if auth.get("ok"):
                    return self._request(method,path,payload,retry_auth=False)
            try:
                data=r.json()
            except Exception:
                data={"raw":r.text[:5000]}
            return {
                "ok":200 <= r.status_code < 300,
                "status":r.status_code,
                "data":data,
            }
        except Exception as e:
            return {"ok":False,"status":0,"error":str(e)}

    def classic(self, method, path, payload=None):
        prefix=f"/proxy/network/api/s/{self.site}"
        return self._request(method,prefix+path,payload)

    @staticmethod
    def _items(result):
        if not result or not result.get("ok"):
            return []
        payload=result.get("data")
        if isinstance(payload,dict) and isinstance(payload.get("data"),list):
            return payload["data"]
        if isinstance(payload,list):
            return payload
        return []

    def devices(self):
        return self._items(self.classic("GET","/stat/device"))

    def clients(self):
        return self._items(self.classic("GET","/stat/sta"))

    def site_dpi(self):
        return self._items(self.classic("GET","/stat/sitedpi"))

    def station_dpi(self):
        return self._items(self.classic("GET","/stat/stadpi"))

    def rogue_aps(self):
        return self._items(self.classic("GET","/stat/rogueap"))

    def qos_rules(self):
        """Read gateway QoS rules from UniFi Network's local v2 API.

        Returns None when the endpoint is unavailable so callers can distinguish
        "no configured rules" from "controller did not expose QoS inventory".
        """
        result=self._request(
            "GET",
            f"/proxy/network/v2/api/site/{self.site}/qos-rules",
        )
        if not result.get("ok"):
            return None
        payload=result.get("data")
        if isinstance(payload,list):
            return payload
        if isinstance(payload,dict):
            if isinstance(payload.get("data"),list):
                return payload["data"]
            if isinstance(payload.get("items"),list):
                return payload["items"]
        return []

    def discover_radios(self):
        devices=self.devices()
        aps=[]
        for d in devices:
            radios=d.get("radio_table") or []
            if not radios:
                continue
            aps.append({
                "id":d.get("_id"),
                "mac":d.get("mac"),
                "name":d.get("name") or d.get("model") or d.get("mac"),
                "model":d.get("model"),
                "ip":d.get("ip"),
                "radios":[{
                    "radio":r.get("radio"),
                    "name":r.get("name"),
                    "channel":r.get("channel"),
                    "ht":r.get("ht"),
                    "txPowerMode":r.get("tx_power_mode"),
                    "txPower":r.get("tx_power"),
                    "minRssiEnabled":r.get("min_rssi_enabled"),
                    "minRssi":r.get("min_rssi"),
                    "hasDfs":r.get("has_dfs"),
                } for r in radios]
            })
        return {"ok":True,"accessPoints":aps} if aps else {
            "ok":False,
            "error":"Classic API connected but no radio_table data was returned"
        }

    def find_device(self, *, mac=None, name=None, ip=None):
        mac_norm=(mac or "").lower().replace("-",":")
        for d in self.devices():
            dm=(d.get("mac") or "").lower().replace("-",":")
            if mac_norm and dm==mac_norm:
                return d
        if ip:
            for d in self.devices():
                if d.get("ip")==ip:
                    return d
        if name:
            for d in self.devices():
                if d.get("name")==name:
                    return d
        return None

    @staticmethod
    def band_radio_name(band):
        if float(band)==2.4:
            return "ng"
        if float(band)==5.0:
            return "na"
        if float(band)==6.0:
            return "6e"
        return None

    def _updated_radio_table(self, device, band, channel, width):
        target=self.band_radio_name(band)
        if not target:
            return None
        radios=deepcopy(device.get("radio_table") or [])
        found=False
        for r in radios:
            if r.get("radio")!=target:
                continue
            if channel is not None:
                current=r.get("channel")
                r["channel"]=str(int(channel)) if isinstance(current,str) else int(channel)
            if width is not None:
                r["ht"]=int(width)
            found=True
        return radios if found else None

    def write_radio(self, *, device, band, channel, width):
        device_id=device.get("_id")
        if not device_id:
            return {"ok":False,"error":"Classic device id is missing"}
        radios=self._updated_radio_table(device,band,channel,width)
        if radios is None:
            return {"ok":False,"error":"Requested radio was not found in radio_table"}
        return self.classic("PUT",f"/rest/device/{device_id}",{"radio_table":radios})

    def verify_noop_write(self, device):
        device_id=device.get("_id")
        radios=deepcopy(device.get("radio_table") or [])
        if not device_id or not radios:
            return {"ok":False,"error":"Device/radio_table unavailable for validation"}
        return self.classic("PUT",f"/rest/device/{device_id}",{"radio_table":radios})
