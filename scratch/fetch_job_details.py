import urllib.request
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

try:
    url = "https://api.github.com/repos/mumitrol16666-creator/finance/actions/runs/27019079766/jobs"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as response:
        body = response.read()
        data = json.loads(body.decode('utf-8'))
        for job in data.get("jobs", []):
            print(f"Job Name: {job.get('name')}")
            print(f"Status: {job.get('status')}")
            print(f"Conclusion: {job.get('conclusion')}")
            print("Steps:")
            for step in job.get("steps", []):
                print(f"  - {step.get('name')}: {step.get('status')} / {step.get('conclusion')}")
except Exception as e:
    print("Error:", e)
