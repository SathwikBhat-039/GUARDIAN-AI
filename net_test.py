import socket
import requests
import sys

def test_connectivity():
    print("--- Network Test ---")
    
    # 1. Test DNS resolution
    hosts = ["google.com", "api.pushbullet.com", "ipinfo.io"]
    for host in hosts:
        try:
            ip = socket.gethostbyname(host)
            print(f"✅ DNS: {host} -> {ip}")
        except Exception as e:
            print(f"❌ DNS: {host} failed: {e}")

    # 2. Test direct IP connection (Google DNS)
    try:
        s = socket.create_connection(("8.8.8.8", 53), timeout=3)
        print("✅ Direct IP: 8.8.8.8:53 connected")
        s.close()
    except Exception as e:
        print(f"❌ Direct IP: 8.8.8.8:53 failed: {e}")

    # 3. Test HTTP request
    try:
        r = requests.get("https://www.google.com", timeout=5)
        print(f"✅ HTTP: google.com returned {r.status_code}")
    except Exception as e:
        print(f"❌ HTTP: google.com failed: {e}")

    # 4. Test Pushbullet specifically
    try:
        r = requests.get("https://api.pushbullet.com/v2/users/me", timeout=5)
        print(f"✅ HTTP: Pushbullet returned {r.status_code} (expected 401/403 without key)")
    except Exception as e:
        print(f"❌ HTTP: Pushbullet failed: {e}")

if __name__ == "__main__":
    test_connectivity()
