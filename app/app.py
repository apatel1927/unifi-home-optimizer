import os
import threading
import time
import requests
import subprocess
import json
import re
import dns.resolver
from ping3 import ping
import traceback
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask import Flask, jsonify, render_template, request, send_file, Response

from .database import Database
from .unifi_api import UniFiAPI
from .private_unifi import PrivateUniFiAPI
from .optimizer import build_snapshot, analyze, auto_optimize, wifi_status, build_channel_plan, radio_conflict_key
from .audit import build_network_audit
from .wired_audit import build_wired_audit
from .export_bundle import build_zip_bytes, build_json_bytes, compact_support_summary, sanitize
from .ai_advisor import analyze_with_openai

app = Flask(__name__, template_folder="templates", static_folder="static")

VERSION = open("/app/VERSION").read().strip() if os.path.exists("/app/VERSION") else "0.21.0"
UNIFI_URL = os.getenv("UNIFI_URL", "https://192.168.1.1")
API_KEY = os.getenv("UNIFI_API_KEY", "")
POLL_INTERVAL = max(int(os.getenv("POLL_INTERVAL_SECONDS", "60")), 30)
RETENTION_DAYS = int(os.getenv("RETENTION_DAYS", "30"))
UNIFI_PRIVATE_USERNAME = os.getenv("UNIFI_PRIVATE_USERNAME", "")
UNIFI_PRIVATE_PASSWORD = os.getenv("UNIFI_PRIVATE_PASSWORD", "")
UNIFI_SITE_NAME = os.getenv("UNIFI_SITE_NAME", "default")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.6-luna")

api = UniFiAPI(UNIFI_URL, API_KEY)
private_api = PrivateUniFiAPI(
    UNIFI_URL,
    UNIFI_PRIVATE_USERNAME,
    UNIFI_PRIVATE_PASSWORD,
    UNIFI_SITE_NAME,
)
db = Database("/config", RETENTION_DAYS)
monitor_started = False
monitor_lock = threading.Lock()
last_controller_success = None
last_monitor_cycle = None
last_monitor_error = None
private_rf_last_discovery = None
private_rf_last_error = None
private_client_cache = {"ts":0.0,"items":[]}
private_device_cache = {"ts":0.0,"items":[]}
speedtest_lock = threading.Lock()
speedtest_running = False
speedtest_started_at = None
speedtest_last_error = None
speedtest_scheduler_started = False
speedtest_scheduler_lock = threading.Lock()
traffic_sample_interval_seconds = 300
traffic_last_sample_monotonic = 0.0
traffic_last_sample_at = None
traffic_last_error = None
dpi_reference_cache = {"ts":0.0,"categories":{},"apps":{}}
wan_quality_sample_seconds = 60
wan_dns_sample_seconds = 300
wan_last_sample_monotonic = 0.0
wan_dns_last_sample_monotonic = 0.0
wan_last_sample_at = None
wan_last_error = None
ai_scheduler_started = False
ai_scheduler_lock = threading.Lock()
ai_analysis_lock = threading.Lock()
ai_running = False
ai_starting = False
ai_started_at = None
ai_last_error = None

def _wan_targets():
    gateway=urlparse(UNIFI_URL).hostname
    targets=[
        {"key":"cloudflare","name":"Cloudflare","host":"1.1.1.1","type":"INTERNET"},
        {"key":"google","name":"Google","host":"8.8.8.8","type":"INTERNET"},
        {"key":"quad9","name":"Quad9","host":"9.9.9.9","type":"INTERNET"},
    ]
    if gateway:
        targets.insert(0,{"key":"gateway","name":"Gateway","host":gateway,"type":"GATEWAY"})
    return targets

def _ping_probe(target, count=3, timeout=1.0):
    rtts=[]
    errors=[]
    for _ in range(count):
        try:
            value=ping(target["host"],timeout=timeout,unit="ms")
            if value is not None:
                rtts.append(float(value))
        except Exception as e:
            errors.append(str(e))
    received=len(rtts)
    loss=(1.0-(received/float(count)))*100.0 if count else 100.0
    jitter=None
    if len(rtts)>=2:
        jitter=sum(abs(rtts[i]-rtts[i-1]) for i in range(1,len(rtts)))/(len(rtts)-1)
    return {
        "target":target,
        "sent":count,
        "received":received,
        "packetLossPct":loss,
        "minMs":min(rtts) if rtts else None,
        "avgMs":sum(rtts)/len(rtts) if rtts else None,
        "maxMs":max(rtts) if rtts else None,
        "jitterMs":jitter,
        "error":"; ".join(errors[:2]) if errors and not rtts else None,
    }

def _dns_probe(key, name, nameserver=None, query_name="example.com"):
    started=time.perf_counter()
    try:
        resolver=dns.resolver.Resolver(configure=nameserver is None)
        if nameserver is not None:
            resolver.nameservers=[nameserver]
        resolver.timeout=2.0
        resolver.lifetime=2.0
        answer=resolver.resolve(query_name,"A",raise_on_no_answer=False)
        latency=(time.perf_counter()-started)*1000.0
        count=len(answer) if answer.rrset is not None else 0
        return {
            "key":key,"name":name,"host":nameserver,
            "queryName":query_name,"success":True,
            "latencyMs":latency,"answers":count,"error":None
        }
    except Exception as e:
        return {
            "key":key,"name":name,"host":nameserver,
            "queryName":query_name,"success":False,
            "latencyMs":None,"answers":0,"error":str(e)
        }

def _sample_wan_quality():
    global wan_last_sample_monotonic,wan_dns_last_sample_monotonic,wan_last_sample_at,wan_last_error
    errors=[]
    targets=_wan_targets()
    try:
        with ThreadPoolExecutor(max_workers=len(targets)) as executor:
            futures=[executor.submit(_ping_probe,t) for t in targets]
            for future in as_completed(futures):
                result=future.result()
                t=result["target"]
                db.record_wan_ping(
                    t["key"],t["name"],t["host"],t["type"],
                    result["sent"],result["received"],result["packetLossPct"],
                    result["minMs"],result["avgMs"],result["maxMs"],result["jitterMs"],
                    result["error"]
                )
                if result.get("error"):
                    errors.append(t["name"]+": "+result["error"])
        wan_last_sample_monotonic=time.monotonic()
        wan_last_sample_at=datetime.now(timezone.utc).isoformat()

        if (time.monotonic()-wan_dns_last_sample_monotonic) >= wan_dns_sample_seconds:
            resolvers=[
                ("system","System DNS",None),
                ("cloudflare","Cloudflare DNS","1.1.1.1"),
                ("google","Google DNS","8.8.8.8"),
            ]
            with ThreadPoolExecutor(max_workers=len(resolvers)) as executor:
                futures=[executor.submit(_dns_probe,*x) for x in resolvers]
                for future in as_completed(futures):
                    result=future.result()
                    db.record_wan_dns(
                        result["key"],result["name"],result["host"],result["queryName"],
                        result["success"],result["latencyMs"],result["answers"],result["error"]
                    )
                    if result.get("error"):
                        errors.append(result["name"]+": "+result["error"])
            wan_dns_last_sample_monotonic=time.monotonic()

        wan_last_error=" | ".join(errors[:4]) if errors else None
    except Exception as e:
        wan_last_error=str(e)
        print("WAN quality sampling error:",e,flush=True)

def _wan_quality_score(summary):
    score=100.0
    reach=summary.get("reachabilityPct")
    latency=summary.get("avgLatencyMs")
    jitter=summary.get("avgJitterMs")
    dns_success=summary.get("dnsSuccessPct")
    dns_latency=summary.get("dnsAvgLatencyMs")

    if reach is not None:
        score -= max(0.0,100.0-float(reach))*4.0
    if latency is not None:
        if latency>20:
            score -= min(20.0,(float(latency)-20.0)/4.0)
        if latency>100:
            score -= min(15.0,(float(latency)-100.0)/10.0)
    if jitter is not None and jitter>5:
        score -= min(20.0,(float(jitter)-5.0)*1.5)
    if dns_success is not None:
        score -= max(0.0,100.0-float(dns_success))*2.0
    if dns_latency is not None and dns_latency>50:
        score -= min(10.0,(float(dns_latency)-50.0)/15.0)
    return max(0,min(100,round(score)))

def _norm_mac(value):
    return str(value or "").lower().replace("-",":").strip()

def _classic_devices_cached():
    if not private_api.configured:
        return []
    now=time.time()
    if private_device_cache["items"] and now-private_device_cache["ts"] < 30:
        return private_device_cache["items"]
    try:
        items=private_api.devices()
        if isinstance(items,list):
            private_device_cache["items"]=items
            private_device_cache["ts"]=now
            return items
    except Exception as e:
        print("Classic device inventory error:",e,flush=True)
    return private_device_cache["items"]

def _classic_clients_cached():
    if not private_api.configured:
        return []
    now=time.time()
    if private_client_cache["items"] and now-private_client_cache["ts"] < 30:
        return private_client_cache["items"]
    try:
        items=private_api.clients()
        if isinstance(items,list):
            private_client_cache["items"]=items
            private_client_cache["ts"]=now
            return items
    except Exception as e:
        print("Classic client inventory error:",e,flush=True)
    return private_client_cache["items"]

def _num(value):
    try:
        if value is None or value=="":
            return None
        return float(value)
    except Exception:
        return None

def _int_counter(value):
    n=_num(value)
    return int(n) if n is not None and n >= 0 else None

def _classic_counter(item, direction):
    keys={
        "rx":("rx_bytes","rxBytes","rx_byte","rx_total_bytes","bytes_rx"),
        "tx":("tx_bytes","txBytes","tx_byte","tx_total_bytes","bytes_tx"),
    }.get(direction,())
    for key in keys:
        if key in item:
            value=_int_counter(item.get(key))
            if value is not None:
                return value
    return None

