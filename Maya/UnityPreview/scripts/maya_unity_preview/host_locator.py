"""Find the Unity PreviewHost that ships beside the DCC Launcher. Maya / Qt independent.

Distribution layout (the launcher bat folder is two levels below `out`):

    out/
      launcher/DCCLauncher/   <- dcc_maya_menu.py (the launcher bat folder)
      maya_unity/             <- MS2027.exe + MS2027_Data/  (after Open.bat)
                                 Open.bat + data.mpk.NNN    (still compressed)

When the exe is not unpacked yet, Open.bat is returned instead; run_open_bat() restores the
folder and the exe is looked up again afterwards.
"""
import os
import subprocess
import sys
from pathlib import Path

HOST_FOLDER = "maya_unity"
OPEN_BAT = "Open.bat"
SEARCH_LEVELS = 4          # launcher folder itself and up to 3 parents (normally the 2nd one)


def launcher_directory():
    """Folder of the DCC Launcher bat (where dcc_maya_menu.py lives), or None."""
    override = os.environ.get("DCC_LAUNCHER_ROOT")
    if override:
        return Path(override)
    module = sys.modules.get("dcc_maya_menu")
    path = getattr(module, "__file__", None)
    if not path:
        try:
            import importlib.util
            spec = importlib.util.find_spec("dcc_maya_menu")
            path = spec.origin if spec else None
        except (ImportError, ValueError):
            path = None
    return Path(path).resolve().parent if path else None


def host_directory(start=None):
    """The nearest `maya_unity` folder above the launcher folder, or None."""
    start = Path(start) if start else launcher_directory()
    if start is None:
        return None
    for folder in [start, *start.parents][:SEARCH_LEVELS]:
        candidate = folder / HOST_FOLDER
        if candidate.is_dir():
            return candidate
    return None


def find_exe(folder):
    """The Unity player exe in `folder` (the one with a matching <name>_Data folder)."""
    folder = Path(folder)
    if not folder.is_dir():
        return None
    exes = sorted(p for p in folder.glob("*.exe") if p.is_file())
    for exe in exes:
        if (folder / (exe.stem + "_Data")).is_dir():
            return exe
    others = [p for p in exes if not p.name.lower().startswith("unitycrashhandler")]
    return others[0] if others else None


def find_open_bat(folder):
    bat = Path(folder) / OPEN_BAT
    return bat if bat.is_file() else None


def resolve(path):
    """Turn a configured path (exe, Open.bat or empty) into what to run.

    Returns (exe, open_bat): exe when it can be started now; otherwise the Open.bat that will
    produce it (exe is None). Both None when nothing was found.
    """
    path = Path(str(path).strip().strip('"')) if path and str(path).strip() else None
    if path is not None:
        if path.suffix.lower() == ".exe" and path.is_file():
            return path, None
        folder = path.parent if path.suffix else path
        exe = find_exe(folder)
        if exe:
            return exe, None
        bat = find_open_bat(folder)
        if bat:
            return None, bat
    folder = host_directory()
    if folder is None:
        return None, None
    exe = find_exe(folder)
    if exe:
        return exe, None
    return None, find_open_bat(folder)


def _decode(data):
    for encoding in ("utf-8", "mbcs", "cp932"):
        try:
            return data.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("utf-8", "replace")


def run_open_bat(bat):
    """Restore the folder with Open.bat (no window, no prompt). Returns (ok, last output line)."""
    bat = Path(bat)
    env = dict(os.environ, MPK_NOPAUSE="1")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        # ".\\Open.bat" from its own folder: no quoting issues with spaces / full-width spaces in
        # the path, and still found when NoDefaultCurrentDirectoryInExePath is set.
        result = subprocess.run(["cmd.exe", "/d", "/c", ".\\" + bat.name, "-Force"], cwd=str(bat.parent), env=env,
                                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, creationflags=flags)
    except OSError as error:
        return False, str(error)
    lines = [line.strip() for line in _decode(result.stdout or b"").splitlines() if line.strip()]
    return result.returncode == 0, (lines[-1] if lines else "exit code %d" % result.returncode)
