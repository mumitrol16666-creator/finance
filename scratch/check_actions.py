import urllib.request
import json

try:
    url = "https://api.github.com/repos/mumitrol16666-creator/finance/actions/runs"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0"}
    )
    with urllib.request.urlopen(req, timeout=10) as response:
        data = json.loads(response.read().decode())
        runs = data.get("workflow_runs", [])
        if runs:
            latest = runs[0]
            print(f"Latest run ID: {latest.get('id')}")
            print(f"Event: {latest.get('event')}")
            print(f"Status: {latest.get('status')}")
            print(f"Conclusion: {latest.get('conclusion')}")
            print(f"Commit: {latest.get('head_commit', {}).get('message')}")
        else:
            print("No runs found.")
except Exception as e:
    print("Error fetching runs:", e)
