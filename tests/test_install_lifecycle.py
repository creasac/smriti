import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

SOURCE = Path(__file__).parents[1]
PATH_LINE = 'export PATH="$HOME/.local/bin:$PATH"'


@unittest.skipUnless(all(shutil.which(c) for c in ('python3', 'ffmpeg', 'ffplay', 'pactl')), 'requires desktop system dependencies')
class InstallLifecycleTests(unittest.TestCase):
    def exercise(self, existing_path=False):
        if subprocess.run(['python3', '-c', 'import tkinter'], capture_output=True).returncode:
            self.skipTest('requires Python tkinter')
        with tempfile.TemporaryDirectory(prefix='smriti home ') as directory:
            user_dir = Path(directory)
            temporary = user_dir / 'tmp'
            temporary.mkdir()
            bashrc = user_dir / '.bashrc'
            original = '# user settings\n' + (PATH_LINE + '\n' if existing_path else '')
            bashrc.write_text(original)
            env = dict(os.environ, HOME=str(user_dir), TMPDIR=str(temporary),
                       XDG_CONFIG_HOME=str(user_dir / '.config'), XDG_DATA_HOME=str(user_dir / '.local/share'))
            for _ in range(2):
                subprocess.run(['bash', str(SOURCE / 'install.sh')], env=env, check=True, capture_output=True)
            app = user_dir / '.local/share/smriti'
            self.assertEqual((app / '.path_modified').exists(), not existing_path)
            recordings = user_dir / 'Videos/smriti'
            recordings.mkdir(parents=True)
            recording = recordings / 'keep.mp4'
            recording.write_bytes(b'recording')
            desktop = user_dir / '.local/share/applications/smriti-local.desktop'
            desktop.touch()
            # Exercise scratch cleanup in the private directory without touching /tmp.
            scratch = temporary / 'smriti_transparent.svg'
            scratch.touch()
            recovery = temporary / 'smriti-recovery'
            recovery.mkdir()
            (recovery / 'segment.mp4').write_bytes(b'recovery')
            # Avoid deleting real-session scratch files when running this regression test.
            uninstall = user_dir / 'uninstall.sh'
            uninstall.write_text((SOURCE / 'uninstall.sh').read_text().replace('{Path("/tmp"), Path(tempfile.gettempdir())}', '{Path(tempfile.gettempdir())}'))
            subprocess.run(['bash', str(uninstall)], env=env, check=True, capture_output=True)
            self.assertFalse(app.exists())
            self.assertFalse((user_dir / '.local/bin/smriti').is_symlink())
            self.assertFalse(desktop.exists())
            self.assertFalse(scratch.exists())
            self.assertEqual(recording.read_bytes(), b'recording')
            self.assertEqual((recovery / 'segment.mp4').read_bytes(), b'recovery')
            self.assertFalse(list((user_dir / '.local/share/icons').rglob('smriti.png')))
            self.assertEqual(bashrc.read_text().strip(), original.strip())

    def test_reinstall_then_uninstall_removes_owned_path_block(self):
        self.exercise()

    def test_uninstall_preserves_user_path_configuration(self):
        self.exercise(existing_path=True)


if __name__ == '__main__':
    unittest.main()
