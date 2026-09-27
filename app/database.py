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
        CREATE TABLE IF NOT EXISTS optimization_tests(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            applied_at TEXT,
            completed_at TEXT,
            ap_id TEXT NOT NULL,
            ap_name TEXT NOT NULL,
            band REAL NOT NULL,
            proposed_channel INTEGER,
            proposed_width_mhz INTEGER,
            original_channel INTEGER,
            original_width_mhz INTEGER,
            description TEXT,
            baseline_retry REAL,
            baseline_basis TEXT,
            baseline_retry_60 REAL,
            baseline_client_count REAL,
            baseline_sample_count INTEGER,
            status TEXT NOT NULL DEFAULT 'PROPOSED',
            phase TEXT NOT NULL DEFAULT 'PROPOSED',
            last_retry REAL,
            post_retry_avg REAL,
            post_client_count REAL,
            post_sample_count INTEGER,
            rollback_started_at TEXT,
            rollback_retry_avg REAL,
            rollback_client_count REAL,
            rollback_sample_count INTEGER,
            preliminary_result TEXT,
            result TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_optimization_tests_status
            ON optimization_tests(status);
        CREATE TABLE IF NOT EXISTS radio_config_state(
            ap_id TEXT NOT NULL,
            band REAL NOT NULL,
            ap_name TEXT,
            channel INTEGER,
            width_mhz INTEGER,
            first_seen TEXT NOT NULL,
            last_seen TEXT NOT NULL,
            PRIMARY KEY(ap_id,band)
        );
        CREATE TABLE IF NOT EXISTS radio_config_changes(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            ap_id TEXT NOT NULL,
            ap_name TEXT,
            band REAL NOT NULL,
            from_channel INTEGER,
            from_width_mhz INTEGER,
            to_channel INTEGER,
            to_width_mhz INTEGER
        );
        CREATE INDEX IF NOT EXISTS idx_radio_config_changes_ap_band_ts
            ON radio_config_changes(ap_id,band,ts);
        CREATE TABLE IF NOT EXISTS health_history(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            score REAL NOT NULL,
            high_count INTEGER NOT NULL,
            medium_count INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_health_history_ts
            ON health_history(ts);
        """)
        # Lightweight schema migrations for databases created by older releases.
        ap_cols = {row[1] for row in c.execute("PRAGMA table_info(ap_history)").fetchall()}
        if "retry_24" not in ap_cols:
            c.execute("ALTER TABLE ap_history ADD COLUMN retry_24 REAL")
        if "retry_5" not in ap_cols:
            c.execute("ALTER TABLE ap_history ADD COLUMN retry_5 REAL")
        if "retry_6" not in ap_cols:
            c.execute("ALTER TABLE ap_history ADD COLUMN retry_6 REAL")

        test_cols = {row[1] for row in c.execute("PRAGMA table_info(optimization_tests)").fetchall()}
        test_migrations = {
            "original_channel":"INTEGER",
            "original_width_mhz":"INTEGER",
            "baseline_retry_60":"REAL",
            "baseline_client_count":"REAL",
            "baseline_sample_count":"INTEGER",
            "phase":"TEXT NOT NULL DEFAULT 'PROPOSED'",
            "post_retry_avg":"REAL",
            "post_client_count":"REAL",
            "post_sample_count":"INTEGER",
            "rollback_started_at":"TEXT",
            "rollback_retry_avg":"REAL",
            "rollback_client_count":"REAL",
            "rollback_sample_count":"INTEGER",
            "preliminary_result":"TEXT"
        }
        for col, ddl in test_migrations.items():
            if col not in test_cols:
                c.execute(f"ALTER TABLE optimization_tests ADD COLUMN {col} {ddl}")

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


    def create_optimization_test(self, ap_id, ap_name, band, proposed_channel, proposed_width_mhz, original_channel, original_width_mhz, description, baseline_retry, baseline_basis, baseline_retry_60=None, baseline_client_count=None, baseline_sample_count=None):
        now=datetime.now(timezone.utc).isoformat()
        c=self.connect()
        cur=c.execute("""
            INSERT INTO optimization_tests(
                created_at,ap_id,ap_name,band,proposed_channel,proposed_width_mhz,
                original_channel,original_width_mhz,description,baseline_retry,baseline_basis,
                baseline_retry_60,baseline_client_count,baseline_sample_count,status,phase
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,'PROPOSED','PROPOSED')
        """,(now,ap_id,ap_name,band,proposed_channel,proposed_width_mhz,original_channel,original_width_mhz,description,baseline_retry,baseline_basis,baseline_retry_60,baseline_client_count,baseline_sample_count))
        test_id=cur.lastrowid
        c.commit()
        row=c.execute("SELECT * FROM optimization_tests WHERE id=?",(test_id,)).fetchone()
        c.close()
        return dict(row)

    def mark_test_applied(self, test_id):
        now=datetime.now(timezone.utc).isoformat()
        c=self.connect()
        c.execute("""
            UPDATE optimization_tests
            SET applied_at=?, status='MONITORING', phase='SETTLING_NEW'
            WHERE id=? AND status='PROPOSED'
        """,(now,test_id))
        c.commit()
        row=c.execute("SELECT * FROM optimization_tests WHERE id=?",(test_id,)).fetchone()
        c.close()
        return dict(row) if row else None

    def mark_test_applied_at(self, test_id, applied_at):
        c=self.connect()
        c.execute("""
            UPDATE optimization_tests
            SET applied_at=?, status='MONITORING', phase='SETTLING_NEW'
            WHERE id=? AND status='PROPOSED'
        """,(applied_at,test_id))
        c.commit()
        row=c.execute("SELECT * FROM optimization_tests WHERE id=?",(test_id,)).fetchone()
        c.close()
        return dict(row) if row else None

    def cancel_test(self, test_id):
        now=datetime.now(timezone.utc).isoformat()
        c=self.connect()
        c.execute("""
            UPDATE optimization_tests
            SET completed_at=?, status='CANCELLED', result='CANCELLED'
            WHERE id=? AND status IN ('PROPOSED','MONITORING','ROLLBACK_REQUIRED','ROLLBACK_MONITORING')
        """,(now,test_id))
        c.commit()
        row=c.execute("SELECT * FROM optimization_tests WHERE id=?",(test_id,)).fetchone()
        c.close()
        return dict(row) if row else None

    def list_optimization_tests(self, limit=100):
        c=self.connect()
        rows=c.execute("""
            SELECT * FROM optimization_tests ORDER BY id DESC LIMIT ?
        """,(limit,)).fetchall()
        c.close()
        return [dict(r) for r in rows]

    def update_optimization_test_metrics(self, test_id, last_retry, status=None, result=None, completed=False):
        now=datetime.now(timezone.utc).isoformat()
        c=self.connect()
        if completed:
            c.execute("""
                UPDATE optimization_tests
                SET last_retry=?, status=?, result=?, completed_at=?
                WHERE id=?
            """,(last_retry,status,result,now,test_id))
        else:
            c.execute("""
                UPDATE optimization_tests
                SET last_retry=?, status=COALESCE(?,status), result=COALESCE(?,result)
                WHERE id=?
            """,(last_retry,status,result,test_id))
        c.commit()
        c.close()


    def database_stats(self):
        c=self.connect()
        tables=["ap_history","client_state","roam_events","internet_samples","optimization_log","optimization_tests","health_history","radio_config_state","radio_config_changes"]
        counts={}
        for table in tables:
            try:
                counts[table]=c.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"]
            except Exception:
                counts[table]=None
        c.close()
        try:
            size=os.path.getsize(self.path)
        except Exception:
            size=None
        return {"path":self.path,"sizeBytes":size,"rowCounts":counts}


    def ap_client_baselines(self, hours=24):
        cutoff=(datetime.now(timezone.utc)-timedelta(hours=hours)).isoformat()
        c=self.connect()
        rows=c.execute("""
            SELECT device_id, device_name,
                   COUNT(*) AS sample_count,
                   AVG(client_count) AS avg_clients,
                   MIN(client_count) AS min_clients,
                   MAX(client_count) AS max_clients
            FROM ap_history
            WHERE ts >= ?
            GROUP BY device_id, device_name
        """,(cutoff,)).fetchall()
        c.close()
        return {
            r["device_id"]:{
                "deviceName":r["device_name"],
                "sampleCount":r["sample_count"],
                "avgClients":r["avg_clients"],
                "minClients":r["min_clients"],
                "maxClients":r["max_clients"],
                "windowHours":hours
            } for r in rows
        }


    def record_health_score(self, score, high_count, medium_count):
        now=datetime.now(timezone.utc).isoformat()
        cutoff=(datetime.now(timezone.utc)-timedelta(days=self.retention_days)).isoformat()
        c=self.connect()
        c.execute("""
            INSERT INTO health_history(ts,score,high_count,medium_count)
            VALUES(?,?,?,?)
        """,(now,float(score),int(high_count),int(medium_count)))
        c.execute("DELETE FROM health_history WHERE ts < ?",(cutoff,))
        c.commit()
        c.close()

    def health_history(self, hours=24, limit=720):
        cutoff=(datetime.now(timezone.utc)-timedelta(hours=hours)).isoformat()
        c=self.connect()
        rows=c.execute("""
            SELECT ts,score,high_count,medium_count
            FROM health_history
            WHERE ts >= ?
            ORDER BY id DESC
            LIMIT ?
        """,(cutoff,limit)).fetchall()
        c.close()
        return list(reversed([dict(r) for r in rows]))


    def ap_window_stats(self, device_id, band, start_iso, end_iso):
        col={2.4:"retry_24",5:"retry_5",5.0:"retry_5",6:"retry_6",6.0:"retry_6"}.get(band)
        if not col:
            return {"retryAvg":None,"clientAvg":None,"sampleCount":0}
        c=self.connect()
        row=c.execute(f"""
            SELECT COUNT({col}) AS n,
                   AVG({col}) AS retry_avg,
                   AVG(client_count) AS client_avg
            FROM ap_history
            WHERE device_id=? AND ts>=? AND ts<=?
        """,(device_id,start_iso,end_iso)).fetchone()
        c.close()
        return {
            "retryAvg":row["retry_avg"] if row else None,
            "clientAvg":row["client_avg"] if row else None,
            "sampleCount":row["n"] if row else 0
        }

    def update_test_phase(self, test_id, phase, status=None, last_retry=None, preliminary_result=None, post_stats=None):
        c=self.connect()
        post_stats=post_stats or {}
        c.execute("""
            UPDATE optimization_tests
            SET phase=?,
                status=COALESCE(?,status),
                last_retry=COALESCE(?,last_retry),
                preliminary_result=COALESCE(?,preliminary_result),
                post_retry_avg=COALESCE(?,post_retry_avg),
                post_client_count=COALESCE(?,post_client_count),
                post_sample_count=COALESCE(?,post_sample_count)
            WHERE id=?
        """,(phase,status,last_retry,preliminary_result,post_stats.get("retryAvg"),post_stats.get("clientAvg"),post_stats.get("sampleCount"),test_id))
        c.commit()
        row=c.execute("SELECT * FROM optimization_tests WHERE id=?",(test_id,)).fetchone()
        c.close()
        return dict(row) if row else None

    def start_test_rollback(self, test_id):
        now=datetime.now(timezone.utc).isoformat()
        c=self.connect()
        c.execute("""
            UPDATE optimization_tests
            SET rollback_started_at=?, phase='SETTLING_ROLLBACK', status='ROLLBACK_MONITORING'
            WHERE id=? AND status='ROLLBACK_REQUIRED'
        """,(now,test_id))
        c.commit()
        row=c.execute("SELECT * FROM optimization_tests WHERE id=?",(test_id,)).fetchone()
        c.close()
        return dict(row) if row else None

    def complete_aba_test(self, test_id, result, rollback_stats):
        now=datetime.now(timezone.utc).isoformat()
        rollback_stats=rollback_stats or {}
        c=self.connect()
        c.execute("""
            UPDATE optimization_tests
            SET completed_at=?, status=?, phase='COMPLETE', result=?,
                rollback_retry_avg=?, rollback_client_count=?, rollback_sample_count=?
            WHERE id=?
        """,(now,result,result,rollback_stats.get("retryAvg"),rollback_stats.get("clientAvg"),rollback_stats.get("sampleCount"),test_id))
        c.commit()
        row=c.execute("SELECT * FROM optimization_tests WHERE id=?",(test_id,)).fetchone()
        c.close()
        return dict(row) if row else None


    def invalidate_test(self, test_id, reason="INVALID_NO_CHANGE"):
        now=datetime.now(timezone.utc).isoformat()
        c=self.connect()
        c.execute("""
            UPDATE optimization_tests
            SET completed_at=?, status=?, phase='COMPLETE', result=?
            WHERE id=? AND status IN ('PROPOSED','MONITORING','ROLLBACK_REQUIRED','ROLLBACK_MONITORING')
        """,(now,reason,reason,test_id))
        c.commit()
        row=c.execute("SELECT * FROM optimization_tests WHERE id=?",(test_id,)).fetchone()
        c.close()
        return dict(row) if row else None

    def record_radio_configs(self, device):
        ap_id=device.get("id")
        ap_name=device.get("name") or ap_id
        if not ap_id:
            return
        now=datetime.now(timezone.utc).isoformat()
        radios=((device.get("interfaces") or {}).get("radios") or [])
        c=self.connect()
        for r in radios:
            band=r.get("frequencyGHz")
            if band not in (2.4,5,6):
                continue
            channel=r.get("channel")
            width=r.get("channelWidthMHz")
            row=c.execute(
                "SELECT * FROM radio_config_state WHERE ap_id=? AND band=?",
                (ap_id,band)
            ).fetchone()
            if row is None:
                c.execute("""
                    INSERT INTO radio_config_state(ap_id,band,ap_name,channel,width_mhz,first_seen,last_seen)
                    VALUES(?,?,?,?,?,?,?)
                """,(ap_id,band,ap_name,channel,width,now,now))
            else:
                changed=(row["channel"]!=channel or row["width_mhz"]!=width)
                if changed:
                    c.execute("""
                        INSERT INTO radio_config_changes(
                            ts,ap_id,ap_name,band,from_channel,from_width_mhz,to_channel,to_width_mhz
                        ) VALUES(?,?,?,?,?,?,?,?)
                    """,(now,ap_id,ap_name,band,row["channel"],row["width_mhz"],channel,width))
                c.execute("""
                    UPDATE radio_config_state
                    SET ap_name=?,channel=?,width_mhz=?,last_seen=?
                    WHERE ap_id=? AND band=?
                """,(ap_name,channel,width,now,ap_id,band))
        cutoff=(datetime.now(timezone.utc)-timedelta(days=self.retention_days)).isoformat()
        c.execute("DELETE FROM radio_config_changes WHERE ts < ?",(cutoff,))
        c.commit()
        c.close()

    def recent_radio_change(self, ap_id, band, hours=24):
        cutoff=(datetime.now(timezone.utc)-timedelta(hours=hours)).isoformat()
        c=self.connect()
        row=c.execute("""
            SELECT * FROM radio_config_changes
            WHERE ap_id=? AND band=? AND ts>=?
            ORDER BY id DESC LIMIT 1
        """,(ap_id,band,cutoff)).fetchone()
        c.close()
        return dict(row) if row else None
