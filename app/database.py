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
        """)
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