def _classic_bytes_rate_bps(item, direction):
    # UniFi classic station payload commonly exposes rx_bytes-r / tx_bytes-r
    # as byte rates. Keep this separate from rx_rate/tx_rate, which can be
    # Wi-Fi PHY rates rather than client traffic throughput.
    raw=item.get(direction+"_bytes-r")
    if raw is None:
        raw=item.get(direction+"_bytes_r")
    if raw is None:
        raw=item.get(direction+"BytesRate")
    n=_num(raw)
    return n*8.0 if n is not None else None

def _station_dpi_counter_map():
    output={}
    if not private_api.configured:
        return output
    try:
        tables=private_api.station_dpi()
    except Exception:
        return output
    for table in tables:
        if not isinstance(table,dict):
            continue
        mac=_norm_mac(table.get("mac") or table.get("sta") or table.get("station_mac"))
        if not mac:
            continue
        rx=_classic_counter(table,"rx")
        tx=_classic_counter(table,"tx")
        if rx is None or tx is None:
            items=table.get("by_app") or table.get("by_cat") or []
            sum_rx=0
            sum_tx=0
            found=False
            for item in items:
                if not isinstance(item,dict):
                    continue
                irx=_int_counter(item.get("rx_bytes"))
                itx=_int_counter(item.get("tx_bytes"))
                if irx is not None:
                    sum_rx+=irx
                    found=True
                if itx is not None:
                    sum_tx+=itx
                    found=True
            if found:
                if rx is None:
                    rx=sum_rx
                if tx is None:
                    tx=sum_tx
        output[mac]={"rxBytes":rx,"txBytes":tx}
    return output

def _traffic_rows_from_report(data):
    enriched={_norm_mac(x.get("macAddress")):x for x in (data.get("clients") or []) if x.get("macAddress")}
    station_dpi=_station_dpi_counter_map()
    rows=[]
    for raw in _classic_clients_cached():
        mac=_norm_mac(raw.get("mac"))
        if not mac:
            continue
        client=enriched.get(mac) or {}
        dpi_counter=station_dpi.get(mac) or {}
        rx_counter=_classic_counter(raw,"rx")
        tx_counter=_classic_counter(raw,"tx")
        if rx_counter is None:
            rx_counter=dpi_counter.get("rxBytes")
        if tx_counter is None:
            tx_counter=dpi_counter.get("txBytes")
        rows.append({
            "mac":mac,
            "name":client.get("name") or raw.get("name") or raw.get("hostname") or mac,
            "ip":client.get("ipAddress") or raw.get("ip"),
            "vlanId":client.get("vlanId") if client.get("vlanId") is not None else raw.get("vlan"),
            "networkName":client.get("networkName") or raw.get("network") or raw.get("network_name") or "Unknown",
            "uplinkName":client.get("uplinkDeviceName") or "Unknown",
            "rxBytes":rx_counter,
            "txBytes":tx_counter,
            "rxRateBps":_classic_bytes_rate_bps(raw,"rx"),
            "txRateBps":_classic_bytes_rate_bps(raw,"tx"),
        })
    return rows

def _traffic_live_rows_from_summary(summary):
    latest={_norm_mac(x.get("mac")):x for x in (summary.get("latestClients") or []) if x.get("mac")}
    rows=[]
    for raw in _classic_clients_cached():
        mac=_norm_mac(raw.get("mac"))
        if not mac:
            continue
        meta=latest.get(mac) or {}
        rows.append({
            "mac":mac,
            "name":meta.get("name") or raw.get("name") or raw.get("hostname") or mac,
            "ip":meta.get("ip") or raw.get("ip"),
            "vlanId":meta.get("vlan_id") if meta.get("vlan_id") is not None else raw.get("vlan"),
            "networkName":meta.get("network_name") or raw.get("network") or raw.get("network_name") or "Unknown",
            "uplinkName":meta.get("uplink_name") or "Unknown",
            "rxBytes":_classic_counter(raw,"rx"),
            "txBytes":_classic_counter(raw,"tx"),
            "rxRateBps":_classic_bytes_rate_bps(raw,"rx"),
            "txRateBps":_classic_bytes_rate_bps(raw,"tx"),
        })
    return rows

def _dpi_reference_maps():
    now=time.time()
    if dpi_reference_cache["categories"] and now-dpi_reference_cache["ts"] < 21600:
        return dpi_reference_cache["categories"],dpi_reference_cache["apps"]

    categories={}
    apps={}
    try:
        for item in api.dpi_categories():
            cid=item.get("id")
            if cid is None:
                cid=item.get("categoryId")
            if cid is None:
                cid=item.get("category")
            name=item.get("name") or item.get("displayName") or item.get("description")
            if cid is not None and name:
                categories[str(cid)]=str(name)
    except Exception as e:
        print("DPI category reference error:",e,flush=True)

    try:
        for item in api.dpi_applications():
            aid=item.get("id")
            if aid is None:
                aid=item.get("applicationId")
            if aid is None:
                aid=item.get("app")
            cid=item.get("categoryId")
            if cid is None:
                cid=item.get("category")
            name=item.get("name") or item.get("displayName") or item.get("description")
            if aid is not None and name:
                apps[str(aid)]=str(name)
                if cid is not None:
                    apps[str(cid)+":"+str(aid)]=str(name)
    except Exception as e:
        print("DPI application reference error:",e,flush=True)

    dpi_reference_cache["ts"]=now
    dpi_reference_cache["categories"]=categories
    dpi_reference_cache["apps"]=apps
    return categories,apps

def _site_dpi_rows():
    if not private_api.configured:
        return []
    categories,apps=_dpi_reference_maps()
    output=[]
    try:
        tables=private_api.site_dpi()
        for table in tables:
            by_app=table.get("by_app") or []
            if by_app:
                for item in by_app:
                    cat=item.get("cat")
                    app_id=item.get("app")
                    cat_name=categories.get(str(cat),"Category "+str(cat) if cat is not None else "Unknown")
                    app_name=(apps.get(str(cat)+":"+str(app_id))
                              or apps.get(str(app_id))
                              or ("App "+str(app_id) if app_id is not None else cat_name))
                    output.append({
                        "categoryId":cat,
                        "appId":app_id,
                        "categoryName":cat_name,
                        "appName":app_name,
                        "rxBytes":_int_counter(item.get("rx_bytes")),
                        "txBytes":_int_counter(item.get("tx_bytes")),
                    })
                continue
            for item in (table.get("by_cat") or []):
                cat=item.get("cat")
                output.append({
                    "categoryId":cat,
                    "appId":None,
                    "categoryName":categories.get(str(cat),"Category "+str(cat) if cat is not None else "Unknown"),
                    "appName":"Unclassified application",
                    "rxBytes":_int_counter(item.get("rx_bytes")),
                    "txBytes":_int_counter(item.get("tx_bytes")),
                })
    except Exception as e:
        print("Classic DPI error:",e,flush=True)
    return output

def _traffic_diagnostics():
    stations=_classic_clients_cached() if private_api.configured else []
    station_keys=sorted({str(k) for row in stations[:50] for k in row.keys()})
    counter_fields=[
        "rx_bytes","tx_bytes","rxBytes","txBytes","rx_byte","tx_byte",
        "rx_total_bytes","tx_total_bytes","bytes_rx","bytes_tx",
        "rx_bytes-r","tx_bytes-r","rx_bytes_r","tx_bytes_r",
        "rxBytesRate","txBytesRate"
    ]
    coverage={}
    for field in counter_fields:
        present=sum(1 for row in stations if field in row and row.get(field) not in (None,""))
        nonzero=sum(1 for row in stations if _num(row.get(field)) not in (None,0))
        if present:
            coverage[field]={"present":present,"nonzero":nonzero}

    dpi_tables=[]
    station_dpi_tables=[]
    dpi_error=None
    try:
        dpi_tables=private_api.site_dpi() if private_api.configured else []
        station_dpi_tables=private_api.station_dpi() if private_api.configured else []
    except Exception as e:
        dpi_error=str(e)
    dpi_keys=sorted({str(k) for row in dpi_tables[:20] for k in row.keys()})
    station_dpi_keys=sorted({str(k) for row in station_dpi_tables[:20] for k in row.keys()})
    by_app=sum(len((row.get("by_app") or [])) for row in dpi_tables if isinstance(row,dict))
    by_cat=sum(len((row.get("by_cat") or [])) for row in dpi_tables if isinstance(row,dict))

    summary=db.traffic_summary(24)
    totals=summary.get("totals") or {}
    return {
        "privateConfigured":private_api.configured,
        "stationCount":len(stations),
        "stationKeys":station_keys,
        "counterCoverage":coverage,
        "dpiTableCount":len(dpi_tables),
        "dpiKeys":dpi_keys,
        "stationDpiCount":len(station_dpi_tables),
        "stationDpiKeys":station_dpi_keys,
        "dpiByAppCount":by_app,
        "dpiByCategoryCount":by_cat,
        "dpiError":dpi_error,
        "databaseClientCount":totals.get("client_count",0),
        "databaseRxBytes":totals.get("rx_bytes",0),
        "databaseTxBytes":totals.get("tx_bytes",0),
        "lastSampleAt":traffic_last_sample_at,
        "lastError":traffic_last_error,
    }

def _sample_traffic(data):
    global traffic_last_sample_monotonic,traffic_last_sample_at,traffic_last_error
    if not private_api.configured:
        return
    try:
        rows=_traffic_rows_from_report(data)
        db.record_traffic_clients(rows)
        dpi=_site_dpi_rows()
        db.record_traffic_dpi(dpi)
        traffic_last_sample_monotonic=time.monotonic()
        traffic_last_sample_at=datetime.now(timezone.utc).isoformat()
        traffic_last_error=None
    except Exception as e:
        traffic_last_error=str(e)
        print("Traffic sampling error:",e,flush=True)

