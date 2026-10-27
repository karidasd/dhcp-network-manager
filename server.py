import os
import sys
import json
import csv
import io
import urllib.parse
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from dhcp_engine import DHCPEngine

dhcp = DHCPEngine()
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(ROOT_DIR, "web") if os.path.exists(os.path.join(ROOT_DIR, "web", "index.html")) else ROOT_DIR

class DHCPRequestHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=WEB_DIR, **kwargs)

    def _send_json(self, data, status_code=200):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_csv(self, filename: str, content: str):
        body = content.encode('utf-8-sig')
        self.send_response(200)
        self.send_header("Content-Type", "text/csv; charset=utf-8")
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self):
        content_length = int(self.headers.get('Content-Length', 0))
        if content_length > 0:
            raw_data = self.rfile.read(content_length).decode('utf-8')
            return json.loads(raw_data)
        return {}

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/api/status":
            self._send_json(dhcp.get_status())
            return

        elif path == "/api/export/json":
            self._send_json(dhcp.get_status())
            return

        elif path == "/api/export/csv":
            status_data = dhcp.get_status()
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(["Hostname", "Vendor", "IP Address", "MAC Address", "Type", "Status", "Latency", "Issued At", "Expires At"])
            
            for l in status_data.get("leases", []):
                writer.writerow([
                    l["hostname"],
                    l.get("vendor", "Unknown"),
                    l["ip"],
                    l["mac"],
                    "Static" if l["is_static"] else "Dynamic",
                    "Online" if l.get("is_online") else "Offline",
                    f"{l.get('latency_ms')}ms" if l.get('latency_ms', -1) >= 0 else "-",
                    l["issued_at"],
                    l["expires_at"]
                ])
            self._send_csv("dhcp_leases_report.csv", output.getvalue())
            return
        
        if path == "/" or path == "":
            self.path = "/index.html"

        return super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        try:
            body = self._read_json_body()

            if path == "/api/config":
                dhcp.update_config(body)
                self._send_json({"status": "OK", "message": "Configuration updated"})
                return

            elif path == "/api/simulate/request":
                mac = body.get("mac", "02:00:00:11:22:33")
                hostname = body.get("hostname", "PC-Simulated")
                requested_ip = body.get("requested_ip")

                discover_res = dhcp.handle_discover(mac, hostname, requested_ip)
                if discover_res.get("status") != "OK":
                    self._send_json(discover_res, status_code=400)
                    return

                offered_ip = discover_res["offer"]["offered_ip"]
                ack_res = dhcp.handle_request(mac, hostname, offered_ip)
                self._send_json({
                    "status": "OK",
                    "offer": discover_res["offer"],
                    "ack": ack_res.get("ack"),
                    "lease": ack_res.get("lease")
                })
                return

            elif path == "/api/simulate/release":
                mac = body.get("mac")
                if not mac:
                    self._send_json({"status": "ERROR", "message": "MAC address required"}, status_code=400)
                    return
                res = dhcp.handle_release(mac)
                self._send_json(res)
                return

            elif path == "/api/reservations/add":
                mac = body.get("mac")
                ip = body.get("ip")
                hostname = body.get("hostname", "")
                note = body.get("note", "")
                if not mac or not ip:
                    self._send_json({"status": "ERROR", "message": "MAC and IP required"}, status_code=400)
                    return
                dhcp.add_reservation(mac, ip, hostname, note)
                self._send_json({"status": "OK", "message": "Reservation added"})
                return

            elif path == "/api/reservations/remove":
                mac = body.get("mac")
                if not mac:
                    self._send_json({"status": "ERROR", "message": "MAC required"}, status_code=400)
                    return
                dhcp.remove_reservation(mac)
                self._send_json({"status": "OK", "message": "Reservation removed"})
                return

            elif path == "/api/leases/revoke":
                mac = body.get("mac")
                if not mac:
                    self._send_json({"status": "ERROR", "message": "MAC required"}, status_code=400)
                    return
                res = dhcp.revoke_lease(mac)
                self._send_json(res)
                return

            elif path == "/api/alerts/clear":
                dhcp.clear_alerts()
                self._send_json({"status": "OK", "message": "Alerts cleared"})
                return

            elif path == "/api/backup/import":
                success = dhcp.import_backup(body)
                self._send_json({"status": "OK", "message": "Backup imported successfully"})
                return

            elif path == "/api/webhook/test":
                dhcp.add_alert("info", "🔔 Webhook Test", "Αυτό είναι ένα δοκιμαστικό μήνυμα ελέγχου σύνδεσης Webhook.")
                self._send_json({"status": "OK", "message": "Test alert sent"})
                return

            elif path == "/api/toggle-real-dhcp":
                action = body.get("action", "start")
                if action == "start":
                    dhcp.start_real_dhcp_listener()
                else:
                    dhcp.stop_real_dhcp_listener()
                self._send_json(dhcp.get_status())
                return

            else:
                self._send_json({"status": "NOT_FOUND"}, status_code=404)

        except Exception as e:
            self._send_json({"status": "ERROR", "message": str(e)}, status_code=500)

    def log_message(self, format, *args):
        pass


def run(port=8080):
    server_address = ('', port)
    httpd = ThreadingHTTPServer(server_address, DHCPRequestHandler)
    print("=" * 65)
    print("   🌐 DHCP SERVER & NETWORK IP MANAGER (PYTHON + SQLITE)")
    print("=" * 65)
    print(f" -> Web Dashboard:    http://localhost:{port}")
    print(f" -> Live Status API:  http://localhost:{port}/api/status")
    print(f" -> Export CSV:       http://localhost:{port}/api/export/csv")
    print("=" * 65)
    print(" Πατήστε Ctrl+C για τερματισμό του διακομιστή.")
    print("=" * 65)

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping DHCP server...")
        httpd.server_close()
        sys.exit(0)

if __name__ == "__main__":
    port = 8080
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            pass
    run(port)
