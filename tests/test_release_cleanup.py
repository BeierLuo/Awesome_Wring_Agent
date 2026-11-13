import importlib.util
from pathlib import Path
import plistlib
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('cleanup', Path(__file__).resolve().parents[1]/'macos/cleanup_releases.py')
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)

class CleanupTests(unittest.TestCase):
    def app(self, path, channel='release'):
        (path/'Contents/Resources/app').mkdir(parents=True)
        (path/'Contents/Info.plist').write_bytes(plistlib.dumps({'CFBundleIdentifier':'local.paper.draft','DraftBuildChannel':channel,'CFBundleShortVersionString':'0.3.1'}))
        (path/'Contents/Resources/app/ui.js').write_text('published')
        return path

    def test_unpublished_build_is_preserved(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            installed=self.app(root/'installed.app')
            candidate=self.app(root/'tmp.app', 'tmp')
            self.assertTrue(c.published_copy(candidate, installed))
            (candidate/'Contents/Resources/app/ui.js').write_text('new work')
            self.assertFalse(c.published_copy(candidate, installed))
            (candidate/'Contents/Resources/app/ui.js').write_text('published')
            (candidate/'Contents/native').write_text('new native code')
            self.assertFalse(c.published_copy(candidate, installed))

    def test_running_copy_is_preserved(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            installed=self.app(root/'installed.app')
            candidate=self.app(root/'dist/Draft.app')
            with patch.object(c.subprocess,'run'), patch.object(c.subprocess,'check_output',return_value=str(candidate)+'/Contents/MacOS/Draft'), patch.object(c,'archive') as archive:
                c.cleanup(root, installed, apply=True)
                archive.assert_not_called()
            self.assertTrue(candidate.exists())

    def test_archive_failure_preserves_original(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            app=self.app(root/'Draft.app')
            with patch.object(c.subprocess,'run',side_effect=RuntimeError('failed')):
                with self.assertRaises(RuntimeError):c.archive(app, root/'backup.zip')
            self.assertTrue(app.exists())

if __name__=='__main__':unittest.main()