def _enrich_client_inventory(snapshot):
    clients=[dict(x) for x in (snapshot.get("clients") or [])]
    networks=snapshot.get("networks") or []
    network_map={str(n.get("id")):n for n in networks if n.get("id")}
    network_name_map={str(n.get("name")):n for n in networks if n.get("name")}
    device_mac_map={}
    for d in snapshot.get("devices") or []:
        mac=_norm_mac(d.get("macAddress") or d.get("mac"))
        if mac:
            device_mac_map[mac]=d

    classic_map={}
    for x in _classic_clients_cached():
        mac=_norm_mac(x.get("mac"))
        if mac:
            classic_map[mac]=x

    for row in clients:
        mac=_norm_mac(row.get("macAddress"))
        classic=classic_map.get(mac) or {}
        access=row.get("access") or {}

        network_id=(row.get("networkId")
                    or access.get("networkId")
                    or row.get("network_id")
                    or classic.get("network_id"))
        official_network=network_map.get(str(network_id)) if network_id else None

        classic_network_name=(classic.get("network")
                              or classic.get("network_name")
                              or classic.get("usergroup_name"))
        classic_network=network_name_map.get(str(classic_network_name)) if classic_network_name else None
        network=official_network or classic_network or {}

        vlan=(row.get("vlanId")
              or row.get("vlan")
              or access.get("vlanId")
              or classic.get("vlan")
              or network.get("vlanId"))
        try:
            vlan=int(vlan) if vlan not in (None,"") else None
        except Exception:
            pass

        network_name=(network.get("name")
                      or classic_network_name
                      or row.get("networkName")
                      or "Unknown")
        ssid=(classic.get("essid")
              or row.get("ssid")
              or row.get("wifiName")
              or None)

        ap_mac=_norm_mac(classic.get("ap_mac"))
        sw_mac=_norm_mac(classic.get("sw_mac"))
        private_uplink=device_mac_map.get(ap_mac) or device_mac_map.get(sw_mac) or {}

        if (not row.get("uplinkDeviceName") or row.get("uplinkDeviceName")=="Unknown") and private_uplink:
            row["uplinkDeviceName"]=private_uplink.get("name") or row.get("uplinkDeviceName")
            row["uplinkDeviceModel"]=private_uplink.get("model") or row.get("uplinkDeviceModel")

        row["vlanId"]=vlan
        row["networkName"]=network_name
        row["ssid"]=ssid
        row["switchPort"]=classic.get("sw_port")
        row["radioName"]=classic.get("radio_name") or classic.get("radio")
        row["channel"]=classic.get("channel")
        row["clientSource"]="official+classic" if classic else "official"
    return clients

def _wired_audit_for_snapshot(snapshot, include_events=True):
    classic_devices=_classic_devices_cached()
    classic_clients=_classic_clients_cached()
    events=db.wired_port_event_summary(24) if include_events else {}
    recent=db.wired_recent_events(24,200) if include_events else []
    counters=db.wired_port_counter_summary()
    return build_wired_audit(
        snapshot,
        classic_devices=classic_devices,
        classic_clients=classic_clients,
        event_summary=events,
        recent_events=recent,
        counter_summary=counters,
    )

def _build_support_context():
    snap=build_snapshot(api)
    if not snap:
        raise RuntimeError("Unable to retrieve UniFi snapshot")
    retry=db.ap_retry_trends(15)
    baselines=db.ap_client_baselines(24)
    analysis=analyze(snap,retry,baselines)
    channel_plan=build_channel_plan(snap,retry)
    wired=_wired_audit_for_snapshot(snap)
    audit=build_network_audit(snap,api,wired_audit=wired)

    snap_export=dict(snap)
    snap_export["clients"]=_enrich_client_inventory(snap)

    traffic=db.traffic_summary(24)
    traffic_dpi=db.traffic_dpi_summary(24)
    speed=db.speedtest_summary(30)
    speed["history"]=db.speedtest_history(30,200)
    wan=db.wan_quality_summary(24)

    return {
        "generatedAt":datetime.now(timezone.utc).isoformat(),
        "version":VERSION,
        "snapshot":snap_export,
        "analysis":analysis,
        "networkAudit":audit,
        "wiredAudit":wired,
        "wanQuality24h":wan,
        "traffic24h":{
            "usage":traffic,
            "dpi":traffic_dpi,
        },
        "speedtest":speed,
        "channelPlan":channel_plan,
        "optimizationTests":db.list_optimization_tests(100),
        "automationState":{
            "autoOptimizeEnabled":db.get_setting("auto_optimize_enabled","0")=="1",
            "autoOptimizeCapabilities":["enable_band_steering","enable_bss_transition"],
            "autoRfEnabled":db.get_setting("auto_rf_enabled","0")=="1",
            "autoRfCapabilities":["channel","channel_width"],
            "privateRfWriteVerified":db.get_setting("private_rf_write_verified","0")=="1",
            "privateRfConfigured":private_api.configured,
            "rfTestActive":_rf_test_active(),
        },
        "healthHistory24h":db.health_history(24),
        "roaming24h":db.roaming_summary(24),
        "recentLog":db.recent_logs(200),
        "ai":_ai_status(include_history=False),
    }

def _ai_status(include_history=True):
    try:
        interval=max(1,min(24,int(float(db.get_setting("ai_interval_hours","6") or 6))))
    except Exception:
        interval=6
    history=db.ai_report_history(20) if include_history else []
    latest=history[0] if history else (db.ai_report_history(1)[0] if db.ai_report_history(1) else None)
    return {
        "configured":bool(OPENAI_API_KEY),
        "model":OPENAI_MODEL,
        "automaticEnabled":db.get_setting("ai_auto_enabled","0")=="1",
        "intervalHours":interval,
        "running":bool(ai_running or ai_starting),
        "phase":"STARTING" if ai_starting and not ai_running else ("RUNNING" if ai_running else "IDLE"),
        "startedAt":ai_started_at,
        "lastError":ai_last_error,
        "latest":latest,
        "history":history,
        "advisoryOnly":True,
    }

def run_ai_analysis(trigger="manual"):
    global ai_running,ai_started_at,ai_last_error
    if not OPENAI_API_KEY:
        ai_last_error="OPENAI_API_KEY is not configured"
        return False
    if not ai_analysis_lock.acquire(blocking=False):
        return False
    ai_running=True
    ai_started_at=datetime.now(timezone.utc).isoformat()
    ai_last_error=None
    try:
        context=_build_support_context()
        result=analyze_with_openai(OPENAI_API_KEY,OPENAI_MODEL,sanitize(context))
        if result.get("ok"):
            db.record_ai_report(
                trigger,
                result.get("model") or OPENAI_MODEL,
                "SUCCESS",
                summary=result.get("text"),
            )
            return True
        ai_last_error=result.get("error") or "AI analysis failed"
        db.record_ai_report(trigger,OPENAI_MODEL,"FAILED",error=ai_last_error)
        return False
    except Exception as e:
        ai_last_error=str(e)
        db.record_ai_report(trigger,OPENAI_MODEL,"FAILED",error=str(e))
        print("AI advisor error:",e,flush=True)
        return False
    finally:
        ai_running=False
        ai_started_at=None
        ai_analysis_lock.release()

def _run_ai_thread(trigger):
    global ai_starting
    try:
        run_ai_analysis(trigger)
    finally:
        ai_starting=False

def ai_scheduler_loop():
    time.sleep(90)
    while True:
        try:
            if OPENAI_API_KEY and db.get_setting("ai_auto_enabled","0")=="1" and not ai_running:
                interval=max(1,min(24,int(float(db.get_setting("ai_interval_hours","6") or 6))))
                history=db.ai_report_history(1)
                due=True
                if history and history[0].get("ts"):
                    dt=datetime.fromisoformat(history[0]["ts"])
                    if dt.tzinfo is None:
                        dt=dt.replace(tzinfo=timezone.utc)
                    due=(datetime.now(timezone.utc)-dt).total_seconds() >= interval*3600
                if due and not _rf_test_active():
                    run_ai_analysis("automatic")
        except Exception as e:
            print("AI scheduler error:",e,flush=True)
        time.sleep(60)

def start_ai_scheduler():
    global ai_scheduler_started
    with ai_scheduler_lock:
        if ai_scheduler_started:
            return
        ai_scheduler_started=True
        threading.Thread(target=ai_scheduler_loop,daemon=True).start()

def report_data():
    global last_controller_success
    snap = build_snapshot(api)
    if not snap:
        return None
    last_controller_success=datetime.now(timezone.utc).isoformat()
    try:
        retry_trends = db.ap_retry_trends(15)
    except Exception as e:
        print("Retry trend error:", e, flush=True)
        retry_trends = {}
    try:
        ap_baselines = db.ap_client_baselines(24)
    except Exception as e:
        print("AP baseline error:", e, flush=True)
        ap_baselines = {}
    analysis = analyze(snap, retry_trends, ap_baselines)
    channel_plan = build_channel_plan(snap, retry_trends)
    aps = [d for d in snap["devices"] if d.get("optimizerType") == "ACCESS_POINT"]
    switches = [d for d in snap["devices"] if d.get("optimizerType") in ("SWITCH","GATEWAY")]
    gateway = next((d for d in snap["devices"] if d.get("optimizerType") == "GATEWAY"), None)
    wifi = []
    for w in snap["wifiBroadcasts"]:
        row=dict(w); row["optimizerStatus"]=wifi_status(w); wifi.append(row)
    try:
        roaming_data = db.roaming_summary(24)
    except Exception as e:
        print("Roaming summary error:", e, flush=True)
        roaming_data = []
    try:
        internet_data = db.internet_summary(24)
    except Exception as e:
        print("Internet summary error:", e, flush=True)
        internet_data = {"latest":None,"availabilityPct":None,"avgLatencyMs":None,"maxLatencyMs":None,"outageCount":0,"lastOutage":None,"onlineSince":None,"samples":[]}

    return {
        "ok":True,"version":VERSION,"site":snap["site"],"devices":snap["devices"],
        "accessPoints":aps,"switches":switches,"clients":_enrich_client_inventory(snap),
        "networks":snap.get("networks") or [],
        "wifiBroadcasts":wifi,"analysis":analysis,
        "autoOptimizeEnabled":db.get_setting("auto_optimize_enabled","0")=="1",
        "lastChecked":datetime.now(timezone.utc).isoformat(),
        "pollIntervalSeconds":POLL_INTERVAL,
        "retentionDays":RETENTION_DAYS,
        "roaming":roaming_data,
        "retryTrends":retry_trends,
        "apBaselines":ap_baselines,
        "channelPlan":channel_plan,
        "gateway":gateway,
        "internet":internet_data,
        "optimizationTests":evaluate_optimization_tests(snap),
        "healthHistory":db.health_history(24)
    }

