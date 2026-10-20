import hashlib
import tarfile
import tempfile
import unittest
import zipfile

from scripts.build_release import build_archives, is_public_file


class ReleaseTests(unittest.TestCase):
    def test_packages_exclude_private_files_and_match_checksums(self):
        files = {'install.sh': b'#!/bin/bash\necho install\n', 'web/index.html': b'preview',
                 'config.example.json': b'{}', 'config.local.json': b'secret',
                 '.env': b'API_KEY=secret', 'data/history.sqlite3': b'private', 'tests/local.py': b'test'}
        with tempfile.TemporaryDirectory() as folder:
            paths = build_archives(files, '0.1.0', 1700000000, folder)
            first = [path.read_bytes() for path in paths]
            with tarfile.open(paths[0]) as archive:
                self.assertEqual(len(archive.getnames()), 3)
                info = archive.getmember('temperature-history-0.1.0/install.sh')
                self.assertEqual(info.mode, 0o755)
                self.assertEqual(archive.extractfile(info).read(), files['install.sh'])
            with zipfile.ZipFile(paths[1]) as archive:
                self.assertEqual(len(archive.namelist()), 3)
                self.assertEqual(archive.read('temperature-history-0.1.0/web/index.html'), b'preview')
            for path in paths[:2]:
                self.assertIn(hashlib.sha256(path.read_bytes()).hexdigest(), paths[2].read_text())
            build_archives(files, '0.1.0', 1700000000, folder)
            self.assertEqual([path.read_bytes() for path in paths], first)

    def test_private_file_names_are_not_release_content(self):
        for name in ('data/test.png', '.env', 'config.local.json', 'server.log', 'web/secret.json'):
            self.assertFalse(is_public_file(name))
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):
                build_archives({}, '../../unsafe', 1700000000, folder)
