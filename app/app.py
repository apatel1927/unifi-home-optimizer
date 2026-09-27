import os
import threading
import time
from datetime import datetime, timezone
from flask import Flask, jsonify, render_template, request

from .database import Database
from .unifi_api import UniFiAPI
from .optimizer import build_snapshot, analyze, auto_optimize, wifi_status

app = Flask(__name__, template_folder="templates", static_folder="static")

VERSION = open("/app/VERSION").read().strip() if os.path.exists("/app/VERSION") else "0.8.1"
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
    analysis = analyze(snap)
    aps = [d for d in snap["devices"] if d.get("optimizerType") == "ACCESS_POINT"]
    switches = [d for d in snap["devices"] if d.get("optimizerType") in ("SWITCH","GATEWAY")]
    wifi = []
    for w in snap["wifiBroadcasts"]:
        row=dict(w); row["optimizerStatus"]=wifi_status(w); wifi.append(row)
    return {
        "ok":True,"version":VERSION,"site":snap["site"],"devices":snap["devices"],
        "accessPoints":aps,"switches":switches,"clients":snap["clients"],
        "wifiBroadcasts":wifi,"analysis":analysis,
        "autoOptimizeEnabled":db.get_setting("auto_optimize_enabled","0")=="1",
        "lastChecked":datetime.now(timezone.utc).isoformat(),
        "pollIntervalSeconds":POLL_INTERVAL,
        "retentionDays":RETENTION_DAYS
    }

def monitor_loop():
    elapsed=0
    while True:
        try:
            data=report_data()
            if data:
                for ap in data["accessPoints"]:
                    db.record_ap(ap)
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
    data=report_data()
    if not data:
        return jsonify({"ok":False,"error":"Unable to retrieve UniFi data"}),500
    return jsonify(data)

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

@app.route("/health")
def health():
    return jsonify({"ok":True,"version":VERSION,"controller":UNIFI_URL,"database":db.path})

start_monitor()