def _current_radio_config(snapshot, ap_id, band):
    if not snapshot:
        return None
    for ap in snapshot.get("devices",[]):
        if ap.get("id")!=ap_id:
            continue
        for radio in ((ap.get("interfaces") or {}).get("radios") or []):
            if radio.get("frequencyGHz")==band:
                return {
                    "channel":radio.get("channel"),
                    "widthMHz":radio.get("channelWidthMHz")
                }
    return None

def _trend_retry_for_band(trends, ap_id, band):
    t=(trends or {}).get(ap_id) or {}
    key={2.4:"retry24",5.0:"retry5",5:"retry5",6.0:"retry6",6:"retry6"}.get(band)
    if not key:
        return None
    value=t.get(key)
    return float(value) if value is not None else None

def _retry_comparison(reference, candidate):
    if reference is None or candidate is None:
        return "INCONCLUSIVE"
    reference=float(reference)
    candidate=float(candidate)
    delta=candidate-reference
    if delta <= -2.0:
        return "IMPROVED"
    if delta >= 2.0:
        return "WORSE"
    # Percentage comparisons become misleading near zero, so only use them
    # when the reference retry rate is large enough to be meaningful.
    if reference >= 5.0:
        if candidate <= reference*0.80:
            return "IMPROVED"
        if candidate >= reference*1.20:
            return "WORSE"
    return "NO_CHANGE"

def _preliminary_result(baseline, post):
    return _retry_comparison(baseline,post)

def _candidate_conflict_count(snapshot, target_ap_id, band, channel, width):
    if not snapshot:
        return None
    rows=[]
    for ap in snapshot.get("devices",[]):
        if ap.get("optimizerType")!="ACCESS_POINT":
            continue
        radio=next((r for r in ((ap.get("interfaces") or {}).get("radios") or []) if r.get("frequencyGHz")==band),None)
        if not radio:
            continue
        ch=channel if ap.get("id")==target_ap_id else radio.get("channel")
        w=width if ap.get("id")==target_ap_id else radio.get("channelWidthMHz")
        key=radio_conflict_key(band,ch,w)
        rows.append({"id":ap.get("id"),"key":key})

    count=0
    target_conflicts=0
    for i in range(len(rows)):
        for j in range(i+1,len(rows)):
            if rows[i]["key"] and rows[i]["key"]==rows[j]["key"]:
                count+=1
                if target_ap_id in (rows[i]["id"],rows[j]["id"]):
                    target_conflicts+=1
    return {"networkConflicts":count,"targetConflicts":target_conflicts}

def _topology_metrics_for_test(snapshot, test):
    original=_candidate_conflict_count(
        snapshot,test.get("ap_id"),test.get("band"),
        test.get("original_channel"),test.get("original_width_mhz")
    )
    proposed=_candidate_conflict_count(
        snapshot,test.get("ap_id"),test.get("band"),
        test.get("proposed_channel"),test.get("proposed_width_mhz")
    )
    if not original or not proposed:
        return None
    return {
        "originalNetworkConflicts":original["networkConflicts"],
        "proposedNetworkConflicts":proposed["networkConflicts"],
        "originalTargetConflicts":original["targetConflicts"],
        "proposedTargetConflicts":proposed["targetConflicts"],
        "targetConflictDelta":proposed["targetConflicts"]-original["targetConflicts"],
        "networkConflictDelta":proposed["networkConflicts"]-original["networkConflicts"],
    }

def _aba_final_result(t, rollback_stats, topology=None):
    baseline=t.get("baseline_retry_60")
    if baseline is None:
        baseline=t.get("baseline_retry")
    post=t.get("post_retry_avg")
    rollback=rollback_stats.get("retryAvg")
    if baseline is None or post is None or rollback is None:
        return "INCONCLUSIVE"

    baseline_samples=t.get("baseline_sample_count") or 0
    post_samples=t.get("post_sample_count") or 0
    rollback_samples=rollback_stats.get("sampleCount") or 0
    if min(post_samples,rollback_samples) < 20 or (baseline_samples and baseline_samples < 20):
        return "INCONCLUSIVE"

    baseline_clients=t.get("baseline_client_count")
    post_clients=t.get("post_client_count")
    rollback_clients=rollback_stats.get("clientAvg")
    if baseline_clients is not None and post_clients is not None:
        if abs(float(post_clients)-float(baseline_clients)) > max(3.0,float(baseline_clients)*0.50):
            return "INCONCLUSIVE_LOAD_CHANGED"
    if rollback_clients is not None and post_clients is not None:
        if abs(float(post_clients)-float(rollback_clients)) > max(3.0,float(rollback_clients)*0.50):
            return "INCONCLUSIVE_LOAD_CHANGED"

    if abs(float(rollback)-float(baseline)) > max(3.0,float(baseline)*0.35):
        return "INCONCLUSIVE_ENVIRONMENT_CHANGED"

    reference=(float(baseline)+float(rollback))/2.0
    retry_result=_retry_comparison(reference,post)
    if retry_result=="IMPROVED":
        return "IMPROVED_CONFIRMED"
    if retry_result=="WORSE":
        return "WORSE_CONFIRMED"

    # If retry performance is effectively unchanged, allow a proven topology
    # improvement (removing our own AP overlap) to count as a confirmed win.
    if topology:
        original_target=topology.get("originalTargetConflicts")
        proposed_target=topology.get("proposedTargetConflicts")
        if original_target is not None and proposed_target is not None:
            if proposed_target < original_target and float(post) <= reference + 2.0:
                return "IMPROVED_TOPOLOGY"
            if proposed_target > original_target:
                return "WORSE_TOPOLOGY"

    return "NO_MEANINGFUL_CHANGE"

def _private_rf_status():
    configured=private_api.configured
    verified=db.get_setting("private_rf_write_verified","0")=="1"
    auto_enabled=db.get_setting("auto_rf_enabled","0")=="1"
    if not configured:
        status="CREDENTIALS_MISSING"
        detail="Add UNIFI_PRIVATE_USERNAME and UNIFI_PRIVATE_PASSWORD to the Unraid container to enable classic API discovery."
    elif not verified:
        status="DISCOVERY_READY"
        detail="Private API credentials are configured. Run read-only discovery, then explicitly validate a no-op radio write before Auto RF can be enabled."
    else:
        status="WRITE_VERIFIED"
        detail="Private RF write path has been validated. Auto RF can make one channel/width change at a time through the A/B/A workflow."
    return {
        "status":status,
        "detail":detail,
        "configured":configured,
        "writeVerified":verified,
        "autoEnabled":auto_enabled,
        "lastDiscovery":private_rf_last_discovery,
        "lastError":private_rf_last_error,
        "site":UNIFI_SITE_NAME,
    }

def _private_device_for_test(snapshot, test):
    if not snapshot:
        return None
    ap=next((d for d in snapshot.get("devices",[]) if d.get("id")==test.get("ap_id")),None)
    if not ap:
        return None
    mac=ap.get("macAddress") or ap.get("mac")
    ip=ap.get("ipAddress") or ap.get("ip")
    return private_api.find_device(mac=mac,name=ap.get("name"),ip=ip)

def _attempt_private_rf_write(snapshot, test, channel, width, attempt_field, action_name):
    if db.get_setting("auto_rf_enabled","0")!="1":
        return None
    if db.get_setting("private_rf_write_verified","0")!="1":
        return None
    attempted=test.get(attempt_field)
    if attempted:
        try:
            at=datetime.fromisoformat(attempted)
            if at.tzinfo is None:
                at=at.replace(tzinfo=timezone.utc)
            if (datetime.now(timezone.utc)-at).total_seconds() < 600:
                return None
        except Exception:
            pass

    db.mark_rf_attempt(test["id"],attempt_field)
    device=_private_device_for_test(snapshot,test)
    if not device:
        db.log(action_name,test.get("ap_name"),"Classic API device mapping failed","FAILED")
        db.set_setting("auto_rf_enabled","0")
        return {"ok":False,"error":"Classic device mapping failed"}

    result=private_api.write_radio(
        device=device,
        band=test.get("band"),
        channel=channel,
        width=width,
    )
    if result.get("ok"):
        db.log(
            action_name,
            test.get("ap_name"),
            str(test.get("band"))+" GHz -> channel "+str(channel)+" / "+str(width)+" MHz",
            "ACCEPTED"
        )
    else:
        db.log(
            action_name,
            test.get("ap_name"),
            "Private API write failed: "+str(result.get("status"))+" "+str(result.get("error") or result.get("data")),
            "FAILED"
        )
        # Fail closed. The user can inspect the error and re-enable only after fixing it.
        db.set_setting("auto_rf_enabled","0")
    return result

