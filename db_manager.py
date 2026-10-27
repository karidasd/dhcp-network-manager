import os
import sqlite3
import threading
from datetime import datetime

DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dhcp_leases.db")

class DHCPDatabase:
    def __init__(self, db_path: str = DB_FILE):
        self.db_path = db_path
        self.lock = threading.Lock()
        self._init_db()

    def _get_connection(self):
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self.lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # Config table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS config (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL
                    )
                """)

                # Leases table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS leases (
                        mac TEXT PRIMARY KEY,
                        ip TEXT NOT NULL,
                        hostname TEXT NOT NULL,
                        vendor TEXT DEFAULT 'Unknown',
                        issued_at TEXT NOT NULL,
                        expires_at TEXT NOT NULL,
                        duration_seconds INTEGER NOT NULL,
                        is_static INTEGER NOT NULL,
                        state TEXT NOT NULL,
                        is_online INTEGER DEFAULT 0,
                        latency_ms INTEGER DEFAULT -1,
                        last_seen TEXT
                    )
                """)

                # Auto-migration for existing databases
                cursor.execute("PRAGMA table_info(leases)")
                columns = [row["name"] for row in cursor.fetchall()]
                if "vendor" not in columns:
                    cursor.execute("ALTER TABLE leases ADD COLUMN vendor TEXT DEFAULT 'Unknown'")
                if "latency_ms" not in columns:
                    cursor.execute("ALTER TABLE leases ADD COLUMN latency_ms INTEGER DEFAULT -1")

                # Reservations table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS reservations (
                        mac TEXT PRIMARY KEY,
                        ip TEXT NOT NULL,
                        hostname TEXT,
                        note TEXT,
                        created_at TEXT NOT NULL
                    )
                """)

                # Known Devices
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS known_devices (
                        mac TEXT PRIMARY KEY,
                        first_seen TEXT NOT NULL,
                        hostname TEXT
                    )
                """)

                # Historical Logs
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS activity_logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL,
                        level TEXT NOT NULL,
                        message TEXT NOT NULL,
                        mac TEXT,
                        ip TEXT
                    )
                """)
                conn.commit()

    def load_config(self) -> dict:
        with self.lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT key, value FROM config")
                rows = cursor.fetchall()
                config = {}
                for r in rows:
                    k, v = r["key"], r["value"]
                    if k == "dns_servers":
                        config[k] = [x.strip() for x in v.split(",") if x.strip()]
                    elif k == "lease_duration_seconds":
                        config[k] = int(v)
                    else:
                        config[k] = v
                return config

    def save_config(self, config: dict):
        with self.lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                for k, v in config.items():
                    val_str = ",".join(v) if isinstance(v, list) else str(v)
                    cursor.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", (k, val_str))
                conn.commit()

    def load_reservations(self) -> dict:
        with self.lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT mac, ip, hostname, note FROM reservations")
                rows = cursor.fetchall()
                res = {}
                for r in rows:
                    res[r["mac"]] = {
                        "ip": r["ip"],
                        "hostname": r["hostname"],
                        "note": r["note"]
                    }
                return res

    def save_reservation(self, mac: str, ip: str, hostname: str, note: str):
        with self.lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO reservations (mac, ip, hostname, note, created_at)
                    VALUES (?, ?, ?, ?, ?)
                """, (mac, ip, hostname, note, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                conn.commit()

    def delete_reservation(self, mac: str):
        with self.lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM reservations WHERE mac = ?", (mac,))
                conn.commit()

    def load_leases(self) -> list:
        with self.lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM leases WHERE state = 'ACTIVE'")
                rows = cursor.fetchall()
                return [dict(r) for r in rows]

    def save_lease(self, lease_dict: dict):
        with self.lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO leases 
                    (mac, ip, hostname, vendor, issued_at, expires_at, duration_seconds, is_static, state, is_online, latency_ms, last_seen)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    lease_dict["mac"],
                    lease_dict["ip"],
                    lease_dict["hostname"],
                    lease_dict.get("vendor", "Unknown"),
                    lease_dict["issued_at"],
                    lease_dict["expires_at"],
                    lease_dict.get("duration_seconds", 3600),
                    1 if lease_dict.get("is_static") else 0,
                    lease_dict.get("state", "ACTIVE"),
                    1 if lease_dict.get("is_online") else 0,
                    lease_dict.get("latency_ms", -1),
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                ))
                conn.commit()

    def update_lease_status(self, ip: str, is_online: bool, latency_ms: int):
        with self.lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE leases 
                    SET is_online = ?, latency_ms = ?, last_seen = ?
                    WHERE ip = ?
                """, (1 if is_online else 0, latency_ms, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), ip))
                conn.commit()

    def delete_lease(self, mac: str):
        with self.lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("UPDATE leases SET state = 'RELEASED' WHERE mac = ?", (mac,))
                conn.commit()

    def is_known_device(self, mac: str) -> bool:
        with self.lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 1 FROM known_devices WHERE mac = ?", (mac,))
                return cursor.fetchone() is not None

    def register_device(self, mac: str, hostname: str):
        with self.lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR IGNORE INTO known_devices (mac, first_seen, hostname)
                    VALUES (?, ?, ?)
                """, (mac, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), hostname))
                conn.commit()

    def add_log(self, level: str, message: str, mac: str = None, ip: str = None):
        with self.lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO activity_logs (timestamp, level, message, mac, ip)
                    VALUES (?, ?, ?, ?, ?)
                """, (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), level, message, mac, ip))
                conn.commit()

    def get_recent_logs(self, limit: int = 50) -> list:
        with self.lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT timestamp, level, message, mac, ip 
                    FROM activity_logs 
                    ORDER BY id DESC LIMIT ?
                """, (limit,))
                rows = cursor.fetchall()
                return [dict(r) for r in rows]
