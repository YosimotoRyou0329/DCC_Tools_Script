import subprocess, io, os, time
subprocess.run(["taskkill", "/F", "/IM", "MS2027.exe"], capture_output=True, creationflags=0x08000000)
time.sleep(1)
unity = r"D:\Unity\Unity Hub\6000.3.23f1\Editor\Unity.exe"
log = r"D:\DCC\Tools\_tmp_unity_build.log"
if os.path.exists(log):
    os.remove(log)
args = [unity, "-batchmode", "-quit", "-projectPath", r"C:\BaerProject\MS2027Project",
        "-executeMethod", "CSE_MayaPreviewHostBuild.BuildFromCommandLine", "-logFile", log]
p = subprocess.Popen(args, creationflags=0x08000000)
io.open(r"D:/DCC/Tools/_tmp_log.txt", "w", encoding="utf-8").write("pid %d" % p.pid)
