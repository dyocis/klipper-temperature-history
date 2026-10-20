#!/usr/bin/env python3
"""Build reproducible release archives from committed public files only."""
import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import io
from pathlib import Path
import re
import subprocess
import tarfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_FILES = {'server.py', 'add_mainsail_link.py', 'install.sh',
                'config.example.json', 'README.md', 'INSTALL.md', 'LICENSE',
                'CONTRIBUTING.md', 'VERSION'}


def is_public_file(name):
    return name in PUBLIC_FILES or (name.startswith('web/') and
        name.rsplit('.', 1)[-1] in {'html', 'js', 'css', 'svg', 'ico', 'png'}) or name == 'docs/images/temperature-history-dashboard.png'


def git_bytes(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def build_archives(files, version, epoch, output):
    if not re.fullmatch(r'\d+\.\d+\.\d+(?:-[a-zA-Z0-9.-]+)?', version):
        raise ValueError('Expected a semantic version such as 0.1.0')
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    prefix = f'temperature-history-{version}'
    tar_path, zip_path = output / (prefix+'.tar.gz'), output / (prefix+'.zip')
    timestamp = datetime.fromtimestamp(max(epoch, 315532800), timezone.utc).timetuple()[:6]
    with tar_path.open('wb') as raw, gzip.GzipFile(filename='', mode='wb', fileobj=raw, mtime=epoch) as compressed:
        with tarfile.open(fileobj=compressed, mode='w') as archive:
            for name, data in sorted(files.items()):
                if not is_public_file(name):
                    continue
                info = tarfile.TarInfo(prefix+'/'+name)
                info.size, info.mtime = len(data), epoch
                info.mode = 0o755 if name.endswith('.sh') else 0o644
                archive.addfile(info, io.BytesIO(data))
    with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in sorted(files.items()):
            if not is_public_file(name):
                continue
            info = zipfile.ZipInfo(prefix+'/'+name, timestamp)
            info.create_system = 3
            info.external_attr = ((0o100755 if name.endswith('.sh') else 0o100644) << 16)
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data)
    checksums = output / 'SHA256SUMS'
    with checksums.open('w', encoding='utf-8', newline='\n') as stream:
        stream.write(''.join(f'{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n'
                             for path in (tar_path, zip_path)))
    return tar_path, zip_path, checksums


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ref', default='HEAD', help='Committed revision to package')
    parser.add_argument('--output', default=str(ROOT/'dist'))
    args = parser.parse_args()
    commit = git_bytes('rev-parse', '--verify', args.ref+'^{commit}').decode().strip()
    version = git_bytes('show', commit+':VERSION').decode().strip()
    epoch = int(git_bytes('show', '-s', '--format=%ct', commit).decode().strip())
    names = git_bytes('ls-tree', '-rz', '--name-only', commit).decode().split('\0')
    files = {name: git_bytes('show', commit+':'+name) for name in names if is_public_file(name)}
    for required in PUBLIC_FILES:
        if required not in files:
            raise ValueError('Missing release file: '+required)
    for path in build_archives(files, version, epoch, args.output):
        print(path)


if __name__ == '__main__':
    main()
