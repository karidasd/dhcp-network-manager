import time
import socket
import struct
import threading
import subprocess
import platform
import urllib.request
import json
from datetime import datetime, timedelta
import ipaddress
from db_manager import DHCPDatabase

# Top Hardware Manufacturer OUIs
OUI_DATABASE = {
    "00:1A:2B": "Cisco",
    "00:0C:29": "VMware",
    "00:50:56": "VMware",
    "00:1C:42": "Parallels",
    "B8:27:EB": "Raspberry Pi",
    "DC:A6:32": "Raspberry Pi",
    "E4:5F:01": "Raspberry Pi",
    "28:CD:C1": "Raspberry Pi",
    "00:14:22": "Dell",
    "18:66:DA": "Dell",
    "00:1E:67": "Intel",
    "34:17:EB": "Intel",
    "00:25:B3": "Hewlett-Packard",
    "3C:D9:2B": "Hewlett-Packard",
    "F0:18:98": "Apple",
    "AC:BC:32": "Apple",
    "38:F9:D3": "Apple",
    "A4:83:E7": "Apple",
    "00:1A:8C": "Sophos",
    "24:4B:FE": "Samsung",
    "50:01:D9": "Samsung",
    "84:F3:EB": "Espressif IoT",
    "24:6F:28": "Espressif IoT",
    "5C:CF:7F": "Espressif IoT",
    "50:C7:BF": "TP-Link",
    "14:EB:B6": "TP-Link",
    "64:66:B3": "TP-Link",
    "60:A4:4C": "Xiaomi",
    "34:CE:00": "Xiaomi",
    "00:15:5D": "Microsoft Hyper-V",
    "F8:75:A4": "Sony",
    "00:09:B0": "Onkyo",
    "02:00:00": "Virtual Interface"
}

def lookup_vendor(mac: str) -> str:
    clean_mac = mac.upper().replace("-", ":")
    prefix = ":".join(clean_mac.split(":")[:3])
    if prefix in OUI_DATABASE:
        return OUI_DATABASE[prefix]
    if clean_mac.startswith("02:"):
        return "Simulated / Virtual"
    return "Generic Device"


class DHCPLease:
    def __init__(self, ip: str, mac: str, hostname: str = "Unknown", vendor: str = None, duration_seconds: int = 86400, is_static: bool = False, issued_at: datetime = None, expires_at: datetime = None, state: str = "ACTIVE", is_online: bool = False, latency_ms: int = -1):
        self.ip = ip
        self.mac = mac.upper()
        self.hostname = hostname or "Unknown"
        self.vendor = vendor if vendor else lookup_vendor(self.mac)
        self.duration_seconds = duration_seconds
        self.is_static = is_static
        self.issued_at = issued_at if issued_at else datetime.now()
        if expires_at:
            self.expires_at = expires_at
        else:
            self.expires_at = datetime.max if is_static else self.issued_at + timedelta(seconds=duration_seconds)
        self.state = state
        self.is_online = is_online
        self.latency_ms = latency_ms
        self.last_seen = datetime.now()

    def is_expired(self) -> bool:
        if self.is_static:
            return False
        return datetime.now() > self.expires_at

    def to_dict(self):
        return {
            "ip": self.ip,
            "mac": self.mac,
            "hostname": self.hostname,
            "vendor": self.vendor,
            "issued_at": self.issued_at.strftime("%Y-%m-%d %H:%M:%S") if isinstance(self.issued_at, datetime) else str(self.issued_at),
            "expires_at": "Never (Static)" if self.is_static else (self.expires_at.strftime("%Y-%m-%d %H:%M:%S") if isinstance(self.expires_at, datetime) else str(self.expires_at)),
            "remaining_seconds": -1 if self.is_static else max(0, int((self.expires_at - datetime.now()).total_seconds())) if isinstance(self.expires_at, datetime) else 0,
            "is_static": bool(self.is_static),
            "state": "EXPIRED" if self.is_expired() else self.state,
            "is_online": bool(self.is_online),
            "latency_ms": self.latency_ms,
            "last_seen": self.last_seen.strftime("%Y-%m-%d %H:%M:%S") if isinstance(self.last_seen, datetime) else str(self.last_seen)
        }


