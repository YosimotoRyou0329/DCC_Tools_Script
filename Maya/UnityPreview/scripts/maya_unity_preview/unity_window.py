"""Control the Unity PreviewHost window from Maya (Windows only, ctypes + Win32).

- make it resizable (adds a sizing border even if the player was built without one)
- Picture-in-Picture: always on top, small, remembered position
- hide / show without closing the player
No Maya or Qt imports, so it can be used from anywhere.
"""
import ctypes
import os
import sys

IS_WINDOWS = sys.platform == "win32"

if IS_WINDOWS:
    from ctypes import wintypes as wt

    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    _WNDENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)

    class _MONITORINFO(ctypes.Structure):
        _fields_ = [("cbSize", wt.DWORD), ("rcMonitor", wt.RECT),
                    ("rcWork", wt.RECT), ("dwFlags", wt.DWORD)]

    def _declare(function, argtypes, restype):
        function.argtypes = argtypes
        function.restype = restype

    _declare(_user32.EnumWindows, [_WNDENUMPROC, wt.LPARAM], wt.BOOL)
    _declare(_user32.GetClassNameW, [wt.HWND, wt.LPWSTR, ctypes.c_int], ctypes.c_int)
    _declare(_user32.GetWindowThreadProcessId, [wt.HWND, ctypes.POINTER(wt.DWORD)], wt.DWORD)
    _declare(_user32.IsWindow, [wt.HWND], wt.BOOL)
    _declare(_user32.IsWindowVisible, [wt.HWND], wt.BOOL)
    _declare(_user32.IsIconic, [wt.HWND], wt.BOOL)
    _declare(_user32.GetWindowLongW, [wt.HWND, ctypes.c_int], ctypes.c_long)
    _declare(_user32.SetWindowLongW, [wt.HWND, ctypes.c_int, ctypes.c_long], ctypes.c_long)
    _declare(_user32.SetWindowPos, [wt.HWND, wt.HWND, ctypes.c_int, ctypes.c_int,
                                    ctypes.c_int, ctypes.c_int, wt.UINT], wt.BOOL)
    _declare(_user32.GetWindowRect, [wt.HWND, ctypes.POINTER(wt.RECT)], wt.BOOL)
    _declare(_user32.GetClientRect, [wt.HWND, ctypes.POINTER(wt.RECT)], wt.BOOL)
    _declare(_user32.ShowWindow, [wt.HWND, ctypes.c_int], wt.BOOL)
    _declare(_user32.MonitorFromWindow, [wt.HWND, wt.DWORD], wt.HMONITOR)
    _declare(_user32.GetMonitorInfoW, [wt.HMONITOR, ctypes.POINTER(_MONITORINFO)], wt.BOOL)
    _declare(_kernel32.OpenProcess, [wt.DWORD, wt.BOOL, wt.DWORD], wt.HANDLE)
    _declare(_kernel32.CloseHandle, [wt.HANDLE], wt.BOOL)
    _declare(_kernel32.QueryFullProcessImageNameW,
             [wt.HANDLE, wt.DWORD, wt.LPWSTR, ctypes.POINTER(wt.DWORD)], wt.BOOL)

GWL_STYLE = -16
WS_THICKFRAME = 0x00040000
WS_MINIMIZEBOX = 0x00020000
WS_MAXIMIZEBOX = 0x00010000
SWP_NOSIZE, SWP_NOMOVE, SWP_NOZORDER, SWP_NOACTIVATE, SWP_FRAMECHANGED = 0x1, 0x2, 0x4, 0x10, 0x20
HWND_TOPMOST, HWND_NOTOPMOST = -1, -2
SW_HIDE, SW_SHOWNOACTIVATE, SW_RESTORE = 0, 4, 9
MONITOR_DEFAULTTONEAREST = 2
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
UNITY_PLAYER_CLASS = "UnityWndClass"


def _process_path(pid):
    handle = _kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ""
    try:
        size = wt.DWORD(1024)
        buffer = ctypes.create_unicode_buffer(size.value)
        if _kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return buffer.value
        return ""
    finally:
        _kernel32.CloseHandle(handle)