def evaluate_optimization_tests(snapshot=None):
    try:
        tests=db.list_optimization_tests(100)
        trends=db.ap_retry_trends(15)
    except Exception as e:
        print("Optimization test evaluation error:",e,flush=True)
        return []

    now=datetime.now(timezone.utc)
    for t in tests:
        status=t.get("status")
        phase=t.get("phase") or "PROPOSED"

        if status in ("PROPOSED","MONITORING","ROLLBACK_REQUIRED","ROLLBACK_MONITORING"):
            original_known=(t.get("original_channel") is not None or t.get("original_width_mhz") is not None)
            proposed_known=(t.get("proposed_channel") is not None or t.get("proposed_width_mhz") is not None)
            same_channel=(t.get("original_channel")==t.get("proposed_channel"))
            same_width=(t.get("original_width_mhz")==t.get("proposed_width_mhz"))
            if original_known and proposed_known and same_channel and same_width:
                invalid=db.invalidate_test(t["id"],"INVALID_NO_CHANGE")
                db.log("RF_TEST_INVALID",t.get("ap_name"),str(t.get("band"))+" GHz test had identical A and B settings","INVALID_NO_CHANGE")
                t=invalid or t
                continue

        if status=="PROPOSED" and snapshot and db.get_setting("auto_rf_enabled","0")=="1":
            _attempt_private_rf_write(
                snapshot,t,
                t.get("proposed_channel"),t.get("proposed_width_mhz"),
                "auto_apply_attempted_at","RF_AUTO_APPLY_TEST"
            )

        if status=="PROPOSED" and snapshot:
            live=_current_radio_config(snapshot,t.get("ap_id"),t.get("band"))
            if live:
                channel_match=(t.get("proposed_channel") is None or live.get("channel")==t.get("proposed_channel"))
                width_match=(t.get("proposed_width_mhz") is None or live.get("widthMHz")==t.get("proposed_width_mhz"))
                if channel_match and width_match:
                    updated=db.mark_test_applied(t["id"])
                    if updated:
                        db.log("RF_TEST_AUTO_DETECT",t.get("ap_name"),str(t.get("band"))+" GHz new setting detected","MONITORING")
                        t=updated
                        status=t.get("status")
                        phase=t.get("phase") or "SETTLING_NEW"

        if status=="MONITORING" and t.get("applied_at"):
            current=_trend_retry_for_band(trends,t.get("ap_id"),t.get("band"))
            applied=datetime.fromisoformat(t["applied_at"])
            if applied.tzinfo is None:
                applied=applied.replace(tzinfo=timezone.utc)
            minutes=(now-applied).total_seconds()/60.0

            if minutes < 15:
                db.update_test_phase(t["id"],"SETTLING_NEW",status="MONITORING",last_retry=current)
                continue

            if minutes < 75:
                db.update_test_phase(t["id"],"MONITORING_NEW",status="MONITORING",last_retry=current)
                continue

            start_window=(applied+timedelta(minutes=15)).isoformat()
            end_window=(applied+timedelta(minutes=75)).isoformat()
            post_stats=db.ap_window_stats(t.get("ap_id"),t.get("band"),start_window,end_window)
            baseline=t.get("baseline_retry_60")
            if baseline is None:
                baseline=t.get("baseline_retry")
            preliminary=_preliminary_result(baseline,post_stats.get("retryAvg"))
            updated=db.update_test_phase(
                t["id"],"AWAITING_ROLLBACK",status="ROLLBACK_REQUIRED",
                last_retry=current,preliminary_result=preliminary,post_stats=post_stats
            )
            db.log(
                "RF_TEST_B_PHASE",
                t.get("ap_name"),
                str(t.get("band"))+" GHz new-setting average "+str(round(post_stats.get("retryAvg") or 0,1))+"%; rollback verification required",
                preliminary
            )
            t=updated or t
            status=t.get("status")

        if status=="ROLLBACK_REQUIRED" and snapshot and db.get_setting("auto_rf_enabled","0")=="1":
            _attempt_private_rf_write(
                snapshot,t,
                t.get("original_channel"),t.get("original_width_mhz"),
                "auto_rollback_attempted_at","RF_AUTO_ROLLBACK_TEST"
            )

        if status=="ROLLBACK_REQUIRED" and snapshot:
            original_channel=t.get("original_channel")
            original_width=t.get("original_width_mhz")
            if original_channel is not None or original_width is not None:
                live=_current_radio_config(snapshot,t.get("ap_id"),t.get("band"))
                if live:
                    channel_match=(original_channel is None or live.get("channel")==original_channel)
                    width_match=(original_width is None or live.get("widthMHz")==original_width)
                    if channel_match and width_match:
                        updated=db.start_test_rollback(t["id"])
                        if updated:
                            db.log("RF_TEST_ROLLBACK_DETECT",t.get("ap_name"),str(t.get("band"))+" GHz original setting detected","ROLLBACK_MONITORING")
                            t=updated
                            status=t.get("status")

        if status=="ROLLBACK_MONITORING" and t.get("rollback_started_at"):
            rollback_started=datetime.fromisoformat(t["rollback_started_at"])
            if rollback_started.tzinfo is None:
                rollback_started=rollback_started.replace(tzinfo=timezone.utc)
            minutes=(now-rollback_started).total_seconds()/60.0
            current=_trend_retry_for_band(trends,t.get("ap_id"),t.get("band"))

            if minutes < 15:
                db.update_test_phase(t["id"],"SETTLING_ROLLBACK",status="ROLLBACK_MONITORING",last_retry=current)
                continue

            if minutes < 75:
                db.update_test_phase(t["id"],"MONITORING_ROLLBACK",status="ROLLBACK_MONITORING",last_retry=current)
                continue

            start_window=(rollback_started+timedelta(minutes=15)).isoformat()
            end_window=(rollback_started+timedelta(minutes=75)).isoformat()
            rollback_stats=db.ap_window_stats(t.get("ap_id"),t.get("band"),start_window,end_window)
            topology=_topology_metrics_for_test(snapshot,t)
            result=_aba_final_result(t,rollback_stats,topology)
            completed=db.complete_aba_test(t["id"],result,rollback_stats)
            if result in ("IMPROVED_CONFIRMED","IMPROVED_TOPOLOGY") and snapshot and db.get_setting("auto_rf_enabled","0")=="1":
                final_test=completed or t
                _attempt_private_rf_write(
                    snapshot,final_test,
                    final_test.get("proposed_channel"),final_test.get("proposed_width_mhz"),
                    "final_apply_attempted_at","RF_AUTO_FINAL_APPLY"
                )
            db.log(
                "RF_TEST_ABA_RESULT",
                t.get("ap_name"),
                str(t.get("band"))+" GHz A/B/A verification complete",
                result
            )
            t=completed or t

    try:
        items=db.list_optimization_tests(100)
        if snapshot:
            for item in items:
                item["topology"]=_topology_metrics_for_test(snapshot,item)
        return items
    except Exception:
        return []

def _active_rf_tests():
    try:
        active={"PROPOSED","MONITORING","ROLLBACK_REQUIRED","ROLLBACK_MONITORING"}
        return [t for t in db.list_optimization_tests(100) if t.get("status") in active]
    except Exception:
        return []

def _rf_test_active():
    return bool(_active_rf_tests())

def _ookla_speedtest_available():
    try:
        r=subprocess.run(
            ["speedtest","--version"],
            capture_output=True,text=True,timeout=10
        )
        return r.returncode==0
    except Exception:
        return False

def _list_speedtest_servers():
    try:
        r=subprocess.run(
            ["speedtest","--accept-license","--accept-gdpr","-L"],
            capture_output=True,text=True,timeout=30
        )
        if r.returncode!=0:
            return {
                "ok":False,
                "error":(r.stderr or r.stdout or "Unable to list Ookla servers").strip(),
                "returnCode":r.returncode
            }

        servers=[]
        for raw in r.stdout.splitlines():
            line=raw.rstrip()
            if not line.strip():
                continue
            if "Closest servers" in line or set(line.strip())=={"="}:
                continue
            if re.match(r"^\s*ID\s+",line):
                continue

            # Official Ookla -L output is fixed-width, but names/locations may
            # themselves contain spaces. Split on runs of 2+ spaces.
            parts=[p.strip() for p in re.split(r"\s{2,}",line.strip()) if p.strip()]
            if len(parts) < 4 or not parts[0].isdigit():
                continue

            servers.append({
                "id":parts[0],
                "name":parts[1],
                "location":parts[2],
                "country":" ".join(parts[3:]),
            })

        if not servers:
            preview=" | ".join(x.strip() for x in r.stdout.splitlines()[:8] if x.strip())
            return {
                "ok":False,
                "error":"Ookla returned a server list, but the app could not parse it.",
                "outputPreview":preview[:1000]
            }

        return {"ok":True,"servers":servers[:25],"count":len(servers)}
    except FileNotFoundError:
        return {"ok":False,"error":"Official Ookla Speedtest CLI is not installed in this container."}
    except subprocess.TimeoutExpired:
        return {"ok":False,"error":"Ookla nearby-server lookup timed out after 30 seconds."}
    except Exception as e:
        return {"ok":False,"error":str(e)}

def _speedtest_state():
    summary=db.speedtest_summary(30)
    interval=max(1,min(24,int(float(db.get_setting("speedtest_interval_hours","6") or 6))))
    enabled=db.get_setting("speedtest_enabled","1")=="1"
    preferred_server_id=(db.get_setting("speedtest_preferred_server_id","") or "").strip()
    latest=summary.get("latest")
    next_due=None
    if latest and latest.get("ts"):
        try:
            dt=datetime.fromisoformat(latest["ts"])
            if dt.tzinfo is None:
                dt=dt.replace(tzinfo=timezone.utc)
            next_due=(dt+timedelta(hours=interval)).isoformat()
        except Exception:
            next_due=None
    return {
        "enabled":enabled,
        "intervalHours":interval,
        "running":speedtest_running,
        "startedAt":speedtest_started_at,
        "lastError":speedtest_last_error,
        "nextDue":next_due,
        "deferredByRfTest":_rf_test_active(),
        "preferredServerId":preferred_server_id,
        "engine":"OOKLA_OFFICIAL",
        "engineAvailable":_ookla_speedtest_available(),
        **summary
    }

