import time
import socket
import struct
import threading
from datetime import datetime, timedelta
import ipaddress

class DHCPLease:
    def __init__(self, ip: str, mac: str, hostname: str = "Unknown", duration_seconds: int = 86400, is_static: bool = False):
        self.ip = ip
        self.mac = mac.upper()
        self.hostname = hostname or "Unknown"
        self.duration_seconds = duration_seconds
        self.is_static = is_static
        self.issued_at = datetime.now()
        self.expires_at = datetime.max if is_static else self.issued_at + timedelta(seconds=duration_seconds)
        self.state = "ACTIVE"  # ACTIVE, EXPIRED, RELEASED

    def is_expired(self) -> bool:
        if self.is_static:
            return False
        return datetime.now() > self.expires_at

    def to_dict(self):
        return {
            "ip": self.ip,
            "mac": self.mac,
            "hostname": self.hostname,
            "issued_at": self.issued_at.strftime("%Y-%m-%d %H:%M:%S"),
            "expires_at": "Never (Static)" if self.is_static else self.expires_at.strftime("%Y-%m-%d %H:%M:%S"),
            "remaining_seconds": -1 if self.is_static else max(0, int((self.expires_at - datetime.now()).total_seconds())),
            "is_static": self.is_static,
            "state": "EXPIRED" if self.is_expired() else self.state
        }


