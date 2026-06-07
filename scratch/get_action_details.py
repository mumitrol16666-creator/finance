import urllib.request
import json

try:
    url = "https://api.github.com/repos/mumitrol16666-creator/finance/actions/runs/26965418339"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as response:
        data = json.loads(response.read().decode())
        print(f"Status: {data.get('status')}")
        print(f"Conclusion: {data.get('conclusion')}")
        print(f"Created At: {data.get('created_at')}")
        print(f"Updated At: {data.get('updated_at')}")
except Exception as e:
    print("Error:", e)
