import sys
from dhcp_engine import DHCPEngine

def test_engine():
    engine = DHCPEngine()
    
    # Test 1: Discover
    print("Testing Discover...")
    d_res = engine.handle_discover("00:11:22:33:44:AA", "Test-PC-1")
    assert d_res["status"] == "OK", "Discover failed"
    offered_ip = d_res["offer"]["offered_ip"]
    print(f"Offered IP: {offered_ip}")
    assert offered_ip == "192.168.1.100", f"Unexpected IP {offered_ip}"

    # Test 2: Request
    print("Testing Request...")
    r_res = engine.handle_request("00:11:22:33:44:AA", "Test-PC-1", offered_ip)
    assert r_res["status"] == "OK", "Request failed"
    print(f"Assigned Lease IP: {r_res['lease']['ip']}")

    # Test 3: Second client gets next IP
    print("Testing Second Client...")
    d2 = engine.handle_discover("00:11:22:33:44:BB", "Test-PC-2")
    offered_ip2 = d2["offer"]["offered_ip"]
    assert offered_ip2 == "192.168.1.101", f"Expected 192.168.1.101, got {offered_ip2}"
    r2 = engine.handle_request("00:11:22:33:44:BB", "Test-PC-2", offered_ip2)
    assert r2["status"] == "OK"

    # Test 4: Static reservation overrides
    print("Testing Static Reservation...")
    engine.add_reservation("00:AA:BB:CC:DD:EE", "192.168.1.250", "Special-Server")
    d3 = engine.handle_discover("00:AA:BB:CC:DD:EE", "Special-Server")
    assert d3["offer"]["offered_ip"] == "192.168.1.250"

    # Test 5: Release
    print("Testing Release...")
    rel_res = engine.handle_release("00:11:22:33:44:AA")
    assert rel_res["status"] == "OK"

    # Test 6: Status check
    status = engine.get_status()
    assert status["stats"]["active_leases"] == 1
    print("All tests passed successfully!")

if __name__ == "__main__":
    test_engine()
