import urllib.request
import json

req = urllib.request.Request(
    'https://api.github.com/repos/mumitrol16666-creator/finance/actions/runs',
    headers={'User-Agent': 'Mozilla/5.0'}
)
try:
    with urllib.request.urlopen(req) as res:
        data = json.loads(res.read().decode())
        if 'workflow_runs' in data and data['workflow_runs']:
            for i, r in enumerate(data['workflow_runs'][:5]):
                print(f"Run {i+1}:")
                print(f"  Name: {r.get('name')}")
                print(f"  Status: {r.get('status')}")
                print(f"  Conclusion: {r.get('conclusion')}")
                print(f"  Commit: {r.get('head_commit', {}).get('message')}")
                print(f"  Created At: {r.get('created_at')}")
                print()
        else:
            print("No workflow runs found.")
except Exception as e:
    print(f"Error fetching runs: {e}")
