import os
import sys
import time

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from dhcp_engine import DHCPEngine, lookup_vendor

def test_engine():
    print("Initializing DHCP Engine...")
    engine = DHCPEngine()
    
    # Test 0: OUI Vendor Lookup
    print("Testing OUI Vendor Lookup...")
    assert lookup_vendor("F0:18:98:11:22:33") == "Apple"
    assert lookup_vendor("B8:27:EB:00:11:22") == "Raspberry Pi"
    assert lookup_vendor("00:14:22:AA:BB:CC") == "Dell"
    print("Vendor lookup tests passed!")

    # Generate unique test MAC
    test_mac_suffix = hex(int(time.time()))[-4:].upper()
    test_mac = f"00:14:22:77:{test_mac_suffix[:2]}:{test_mac_suffix[2:]}"

    # Test 1: Discover and Rogue Device Alert check
    print(f"Testing Discover with MAC {test_mac}...")
    d_res = engine.handle_discover(test_mac, "Test-Dell-PC")
    assert d_res["status"] == "OK", "Discover failed"
    assert d_res["offer"]["vendor"] == "Dell"
    offered_ip = d_res["offer"]["offered_ip"]
    print(f"Offered IP: {offered_ip} for vendor {d_res['offer']['vendor']}")

    # Test 2: Request & SQLite Lease Save
    print("Testing Request & SQLite Persistence...")
    r_res = engine.handle_request(test_mac, "Test-Dell-PC", offered_ip)
    assert r_res["status"] == "OK", "Request failed"
    assert r_res["lease"]["vendor"] == "Dell"
    print(f"Assigned Lease IP: {r_res['lease']['ip']}")

    # Test 3: Static reservation overrides
    print("Testing Static Reservation & Persistence...")
    res_mac = f"F0:18:98:CC:{test_mac_suffix[:2]}:{test_mac_suffix[2:]}"
    engine.add_reservation(res_mac, "192.168.1.250", "CEO-MacBook", "Executive Laptop")
    d3 = engine.handle_discover(res_mac, "CEO-MacBook")
    assert d3["offer"]["offered_ip"] == "192.168.1.250"
    assert d3["offer"]["vendor"] == "Apple"

    # Test 4: Release
    print("Testing Release...")
    rel_res = engine.handle_release(test_mac)
    assert rel_res["status"] == "OK"

    # Test 5: Verify Database File exists
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dhcp_leases.db")
    assert os.path.exists(db_path), f"Database file not found at {db_path}"
    print(f"Verified SQLite database at: {db_path}")

    # Test 6: Backup Import
    print("Testing Backup Import...")
    dummy_backup = {
        "config": {"domain_name": "corp.internal"},
        "reservations": [{"mac": "00:1A:2B:99:99:99", "ip": "192.168.1.199", "hostname": "Cisco-Core-Switch", "note": "Core"}]
    }
    assert engine.import_backup(dummy_backup) == True
    assert engine.config["domain_name"] == "corp.internal"
    print("Backup import passed!")

    # Test 7: Status check
    status = engine.get_status()
    assert "stats" in status
    print("All tests passed successfully!")

    engine.ping_scanner_running = False

if __name__ == "__main__":
    test_engine()