class DHCPEngine:
    def __init__(self):
        self.lock = threading.Lock()
        
        # Configuration
        self.config = {
            "network": "192.168.1.0/24",
            "start_ip": "192.168.1.100",
            "end_ip": "192.168.1.150",
            "subnet_mask": "255.255.255.0",
            "gateway": "192.168.1.1",
            "dns_servers": ["8.8.8.8", "1.1.1.1"],
            "domain_name": "lan.local",
            "lease_duration_seconds": 3600  # 1 ώρα default
        }

        # Reservations: MAC -> {ip, hostname, note}
        self.reservations = {
            "00:1A:2B:3C:4D:5E": {
                "ip": "192.168.1.99",
                "hostname": "Server-NAS",
                "note": "Static assignment for File Server"
            }
        }

        # Leases: MAC -> DHCPLease
        self.leases = {}
        
        # Activity log
        self.logs = []
        self._add_log("SYSTEM", "DHCP Engine initialized successfully.")

        # Real UDP Socket State
        self.real_socket_running = False
        self.real_socket_thread = None
        self.real_socket_error = None

    def _add_log(self, level: str, message: str, mac: str = None, ip: str = None):
        entry = {
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "level": level,  # DISCOVER, OFFER, REQUEST, ACK, NAK, RELEASE, SYSTEM, WARNING
            "message": message,
            "mac": mac,
            "ip": ip
        }
        self.logs.insert(0, entry)
        if len(self.logs) > 100:
            self.logs.pop()

    def update_config(self, new_config: dict):
        with self.lock:
            for k in ["start_ip", "end_ip", "subnet_mask", "gateway", "domain_name"]:
                if k in new_config and new_config[k]:
                    self.config[k] = str(new_config[k]).strip()
            
            if "lease_duration_seconds" in new_config:
                self.config["lease_duration_seconds"] = int(new_config["lease_duration_seconds"])

            if "dns_servers" in new_config:
                if isinstance(new_config["dns_servers"], str):
                    self.config["dns_servers"] = [x.strip() for x in new_config["dns_servers"].split(",") if x.strip()]
                elif isinstance(new_config["dns_servers"], list):
                    self.config["dns_servers"] = [str(x).strip() for x in new_config["dns_servers"] if str(x).strip()]

            self._add_log("SYSTEM", "Network configuration updated.")

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
            self._add_log("SYSTEM", f"Static IP reservation added: {mac} -> {ip} ({hostname})", mac=mac, ip=ip)

    def remove_reservation(self, mac: str):
        mac = mac.upper().strip()
        with self.lock:
            if mac in self.reservations:
                del self.reservations[mac]
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
        # 1. Έλεγχος αν υπάρχει Static Reservation
        if mac in self.reservations:
            return self.reservations[mac]["ip"]

        # 2. Έλεγχος αν η συσκευή είχε ήδη πρόσφατη ενεργή IP
        if mac in self.leases and not self.leases[mac].is_expired():
            return self.leases[mac].ip

        # 3. Έλεγχος αν η προτιμώμενη IP είναι διαθέσιμη
        ip_pool = self._get_ip_range_list()
        reserved_ips = {r["ip"] for r in self.reservations.values()}
        active_leased_ips = {l.ip for l in self.leases.values() if not l.is_expired() and l.state == "ACTIVE"}

        if preferred_ip and preferred_ip in ip_pool:
            if preferred_ip not in reserved_ips and preferred_ip not in active_leased_ips:
                return preferred_ip

        # 4. Βρες την πρώτη ελεύθερη IP από το pool
        for ip in ip_pool:
            if ip not in reserved_ips and ip not in active_leased_ips:
                return ip

        # Αν δεν υπάρχει διαθέσιμη, δες αν υπάρχει κάποιο ληγμένο lease
        for ip in ip_pool:
            if ip not in reserved_ips:
                return ip

        return None

    # --- DORA Process Implementation ---

    def handle_discover(self, mac: str, hostname: str = "Client-PC", requested_ip: str = None) -> dict:
        """Βήμα 1: DHCPDISCOVER από τον client -> Επιστρέφει DHCPOFFER"""
        mac = mac.upper().strip()
        with self.lock:
            self._add_log("DISCOVER", f"DHCPDISCOVER from {mac} ({hostname})", mac=mac)
            
            allocated_ip = self._find_available_ip(mac, requested_ip)
            if not allocated_ip:
                self._add_log("WARNING", f"No available IPs in pool to offer {mac}!", mac=mac)
                return {"status": "ERROR", "message": "IP pool exhausted"}

            offer_packet = {
                "message_type": "DHCPOFFER",
                "offered_ip": allocated_ip,
                "mac": mac,
                "hostname": hostname,
                "subnet_mask": self.config["subnet_mask"],
                "gateway": self.config["gateway"],
                "dns_servers": self.config["dns_servers"],
                "lease_duration": self.config["lease_duration_seconds"],
                "domain_name": self.config["domain_name"]
            }

            self._add_log("OFFER", f"DHCPOFFER {allocated_ip} offered to {mac}", mac=mac, ip=allocated_ip)
            return {"status": "OK", "offer": offer_packet}

    def handle_request(self, mac: str, hostname: str = "Client-PC", requested_ip: str = None) -> dict:
        """Βήμα 2: DHCPREQUEST από τον client -> Επιστρέφει DHCPACK ή DHCPNAK"""
        mac = mac.upper().strip()
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
                duration_seconds=self.config["lease_duration_seconds"],
                is_static=is_static
            )
            self.leases[mac] = lease

            ack_packet = {
                "message_type": "DHCPACK",
                "assigned_ip": final_ip,
                "mac": mac,
                "hostname": hostname,
                "subnet_mask": self.config["subnet_mask"],
                "gateway": self.config["gateway"],
                "dns_servers": self.config["dns_servers"],
                "lease_duration": lease.duration_seconds,
                "domain_name": self.config["domain_name"]
            }

            self._add_log("ACK", f"DHCPACK IP {final_ip} assigned to {mac} ({hostname})", mac=mac, ip=final_ip)
            return {"status": "OK", "ack": ack_packet, "lease": lease.to_dict()}

    def handle_release(self, mac: str) -> dict:
        """DHCPRELEASE: Ο υπολογιστής απελευθερώνει την IP του"""
        mac = mac.upper().strip()
        with self.lock:
            if mac in self.leases:
                released_ip = self.leases[mac].ip
                self.leases[mac].state = "RELEASED"
                del self.leases[mac]
                self._add_log("RELEASE", f"DHCPRELEASE from {mac} - Released IP {released_ip}", mac=mac, ip=released_ip)
                return {"status": "OK", "message": f"IP {released_ip} released"}
            return {"status": "NOT_FOUND", "message": "No active lease found for MAC"}

    def revoke_lease(self, mac: str) -> dict:
        return self.handle_release(mac)

    def get_status(self) -> dict:
        with self.lock:
            all_ips = self._get_ip_range_list()
            total_pool = len(all_ips)
            
            # Ανανέωση κατάστασης expired
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
                    "utilization_percent": round((active_count / total_pool * 100), 1) if total_pool > 0 else 0
                },
                "leases": active_leases_list,
                "reservations": [{"mac": k, **v} for k, v in self.reservations.items()],
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