def run_speedtest_job(source="automatic"):
    global speedtest_running,speedtest_started_at,speedtest_last_error
    if not speedtest_lock.acquire(blocking=False):
        return False
    speedtest_running=True
    speedtest_started_at=datetime.now(timezone.utc).isoformat()
    speedtest_last_error=None
    started=time.perf_counter()
    try:
        preferred=(db.get_setting("speedtest_preferred_server_id","") or "").strip()
        cmd=[
            "speedtest",
            "--accept-license",
            "--accept-gdpr",
            "--progress=no",
            "--format=json",
        ]
        if preferred:
            cmd.append("--server-id="+preferred)

        proc=subprocess.run(cmd,capture_output=True,text=True,timeout=180)
        if proc.returncode!=0:
            raise RuntimeError((proc.stderr or proc.stdout or "Ookla Speedtest CLI failed").strip())

        results=json.loads(proc.stdout)
        duration=time.perf_counter()-started
        download=float(((results.get("download") or {}).get("bandwidth") or 0))*8.0/1_000_000.0
        upload=float(((results.get("upload") or {}).get("bandwidth") or 0))*8.0/1_000_000.0
        ping_data=results.get("ping") or {}
        ping=float(ping_data.get("latency")) if ping_data.get("latency") is not None else None
        jitter=float(ping_data.get("jitter")) if ping_data.get("jitter") is not None else None
        packet_loss=results.get("packetLoss")
        packet_loss=float(packet_loss) if packet_loss is not None else None
        srv=results.get("server") or {}
        iface=results.get("interface") or {}
        server_provider=srv.get("name")
        server_location=srv.get("location")
        server_country=srv.get("country")
        server_label=server_location or server_provider
        client_ip=iface.get("externalIp") or iface.get("internalIp")

        db.record_speedtest(
            True,
            download_mbps=download,
            upload_mbps=upload,
            ping_ms=ping,
            server_name=server_label,
            server_sponsor=server_provider,
            server_id=srv.get("id"),
            server_location=server_location,
            server_country=server_country,
            server_host=srv.get("host"),
            jitter_ms=jitter,
            packet_loss_pct=packet_loss,
            client_ip=client_ip,
            duration_sec=duration,
        )
        server_desc=" / ".join([x for x in (server_provider,server_location,server_country) if x])
        detail=f"{download:.1f} Mbps down / {upload:.1f} Mbps up"
        if ping is not None:
            detail+=f" / {ping:.1f} ms ping"
        if server_desc:
            detail+=" / "+server_desc
        db.log("SPEEDTEST",source,detail,"SUCCESS")
        return True
    except Exception as e:
        duration=time.perf_counter()-started
        speedtest_last_error=str(e)
        db.record_speedtest(False,duration_sec=duration,error=str(e))
        db.log("SPEEDTEST",source,str(e),"FAILED")
        print("Speedtest error:",e,flush=True)
        return False
    finally:
        speedtest_running=False
        speedtest_started_at=None
        speedtest_lock.release()

def speedtest_scheduler_loop():
    # Give the rest of the monitor time to settle after container startup.
    time.sleep(60)
    while True:
        try:
            if db.get_setting("speedtest_enabled","1")=="1" and not speedtest_running:
                interval=max(1,min(24,int(float(db.get_setting("speedtest_interval_hours","6") or 6))))
                state=db.speedtest_summary(30)
                latest=state.get("latest")
                due=True
                if latest and latest.get("ts"):
                    dt=datetime.fromisoformat(latest["ts"])
                    if dt.tzinfo is None:
                        dt=dt.replace(tzinfo=timezone.utc)
                    due=(datetime.now(timezone.utc)-dt).total_seconds() >= interval*3600
                # Avoid adding heavy WAN traffic while an RF A/B/A test is active.
                if due and not _rf_test_active():
                    run_speedtest_job("automatic")
        except Exception as e:
            print("Speedtest scheduler error:",e,flush=True)
        time.sleep(60)

def start_speedtest_scheduler():
    global speedtest_scheduler_started
    with speedtest_scheduler_lock:
        if speedtest_scheduler_started:
            return
        speedtest_scheduler_started=True
        threading.Thread(target=speedtest_scheduler_loop,daemon=True).start()

def probe_internet():
    started=time.perf_counter()
    try:
        r=requests.get("https://connectivitycheck.gstatic.com/generate_204",timeout=5)
        latency_ms=(time.perf_counter()-started)*1000.0
        return 200 <= r.status_code < 400, latency_ms
    except Exception:
        return False, None

def monitor_loop():
    global last_monitor_cycle,last_monitor_error,traffic_last_sample_monotonic,wan_last_sample_monotonic
    elapsed=0
    while True:
        try:
            data=report_data()
            if data:
                for ap in data["accessPoints"]:
                    db.record_ap(ap)
                    db.record_radio_configs(ap)
                db.record_wireless_clients(data["clients"])
                try:
                    wired_now=_wired_audit_for_snapshot(data,include_events=False)
                    db.record_wired_ports(wired_now.get("ports") or [])
                except Exception as e:
                    print("Wired port monitor error:",e,flush=True)
                if (time.monotonic()-traffic_last_sample_monotonic) >= traffic_sample_interval_seconds:
                    _sample_traffic(data)
                if (time.monotonic()-wan_last_sample_monotonic) >= wan_quality_sample_seconds:
                    _sample_wan_quality()
                analysis=data.get("analysis") or {}
                db.record_health_score(
                    analysis.get("healthScore",0),
                    analysis.get("high",0),
                    analysis.get("medium",0)
                )
                gateway=data.get("gateway") or {}
                stats=gateway.get("statistics") or {}
                uplink=stats.get("uplink") or {}
                online,latency_ms=probe_internet()
                db.record_internet_sample(
                    online,
                    latency_ms,
                    uplink.get("rxRateBps"),
                    uplink.get("txRateBps"),
                    stats.get("uptimeSec")
                )
            last_monitor_cycle=datetime.now(timezone.utc).isoformat()
            last_monitor_error=None
            elapsed += POLL_INTERVAL
            if elapsed >= 900:
                elapsed=0
                if db.get_setting("auto_optimize_enabled","0")=="1":
                    auto_optimize(api,db)
        except Exception as e:
            last_monitor_error=str(e)
            print("Monitor error:",e,flush=True)
        time.sleep(POLL_INTERVAL)

def start_monitor():
    global monitor_started
    with monitor_lock:
        if monitor_started: return
        monitor_started=True
        threading.Thread(target=monitor_loop,daemon=True).start()

@app.route("/")
def index():
    return render_template("index.html", version=VERSION)

@app.route("/api/export/support-bundle.zip")
def export_support_bundle():
    try:
        context=_build_support_context()
        bundle=build_zip_bytes(context)
        stamp=datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        return send_file(
            bundle,
            mimetype="application/zip",
            as_attachment=True,
            download_name=f"unifi-optimizer-support-{stamp}.zip"
        )
    except Exception as e:
        print("Export bundle error:",e,flush=True)
        return jsonify({"ok":False,"error":str(e)}),500

@app.route("/api/export/support-bundle.json")
def export_support_json():
    try:
        context=_build_support_context()
        body=build_json_bytes(context)
        stamp=datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        return Response(
            body,
            mimetype="application/json",
            headers={"Content-Disposition":f'attachment; filename="unifi-optimizer-support-{stamp}.json"'}
        )
    except Exception as e:
        return jsonify({"ok":False,"error":str(e)}),500

@app.route("/api/export/summary")
def export_support_summary():
    try:
        context=_build_support_context()
        return Response(compact_support_summary(sanitize(context)),mimetype="text/plain")
    except Exception as e:
        return Response("Export summary failed: "+str(e),status=500,mimetype="text/plain")

@app.route("/api/ai")
def ai_status():
    return jsonify({"ok":True,**_ai_status()})

@app.route("/api/ai/analyze",methods=["POST"])
def ai_analyze():
    global ai_starting,ai_started_at
    if not OPENAI_API_KEY:
        return jsonify({
            "ok":False,
            "error":"OPENAI_API_KEY is not configured in the Unraid container."
        }),400
    if ai_running or ai_starting:
        return jsonify({"ok":False,"error":"AI analysis is already running"}),409
    if _rf_test_active():
        blockers=[{
            "id":t.get("id"),
            "apName":t.get("ap_name"),
            "band":t.get("band"),
            "status":t.get("status"),
            "phase":t.get("phase")
        } for t in _active_rf_tests()]
        return jsonify({
            "ok":False,
            "error":"AI analysis is deferred while an RF A/B/A test is active so the advisor does not judge a temporary test state.",
            "blockers":blockers
        }),409

    # Mark the job as starting synchronously before spawning the worker so
    # the UI never falls back to READY during the thread-start race.
    ai_starting=True
    ai_started_at=datetime.now(timezone.utc).isoformat()
    threading.Thread(target=_run_ai_thread,args=("manual",),daemon=True).start()
    return jsonify({
        "ok":True,
        "started":True,
        "phase":"STARTING",
        "startedAt":ai_started_at
    })

