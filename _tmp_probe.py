import subprocess, io
r = subprocess.run(["powershell", "-NoProfile", "-Command",
    "Get-Process Unity,MS2027,maya -ErrorAction SilentlyContinue | Select Id,StartTime,MainWindowHandle,MainWindowTitle | Format-List"],
    capture_output=True, text=True, creationflags=0x08000000)
io.open(r"D:/DCC/Tools/_tmp_log.txt", "w", encoding="utf-8").write(r.stdout)