class DHCPEngine:
    def __init__(self):
        self.lock = threading.Lock()
        self.db = DHCPDatabase()
        
        default_config = {
            "network": "192.168.1.0/24",
            "start_ip": "192.168.1.100",
            "end_ip": "192.168.1.150",
            "subnet_mask": "255.255.255.0",
            "gateway": "192.168.1.1",
            "dns_servers": ["8.8.8.8", "1.1.1.1"],
            "domain_name": "lan.local",
            "lease_duration_seconds": 3600,
            "webhook_url": ""
        }

        saved_config = self.db.load_config()
        self.config = {**default_config, **saved_config}
        if not saved_config:
            self.db.save_config(self.config)

        self.reservations = self.db.load_reservations()
        if not self.reservations:
            self.reservations = {
                "00:1A:2B:3C:4D:5E": {
                    "ip": "192.168.1.99",
                    "hostname": "Server-NAS",
                    "note": "Static assignment for File Server"
                }
            }
            self.db.save_reservation("00:1A:2B:3C:4D:5E", "192.168.1.99", "Server-NAS", "Static assignment for File Server")

        self.leases = {}
        saved_leases = self.db.load_leases()
        for sl in saved_leases:
            try:
                iss = datetime.strptime(sl["issued_at"], "%Y-%m-%d %H:%M:%S")
                exp = datetime.max if sl["is_static"] else datetime.strptime(sl["expires_at"], "%Y-%m-%d %H:%M:%S")
            except Exception:
                iss = datetime.now()
                exp = datetime.now() + timedelta(seconds=sl.get("duration_seconds", 3600))

            lease = DHCPLease(
                ip=sl["ip"],
                mac=sl["mac"],
                hostname=sl["hostname"],
                vendor=sl.get("vendor"),
                duration_seconds=sl["duration_seconds"],
                is_static=bool(sl["is_static"]),
                issued_at=iss,
                expires_at=exp,
                state=sl.get("state", "ACTIVE"),
                is_online=bool(sl.get("is_online", False)),
                latency_ms=sl.get("latency_ms", -1)
            )
            if not lease.is_expired():
                self.leases[lease.mac] = lease

        self.logs = []
        self.alerts = []
        self._add_log("SYSTEM", "DHCP Engine & SQLite Database initialized with OUI Vendor Lookup.")

        self.real_socket_running = False
        self.real_socket_thread = None
        self.real_socket_error = None

        self.ping_scanner_running = True
        self.ping_thread = threading.Thread(target=self._ping_scanner_loop, daemon=True)
        self.ping_thread.start()

    def _add_log(self, level: str, message: str, mac: str = None, ip: str = None):
        entry = {
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "level": level,
            "message": message,
            "mac": mac,
            "ip": ip
        }
        self.logs.insert(0, entry)
        if len(self.logs) > 100:
            self.logs.pop()
        
        try:
            self.db.add_log(level, message, mac, ip)
        except Exception:
            pass

    def add_alert(self, alert_type: str, title: str, description: str):
        alert = {
            "id": f"{int(time.time()*1000)}",
            "type": alert_type,
            "title": title,
            "description": description,
            "timestamp": datetime.now().strftime("%H:%M:%S")
        }
        self.alerts.insert(0, alert)
        if len(self.alerts) > 10:
            self.alerts.pop()

        # Send Webhook alert if configured
        if self.config.get("webhook_url"):
            threading.Thread(target=self._send_webhook, args=(title, description), daemon=True).start()

    def _send_webhook(self, title: str, description: str):
        url = self.config.get("webhook_url")
        if not url:
            return
        try:
            payload = json.dumps({"content": f"**DHCP Server Alert**: {title}\n{description}"}).encode("utf-8")
            req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json", "User-Agent": "DHCP-Server"})
            urllib.request.urlopen(req, timeout=3)
        except Exception:
            pass

    def clear_alerts(self):
        with self.lock:
            self.alerts = []

    def update_config(self, new_config: dict):
        with self.lock:
            for k in ["start_ip", "end_ip", "subnet_mask", "gateway", "domain_name", "webhook_url"]:
                if k in new_config:
                    self.config[k] = str(new_config[k]).strip()
            
            if "lease_duration_seconds" in new_config:
                self.config["lease_duration_seconds"] = int(new_config["lease_duration_seconds"])

            if "dns_servers" in new_config:
                if isinstance(new_config["dns_servers"], str):
                    self.config["dns_servers"] = [x.strip() for x in new_config["dns_servers"].split(",") if x.strip()]
                elif isinstance(new_config["dns_servers"], list):
                    self.config["dns_servers"] = [str(x).strip() for x in new_config["dns_servers"] if str(x).strip()]

            self.db.save_config(self.config)
            self._add_log("SYSTEM", "Network configuration updated and persisted to SQLite.")

    def add_reservation(self, mac: str, ip: str, hostname: str = "", note: str = ""):
        mac = mac.upper().strip()
        ip = ip.strip()
        with self.lock:
            self.reservations[mac] = {
                "ip": ip,
                "hostname": hostname or "Reserved-Device",
                "note": note
            }
            if mac in self.leases:
                del self.leases[mac]
            self.db.save_reservation(mac, ip, hostname, note)
            self._add_log("SYSTEM", f"Static IP reservation added: {mac} -> {ip} ({hostname})", mac=mac, ip=ip)

    def remove_reservation(self, mac: str):
        mac = mac.upper().strip()
        with self.lock:
            if mac in self.reservations:
                del self.reservations[mac]
                self.db.delete_reservation(mac)
                self._add_log("SYSTEM", f"Static IP reservation removed: {mac}", mac=mac)

    def _get_ip_range_list(self):
        try:
            start = int(ipaddress.IPv4Address(self.config["start_ip"]))
            end = int(ipaddress.IPv4Address(self.config["end_ip"]))
            if start > end:
                start, end = end, start
            return [str(ipaddress.IPv4Address(i)) for i in range(start, end + 1)]
        except Exception:
            return []

    def _find_available_ip(self, mac: str, preferred_ip: str = None) -> str:
        if mac in self.reservations:
            return self.reservations[mac]["ip"]

        if mac in self.leases and not self.leases[mac].is_expired():
            return self.leases[mac].ip

        ip_pool = self._get_ip_range_list()
        reserved_ips = {r["ip"] for r in self.reservations.values()}
        active_leased_ips = {l.ip for l in self.leases.values() if not l.is_expired() and l.state == "ACTIVE"}

        if preferred_ip and preferred_ip in ip_pool:
            if preferred_ip not in reserved_ips and preferred_ip not in active_leased_ips:
                return preferred_ip

        for ip in ip_pool:
            if ip not in reserved_ips and ip not in active_leased_ips:
                return ip

        for ip in ip_pool:
            if ip not in reserved_ips:
                return ip

        return None

    # --- DORA Process Implementation ---

    def handle_discover(self, mac: str, hostname: str = "Client-PC", requested_ip: str = None) -> dict:
        mac = mac.upper().strip()
        vendor = lookup_vendor(mac)
        with self.lock:
            if not self.db.is_known_device(mac):
                self._add_log("SECURITY_ALERT", f"New device connected: {mac} ({hostname}) [{vendor}]", mac=mac)
                self.add_alert("warning", "🚨 Νέα Συσκευή στο Δίκτυο", f"Συνδέθηκε συσκευή: {mac} ({hostname}) - Κατασκευαστής: {vendor}")
                self.db.register_device(mac, hostname)
            
            self._add_log("DISCOVER", f"DHCPDISCOVER from {mac} ({hostname}) [{vendor}]", mac=mac)
            
            allocated_ip = self._find_available_ip(mac, requested_ip)
            if not allocated_ip:
                self._add_log("WARNING", f"No available IPs in pool to offer {mac}!", mac=mac)
                self.add_alert("danger", "⚠️ Εξάντληση IP Pool", "Δεν υπάρχουν άλλες ελεύθερες διευθύνσεις IP στο εύρος!")
                return {"status": "ERROR", "message": "IP pool exhausted"}

            offer_packet = {
                "message_type": "DHCPOFFER",
                "offered_ip": allocated_ip,
                "mac": mac,
                "hostname": hostname,
                "vendor": vendor,
                "subnet_mask": self.config["subnet_mask"],
                "gateway": self.config["gateway"],
                "dns_servers": self.config["dns_servers"],
                "lease_duration": self.config["lease_duration_seconds"],
                "domain_name": self.config["domain_name"]
            }

            self._add_log("OFFER", f"DHCPOFFER {allocated_ip} offered to {mac}", mac=mac, ip=allocated_ip)
            return {"status": "OK", "offer": offer_packet}

    def handle_request(self, mac: str, hostname: str = "Client-PC", requested_ip: str = None) -> dict:
        mac = mac.upper().strip()
        vendor = lookup_vendor(mac)
        with self.lock:
            self._add_log("REQUEST", f"DHCPREQUEST for IP {requested_ip} from {mac} ({hostname})", mac=mac, ip=requested_ip)

            valid_ip = self._find_available_ip(mac, requested_ip)
            is_static = mac in self.reservations

            if not valid_ip or (requested_ip and valid_ip != requested_ip):
                self._add_log("NAK", f"DHCPNAK sent to {mac} for {requested_ip} (Invalid or unavailable)", mac=mac, ip=requested_ip)
                return {"status": "NAK", "message": "Requested IP cannot be assigned"}

            final_ip = requested_ip if requested_ip else valid_ip
            lease = DHCPLease(
                ip=final_ip,
                mac=mac,
                hostname=hostname,
                vendor=vendor,
                duration_seconds=self.config["lease_duration_seconds"],
                is_static=is_static,
                is_online=True,
                latency_ms=1
            )
            self.leases[mac] = lease
            
            self.db.save_lease(lease.to_dict())

            all_ips = self._get_ip_range_list()
            active_count = len([l for l in self.leases.values() if not l.is_expired() and l.state == "ACTIVE"])
            if len(all_ips) > 0 and (active_count / len(all_ips)) >= 0.85:
                self.add_alert("warning", "📊 Υψηλή Χρήση IP Pool", f"Το IP Pool ξεπέρασε το 85% χωρητικότητας ({active_count}/{len(all_ips)} IPs)")

            ack_packet = {
                "message_type": "DHCPACK",
                "assigned_ip": final_ip,
                "mac": mac,
                "hostname": hostname,
                "vendor": vendor,
                "subnet_mask": self.config["subnet_mask"],
                "gateway": self.config["gateway"],
                "dns_servers": self.config["dns_servers"],
                "lease_duration": lease.duration_seconds,
                "domain_name": self.config["domain_name"]
            }

            self._add_log("ACK", f"DHCPACK IP {final_ip} confirmed & assigned to {mac} ({hostname}) [{vendor}]", mac=mac, ip=final_ip)
            return {"status": "OK", "ack": ack_packet, "lease": lease.to_dict()}

    def handle_release(self, mac: str) -> dict:
        mac = mac.upper().strip()
        with self.lock:
            if mac in self.leases:
                released_ip = self.leases[mac].ip
                self.leases[mac].state = "RELEASED"
                del self.leases[mac]
                self.db.delete_lease(mac)
                self._add_log("RELEASE", f"DHCPRELEASE from {mac} - Released IP {released_ip}", mac=mac, ip=released_ip)
                return {"status": "OK", "message": f"IP {released_ip} released"}
            return {"status": "NOT_FOUND", "message": "No active lease found for MAC"}

    def revoke_lease(self, mac: str) -> dict:
        return self.handle_release(mac)

    def _ping_scanner_loop(self):
        time.sleep(2)
        while self.ping_scanner_running:
            try:
                with self.lock:
                    ips_to_check = [(l.ip, l.mac) for l in self.leases.values() if l.state == "ACTIVE"]

                for ip, mac in ips_to_check:
                    is_alive, latency = self._ping_single_ip(ip)
                    with self.lock:
                        if mac in self.leases:
                            self.leases[mac].is_online = is_alive
                            self.leases[mac].latency_ms = latency
                            self.leases[mac].last_seen = datetime.now()
                            try:
                                self.db.update_lease_status(ip, is_alive, latency)
                            except Exception:
                                pass

            except Exception:
                pass
            
            time.sleep(15)

    def _ping_single_ip(self, ip: str) -> tuple[bool, int]:
        try:
            start_t = time.time()
            param = "-n" if platform.system().lower() == "windows" else "-c"
            timeout_param = "-w" if platform.system().lower() == "windows" else "-W"
            timeout_val = "350" if platform.system().lower() == "windows" else "1"
            
            cmd = ["ping", param, "1", timeout_param, timeout_val, ip]
            res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=1.0)
            elapsed_ms = int((time.time() - start_t) * 1000)
            return (res.returncode == 0, elapsed_ms if res.returncode == 0 else -1)
        except Exception:
            return (False, -1)

    def import_backup(self, backup_data: dict) -> bool:
        with self.lock:
            if "config" in backup_data:
                self.config = {**self.config, **backup_data["config"]}
                self.db.save_config(self.config)
            
            if "reservations" in backup_data:
                for r in backup_data["reservations"]:
                    self.reservations[r["mac"]] = {
                        "ip": r["ip"],
                        "hostname": r.get("hostname", ""),
                        "note": r.get("note", "")
                    }
                    self.db.save_reservation(r["mac"], r["ip"], r.get("hostname", ""), r.get("note", ""))

            self._add_log("SYSTEM", "Backup data successfully restored into SQLite database.")
            return True

    def get_status(self) -> dict:
        with self.lock:
            all_ips = self._get_ip_range_list()
            total_pool = len(all_ips)
            
            for k, v in list(self.leases.items()):
                if v.is_expired():
                    v.state = "EXPIRED"

            active_leases_list = [l.to_dict() for l in self.leases.values() if l.state == "ACTIVE"]
            active_count = len(active_leases_list)
            reserved_count = len(self.reservations)
            available_count = max(0, total_pool - active_count)

            return {
                "config": self.config,
                "stats": {
                    "total_pool_ips": total_pool,
                    "active_leases": active_count,
                    "reserved_ips": reserved_count,
                    "available_ips": available_count,
                    "online_devices": len([l for l in active_leases_list if l.get("is_online")]),
                    "utilization_percent": round((active_count / total_pool * 100), 1) if total_pool > 0 else 0
                },
                "leases": active_leases_list,
                "reservations": [{"mac": k, **v} for k, v in self.reservations.items()],
                "alerts": self.alerts,
                "logs": self.logs[:50],
                "real_socket_running": self.real_socket_running,
                "real_socket_error": self.real_socket_error
            }

    # --- Real Network UDP Socket Listener (Port 67) ---

    def start_real_dhcp_listener(self):
        with self.lock:
            if self.real_socket_running:
                return True, "Already running"

        def _listener():
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                sock.bind(('', 67))
                self.real_socket_running = True
                self.real_socket_error = None
                self._add_log("SYSTEM", "Real DHCP UDP socket listening on 0.0.0.0:67 (Broadcast)")

                while self.real_socket_running:
                    sock.settimeout(2.0)
                    try:
                        data, addr = sock.recvfrom(2048)
                        if len(data) < 240:
                            continue
                        
                        op, htype, hlen, hops, xid, secs, flags, ciaddr, yiaddr, siaddr, giaddr = struct.unpack("!BBBBIHHIIII", data[:28])
                        chaddr = data[28:44]
                        mac = ':'.join(f'{b:02X}' for b in chaddr[:hlen])
                        
                        magic = data[236:240]
                        dhcp_msg_type = None
                        hostname = "Real-Device"
                        requested_ip = None

                        if magic == b'\x63\x82\x53\x63':
                            idx = 240
                            while idx < len(data):
                                opt_code = data[idx]
                                if opt_code == 255:
                                    break
                                if opt_code == 0:
                                    idx += 1
                                    continue
                                opt_len = data[idx+1]
                                opt_data = data[idx+2 : idx+2+opt_len]
                                idx += 2 + opt_len

                                if opt_code == 53 and len(opt_data) == 1:
                                    dhcp_msg_type = opt_data[0]
                                elif opt_code == 12:
                                    try:
                                        hostname = opt_data.decode('utf-8', errors='ignore')
                                    except:
                                        pass
                                elif opt_code == 50 and len(opt_data) == 4:
                                    requested_ip = socket.inet_ntoa(opt_data)

                        if dhcp_msg_type == 1:
                            self.handle_discover(mac, hostname, requested_ip)
                        elif dhcp_msg_type == 3:
                            self.handle_request(mac, hostname, requested_ip)
                        elif dhcp_msg_type == 7:
                            self.handle_release(mac)

                    except socket.timeout:
                        continue
                    except Exception as e:
                        if self.real_socket_running:
                            self._add_log("WARNING", f"Error in DHCP listener: {str(e)}")
            except Exception as e:
                self.real_socket_running = False
                self.real_socket_error = str(e)
                self._add_log("WARNING", f"Cannot bind UDP port 67: {str(e)} (Admin rights required)")
            finally:
                self.real_socket_running = False

        self.real_socket_thread = threading.Thread(target=_listener, daemon=True)
        self.real_socket_thread.start()
        return True, "Starting listener..."

    def stop_real_dhcp_listener(self):
        with self.lock:
            self.real_socket_running = False
            self._add_log("SYSTEM", "Real DHCP UDP socket listener stopped.")
        return True, "Stopped"