@app.route("/api/ai/settings",methods=["POST"])
def ai_settings():
    body=request.get_json(silent=True) or {}
    if "automaticEnabled" in body:
        if bool(body.get("automaticEnabled")) and not OPENAI_API_KEY:
            return jsonify({"ok":False,"error":"Configure OPENAI_API_KEY before enabling automatic AI analysis."}),400
        db.set_setting("ai_auto_enabled","1" if bool(body.get("automaticEnabled")) else "0")
    if "intervalHours" in body:
        try:
            interval=int(body.get("intervalHours"))
            if interval not in (1,3,6,12,24):
                return jsonify({"ok":False,"error":"Interval must be 1, 3, 6, 12, or 24 hours"}),400
            db.set_setting("ai_interval_hours",str(interval))
        except Exception:
            return jsonify({"ok":False,"error":"Invalid AI interval"}),400
    return jsonify({"ok":True,**_ai_status()})

@app.route("/api/report")
def report():
    try:
        data=report_data()
        if not data:
            return jsonify({"ok":False,"error":"Unable to retrieve UniFi data"}),500
        return jsonify(data)
    except Exception as e:
        print("Report error:", e, flush=True)
        traceback.print_exc()
        return jsonify({"ok":False,"error":str(e)}),500

@app.route("/api/auto-optimize",methods=["POST"])
def toggle_auto():
    enabled=bool((request.get_json(silent=True) or {}).get("enabled"))
    db.set_setting("auto_optimize_enabled","1" if enabled else "0")
    return jsonify({"ok":True,"enabled":enabled})

@app.route("/api/auto-optimize/run",methods=["POST"])
def run_optimize():
    return jsonify(auto_optimize(api,db))

@app.route("/api/optimization-log")
def logs():
    return jsonify({"ok":True,"items":db.recent_logs(100)})

@app.route("/api/roaming")
def roaming():
    return jsonify({"ok":True,"clients":db.roaming_summary(24),"events":db.recent_roams(100)})

@app.route("/api/internet")
def internet():
    return jsonify({"ok":True,**db.internet_summary(24)})

@app.route("/api/speedtest")
def speedtest_data():
    state=_speedtest_state()
    state["history"]=db.speedtest_history(30,500)
    return jsonify({"ok":True,**state})

@app.route("/api/speedtest/servers")
def speedtest_servers():
    result=_list_speedtest_servers()
    status=200 if result.get("ok") else 500
    return jsonify(result),status

@app.route("/api/speedtest/run",methods=["POST"])
def speedtest_run():
    if speedtest_running:
        return jsonify({"ok":False,"error":"A speed test is already running"}),409
    if _rf_test_active():
        return jsonify({
            "ok":False,
            "error":"An RF A/B/A test is active. Automatic speed tests are deferred to avoid adding traffic during RF measurements."
        }),409
    threading.Thread(target=run_speedtest_job,args=("manual",),daemon=True).start()
    return jsonify({"ok":True,"started":True})

@app.route("/api/speedtest/settings",methods=["POST"])
def speedtest_settings():
    body=request.get_json(silent=True) or {}
    if "enabled" in body:
        db.set_setting("speedtest_enabled","1" if bool(body.get("enabled")) else "0")
    if "intervalHours" in body:
        try:
            interval=int(body.get("intervalHours"))
            if interval not in (1,3,6,12,24):
                return jsonify({"ok":False,"error":"Interval must be 1, 3, 6, 12, or 24 hours"}),400
            db.set_setting("speedtest_interval_hours",str(interval))
        except Exception:
            return jsonify({"ok":False,"error":"Invalid speed test interval"}),400
    if "preferredServerId" in body:
        value=str(body.get("preferredServerId") or "").strip()
        if value and not value.isdigit():
            return jsonify({"ok":False,"error":"Preferred server ID must be numeric"}),400
        db.set_setting("speedtest_preferred_server_id",value)
    return jsonify({"ok":True,**_speedtest_state()})

@app.route("/api/wired-audit")
def wired_audit():
    try:
        snap=build_snapshot(api)
        if not snap:
            return jsonify({"ok":False,"error":"Unable to retrieve UniFi data"}),500
        result=_wired_audit_for_snapshot(snap)
        return jsonify({
            "ok":True,
            "generatedAt":datetime.now(timezone.utc).isoformat(),
            **result
        })
    except Exception as e:
        print("Wired audit error:",e,flush=True)
        traceback.print_exc()
        return jsonify({"ok":False,"error":str(e)}),500

@app.route("/api/network-audit")
def network_audit():
    try:
        snap=build_snapshot(api)
        if not snap:
            return jsonify({"ok":False,"error":"Unable to retrieve UniFi data"}),500
        wired=_wired_audit_for_snapshot(snap)
        result=build_network_audit(snap,api,wired_audit=wired)
        return jsonify({
            "ok":True,
            "generatedAt":datetime.now(timezone.utc).isoformat(),
            **result
        })
    except Exception as e:
        print("Network audit error:",e,flush=True)
        traceback.print_exc()
        return jsonify({"ok":False,"error":str(e)}),500

@app.route("/api/wan-quality")
def wan_quality():
    try:
        hours=int(request.args.get("hours","24"))
    except Exception:
        hours=24
    if hours not in (1,24,168,720):
        hours=24
    summary=db.wan_quality_summary(hours)
    return jsonify({
        "ok":True,
        **summary,
        "score":_wan_quality_score(summary),
        "sampleIntervalSeconds":wan_quality_sample_seconds,
        "dnsSampleIntervalSeconds":wan_dns_sample_seconds,
        "lastSampleAt":wan_last_sample_at,
        "lastError":wan_last_error,
        "targets":summary.get("targets") or [],
    })

@app.route("/api/traffic/diagnostics")
def traffic_diagnostics():
    return jsonify({"ok":True,**_traffic_diagnostics()})

@app.route("/api/traffic/sample",methods=["POST"])
def traffic_sample_now():
    if not private_api.configured:
        return jsonify({"ok":False,"error":"Private UniFi API credentials are not configured"}),400
    try:
        data=report_data()
        if not data:
            return jsonify({"ok":False,"error":"Unable to retrieve UniFi report"}),500
        _sample_traffic(data)
        return jsonify({"ok":True,"diagnostics":_traffic_diagnostics()})
    except Exception as e:
        return jsonify({"ok":False,"error":str(e)}),500

@app.route("/api/traffic")
def traffic_data():
    try:
        hours=int(request.args.get("hours","24"))
    except Exception:
        hours=24
    if hours not in (1,24,168,720):
        hours=24

    summary=db.traffic_summary(hours)
    dpi=db.traffic_dpi_summary(hours)

    live_rows=[]
    if private_api.configured:
        try:
            live_rows=_traffic_live_rows_from_summary(summary)
        except Exception as e:
            print("Live traffic retrieval error:",e,flush=True)

    live_rx=sum(float(x.get("rxRateBps") or 0) for x in live_rows)
    live_tx=sum(float(x.get("txRateBps") or 0) for x in live_rows)

    return jsonify({
        "ok":True,
        "hours":hours,
        "privateConfigured":private_api.configured,
        "sampleIntervalSeconds":traffic_sample_interval_seconds,
        "lastSampleAt":traffic_last_sample_at,
        "lastError":traffic_last_error,
        "live":{
            "rxRateBps":live_rx,
            "txRateBps":live_tx,
            "clients":live_rows
        },
        "usage":summary,
        "dpi":dpi,
        "visibility":{
            "applications":True if private_api.configured else False,
            "exactDestinations":False,
            "detail":"Application/category visibility comes from UniFi DPI. Exact URLs and every encrypted remote destination are not available from the current data source."
        }
    })

@app.route("/api/optimization-tests",methods=["GET","POST"])
def optimization_tests():
    if request.method=="POST":
        body=request.get_json(silent=True) or {}
        required=["apId","apName","band"]
        if any(body.get(k) in (None,"") for k in required):
            return jsonify({"ok":False,"error":"Missing required test fields"}),400
        band=float(body.get("band"))
        snap=build_snapshot(api)
        live=_current_radio_config(snap,body.get("apId"),band) if snap else None
        now=datetime.now(timezone.utc)
        baseline_stats=db.ap_window_stats(
            body.get("apId"),band,
            (now-timedelta(minutes=60)).isoformat(),
            now.isoformat()
        )
        trends=db.ap_retry_trends(15)
        baseline=_trend_retry_for_band(trends,body.get("apId"),band)
        if baseline is None and body.get("baselineRetry") is not None:
            baseline=float(body.get("baselineRetry"))
        baseline60=baseline_stats.get("retryAvg")
        proposed_channel=body.get("proposedChannel")
        proposed_width=body.get("proposedWidthMHz")
        live_channel=(live or {}).get("channel")
        live_width=(live or {}).get("widthMHz")
        if proposed_channel==live_channel and proposed_width==live_width:
            return jsonify({
                "ok":False,
                "error":"No RF configuration change is proposed for this radio. Use monitoring/investigation instead of an A/B/A test."
            }),400
        item=db.create_optimization_test(
            body.get("apId"),body.get("apName"),band,
            proposed_channel,proposed_width,
            live_channel,live_width,
            body.get("description") or "",
            baseline,
            body.get("baselineBasis") or ("15-min average" if baseline is not None else "unavailable"),
            baseline60,
            baseline_stats.get("clientAvg"),
            baseline_stats.get("sampleCount")
        )
        return jsonify({"ok":True,"item":item})
    snap=build_snapshot(api)
    return jsonify({"ok":True,"items":evaluate_optimization_tests(snap)})

