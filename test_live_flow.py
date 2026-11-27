"""
Test script to simulate the live stream flow and capture debug output
"""
import requests
import urllib3
import time

# Disable SSL warnings for self-signed cert
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE_URL = "https://localhost:8443"

print("=" * 70)
print("Testing Live Stream Flow")
print("=" * 70)

# Step 1: Check /live/info BEFORE session is created
print("\n[Step 1] Checking /live/info BEFORE session creation...")
try:
    response = requests.get(f"{BASE_URL}/live/info", verify=False, timeout=5)
    data = response.json()
    print(f"Response: {data}")
    print(f"Has session: {data.get('has_session')}")
    print(f"Phone URL: {data.get('phone_url')}")
except Exception as e:
    print(f"ERROR: {e}")

# Step 2: Create session
print("\n[Step 2] Creating session via /live/session/start...")
try:
    response = requests.post(f"{BASE_URL}/live/session/start", verify=False, timeout=5)
    data = response.json()
    print(f"Response: {data}")
    print(f"Success: {data.get('success')}")
    print(f"Session ID: {data.get('session_id')}")
    print(f"Token: {data.get('token')}")
    token = data.get('token')
except Exception as e:
    print(f"ERROR: {e}")
    token = None

# Step 3: Check /live/info AFTER session is created
print("\n[Step 3] Checking /live/info AFTER session creation...")
time.sleep(0.5)
try:
    response = requests.get(f"{BASE_URL}/live/info", verify=False, timeout=5)
    data = response.json()
    print(f"Response: {data}")
    print(f"Has session: {data.get('has_session')}")
    print(f"Phone URL: {data.get('phone_url')}")
    phone_url = data.get('phone_url')
except Exception as e:
    print(f"ERROR: {e}")
    phone_url = None

# Step 4: Try to access /live/phone with token
if token and phone_url:
    print(f"\n[Step 4] Accessing /live/phone?token={token}...")
    try:
        response = requests.get(f"{BASE_URL}/live/phone?token={token}", verify=False, timeout=5)
        print(f"Status code: {response.status_code}")
        if response.status_code == 200:
            print("SUCCESS! Phone page served correctly")
        elif response.status_code == 403:
            print("FORBIDDEN - Invalid token")
            print(f"Response: {response.text[:200]}...")
    except Exception as e:
        print(f"ERROR: {e}")

# Step 5: Try to access with WRONG token
print(f"\n[Step 5] Accessing /live/phone with WRONG token...")
try:
    response = requests.get(f"{BASE_URL}/live/phone?token=WRONG_TOKEN", verify=False, timeout=5)
    print(f"Status code: {response.status_code}")
    if response.status_code == 403:
        print("Correctly rejected invalid token")
except Exception as e:
    print(f"ERROR: {e}")

print("\n" + "=" * 70)
print("Test Complete - Check server terminal for debug logs")
print("=" * 70)
