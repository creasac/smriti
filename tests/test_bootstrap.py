"""Network-free tests of archive extraction, argument forwarding, and cleanup."""
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest


class BootstrapTests(unittest.TestCase):
    def exercise(self, installer_status=0, download_status=0):
        with tempfile.TemporaryDirectory(prefix="bootstrap test ") as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            # Deliberately non-executable: bootstrap must invoke bash explicitly.
            (source / "install.sh").write_text(
                '#!/bin/bash\n[[ "$1" == "--test-argument" && "$2" == "has spaces" ]] || exit 99\n'
                f'exit {installer_status}\n'
            )
            archive = root / "source.tar.gz"
            with tarfile.open(archive, "w:gz") as tar:
                tar.add(source, arcname="project-master")
            commands = root / "commands"
            commands.mkdir()
            curl = commands / "curl"
            curl.write_text(
                '#!/usr/bin/env python3\nimport os, shutil, sys\n'
                f'if {download_status}: sys.exit({download_status})\n'
                'shutil.copyfile(os.environ["TEST_ARCHIVE"], sys.argv[sys.argv.index("--output") + 1])\n'
            )
            curl.chmod(0o755)
            downloads = root / "downloads"
            downloads.mkdir()
            env = dict(os.environ, TMPDIR=str(downloads), TEST_ARCHIVE=str(archive),
                       PATH=str(commands) + os.pathsep + os.environ["PATH"])
            result = subprocess.run(
                ["bash", str(Path(__file__).parents[1] / "bootstrap.sh"), "--test-argument", "has spaces"],
                env=env, capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, download_status or installer_status, result.stderr)
            self.assertEqual(list(downloads.iterdir()), [])

    def test_success_and_arguments(self):
        self.exercise()

    def test_download_failure_cleans_up(self):
        self.exercise(download_status=22)

    def test_installer_failure_cleans_up(self):
        self.exercise(installer_status=42)


if __name__ == "__main__":
    unittest.main()
