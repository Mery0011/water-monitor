"""Test the macOS launcher without starting a server or installing packages."""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent


class LauncherTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix='water-launcher-')
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)/'Folder with spaces'/'water-monitor'
        self.root.mkdir(parents=True)
        shutil.copyfile(ROOT/'start.command',self.root/'start.command')
        (self.root/'app.py').write_text('# Test fixture\n')
        self.capture = Path(directory.name)/'arguments.txt'
        self.env = {**os.environ,'WATER_LAUNCHER_CAPTURE':str(self.capture)}

    def make_python(self):
        python = self.root/'.venv/bin/python'
        python.parent.mkdir(parents=True)
        python.write_text('''#!/bin/sh
if [ "$1" = "-c" ]; then exit "${WATER_LAUNCHER_IMPORT_STATUS:-0}"; fi
printf '%s\\n' "$PWD" "$@" > "$WATER_LAUNCHER_CAPTURE"
exit "${WATER_LAUNCHER_EXIT_STATUS:-0}"
''')
        python.chmod(0o755)

    def run_launcher(self):
        return subprocess.run(['/bin/zsh',str(self.root/'start.command')],
            cwd='/private/tmp',env=self.env,input='',text=True,capture_output=True,timeout=10)

    def test_missing_environment_has_setup_instructions(self):
        result = self.run_launcher()
        self.assertEqual(result.returncode,1)
        self.assertIn('python3 -m venv .venv',result.stdout)
        self.assertIn('pip install -r requirements.txt',result.stdout)
        self.assertFalse(self.capture.exists())

    def test_missing_dependencies_have_install_instructions(self):
        self.make_python()
        self.env['WATER_LAUNCHER_IMPORT_STATUS']='1'
        result = self.run_launcher()
        self.assertEqual(result.returncode,1)
        self.assertIn('required Python packages',result.stdout)
        self.assertFalse(self.capture.exists())

    def test_space_in_path_and_different_working_directory(self):
        self.make_python()
        result = self.run_launcher()
        self.assertEqual(result.returncode,0,result.stderr)
        args = self.capture.read_text().splitlines()
        self.assertEqual(Path(args[0]).resolve(),self.root.resolve())
        self.assertEqual(args[1:5],['-m','streamlit','run',str((self.root/'app.py').resolve())])

    def test_server_is_local_and_telemetry_disabled(self):
        self.make_python(); self.run_launcher()
        args = self.capture.read_text().splitlines()
        self.assertEqual(args[args.index('--server.port')+1],'8503')
        self.assertEqual(args[args.index('--server.address')+1],'127.0.0.1')
        self.assertEqual(args[args.index('--browser.gatherUsageStats')+1],'false')

    def test_server_failure_exit_code_is_preserved(self):
        self.make_python()
        self.env['WATER_LAUNCHER_EXIT_STATUS']='7'
        self.assertEqual(self.run_launcher().returncode,7)


if __name__=='__main__':
    unittest.main()
