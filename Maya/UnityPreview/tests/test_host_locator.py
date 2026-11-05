import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from maya_unity_preview import host_locator


class HostLocatorTests(unittest.TestCase):
    """Layout: <out>/launcher/DCCLauncher (launcher bat) and <out>/maya_unity (PreviewHost)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name)
        self.launcher = self.out / "launcher" / "DCCLauncher"
        self.launcher.mkdir(parents=True)
        self.host = self.out / "maya_unity"
        self.host.mkdir()
        env = patch.dict(os.environ, {"DCC_LAUNCHER_ROOT": str(self.launcher)})
        env.start()
        self.addCleanup(env.stop)
        self.addCleanup(self.tmp.cleanup)

    def unpack(self):
        (self.host / "UnityCrashHandler64.exe").write_bytes(b"MZ")
        (self.host / "MS2027.exe").write_bytes(b"MZ")
        (self.host / "MS2027_Data").mkdir()
        return self.host / "MS2027.exe"

    def test_host_folder_is_two_levels_above_launcher(self):
        self.assertEqual(host_locator.host_directory(), self.host)

    def test_installed_launcher_one_level_deeper_still_finds_host(self):
        nested = self.launcher / "DCCLauncher"
        nested.mkdir()
        self.assertEqual(host_locator.host_directory(nested), self.host)

    def test_open_bat_when_not_unpacked(self):
        (self.host / "Open.bat").write_text("@echo off\n")
        self.assertEqual(host_locator.resolve(""), (None, self.host / "Open.bat"))

    def test_unity_player_exe_preferred_over_crash_handler(self):
        (self.host / "Open.bat").write_text("@echo off\n")
        exe = self.unpack()
        self.assertEqual(host_locator.resolve(""), (exe, None))
        # a remembered Open.bat switches to the exe once it exists
        self.assertEqual(host_locator.resolve(str(self.host / "Open.bat")), (exe, None))

    def test_missing_exe_falls_back_to_open_bat_in_same_folder(self):
        (self.host / "Open.bat").write_text("@echo off\n")
        self.assertEqual(host_locator.resolve(str(self.host / "MS2027.exe")), (None, self.host / "Open.bat"))

    def test_user_exe_elsewhere_is_kept(self):
        other = self.out / "custom" / "Host.exe"
        other.parent.mkdir()
        other.write_bytes(b"MZ")
        self.assertEqual(host_locator.resolve('"%s"' % other), (other, None))

    def test_nothing_found(self):
        self.host.rmdir()
        self.assertEqual(host_locator.resolve(""), (None, None))

    @unittest.skipUnless(sys.platform == "win32", "Open.bat is Windows only")
    def test_run_open_bat_reports_exit_code(self):
        bat = self.host / "Open.bat"
        bat.write_text('@echo off\r\nif not "%1"=="-Force" exit /b 3\r\n'
                       'if not defined MPK_NOPAUSE exit /b 4\r\n'
                       'mkdir "%~dp0MS2027_Data"\r\ncopy nul "%~dp0MS2027.exe" >nul\r\necho done\r\n')
        ok, message = host_locator.run_open_bat(bat)
        self.assertTrue(ok, message)
        self.assertEqual(message, "done")
        self.assertEqual(host_locator.find_exe(self.host), self.host / "MS2027.exe")


if __name__ == "__main__":
    unittest.main()
