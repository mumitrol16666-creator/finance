import urllib.request
import json
import time

latest_run_id = None
start_time = time.time()

# Let's poll for 15 seconds to give Github Actions a chance to register the new run
while time.time() - start_time < 15:
    try:
        url = "https://api.github.com/repos/mumitrol16666-creator/finance/actions/runs"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode())
            runs = data.get("workflow_runs", [])
            if runs:
                latest = runs[0]
                msg = latest.get("head_commit", {}).get("message")
                if "Gracefully omit WebAppInfo button" in msg:
                    latest_run_id = latest.get("id")
                    print(f"Found latest run {latest_run_id} with status: {latest.get('status')} / conclusion: {latest.get('conclusion')}")
                    break
        time.sleep(3)
    except Exception as e:
        print("Error checking actions:", e)
        time.sleep(3)

if not latest_run_id:
    print("Could not find the latest run in time. Checking details of the topmost run anyway...")
    try:
        url = "https://api.github.com/repos/mumitrol16666-creator/finance/actions/runs"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode())
            runs = data.get("workflow_runs", [])
            if runs:
                latest = runs[0]
                print(f"Topmost run: {latest.get('id')} - Status: {latest.get('status')} - Commit: {latest.get('head_commit', {}).get('message')}")
    except Exception as e:
        print("Error:", e)