def find_unity_window(pid=None, exe_path=None):
    """Return the HWND of a Unity player window (by process id, else by exe path, else any)."""
    if not IS_WINDOWS:
        return None
    wanted = os.path.normcase(os.path.abspath(exe_path)) if exe_path else None
    by_pid, by_path, any_player = [], [], []

    def visit(hwnd, _):
        name = ctypes.create_unicode_buffer(64)
        _user32.GetClassNameW(hwnd, name, 64)
        if name.value != UNITY_PLAYER_CLASS:
            return True
        owner = wt.DWORD()
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if pid and owner.value == pid:
            by_pid.append(hwnd)
        elif wanted and os.path.normcase(_process_path(owner.value)) == wanted:
            by_path.append(hwnd)
        else:
            any_player.append(hwnd)
        return True

    _user32.EnumWindows(_WNDENUMPROC(visit), 0)
    for found in (by_pid, by_path, any_player):
        if found:
            return found[0]
    return None


def is_usable_rect(rect):
    """False for a minimized window's rect (-32000, -32000, 160, 28), garbage or anything tiny."""
    try:
        x, y, width, height = (int(v) for v in rect)
    except (TypeError, ValueError):
        return False
    return x > -10000 and y > -10000 and width >= 320 and height >= 180


class UnityWindow:
    def __init__(self, hwnd):
        self.hwnd = hwnd

    def alive(self):
        return bool(self.hwnd) and bool(_user32.IsWindow(self.hwnd))

    def visible(self):
        return bool(_user32.IsWindowVisible(self.hwnd))

    def make_resizable(self):
        style = _user32.GetWindowLongW(self.hwnd, GWL_STYLE)
        wanted = style | WS_THICKFRAME | WS_MINIMIZEBOX | WS_MAXIMIZEBOX
        if wanted != style:
            _user32.SetWindowLongW(self.hwnd, GWL_STYLE, wanted)
            _user32.SetWindowPos(self.hwnd, None, 0, 0, 0, 0,
                                 SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED)

    def set_topmost(self, enabled):
        _user32.SetWindowPos(self.hwnd, wt.HWND(HWND_TOPMOST if enabled else HWND_NOTOPMOST),
                             0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)

    def rect(self):
        r = wt.RECT()
        _user32.GetWindowRect(self.hwnd, ctypes.byref(r))
        return [r.left, r.top, r.right - r.left, r.bottom - r.top]

    def set_rect(self, rect):
        x, y, width, height = (int(v) for v in rect)
        if _user32.IsIconic(self.hwnd):
            _user32.ShowWindow(self.hwnd, SW_RESTORE)
        _user32.SetWindowPos(self.hwnd, None, x, y, max(160, width), max(90, height),
                             SWP_NOZORDER | SWP_NOACTIVATE)

    def work_area(self, near_hwnd=None):
        """Usable desktop area (x, y, w, h) of the monitor showing near_hwnd (or this window)."""
        monitor = _user32.MonitorFromWindow(near_hwnd or self.hwnd, MONITOR_DEFAULTTONEAREST)
        info = _MONITORINFO()
        info.cbSize = ctypes.sizeof(_MONITORINFO)
        _user32.GetMonitorInfoW(monitor, ctypes.byref(info))
        w = info.rcWork
        return [w.left, w.top, w.right - w.left, w.bottom - w.top]

    def client_size(self):
        r = wt.RECT()
        _user32.GetClientRect(self.hwnd, ctypes.byref(r))
        return r.right - r.left, r.bottom - r.top

    def default_pip_rect(self, near_hwnd=None, margin=24):
        """Bottom-right of the monitor, a quarter of its width, keeping Unity's current ratio."""
        x, y, width, height = self.work_area(near_hwnd)
        _, _, window_width, window_height = self.rect()
        client_width, client_height = self.client_size()
        frame_width, frame_height = window_width - client_width, window_height - client_height
        ratio = client_width / float(client_height) if client_height > 0 else 16 / 9.0
        if client_width < 160 or client_height < 90:   # minimized: sizes are meaningless
            frame_width, frame_height, ratio = 16, 39, 16 / 9.0
        pip_client_width = max(320, width // 4)
        pip_width = pip_client_width + frame_width
        pip_height = int(round(pip_client_width / ratio)) + frame_height
        return [x + width - pip_width - margin, y + height - pip_height - margin, pip_width, pip_height]

    def hide(self):
        _user32.ShowWindow(self.hwnd, SW_HIDE)

    def show(self):
        _user32.ShowWindow(self.hwnd, SW_SHOWNOACTIVATE)
