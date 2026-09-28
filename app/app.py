import os
import threading
import time
import requests
import speedtest
import traceback
from datetime import datetime, timezone, timedelta
from flask import Flask, jsonify, render_template, request

from .database import Database
from .unifi_api import UniFiAPI
from .private_unifi import PrivateUniFiAPI
from .optimizer import build_snapshot, analyze, auto_optimize, wifi_status, build_channel_plan, radio_conflict_key

app = Flask(__name__, template_folder="templates", static_folder="static")

VERSION = open("/app/VERSION").read().strip() if os.path.exists("/app/VERSION") else "0.15.0"
UNIFI_URL = os.getenv("UNIFI_URL", "https://192.168.1.1")
API_KEY = os.getenv("UNIFI_API_KEY", "")
POLL_INTERVAL = max(int(os.getenv("POLL_INTERVAL_SECONDS", "60")), 30)
RETENTION_DAYS = int(os.getenv("RETENTION_DAYS", "30"))
UNIFI_PRIVATE_USERNAME = os.getenv("UNIFI_PRIVATE_USERNAME", "")
UNIFI_PRIVATE_PASSWORD = os.getenv("UNIFI_PRIVATE_PASSWORD", "")
UNIFI_SITE_NAME = os.getenv("UNIFI_SITE_NAME", "default")

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

def _norm_mac(value):
    return str(value or "").lower().replace("-",":").strip()

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

def _traffic_rows_from_report(data):
    enriched={_norm_mac(x.get("macAddress")):x for x in (data.get("clients") or []) if x.get("macAddress")}
    rows=[]
    for raw in _classic_clients_cached():
        mac=_norm_mac(raw.get("mac"))
        if not mac:
            continue
        client=enriched.get(mac) or {}
        rows.append({
            "mac":mac,
            "name":client.get("name") or raw.get("name") or raw.get("hostname") or mac,
            "ip":client.get("ipAddress") or raw.get("ip"),
            "vlanId":client.get("vlanId") if client.get("vlanId") is not None else raw.get("vlan"),
            "networkName":client.get("networkName") or raw.get("network") or raw.get("network_name") or "Unknown",
            "uplinkName":client.get("uplinkDeviceName") or "Unknown",
            "rxBytes":_int_counter(raw.get("rx_bytes")),
            "txBytes":_int_counter(raw.get("tx_bytes")),
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

def _rf_test_active():
    try:
        active={"PROPOSED","MONITORING","ROLLBACK_REQUIRED","ROLLBACK_MONITORING"}
        return any(t.get("status") in active for t in db.list_optimization_tests(100))
    except Exception:
        return False

def _speedtest_state():
    summary=db.speedtest_summary(30)
    interval=max(1,min(24,int(float(db.get_setting("speedtest_interval_hours","6") or 6))))
    enabled=db.get_setting("speedtest_enabled","1")=="1"
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
        tester=speedtest.Speedtest(timeout=20,secure=True)
        server=tester.get_best_server() or {}
        tester.download()
        tester.upload(pre_allocate=False)
        results=tester.results.dict()
        duration=time.perf_counter()-started
        download=float(results.get("download") or 0)/1_000_000.0
        upload=float(results.get("upload") or 0)/1_000_000.0
        ping=float(results.get("ping")) if results.get("ping") is not None else None
        srv=results.get("server") or server or {}
        client=results.get("client") or {}
        db.record_speedtest(
            True,
            download_mbps=download,
            upload_mbps=upload,
            ping_ms=ping,
            server_name=srv.get("name"),
            server_sponsor=srv.get("sponsor"),
            server_id=srv.get("id"),
            server_distance_km=srv.get("d"),
            client_ip=client.get("ip"),
            duration_sec=duration,
        )
        db.log(
            "SPEEDTEST",
            source,
            f"{download:.1f} Mbps down / {upload:.1f} Mbps up / {ping:.1f} ms ping" if ping is not None
            else f"{download:.1f} Mbps down / {upload:.1f} Mbps up",
            "SUCCESS"
        )
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
    global last_monitor_cycle,last_monitor_error,traffic_last_sample_monotonic
    elapsed=0
    while True:
        try:
            data=report_data()
            if data:
                for ap in data["accessPoints"]:
                    db.record_ap(ap)
                    db.record_radio_configs(ap)
                db.record_wireless_clients(data["clients"])
                if (time.monotonic()-traffic_last_sample_monotonic) >= traffic_sample_interval_seconds:
                    _sample_traffic(data)
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
    return jsonify({"ok":True,**_speedtest_state()})

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
            data=report_data()
            if data:
                live_rows=_traffic_rows_from_report(data)
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
