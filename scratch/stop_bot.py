import subprocess
import json

# Get all running python processes
cmd = "powershell \"Get-CimInstance Win32_Process -Filter 'Name = ''python.exe''' | Select-Object ProcessId, CommandLine | ConvertTo-Json\""
res = subprocess.run(cmd, shell=True, capture_output=True, text=True)

if res.stdout.strip():
    try:
        data = json.loads(res.stdout)
        if not isinstance(data, list):
            data = [data]
        
        pids_killed = []
        for proc in data:
            cmdline = proc.get("CommandLine") or ""
            pid = proc.get("ProcessId")
            if "main.py" in cmdline and pid:
                kill_cmd = f"taskkill /F /PID {pid}"
                subprocess.run(kill_cmd, shell=True, capture_output=True)
                pids_killed.append(pid)
                
        if pids_killed:
            print(f"Successfully stopped bot processes with PIDs: {pids_killed}")
        else:
            print("No active bot processes were running.")
    except Exception as e:
        print("Error while terminiting processes:", e)
else:
    print("No python processes found.")
