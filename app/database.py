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
            auto_apply_attempted_at TEXT,
            auto_rollback_attempted_at TEXT,
            final_apply_attempted_at TEXT,
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
        CREATE TABLE IF NOT EXISTS traffic_client_samples(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            mac TEXT NOT NULL,
            name TEXT,
            ip TEXT,
            vlan_id TEXT,
            network_name TEXT,
            uplink_name TEXT,
            rx_bytes INTEGER,
            tx_bytes INTEGER,
            rx_delta_bytes INTEGER NOT NULL DEFAULT 0,
            tx_delta_bytes INTEGER NOT NULL DEFAULT 0,
            rx_rate_bps REAL,
            tx_rate_bps REAL
        );
        CREATE INDEX IF NOT EXISTS idx_traffic_client_samples_ts
            ON traffic_client_samples(ts);
        CREATE INDEX IF NOT EXISTS idx_traffic_client_samples_mac_ts
            ON traffic_client_samples(mac,ts);
        CREATE TABLE IF NOT EXISTS traffic_dpi_samples(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            category_id INTEGER,
            app_id INTEGER,
            category_name TEXT,
            app_name TEXT,
            rx_bytes INTEGER,
            tx_bytes INTEGER,
            rx_delta_bytes INTEGER NOT NULL DEFAULT 0,
            tx_delta_bytes INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_traffic_dpi_samples_ts
            ON traffic_dpi_samples(ts);
        CREATE INDEX IF NOT EXISTS idx_traffic_dpi_samples_key_ts
            ON traffic_dpi_samples(category_id,app_id,ts);
        CREATE TABLE IF NOT EXISTS wan_ping_samples(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            target_key TEXT NOT NULL,
            target_name TEXT NOT NULL,
            target_host TEXT NOT NULL,
            target_type TEXT NOT NULL,
            sent INTEGER NOT NULL,
            received INTEGER NOT NULL,
            packet_loss_pct REAL NOT NULL,
            min_ms REAL,
            avg_ms REAL,
            max_ms REAL,
            jitter_ms REAL,
            error TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_wan_ping_samples_ts
            ON wan_ping_samples(ts);
        CREATE INDEX IF NOT EXISTS idx_wan_ping_target_ts
            ON wan_ping_samples(target_key,ts);

        CREATE TABLE IF NOT EXISTS wan_dns_samples(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            resolver_key TEXT NOT NULL,
            resolver_name TEXT NOT NULL,
            resolver_host TEXT,
            query_name TEXT NOT NULL,
            success INTEGER NOT NULL,
            latency_ms REAL,
            answers INTEGER,
            error TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_wan_dns_samples_ts
            ON wan_dns_samples(ts);
        CREATE INDEX IF NOT EXISTS idx_wan_dns_resolver_ts
            ON wan_dns_samples(resolver_key,ts);
        CREATE TABLE IF NOT EXISTS speedtest_results(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            success INTEGER NOT NULL,
            download_mbps REAL,
            upload_mbps REAL,
            ping_ms REAL,
            server_name TEXT,
            server_sponsor TEXT,
            server_id TEXT,
            server_distance_km REAL,
            server_location TEXT,
            server_country TEXT,
            server_host TEXT,
            jitter_ms REAL,
            packet_loss_pct REAL,
            client_ip TEXT,
            duration_sec REAL,
            error TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_speedtest_results_ts
            ON speedtest_results(ts);
        CREATE TABLE IF NOT EXISTS wired_port_state(
            device_id TEXT NOT NULL,
            device_name TEXT,
            port_idx INTEGER NOT NULL,
            state TEXT,
            speed_mbps REAL,
            endpoint_key TEXT,
            endpoint_name TEXT,
            poe_state TEXT,
            rx_errors INTEGER,
            tx_errors INTEGER,
            rx_drops INTEGER,
            tx_drops INTEGER,
            error_delta INTEGER NOT NULL DEFAULT 0,
            drop_delta INTEGER NOT NULL DEFAULT 0,
            counter_sample_at TEXT,
            first_seen TEXT NOT NULL,
            last_seen TEXT NOT NULL,
            last_change TEXT NOT NULL,
            PRIMARY KEY(device_id,port_idx)
        );
        CREATE TABLE IF NOT EXISTS wired_port_events(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            device_id TEXT NOT NULL,
            device_name TEXT,
            port_idx INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            from_value TEXT,
            to_value TEXT,
            endpoint_name TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_wired_port_events_ts
            ON wired_port_events(ts);
        CREATE INDEX IF NOT EXISTS idx_wired_port_events_device_port_ts
            ON wired_port_events(device_id,port_idx,ts);
        CREATE TABLE IF NOT EXISTS ai_reports(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            trigger TEXT NOT NULL,
            model TEXT,
            status TEXT NOT NULL,
            summary TEXT,
            error TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_ai_reports_ts
            ON ai_reports(ts);
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
            "preliminary_result":"TEXT",
            "auto_apply_attempted_at":"TEXT",
            "auto_rollback_attempted_at":"TEXT",
            "final_apply_attempted_at":"TEXT"
        }
        for col, ddl in test_migrations.items():
            if col not in test_cols:
                c.execute(f"ALTER TABLE optimization_tests ADD COLUMN {col} {ddl}")

        wired_cols = {row[1] for row in c.execute("PRAGMA table_info(wired_port_state)").fetchall()}
        wired_migrations = {
            "rx_errors":"INTEGER",
            "tx_errors":"INTEGER",
            "rx_drops":"INTEGER",
            "tx_drops":"INTEGER",
            "error_delta":"INTEGER NOT NULL DEFAULT 0",
            "drop_delta":"INTEGER NOT NULL DEFAULT 0",
            "counter_sample_at":"TEXT"
        }
        for col, ddl in wired_migrations.items():
            if col not in wired_cols:
                c.execute(f"ALTER TABLE wired_port_state ADD COLUMN {col} {ddl}")

        speed_cols = {row[1] for row in c.execute("PRAGMA table_info(speedtest_results)").fetchall()}
        speed_migrations = {
            "server_location":"TEXT",
            "server_country":"TEXT",
            "server_host":"TEXT",
            "jitter_ms":"REAL",
            "packet_loss_pct":"REAL"
        }
        for col, ddl in speed_migrations.items():
            if col not in speed_cols:
                c.execute(f"ALTER TABLE speedtest_results ADD COLUMN {col} {ddl}")

        c.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('auto_optimize_enabled','0')")
        c.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('auto_rf_enabled','0')")
        c.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('private_rf_write_verified','0')")
        c.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('speedtest_enabled','1')")
        c.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('speedtest_interval_hours','6')")
        c.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('speedtest_preferred_server_id','')")
        c.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('ai_auto_enabled','0')")
        c.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('ai_interval_hours','6')")
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

    def get_optimization_test(self, test_id):
        c=self.connect()
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


    @staticmethod
    def _counter_delta_safe(current, previous):
        try:
            if current is None or previous is None:
                return 0
            current=int(current); previous=int(previous)
            return current-previous if current >= previous else 0
        except Exception:
            return 0

    def record_wired_ports(self, ports):
        if not ports:
            return
        now=datetime.now(timezone.utc).isoformat()
        cutoff=(datetime.now(timezone.utc)-timedelta(days=self.retention_days)).isoformat()
        c=self.connect()
        for p in ports:
            device_id=str(p.get("deviceId") or "")
            port_idx=p.get("portIdx")
            if not device_id or port_idx is None:
                continue
            try:
                port_idx=int(port_idx)
            except Exception:
                continue
            state=str(p.get("state") or "UNKNOWN")
            speed=p.get("speedMbps")
            endpoint_key=str(p.get("endpointKey") or "")
            endpoint_name=p.get("endpointName")
            poe_state=str(p.get("poeState") or "")
            rx_errors=p.get("rxErrors")
            tx_errors=p.get("txErrors")
            rx_drops=p.get("rxDrops")
            tx_drops=p.get("txDrops")
            prev=c.execute("""
                SELECT * FROM wired_port_state
                WHERE device_id=? AND port_idx=?
            """,(device_id,port_idx)).fetchone()

            if prev is None:
                c.execute("""
                    INSERT INTO wired_port_state(
                        device_id,device_name,port_idx,state,speed_mbps,
                        endpoint_key,endpoint_name,poe_state,
                        rx_errors,tx_errors,rx_drops,tx_drops,error_delta,drop_delta,counter_sample_at,
                        first_seen,last_seen,last_change
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,(
                    device_id,p.get("deviceName"),port_idx,state,speed,
                    endpoint_key,endpoint_name,poe_state,
                    rx_errors,tx_errors,rx_drops,tx_drops,0,0,now,
                    now,now,now
                ))
                continue

            changes=[]
            if str(prev["state"] or "")!=state:
                changes.append(("STATE",prev["state"],state))
            prev_speed=prev["speed_mbps"]
            if (prev_speed is None) != (speed is None) or (
                prev_speed is not None and speed is not None and float(prev_speed)!=float(speed)
            ):
                changes.append(("SPEED",prev_speed,speed))
            if str(prev["endpoint_key"] or "")!=endpoint_key:
                changes.append(("ENDPOINT",prev["endpoint_name"],endpoint_name))

            last_change=prev["last_change"]
            if changes:
                last_change=now
                for event_type,from_value,to_value in changes:
                    c.execute("""
                        INSERT INTO wired_port_events(
                            ts,device_id,device_name,port_idx,event_type,
                            from_value,to_value,endpoint_name
                        ) VALUES(?,?,?,?,?,?,?,?)
                    """,(
                        now,device_id,p.get("deviceName"),port_idx,event_type,
                        None if from_value is None else str(from_value),
                        None if to_value is None else str(to_value),
                        endpoint_name
                    ))

            error_delta=(
                self._counter_delta_safe(rx_errors,prev["rx_errors"]) +
                self._counter_delta_safe(tx_errors,prev["tx_errors"])
            )
            drop_delta=(
                self._counter_delta_safe(rx_drops,prev["rx_drops"]) +
                self._counter_delta_safe(tx_drops,prev["tx_drops"])
            )

            c.execute("""
                UPDATE wired_port_state
                SET device_name=?,state=?,speed_mbps=?,endpoint_key=?,endpoint_name=?,
                    poe_state=?,rx_errors=?,tx_errors=?,rx_drops=?,tx_drops=?,
                    error_delta=?,drop_delta=?,counter_sample_at=?,
                    last_seen=?,last_change=?
                WHERE device_id=? AND port_idx=?
            """,(
                p.get("deviceName"),state,speed,endpoint_key,endpoint_name,
                poe_state,rx_errors,tx_errors,rx_drops,tx_drops,
                error_delta,drop_delta,now,
                now,last_change,device_id,port_idx
            ))

        c.execute("DELETE FROM wired_port_events WHERE ts < ?",(cutoff,))
        c.commit()
        c.close()

    def wired_port_counter_summary(self):
        c=self.connect()
        rows=c.execute("""
            SELECT device_id,port_idx,error_delta,drop_delta,counter_sample_at
            FROM wired_port_state
        """).fetchall()
        c.close()
        return {
            f"{r['device_id']}:{r['port_idx']}":{
                "errorDelta":r["error_delta"] or 0,
                "dropDelta":r["drop_delta"] or 0,
                "sampleAt":r["counter_sample_at"],
            } for r in rows
        }

    def wired_port_event_summary(self, hours=24):
        cutoff=(datetime.now(timezone.utc)-timedelta(hours=hours)).isoformat()
        c=self.connect()
        rows=c.execute("""
            SELECT device_id,device_name,port_idx,
                   SUM(CASE WHEN event_type='STATE' THEN 1 ELSE 0 END) AS state_changes,
                   SUM(CASE WHEN event_type='SPEED' THEN 1 ELSE 0 END) AS speed_changes,
                   SUM(CASE WHEN event_type='ENDPOINT' THEN 1 ELSE 0 END) AS endpoint_changes,
                   MAX(ts) AS last_event
            FROM wired_port_events
            WHERE ts>=?
            GROUP BY device_id,device_name,port_idx
        """,(cutoff,)).fetchall()
        c.close()
        return {
            f"{r['device_id']}:{r['port_idx']}":{
                "stateChanges":r["state_changes"] or 0,
                "speedChanges":r["speed_changes"] or 0,
                "endpointChanges":r["endpoint_changes"] or 0,
                "lastEvent":r["last_event"],
            } for r in rows
        }

    def wired_recent_events(self, hours=24, limit=200):
        cutoff=(datetime.now(timezone.utc)-timedelta(hours=hours)).isoformat()
        c=self.connect()
        rows=c.execute("""
            SELECT * FROM wired_port_events
            WHERE ts>=?
            ORDER BY id DESC
            LIMIT ?
        """,(cutoff,limit)).fetchall()
        c.close()
        return [dict(r) for r in rows]

    def record_ai_report(self, trigger, model, status, summary=None, error=None):
        now=datetime.now(timezone.utc).isoformat()
        cutoff=(datetime.now(timezone.utc)-timedelta(days=self.retention_days)).isoformat()
        c=self.connect()
        c.execute("""
            INSERT INTO ai_reports(ts,trigger,model,status,summary,error)
            VALUES(?,?,?,?,?,?)
        """,(now,trigger,model,status,summary,error))
        c.execute("DELETE FROM ai_reports WHERE ts < ?",(cutoff,))
        c.commit()
        row=c.execute("SELECT * FROM ai_reports ORDER BY id DESC LIMIT 1").fetchone()
        c.close()
        return dict(row) if row else None

    def ai_report_history(self, limit=20):
        c=self.connect()
        rows=c.execute("""
            SELECT * FROM ai_reports ORDER BY id DESC LIMIT ?
        """,(limit,)).fetchall()
        c.close()
        return [dict(r) for r in rows]

    def database_stats(self):
        c=self.connect()
        tables=["ap_history","client_state","roam_events","internet_samples","optimization_log","optimization_tests","health_history","radio_config_state","radio_config_changes","speedtest_results","traffic_client_samples","traffic_dpi_samples","wan_ping_samples","wan_dns_samples","wired_port_state","wired_port_events","ai_reports"]
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


    def mark_rf_attempt(self, test_id, field):
        allowed={"auto_apply_attempted_at","auto_rollback_attempted_at","final_apply_attempted_at"}
        if field not in allowed:
            raise ValueError("Invalid RF attempt field")
        now=datetime.now(timezone.utc).isoformat()
        c=self.connect()
        c.execute(f"UPDATE optimization_tests SET {field}=? WHERE id=?",(now,test_id))
        c.commit()
        row=c.execute("SELECT * FROM optimization_tests WHERE id=?",(test_id,)).fetchone()
        c.close()
        return dict(row) if row else None

    def clear_rf_attempt(self, test_id, field):
        allowed={"auto_apply_attempted_at","auto_rollback_attempted_at","final_apply_attempted_at"}
        if field not in allowed:
            raise ValueError("Invalid RF attempt field")
        c=self.connect()
        c.execute(f"UPDATE optimization_tests SET {field}=NULL WHERE id=?",(test_id,))
        c.commit()
        c.close()


    def record_speedtest(self, success, download_mbps=None, upload_mbps=None, ping_ms=None,
                         server_name=None, server_sponsor=None, server_id=None,
                         server_distance_km=None, server_location=None, server_country=None,
                         server_host=None, jitter_ms=None, packet_loss_pct=None,
                         client_ip=None, duration_sec=None, error=None):
        now=datetime.now(timezone.utc).isoformat()
        cutoff=(datetime.now(timezone.utc)-timedelta(days=self.retention_days)).isoformat()
        c=self.connect()
        c.execute("""
            INSERT INTO speedtest_results(
                ts,success,download_mbps,upload_mbps,ping_ms,
                server_name,server_sponsor,server_id,server_distance_km,
                server_location,server_country,server_host,jitter_ms,packet_loss_pct,
                client_ip,duration_sec,error
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,(
            now,1 if success else 0,download_mbps,upload_mbps,ping_ms,
            server_name,server_sponsor,str(server_id) if server_id is not None else None,
            server_distance_km,server_location,server_country,server_host,jitter_ms,packet_loss_pct,
            client_ip,duration_sec,error
        ))
        c.execute("DELETE FROM speedtest_results WHERE ts < ?",(cutoff,))
        c.commit()
        c.close()

    def speedtest_history(self, days=30, limit=500):
        cutoff=(datetime.now(timezone.utc)-timedelta(days=days)).isoformat()
        c=self.connect()
        rows=c.execute("""
            SELECT * FROM speedtest_results
            WHERE ts >= ?
            ORDER BY id DESC
            LIMIT ?
        """,(cutoff,limit)).fetchall()
        c.close()
        return list(reversed([dict(r) for r in rows]))

    def speedtest_summary(self, days=30):
        cutoff=(datetime.now(timezone.utc)-timedelta(days=days)).isoformat()
        c=self.connect()
        latest=c.execute("""
            SELECT * FROM speedtest_results
            ORDER BY id DESC LIMIT 1
        """).fetchone()
        latest_success=c.execute("""
            SELECT * FROM speedtest_results
            WHERE success=1
            ORDER BY id DESC LIMIT 1
        """).fetchone()
        stats=c.execute("""
            SELECT
                COUNT(*) AS total_runs,
                SUM(CASE WHEN success=1 THEN 1 ELSE 0 END) AS successful_runs,
                AVG(CASE WHEN success=1 THEN download_mbps END) AS avg_download,
                AVG(CASE WHEN success=1 THEN upload_mbps END) AS avg_upload,
                AVG(CASE WHEN success=1 THEN ping_ms END) AS avg_ping,
                MIN(CASE WHEN success=1 THEN download_mbps END) AS min_download,
                MAX(CASE WHEN success=1 THEN download_mbps END) AS max_download,
                MIN(CASE WHEN success=1 THEN upload_mbps END) AS min_upload,
                MAX(CASE WHEN success=1 THEN upload_mbps END) AS max_upload,
                MIN(CASE WHEN success=1 THEN ping_ms END) AS min_ping,
                MAX(CASE WHEN success=1 THEN ping_ms END) AS max_ping
            FROM speedtest_results
            WHERE ts >= ?
        """,(cutoff,)).fetchone()
        c.close()
        return {
            "latest":dict(latest) if latest else None,
            "latestSuccess":dict(latest_success) if latest_success else None,
            "stats":dict(stats) if stats else {}
        }


    @staticmethod
    def _counter_delta(current, previous):
        try:
            if current is None or previous is None:
                return 0
            current=int(current)
            previous=int(previous)
            return current-previous if current >= previous else 0
        except Exception:
            return 0

    def record_traffic_clients(self, clients):
        if not clients:
            return
        now=datetime.now(timezone.utc).isoformat()
        cutoff=(datetime.now(timezone.utc)-timedelta(days=self.retention_days)).isoformat()
        c=self.connect()
        for item in clients:
            mac=(item.get("mac") or "").lower()
            if not mac:
                continue
            prev=c.execute("""
                SELECT rx_bytes,tx_bytes
                FROM traffic_client_samples
                WHERE mac=?
                ORDER BY id DESC LIMIT 1
            """,(mac,)).fetchone()
            rx=item.get("rxBytes")
            tx=item.get("txBytes")
            rx_delta=self._counter_delta(rx,prev["rx_bytes"] if prev else None)
            tx_delta=self._counter_delta(tx,prev["tx_bytes"] if prev else None)
            c.execute("""
                INSERT INTO traffic_client_samples(
                    ts,mac,name,ip,vlan_id,network_name,uplink_name,
                    rx_bytes,tx_bytes,rx_delta_bytes,tx_delta_bytes,
                    rx_rate_bps,tx_rate_bps
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,(
                now,mac,item.get("name"),item.get("ip"),
                str(item.get("vlanId")) if item.get("vlanId") is not None else None,
                item.get("networkName"),item.get("uplinkName"),
                rx,tx,rx_delta,tx_delta,
                item.get("rxRateBps"),item.get("txRateBps")
            ))
        c.execute("DELETE FROM traffic_client_samples WHERE ts < ?",(cutoff,))
        c.commit()
        c.close()

    def record_traffic_dpi(self, rows):
        if not rows:
            return
        now=datetime.now(timezone.utc).isoformat()
        cutoff=(datetime.now(timezone.utc)-timedelta(days=self.retention_days)).isoformat()
        c=self.connect()
        for item in rows:
            cat=item.get("categoryId")
            app=item.get("appId")
            prev=c.execute("""
                SELECT rx_bytes,tx_bytes
                FROM traffic_dpi_samples
                WHERE category_id IS ? AND app_id IS ?
                ORDER BY id DESC LIMIT 1
            """,(cat,app)).fetchone()
            rx=item.get("rxBytes")
            tx=item.get("txBytes")
            rx_delta=self._counter_delta(rx,prev["rx_bytes"] if prev else None)
            tx_delta=self._counter_delta(tx,prev["tx_bytes"] if prev else None)
            c.execute("""
                INSERT INTO traffic_dpi_samples(
                    ts,category_id,app_id,category_name,app_name,
                    rx_bytes,tx_bytes,rx_delta_bytes,tx_delta_bytes
                ) VALUES(?,?,?,?,?,?,?,?,?)
            """,(
                now,cat,app,item.get("categoryName"),item.get("appName"),
                rx,tx,rx_delta,tx_delta
            ))
        c.execute("DELETE FROM traffic_dpi_samples WHERE ts < ?",(cutoff,))
        c.commit()
        c.close()

    def traffic_summary(self, hours=24):
        cutoff=(datetime.now(timezone.utc)-timedelta(hours=hours)).isoformat()
        c=self.connect()

        totals=c.execute("""
            SELECT
                COALESCE(SUM(rx_delta_bytes),0) AS rx_bytes,
                COALESCE(SUM(tx_delta_bytes),0) AS tx_bytes,
                COUNT(DISTINCT mac) AS client_count
            FROM traffic_client_samples
            WHERE ts>=?
        """,(cutoff,)).fetchone()

        top_clients=c.execute("""
            SELECT
                mac,
                MAX(name) AS name,
                MAX(ip) AS ip,
                MAX(vlan_id) AS vlan_id,
                MAX(network_name) AS network_name,
                MAX(uplink_name) AS uplink_name,
                SUM(rx_delta_bytes) AS rx_bytes,
                SUM(tx_delta_bytes) AS tx_bytes,
                SUM(rx_delta_bytes+tx_delta_bytes) AS total_bytes
            FROM traffic_client_samples
            WHERE ts>=?
            GROUP BY mac
            ORDER BY total_bytes DESC
            LIMIT 100
        """,(cutoff,)).fetchall()

        top_vlans=c.execute("""
            SELECT
                COALESCE(vlan_id,'Unknown') AS vlan_id,
                COALESCE(MAX(network_name),'Unknown') AS network_name,
                SUM(rx_delta_bytes) AS rx_bytes,
                SUM(tx_delta_bytes) AS tx_bytes,
                SUM(rx_delta_bytes+tx_delta_bytes) AS total_bytes,
                COUNT(DISTINCT mac) AS client_count
            FROM traffic_client_samples
            WHERE ts>=?
            GROUP BY COALESCE(vlan_id,'Unknown')
            ORDER BY total_bytes DESC
        """,(cutoff,)).fetchall()

        top_networks=c.execute("""
            SELECT
                COALESCE(network_name,'Unknown') AS network_name,
                SUM(rx_delta_bytes) AS rx_bytes,
                SUM(tx_delta_bytes) AS tx_bytes,
                SUM(rx_delta_bytes+tx_delta_bytes) AS total_bytes,
                COUNT(DISTINCT mac) AS client_count
            FROM traffic_client_samples
            WHERE ts>=?
            GROUP BY COALESCE(network_name,'Unknown')
            ORDER BY total_bytes DESC
        """,(cutoff,)).fetchall()

        top_uplinks=c.execute("""
            SELECT
                COALESCE(uplink_name,'Unknown') AS uplink_name,
                SUM(rx_delta_bytes) AS rx_bytes,
                SUM(tx_delta_bytes) AS tx_bytes,
                SUM(rx_delta_bytes+tx_delta_bytes) AS total_bytes,
                COUNT(DISTINCT mac) AS client_count
            FROM traffic_client_samples
            WHERE ts>=?
            GROUP BY COALESCE(uplink_name,'Unknown')
            ORDER BY total_bytes DESC
        """,(cutoff,)).fetchall()

        bucket_expr="substr(ts,1,13)"
        series=c.execute(f"""
            SELECT
                {bucket_expr} AS bucket,
                SUM(rx_delta_bytes) AS rx_bytes,
                SUM(tx_delta_bytes) AS tx_bytes
            FROM traffic_client_samples
            WHERE ts>=?
            GROUP BY {bucket_expr}
            ORDER BY bucket ASC
        """,(cutoff,)).fetchall()

        latest_rows=c.execute("""
            SELECT t.*
            FROM traffic_client_samples t
            JOIN (
                SELECT mac,MAX(id) AS max_id
                FROM traffic_client_samples
                GROUP BY mac
            ) x ON x.max_id=t.id
            ORDER BY (COALESCE(t.rx_rate_bps,0)+COALESCE(t.tx_rate_bps,0)) DESC
        """).fetchall()

        c.close()
        return {
            "hours":hours,
            "totals":dict(totals) if totals else {"rx_bytes":0,"tx_bytes":0,"client_count":0},
            "topClients":[dict(r) for r in top_clients],
            "topVlans":[dict(r) for r in top_vlans],
            "topNetworks":[dict(r) for r in top_networks],
            "topUplinks":[dict(r) for r in top_uplinks],
            "series":[dict(r) for r in series],
            "latestClients":[dict(r) for r in latest_rows]
        }

    def traffic_dpi_summary(self, hours=24):
        cutoff=(datetime.now(timezone.utc)-timedelta(hours=hours)).isoformat()
        c=self.connect()
        apps=c.execute("""
            SELECT
                category_id,app_id,
                COALESCE(MAX(category_name),'Unknown') AS category_name,
                COALESCE(MAX(app_name),'Unknown') AS app_name,
                SUM(rx_delta_bytes) AS rx_bytes,
                SUM(tx_delta_bytes) AS tx_bytes,
                SUM(rx_delta_bytes+tx_delta_bytes) AS total_bytes
            FROM traffic_dpi_samples
            WHERE ts>=?
            GROUP BY category_id,app_id
            ORDER BY total_bytes DESC
            LIMIT 100
        """,(cutoff,)).fetchall()
        categories=c.execute("""
            SELECT
                category_id,
                COALESCE(MAX(category_name),'Unknown') AS category_name,
                SUM(rx_delta_bytes) AS rx_bytes,
                SUM(tx_delta_bytes) AS tx_bytes,
                SUM(rx_delta_bytes+tx_delta_bytes) AS total_bytes
            FROM traffic_dpi_samples
            WHERE ts>=?
            GROUP BY category_id
            ORDER BY total_bytes DESC
        """,(cutoff,)).fetchall()
        c.close()
        return {
            "apps":[dict(r) for r in apps],
            "categories":[dict(r) for r in categories]
        }


    def record_wan_ping(self, target_key, target_name, target_host, target_type,
                        sent, received, packet_loss_pct,
                        min_ms=None, avg_ms=None, max_ms=None, jitter_ms=None, error=None):
        now=datetime.now(timezone.utc).isoformat()
        cutoff=(datetime.now(timezone.utc)-timedelta(days=self.retention_days)).isoformat()
        c=self.connect()
        c.execute("""
            INSERT INTO wan_ping_samples(
                ts,target_key,target_name,target_host,target_type,
                sent,received,packet_loss_pct,min_ms,avg_ms,max_ms,jitter_ms,error
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,(
            now,target_key,target_name,target_host,target_type,
            int(sent),int(received),float(packet_loss_pct),
            min_ms,avg_ms,max_ms,jitter_ms,error
        ))
        c.execute("DELETE FROM wan_ping_samples WHERE ts < ?",(cutoff,))
        c.commit()
        c.close()

    def record_wan_dns(self, resolver_key, resolver_name, resolver_host,
                       query_name, success, latency_ms=None, answers=None, error=None):
        now=datetime.now(timezone.utc).isoformat()
        cutoff=(datetime.now(timezone.utc)-timedelta(days=self.retention_days)).isoformat()
        c=self.connect()
        c.execute("""
            INSERT INTO wan_dns_samples(
                ts,resolver_key,resolver_name,resolver_host,query_name,
                success,latency_ms,answers,error
            ) VALUES(?,?,?,?,?,?,?,?,?)
        """,(
            now,resolver_key,resolver_name,resolver_host,query_name,
            1 if success else 0,latency_ms,answers,error
        ))
        c.execute("DELETE FROM wan_dns_samples WHERE ts < ?",(cutoff,))
        c.commit()
        c.close()

    def wan_quality_summary(self, hours=24, limit=1000):
        cutoff=(datetime.now(timezone.utc)-timedelta(hours=hours)).isoformat()
        c=self.connect()

        target_rows=c.execute("""
            SELECT
                target_key,
                MAX(target_name) AS target_name,
                MAX(target_host) AS target_host,
                MAX(target_type) AS target_type,
                SUM(sent) AS sent,
                SUM(received) AS received,
                CASE WHEN SUM(sent)>0
                     THEN (1.0-(CAST(SUM(received) AS REAL)/SUM(sent)))*100.0
                     ELSE NULL END AS packet_loss_pct,
                AVG(avg_ms) AS avg_ms,
                MIN(min_ms) AS min_ms,
                MAX(max_ms) AS max_ms,
                AVG(jitter_ms) AS jitter_ms,
                MAX(ts) AS last_sample
            FROM wan_ping_samples
            WHERE ts>=?
            GROUP BY target_key
            ORDER BY target_type ASC,target_name COLLATE NOCASE ASC
        """,(cutoff,)).fetchall()

        bucket_expr="substr(ts,1,16)" if hours <= 24 else "substr(ts,1,13)"
        ping_series=c.execute(f"""
            SELECT
                {bucket_expr} AS bucket,
                SUM(sent) AS sent,
                SUM(received) AS received,
                CASE WHEN SUM(sent)>0
                     THEN (1.0-(CAST(SUM(received) AS REAL)/SUM(sent)))*100.0
                     ELSE NULL END AS packet_loss_pct,
                AVG(avg_ms) AS avg_ms,
                AVG(jitter_ms) AS jitter_ms
            FROM wan_ping_samples
            WHERE ts>=? AND target_type='INTERNET'
            GROUP BY {bucket_expr}
            ORDER BY bucket ASC
        """,(cutoff,)).fetchall()

        latest_ping=c.execute("""
            SELECT p.*
            FROM wan_ping_samples p
            JOIN (
                SELECT target_key,MAX(id) AS max_id
                FROM wan_ping_samples
                GROUP BY target_key
            ) x ON x.max_id=p.id
            ORDER BY p.target_type ASC,p.target_name COLLATE NOCASE ASC
        """).fetchall()

        ping_history=c.execute("""
            SELECT *
            FROM wan_ping_samples
            WHERE ts>=?
            ORDER BY id DESC
            LIMIT ?
        """,(cutoff,limit)).fetchall()

        dns_rows=c.execute("""
            SELECT
                resolver_key,
                MAX(resolver_name) AS resolver_name,
                MAX(resolver_host) AS resolver_host,
                COUNT(*) AS samples,
                SUM(success) AS successes,
                CASE WHEN COUNT(*)>0
                     THEN CAST(SUM(success) AS REAL)/COUNT(*)*100.0
                     ELSE NULL END AS success_pct,
                AVG(CASE WHEN success=1 THEN latency_ms END) AS avg_latency_ms,
                MIN(CASE WHEN success=1 THEN latency_ms END) AS min_latency_ms,
                MAX(CASE WHEN success=1 THEN latency_ms END) AS max_latency_ms,
                MAX(ts) AS last_sample
            FROM wan_dns_samples
            WHERE ts>=?
            GROUP BY resolver_key
            ORDER BY resolver_name COLLATE NOCASE ASC
        """,(cutoff,)).fetchall()

        dns_series=c.execute(f"""
            SELECT
                {bucket_expr} AS bucket,
                COUNT(*) AS samples,
                SUM(success) AS successes,
                CASE WHEN COUNT(*)>0
                     THEN CAST(SUM(success) AS REAL)/COUNT(*)*100.0
                     ELSE NULL END AS success_pct,
                AVG(CASE WHEN success=1 THEN latency_ms END) AS avg_latency_ms
            FROM wan_dns_samples
            WHERE ts>=?
            GROUP BY {bucket_expr}
            ORDER BY bucket ASC
        """,(cutoff,)).fetchall()

        latest_dns=c.execute("""
            SELECT d.*
            FROM wan_dns_samples d
            JOIN (
                SELECT resolver_key,MAX(id) AS max_id
                FROM wan_dns_samples
                GROUP BY resolver_key
            ) x ON x.max_id=d.id
            ORDER BY d.resolver_name COLLATE NOCASE ASC
        """).fetchall()

        dns_history=c.execute("""
            SELECT *
            FROM wan_dns_samples
            WHERE ts>=?
            ORDER BY id DESC
            LIMIT ?
        """,(cutoff,limit)).fetchall()

        c.close()

        targets=[dict(r) for r in target_rows]
        internet_targets=[r for r in targets if r.get("target_type")=="INTERNET"]
        gateway_targets=[r for r in targets if r.get("target_type")=="GATEWAY"]

        total_sent=sum(int(r.get("sent") or 0) for r in internet_targets)
        total_received=sum(int(r.get("received") or 0) for r in internet_targets)
        reachability=(float(total_received)/total_sent*100.0) if total_sent else None
        avg_latency=None
        avg_jitter=None
        valid_latency=[float(r["avg_ms"]) for r in internet_targets if r.get("avg_ms") is not None]
        valid_jitter=[float(r["jitter_ms"]) for r in internet_targets if r.get("jitter_ms") is not None]
        if valid_latency:
            avg_latency=sum(valid_latency)/len(valid_latency)
        if valid_jitter:
            avg_jitter=sum(valid_jitter)/len(valid_jitter)

        dns=[dict(r) for r in dns_rows]
        dns_samples=sum(int(r.get("samples") or 0) for r in dns)
        dns_successes=sum(int(r.get("successes") or 0) for r in dns)
        dns_success_pct=(float(dns_successes)/dns_samples*100.0) if dns_samples else None
        dns_lat=[float(r["avg_latency_ms"]) for r in dns if r.get("avg_latency_ms") is not None]
        dns_avg=(sum(dns_lat)/len(dns_lat)) if dns_lat else None

        return {
            "hours":hours,
            "reachabilityPct":reachability,
            "avgLatencyMs":avg_latency,
            "avgJitterMs":avg_jitter,
            "gateway":gateway_targets[0] if gateway_targets else None,
            "targets":targets,
            "pingSeries":[dict(r) for r in ping_series],
            "latestPing":[dict(r) for r in latest_ping],
            "pingHistory":list(reversed([dict(r) for r in ping_history])),
            "dnsSuccessPct":dns_success_pct,
            "dnsAvgLatencyMs":dns_avg,
            "dnsResolvers":dns,
            "dnsSeries":[dict(r) for r in dns_series],
            "latestDns":[dict(r) for r in latest_dns],
            "dnsHistory":list(reversed([dict(r) for r in dns_history])),
        }