@app.route("/api/optimization-tests/<int:test_id>/retest",methods=["POST"])
def optimization_test_retest(test_id):
    previous=db.get_optimization_test(test_id)
    if not previous:
        return jsonify({"ok":False,"error":"Test not found"}),404
    if previous.get("status")!="CANCELLED":
        return jsonify({"ok":False,"error":"Only cancelled tests can be restarted with this action"}),400

    active={"PROPOSED","MONITORING","ROLLBACK_REQUIRED","ROLLBACK_MONITORING"}
    for item in db.list_optimization_tests(100):
        if item.get("id")==test_id:
            continue
        if item.get("status") in active and item.get("ap_id")==previous.get("ap_id") and float(item.get("band"))==float(previous.get("band")):
            return jsonify({"ok":False,"error":"Another active RF test already exists for this AP and band"}),409

    snap=build_snapshot(api)
    live=_current_radio_config(snap,previous.get("ap_id"),float(previous.get("band"))) if snap else None
    if not live:
        return jsonify({"ok":False,"error":"Unable to read the current radio configuration"}),400

    proposed_channel=previous.get("proposed_channel")
    proposed_width=previous.get("proposed_width_mhz")
    if live.get("channel")==proposed_channel and live.get("widthMHz")==proposed_width:
        return jsonify({
            "ok":False,
            "needsRestore":True,
            "error":"The AP is still on the cancelled test setting. Restore the original setting before starting a clean retest.",
            "current":{"channel":live.get("channel"),"widthMHz":live.get("widthMHz")},
            "original":{"channel":previous.get("original_channel"),"widthMHz":previous.get("original_width_mhz")}
        }),409

    now=datetime.now(timezone.utc)
    baseline_stats=db.ap_window_stats(
        previous.get("ap_id"),float(previous.get("band")),
        (now-timedelta(minutes=60)).isoformat(),
        now.isoformat()
    )
    trends=db.ap_retry_trends(15)
    baseline=_trend_retry_for_band(trends,previous.get("ap_id"),float(previous.get("band")))
    baseline60=baseline_stats.get("retryAvg")

    item=db.create_optimization_test(
        previous.get("ap_id"),previous.get("ap_name"),float(previous.get("band")),
        proposed_channel,proposed_width,
        live.get("channel"),live.get("widthMHz"),
        "Retest of cancelled test #"+str(test_id)+": "+str(previous.get("description") or ""),
        baseline,
        "15-min average" if baseline is not None else "unavailable",
        baseline60,
        baseline_stats.get("clientAvg"),
        baseline_stats.get("sampleCount")
    )
    db.log("RF_TEST_RETEST",previous.get("ap_name"),str(previous.get("band"))+" GHz retest created from cancelled test #"+str(test_id),"PROPOSED")
    return jsonify({"ok":True,"item":item})

@app.route("/api/optimization-tests/recover",methods=["POST"])
def optimization_test_recover():
    body=request.get_json(silent=True) or {}
    required=["apId","apName","band"]
    if any(body.get(k) in (None,"") for k in required):
        return jsonify({"ok":False,"error":"Missing recovery fields"}),400

    band=float(body.get("band"))
    snap=build_snapshot(api)
    live=_current_radio_config(snap,body.get("apId"),band) if snap else None
    if not live:
        return jsonify({"ok":False,"error":"Unable to read the current radio configuration"}),400

    change=db.recent_radio_change(body.get("apId"),band,24)
    original_channel=None
    original_width=None
    applied_at=None
    source="manual"

    if change and change.get("to_channel")==live.get("channel") and change.get("to_width_mhz")==live.get("widthMHz"):
        original_channel=change.get("from_channel")
        original_width=change.get("from_width_mhz")
        applied_at=change.get("ts")
        source="history"
    else:
        original_channel=body.get("originalChannel")
        original_width=body.get("originalWidthMHz")
        minutes_ago=body.get("minutesAgo")
        if original_channel is None or original_width is None or minutes_ago in (None,""):
            return jsonify({
                "ok":False,
                "needsManual":True,
                "currentChannel":live.get("channel"),
                "currentWidthMHz":live.get("widthMHz"),
                "error":"No recorded pre-change configuration is available yet. Enter the previous channel, previous width, and approximately how many minutes ago the change was applied."
            }),400
        try:
            applied_at=(datetime.now(timezone.utc)-timedelta(minutes=float(minutes_ago))).isoformat()
        except Exception:
            return jsonify({"ok":False,"error":"Invalid minutes-ago value"}),400

    if original_channel==live.get("channel") and original_width==live.get("widthMHz"):
        return jsonify({"ok":False,"error":"The previous and current RF settings are identical."}),400

    applied_dt=datetime.fromisoformat(applied_at)
    if applied_dt.tzinfo is None:
        applied_dt=applied_dt.replace(tzinfo=timezone.utc)
    baseline_stats=db.ap_window_stats(
        body.get("apId"),band,
        (applied_dt-timedelta(minutes=60)).isoformat(),
        applied_dt.isoformat()
    )
    baseline60=baseline_stats.get("retryAvg")

    item=db.create_optimization_test(
        body.get("apId"),body.get("apName"),band,
        live.get("channel"),live.get("widthMHz"),
        original_channel,original_width,
        "Recovered already-applied RF change",
        baseline60,
        "60-min pre-change recovery baseline" if baseline60 is not None else "recovery baseline unavailable",
        baseline60,
        baseline_stats.get("clientAvg"),
        baseline_stats.get("sampleCount")
    )
    item=db.mark_test_applied_at(item["id"],applied_at)
    db.log(
        "RF_TEST_RECOVERED",
        body.get("apName"),
        str(band)+" GHz "+str(original_channel)+"/"+str(original_width)+" -> "+str(live.get("channel"))+"/"+str(live.get("widthMHz"))+" ("+source+")",
        "MONITORING"
    )
    return jsonify({"ok":True,"item":item,"source":source})

@app.route("/api/optimization-tests/<int:test_id>/mark-applied",methods=["POST"])
def optimization_test_mark_applied(test_id):
    item=db.mark_test_applied(test_id)
    if not item:
        return jsonify({"ok":False,"error":"Test not found"}),404
    return jsonify({"ok":True,"item":item})

@app.route("/api/optimization-tests/<int:test_id>/cancel",methods=["POST"])
def optimization_test_cancel(test_id):
    item=db.cancel_test(test_id)
    if not item:
        return jsonify({"ok":False,"error":"Test not found"}),404
    return jsonify({"ok":True,"item":item})

@app.route("/api/channel-plan")
def channel_plan():
    snap=build_snapshot(api)
    if not snap:
        return jsonify({"ok":False,"error":"Unable to retrieve UniFi data"}),500
    try:
        retry_trends=db.ap_retry_trends(15)
    except Exception:
        retry_trends={}
    return jsonify({"ok":True,**build_channel_plan(snap,retry_trends)})

@app.route("/api/system")
def system_info():
    stats=db.database_stats()
    return jsonify({
        "ok":True,
        "version":VERSION,
        "controller":UNIFI_URL,
        "pollIntervalSeconds":POLL_INTERVAL,
        "retentionDays":RETENTION_DAYS,
        "monitorStarted":monitor_started,
        "lastControllerSuccess":last_controller_success,
        "lastMonitorCycle":last_monitor_cycle,
        "lastMonitorError":last_monitor_error,
        "database":stats,
        "privateRf":_private_rf_status()
    })

@app.route("/api/private-rf/discover",methods=["POST"])
def private_rf_discover():
    global private_rf_last_discovery,private_rf_last_error
    if not private_api.configured:
        return jsonify({"ok":False,"error":"Private API credentials are not configured"}),400
    result=private_api.discover_radios()
    if result.get("ok"):
        private_rf_last_discovery=datetime.now(timezone.utc).isoformat()
        private_rf_last_error=None
        db.log("PRIVATE_RF_DISCOVERY","UniFi classic API",str(len(result.get("accessPoints") or []))+" APs with radio_table","SUCCESS")
        return jsonify({**result,"status":_private_rf_status()})
    private_rf_last_error=result.get("error") or str(result)
    db.log("PRIVATE_RF_DISCOVERY","UniFi classic API",private_rf_last_error,"FAILED")
    return jsonify(result),400

@app.route("/api/private-rf/verify-write",methods=["POST"])
def private_rf_verify_write():
    global private_rf_last_error
    body=request.get_json(silent=True) or {}
    classic_id=body.get("classicId")
    if not classic_id:
        return jsonify({"ok":False,"error":"Select an AP to validate"}),400
    devices=private_api.devices()
    device=next((d for d in devices if d.get("_id")==classic_id),None)
    if not device:
        return jsonify({"ok":False,"error":"Selected classic API device was not found"}),404

    result=private_api.verify_noop_write(device)
    if result.get("ok"):
        db.set_setting("private_rf_write_verified","1")
        private_rf_last_error=None
        db.log("PRIVATE_RF_WRITE_VERIFY",device.get("name") or device.get("mac"),"Identical radio_table PUT accepted by controller","SUCCESS")
        return jsonify({"ok":True,"status":_private_rf_status()})

    db.set_setting("private_rf_write_verified","0")
    db.set_setting("auto_rf_enabled","0")
    private_rf_last_error=str(result.get("error") or result.get("data") or result)
    db.log("PRIVATE_RF_WRITE_VERIFY",device.get("name") or device.get("mac"),private_rf_last_error,"FAILED")
    return jsonify({"ok":False,"error":private_rf_last_error,"status":_private_rf_status()}),400

@app.route("/api/private-rf/auto",methods=["POST"])
def private_rf_auto_toggle():
    enabled=bool((request.get_json(silent=True) or {}).get("enabled"))
    if enabled:
        if not private_api.configured:
            return jsonify({"ok":False,"error":"Private API credentials are missing"}),400
        if db.get_setting("private_rf_write_verified","0")!="1":
            return jsonify({"ok":False,"error":"Validate the private RF write path first"}),400
    db.set_setting("auto_rf_enabled","1" if enabled else "0")
    db.log("PRIVATE_RF_AUTO","Experimental Auto RF","Enabled" if enabled else "Disabled","SUCCESS")
    return jsonify({"ok":True,"enabled":enabled,"status":_private_rf_status()})

@app.route("/health")
def health():
    return jsonify({"ok":True,"version":VERSION,"controller":UNIFI_URL,"database":db.path})

start_monitor()
start_speedtest_scheduler()
start_ai_scheduler()
