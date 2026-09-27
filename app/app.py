import os
import threading
import time
import requests
import traceback
from datetime import datetime, timezone, timedelta
from flask import Flask, jsonify, render_template, request

from .database import Database
from .unifi_api import UniFiAPI
from .optimizer import build_snapshot, analyze, auto_optimize, wifi_status, build_channel_plan

app = Flask(__name__, template_folder="templates", static_folder="static")

VERSION = open("/app/VERSION").read().strip() if os.path.exists("/app/VERSION") else "0.11.1"
UNIFI_URL = os.getenv("UNIFI_URL", "https://192.168.1.1")
API_KEY = os.getenv("UNIFI_API_KEY", "")
POLL_INTERVAL = max(int(os.getenv("POLL_INTERVAL_SECONDS", "60")), 30)
RETENTION_DAYS = int(os.getenv("RETENTION_DAYS", "30"))

api = UniFiAPI(UNIFI_URL, API_KEY)
db = Database("/config", RETENTION_DAYS)
monitor_started = False
monitor_lock = threading.Lock()
last_controller_success = None
last_monitor_cycle = None
last_monitor_error = None

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
        "accessPoints":aps,"switches":switches,"clients":snap["clients"],
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

def _preliminary_result(baseline, post):
    if baseline is None or post is None:
        return "INCONCLUSIVE"
    delta=float(post)-float(baseline)
    if delta <= -2.0 or float(post) <= float(baseline)*0.80:
        return "IMPROVED"
    if delta >= 2.0 or float(post) >= float(baseline)*1.20:
        return "WORSE"
    return "NO_CHANGE"

def _aba_final_result(t, rollback_stats):
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
    delta=float(post)-reference
    if delta <= -2.0 or float(post) <= reference*0.80:
        return "IMPROVED_CONFIRMED"
    if delta >= 2.0 or float(post) >= reference*1.20:
        return "WORSE_CONFIRMED"
    return "NO_MEANINGFUL_CHANGE"

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
            result=_aba_final_result(t,rollback_stats)
            completed=db.complete_aba_test(t["id"],result,rollback_stats)
            db.log(
                "RF_TEST_ABA_RESULT",
                t.get("ap_name"),
                str(t.get("band"))+" GHz A/B/A verification complete",
                result
            )
            t=completed or t

    try:
        return db.list_optimization_tests(100)
    except Exception:
        return []

def probe_internet():
    started=time.perf_counter()
    try:
        r=requests.get("https://connectivitycheck.gstatic.com/generate_204",timeout=5)
        latency_ms=(time.perf_counter()-started)*1000.0
        return 200 <= r.status_code < 400, latency_ms
    except Exception:
        return False, None

def monitor_loop():
    global last_monitor_cycle,last_monitor_error
    elapsed=0
    while True:
        try:
            data=report_data()
            if data:
                for ap in data["accessPoints"]:
                    db.record_ap(ap)
                    db.record_radio_configs(ap)
                db.record_wireless_clients(data["clients"])
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
        "privateRf":{
            "status":"NOT_CONFIGURED",
            "mode":"READ_ONLY_DISCOVERY_FIRST",
            "detail":"Private UniFi radio control is intentionally disabled until local-controller authentication and exact U7 radio payloads are verified."
        }
    })

@app.route("/health")
def health():
    return jsonify({"ok":True,"version":VERSION,"controller":UNIFI_URL,"database":db.path})

start_monitor()
