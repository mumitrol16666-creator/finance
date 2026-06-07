import urllib.request
import json

try:
    # Query only the single latest run to keep the response extremely small
    url = "https://api.github.com/repos/mumitrol16666-creator/finance/actions/runs?per_page=1"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0"}
    )
    with urllib.request.urlopen(req, timeout=10) as response:
        # Read the content robustly
        body = response.read()
        data = json.loads(body.decode('utf-8'))
        runs = data.get("workflow_runs", [])
        if runs:
            latest = runs[0]
            print(f"LATEST RUN:")
            print(f"  ID: {latest.get('id')}")
            print(f"  Event: {latest.get('event')}")
            print(f"  Status: {latest.get('status')}")
            print(f"  Conclusion: {latest.get('conclusion')}")
            print(f"  Commit Message: {latest.get('head_commit', {}).get('message')}")
            print(f"  Commit SHA: {latest.get('head_commit', {}).get('id')}")
        else:
            print("No runs found.")
except Exception as e:
    print("Error fetching runs:", e)
