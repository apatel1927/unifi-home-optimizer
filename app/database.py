import os
import sqlite3
from datetime import datetime, timezone, timedelta

class Database:
    def __init__(self, config_dir="/config", retention_days=30):
        os.makedirs(config_dir, exist_ok=True)
        self.path = os.path.join(config_dir, "unifi_optimizer.db")
        self.retention_days = retention_days
        self.init()

    def connect(self):
        c = sqlite3.connect(self.path, timeout=30)
        c.row_factory = sqlite3.Row
        return c

    def init(self):
        c = self.connect()
        c.executescript("""
        CREATE TABLE IF NOT EXISTS settings(
            key TEXT PRIMARY KEY,
            value TEXT
        );
        CREATE TABLE IF NOT EXISTS optimization_log(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            action TEXT NOT NULL,
            target TEXT,
            detail TEXT,
            result TEXT
        );
        CREATE TABLE IF NOT EXISTS ap_history(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            device_id TEXT NOT NULL,
            device_name TEXT NOT NULL,
            client_count INTEGER NOT NULL,
            retry_24 REAL,
            retry_5 REAL,
            retry_6 REAL
        );
        CREATE TABLE IF NOT EXISTS client_state(
            client_id TEXT PRIMARY KEY,
            mac_address TEXT,
            name TEXT,
            ap_id TEXT,
            ap_name TEXT,
            first_seen TEXT NOT NULL,
            last_seen TEXT NOT NULL,
            last_change TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS roam_events(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            client_id TEXT NOT NULL,
            mac_address TEXT,
            name TEXT,
            from_ap_id TEXT,
            from_ap_name TEXT,
            to_ap_id TEXT,
            to_ap_name TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_roam_events_client_ts
            ON roam_events(client_id, ts);
        CREATE TABLE IF NOT EXISTS internet_samples(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            online INTEGER NOT NULL,
            latency_ms REAL,
            rx_bps REAL,
            tx_bps REAL,
            gateway_uptime_sec INTEGER
        );
        CREATE INDEX IF NOT EXISTS idx_internet_samples_ts
            ON internet_samples(ts);
        """)
        # Lightweight schema migrations for databases created by older releases.
        ap_cols = {row[1] for row in c.execute("PRAGMA table_info(ap_history)").fetchall()}
        if "retry_24" not in ap_cols:
            c.execute("ALTER TABLE ap_history ADD COLUMN retry_24 REAL")
        if "retry_5" not in ap_cols:
            c.execute("ALTER TABLE ap_history ADD COLUMN retry_5 REAL")
        if "retry_6" not in ap_cols:
            c.execute("ALTER TABLE ap_history ADD COLUMN retry_6 REAL")

        c.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('auto_optimize_enabled','0')")
        c.commit()
        c.close()

    def get_setting(self, key, default=None):
        c = self.connect()
        row = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        c.close()
        return row["value"] if row else default

    def set_setting(self, key, value):
        c = self.connect()
        c.execute("""
        INSERT INTO settings(key,value) VALUES(?,?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value
        """, (key, str(value)))
        c.commit()
        c.close()

    def log(self, action, target, detail, result):
        c = self.connect()
        c.execute("""
        INSERT INTO optimization_log(ts,action,target,detail,result)
        VALUES(?,?,?,?,?)
        """, (datetime.now(timezone.utc).isoformat(), action, target, detail, result))
        c.commit()
        c.close()

    def recent_logs(self, limit=100):
        c = self.connect()
        rows = c.execute("""
        SELECT ts,action,target,detail,result
        FROM optimization_log ORDER BY id DESC LIMIT ?
        """, (limit,)).fetchall()
        c.close()
        return [dict(r) for r in rows]

    def record_ap(self, device):
        stats = device.get("statistics", {})
        retries = {}
        for radio in ((stats.get("interfaces") or {}).get("radios") or []):
            retries[radio.get("frequencyGHz")] = radio.get("txRetriesPct")
        c = self.connect()
        c.execute("""
        INSERT INTO ap_history(ts,device_id,device_name,client_count,retry_24,retry_5,retry_6)
        VALUES(?,?,?,?,?,?,?)
        """, (
            datetime.now(timezone.utc).isoformat(),
            device.get("id"), device.get("name"), device.get("clientCount",0),
            retries.get(2.4), retries.get(5), retries.get(6)
        ))
        cutoff=(datetime.now(timezone.utc)-timedelta(days=self.retention_days)).isoformat()
        c.execute("DELETE FROM ap_history WHERE ts < ?", (cutoff,))
        c.commit()
        c.close()


    def record_wireless_clients(self, clients):
        now = datetime.now(timezone.utc).isoformat()
        cutoff = (datetime.now(timezone.utc)-timedelta(days=self.retention_days)).isoformat()
        c = self.connect()
        for client in clients:
            if client.get("type") != "WIRELESS":
                continue
            client_id = client.get("id")
            ap_id = client.get("uplinkDeviceId")
            if not client_id or not ap_id:
                continue
            ap_name = client.get("uplinkDeviceName") or "Unknown AP"
            name = client.get("name") or client.get("macAddress") or client_id
            mac = client.get("macAddress")
            row = c.execute("SELECT * FROM client_state WHERE client_id=?", (client_id,)).fetchone()
            if row is None:
                c.execute("""
                    INSERT INTO client_state(client_id,mac_address,name,ap_id,ap_name,first_seen,last_seen,last_change)
                    VALUES(?,?,?,?,?,?,?,?)
                """,(client_id,mac,name,ap_id,ap_name,now,now,now))
            elif row["ap_id"] != ap_id:
                c.execute("""
                    INSERT INTO roam_events(ts,client_id,mac_address,name,from_ap_id,from_ap_name,to_ap_id,to_ap_name)
                    VALUES(?,?,?,?,?,?,?,?)
                """,(now,client_id,mac,name,row["ap_id"],row["ap_name"],ap_id,ap_name))
                c.execute("""
                    UPDATE client_state SET mac_address=?,name=?,ap_id=?,ap_name=?,last_seen=?,last_change=?
                    WHERE client_id=?
                """,(mac,name,ap_id,ap_name,now,now,client_id))
            else:
                c.execute("""
                    UPDATE client_state SET mac_address=?,name=?,ap_name=?,last_seen=? WHERE client_id=?
                """,(mac,name,ap_name,now,client_id))
        c.execute("DELETE FROM roam_events WHERE ts < ?", (cutoff,))
        c.commit()
        c.close()

    def roaming_summary(self, hours=24):
        cutoff=(datetime.now(timezone.utc)-timedelta(hours=hours)).isoformat()
        c=self.connect()
        states=c.execute("SELECT * FROM client_state ORDER BY name COLLATE NOCASE").fetchall()
        out=[]
        for s in states:
            count=c.execute("SELECT COUNT(*) AS n FROM roam_events WHERE client_id=? AND ts>=?",(s["client_id"],cutoff)).fetchone()["n"]
            last=c.execute("SELECT * FROM roam_events WHERE client_id=? ORDER BY id DESC LIMIT 1",(s["client_id"],)).fetchone()
            status="STABLE"
            detail="No AP changes detected in the last 24 hours."
            if count >= 8:
                status="FREQUENT_ROAMING"
                detail=f"{count} AP changes detected in the last 24 hours."
            elif count >= 3:
                status="ACTIVE_ROAMING"
                detail=f"{count} AP changes detected in the last 24 hours."
            elif count >= 1:
                status="ROAMED"
                detail=f"{count} AP change detected in the last 24 hours."
            out.append({
                "clientId":s["client_id"],"name":s["name"],"macAddress":s["mac_address"],
                "currentApId":s["ap_id"],"currentApName":s["ap_name"],
                "firstSeen":s["first_seen"],"lastSeen":s["last_seen"],"lastChange":s["last_change"],
                "roamCount24h":count,"status":status,"detail":detail,
                "lastRoam": dict(last) if last else None
            })
        c.close()
        return out

    def recent_roams(self, limit=100):
        c=self.connect()
        rows=c.execute("SELECT * FROM roam_events ORDER BY id DESC LIMIT ?",(limit,)).fetchall()
        c.close()
        return [dict(r) for r in rows]


    def ap_retry_trends(self, minutes=15):
        cutoff=(datetime.now(timezone.utc)-timedelta(minutes=minutes)).isoformat()
        c=self.connect()
        rows=c.execute("""
            SELECT device_id, device_name,
                   COUNT(*) AS sample_count,
                   AVG(retry_24) AS retry_24,
                   AVG(retry_5) AS retry_5,
                   AVG(retry_6) AS retry_6
            FROM ap_history
            WHERE ts >= ?
            GROUP BY device_id, device_name
        """,(cutoff,)).fetchall()
        c.close()
        return {
            r["device_id"]:{
                "deviceName":r["device_name"],
                "sampleCount":r["sample_count"],
                "retry24":r["retry_24"],
                "retry5":r["retry_5"],
                "retry6":r["retry_6"],
                "windowMinutes":minutes
            } for r in rows
        }

    def record_internet_sample(self, online, latency_ms, rx_bps, tx_bps, gateway_uptime_sec):
        now=datetime.now(timezone.utc).isoformat()
        cutoff=(datetime.now(timezone.utc)-timedelta(days=self.retention_days)).isoformat()
        c=self.connect()
        c.execute("""
            INSERT INTO internet_samples(ts,online,latency_ms,rx_bps,tx_bps,gateway_uptime_sec)
            VALUES(?,?,?,?,?,?)
        """,(now,1 if online else 0,latency_ms,rx_bps,tx_bps,gateway_uptime_sec))
        c.execute("DELETE FROM internet_samples WHERE ts < ?",(cutoff,))
        c.commit()
        c.close()

    def internet_summary(self, hours=24, limit=720):
        cutoff=(datetime.now(timezone.utc)-timedelta(hours=hours)).isoformat()
        c=self.connect()
        rows=c.execute("""
            SELECT * FROM internet_samples WHERE ts >= ? ORDER BY id ASC
        """,(cutoff,)).fetchall()
        recent=c.execute("""
            SELECT * FROM internet_samples ORDER BY id DESC LIMIT ?
        """,(limit,)).fetchall()
        c.close()

        items=[dict(r) for r in rows]
        latest=items[-1] if items else None
        availability=(sum(r["online"] for r in items)/len(items)*100.0) if items else None
        online_lat=[r["latency_ms"] for r in items if r["online"] and r["latency_ms"] is not None]
        avg_latency=(sum(online_lat)/len(online_lat)) if online_lat else None
        max_latency=max(online_lat) if online_lat else None

        outage_count=0
        last_outage=None
        prev=1
        for r in items:
            if prev==1 and r["online"]==0:
                outage_count+=1
                last_outage=r["ts"]
            prev=r["online"]

        online_since=None
        for r in recent:
            if not r["online"]:
                break
            online_since=r["ts"]

        history=list(reversed([dict(r) for r in recent]))
        return {
            "latest":latest,
            "availabilityPct":availability,
            "avgLatencyMs":avg_latency,
            "maxLatencyMs":max_latency,
            "outageCount":outage_count,
            "lastOutage":last_outage,
            "onlineSince":online_since,
            "samples":history
        }
