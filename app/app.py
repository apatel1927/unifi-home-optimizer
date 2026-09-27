import os
import threading
import time
import requests
import traceback
from datetime import datetime, timezone
from flask import Flask, jsonify, render_template, request

from .database import Database
from .unifi_api import UniFiAPI
from .optimizer import build_snapshot, analyze, auto_optimize, wifi_status, build_channel_plan

app = Flask(__name__, template_folder="templates", static_folder="static")

VERSION = open("/app/VERSION").read().strip() if os.path.exists("/app/VERSION") else "0.9.4"
UNIFI_URL = os.getenv("UNIFI_URL", "https://192.168.1.1")
API_KEY = os.getenv("UNIFI_API_KEY", "")
POLL_INTERVAL = max(int(os.getenv("POLL_INTERVAL_SECONDS", "60")), 30)
RETENTION_DAYS = int(os.getenv("RETENTION_DAYS", "30"))

api = UniFiAPI(UNIFI_URL, API_KEY)
db = Database("/config", RETENTION_DAYS)
monitor_started = False
monitor_lock = threading.Lock()

def report_data():
    snap = build_snapshot(api)
    if not snap:
        return None
    try:
        retry_trends = db.ap_retry_trends(15)
    except Exception as e:
        print("Retry trend error:", e, flush=True)
        retry_trends = {}
    analysis = analyze(snap, retry_trends)
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
        "channelPlan":channel_plan,
        "gateway":gateway,
        "internet":internet_data,
        "optimizationTests":evaluate_optimization_tests()
    }

def _trend_retry_for_band(trends, ap_id, band):
    t=(trends or {}).get(ap_id) or {}
    key={2.4:"retry24",5.0:"retry5",5:"retry5",6.0:"retry6",6:"retry6"}.get(band)
    if not key:
        return None
    value=t.get(key)
    return float(value) if value is not None else None

def evaluate_optimization_tests():
    try:
        tests=db.list_optimization_tests(100)
        trends=db.ap_retry_trends(15)
    except Exception as e:
        print("Optimization test evaluation error:",e,flush=True)
        return []
    now=datetime.now(timezone.utc)
    for t in tests:
        if t.get("status")!="MONITORING" or not t.get("applied_at"):
            continue
        current=_trend_retry_for_band(trends,t.get("ap_id"),t.get("band"))
        if current is None:
            continue
        applied=datetime.fromisoformat(t["applied_at"])
        if applied.tzinfo is None:
            applied=applied.replace(tzinfo=timezone.utc)
        minutes=(now-applied).total_seconds()/60.0
        baseline=t.get("baseline_retry")
        if baseline is None:
            db.update_optimization_test_metrics(t["id"],current)
            continue
        delta=current-float(baseline)
        if minutes < 60:
            db.update_optimization_test_metrics(t["id"],current,status="MONITORING")
        else:
            if delta <= -2.0 or current <= float(baseline)*0.80:
                result="IMPROVED"
            elif delta >= 2.0 or current >= float(baseline)*1.20:
                result="WORSE"
            else:
                result="NO_CHANGE"
            db.update_optimization_test_metrics(t["id"],current,status=result,result=result,completed=True)
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
    elapsed=0
    while True:
        try:
            data=report_data()
            if data:
                for ap in data["accessPoints"]:
                    db.record_ap(ap)
                db.record_wireless_clients(data["clients"])
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
            elapsed += POLL_INTERVAL
            if elapsed >= 900:
                elapsed=0
                if db.get_setting("auto_optimize_enabled","0")=="1":
                    auto_optimize(api,db)
        except Exception as e:
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
        trends=db.ap_retry_trends(15)
        baseline=_trend_retry_for_band(trends,body.get("apId"),body.get("band"))
        item=db.create_optimization_test(
            body.get("apId"),body.get("apName"),float(body.get("band")),
            body.get("proposedChannel"),body.get("proposedWidthMHz"),
            body.get("description") or "",
            baseline,
            "15-min average" if baseline is not None else "unavailable"
        )
        return jsonify({"ok":True,"item":item})
    return jsonify({"ok":True,"items":evaluate_optimization_tests()})

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

@app.route("/health")
def health():
    return jsonify({"ok":True,"version":VERSION,"controller":UNIFI_URL,"database":db.path})

start_monitor()
