import os
import sys
import time

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from dhcp_engine import DHCPEngine

def test_engine():
    print("Initializing DHCP Engine...")
    engine = DHCPEngine()
    
    # Generate unique test MAC
    test_mac_suffix = hex(int(time.time()))[-4:].upper()
    test_mac = f"00:99:88:77:{test_mac_suffix[:2]}:{test_mac_suffix[2:]}"

    # Test 1: Discover and Rogue Device Alert check
    print(f"Testing Discover with new MAC {test_mac}...")
    d_res = engine.handle_discover(test_mac, "Test-PC-New")
    assert d_res["status"] == "OK", "Discover failed"
    offered_ip = d_res["offer"]["offered_ip"]
    print(f"Offered IP: {offered_ip}")

    # Verify security alert was registered for brand-new device
    assert len(engine.alerts) > 0, "Expected security alert for new MAC"
    print(f"Alert generated: {engine.alerts[0]['title']}")

    # Test 2: Request & SQLite Lease Save
    print("Testing Request & SQLite Persistence...")
    r_res = engine.handle_request(test_mac, "Test-PC-New", offered_ip)
    assert r_res["status"] == "OK", "Request failed"
    print(f"Assigned Lease IP: {r_res['lease']['ip']}")

    # Test 3: Static reservation overrides
    print("Testing Static Reservation & Persistence...")
    res_mac = f"00:AA:BB:CC:{test_mac_suffix[:2]}:{test_mac_suffix[2:]}"
    engine.add_reservation(res_mac, "192.168.1.250", "Special-Server", "Backup Unit")
    d3 = engine.handle_discover(res_mac, "Special-Server")
    assert d3["offer"]["offered_ip"] == "192.168.1.250"

    # Test 4: Release
    print("Testing Release...")
    rel_res = engine.handle_release(test_mac)
    assert rel_res["status"] == "OK"

    # Test 5: Verify Database File exists
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dhcp_leases.db")
    assert os.path.exists(db_path), f"Database file not found at {db_path}"
    print(f"Verified SQLite database at: {db_path}")

    # Test 6: Status check
    status = engine.get_status()
    assert "stats" in status
    print("All tests passed successfully!")

    # Cleanup ping thread for exit
    engine.ping_scanner_running = False

if __name__ == "__main__":
    test_engine()
