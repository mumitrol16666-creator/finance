import urllib.request
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

try:
    # 1. Get job ID for latest run 27008992311
    run_id = "27008992311"
    url_jobs = f"https://api.github.com/repos/mumitrol16666-creator/finance/actions/runs/{run_id}/jobs"
    req = urllib.request.Request(url_jobs, headers={"User-Agent": "Mozilla/5.0"})
    job_id = None
    with urllib.request.urlopen(req, timeout=10) as response:
        data = json.loads(response.read().decode())
        jobs = data.get("jobs", [])
        if jobs:
            job_id = jobs[0].get("id")
            print(f"Job ID: {job_id}")
            
    if not job_id:
        print("No job ID found.")
        sys.exit(1)
        
    # 2. Get job log
    url_logs = f"https://api.github.com/repos/mumitrol16666-creator/finance/actions/jobs/{job_id}/logs"
    req_logs = urllib.request.Request(url_logs, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req_logs, timeout=10) as response:
        log_content = response.read().decode("utf-8", errors="ignore")
        
        # Look for the deploy step output
        lines = log_content.splitlines()
        
        # Let's write the full log to a scratch file so we can view it
        with open("scratch/deploy_log.txt", "w", encoding="utf-8") as f:
            f.write(log_content)
            
        print("Log downloaded to scratch/deploy_log.txt")
        
        # Print lines containing systemd status or python processes or errors
        print("\n--- Snippet of systemd / python info ---")
        show = False
        count = 0
        for line in lines:
            if "=== SYSTEMD SERVICE INFO ===" in line or "=== PYTHON PROCESSES" in line or "=== SYSTEMD STATUS AFTER RESTART ===" in line:
                show = True
                count = 0
            if show:
                print(line)
                count += 1
                if count > 45:
                    show = False
except Exception as e:
    print("Error:", e)
