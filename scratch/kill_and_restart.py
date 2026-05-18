import subprocess
import json
import time

# Get all running python processes
cmd = "powershell \"Get-CimInstance Win32_Process -Filter 'Name = ''python.exe''' | Select-Object ProcessId, CommandLine | ConvertTo-Json\""
res = subprocess.run(cmd, shell=True, capture_output=True, text=True)

if res.stdout.strip():
    try:
        data = json.loads(res.stdout)
        if not isinstance(data, list):
            data = [data]
        
        pids_to_kill = []
        for proc in data:
            cmdline = proc.get("CommandLine") or ""
            pid = proc.get("ProcessId")
            if "main.py" in cmdline and pid:
                pids_to_kill.append(str(pid))
                
        if pids_to_kill:
            kill_cmd = f"taskkill /F " + " ".join([f"/PID {p}" for p in pids_to_kill])
            print("Killing active bot instances:", kill_cmd)
            subprocess.run(kill_cmd, shell=True)
        else:
            print("No active bot instances running.")
    except Exception as e:
        print("Error parsing or killing:", e)

# Wait 2 seconds to make sure ports and polling handles are cleared
time.sleep(2)

# Start bot in background
print("Starting the bot...")
p = subprocess.Popen([r".venv\Scripts\python.exe", "main.py"])
print("Bot started with PID:", p.pid)
