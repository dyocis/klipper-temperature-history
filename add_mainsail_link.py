#!/usr/bin/env python3
"""Optional installer helper: add a Mainsail sidebar link, preserving existing entries."""
import argparse
import json
import os
from pathlib import Path
import time
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import Request, urlopen
import uuid

from server import ROOT, load_config


def updated_links(entries, dashboard_url):
    if not isinstance(entries, list) or any(not isinstance(item, dict) for item in entries):
        raise ValueError('Mainsail navi.json must contain an array of entries')
    entries = [dict(item) for item in entries]
    for entry in entries:
        if entry.get('title') == 'Temperature History':
            entry['href'] = dashboard_url
            entry.setdefault('target', '_blank')
            return entries
    entries.append({'title': 'Temperature History', 'href': dashboard_url,
                    'target': '_blank', 'position': 86})
    return entries


def add_link(config, dashboard_url):
    parsed = urlparse(dashboard_url)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('Dashboard URL must be HTTP(S) without embedded credentials')
    base = config['moonraker_url']
    headers = {}
    key = os.environ.get(config['api_key_env'])
    if key:
        headers['X-Api-Key'] = key
    source = base + '/server/files/config/.theme/navi.json'
    def read_existing():
        try:
            with urlopen(Request(source, headers=headers), timeout=10) as response:
                return response.read()
        except HTTPError as exc:
            if exc.code == 404:
                return None
            raise
    original = read_existing()
    existing = json.loads(original.decode('utf-8-sig')) if original is not None else []
    entries = updated_links(existing, dashboard_url)
    if entries == existing:
        print('Temperature History sidebar link is already configured.')
        return
    backup = ROOT / 'data' / f'mainsail-navi-{time.time_ns()}.json'
    backup.parent.mkdir(parents=True, exist_ok=True)
    if original is not None:
        backup.write_bytes(original)
    if read_existing() != original:
        raise RuntimeError('Sidebar changed during setup; retry to preserve concurrent edits')
    boundary = 'temperature-history-' + uuid.uuid4().hex
    content = json.dumps(entries, indent=2).encode()
    body = (f'--{boundary}\r\nContent-Disposition: form-data; name="root"\r\n\r\nconfig\r\n'
            f'--{boundary}\r\nContent-Disposition: form-data; name="path"\r\n\r\n.theme\r\n'
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="navi.json"\r\n'
            'Content-Type: application/json\r\n\r\n').encode() + content + f'\r\n--{boundary}--\r\n'.encode()
    with urlopen(Request(base + '/server/files/upload', data=body, headers={**headers, 'Content-Type': 'multipart/form-data; boundary=' + boundary}, method='POST'), timeout=15) as response:
        payload = json.load(response)
    if 'error' in payload:
        raise RuntimeError('Moonraker rejected the sidebar upload')
    saved = read_existing()
    if saved is None or json.loads(saved.decode('utf-8-sig')) != entries:
        raise RuntimeError('Sidebar upload could not be verified')
    print('Added Temperature History to Mainsail. Refresh Mainsail to see the link.')
    if original is not None:
        print(f'Previous sidebar backed up to {backup}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', default=str(ROOT / 'config.local.json'))
    parser.add_argument('--dashboard-url', required=True, help='URL accessible from your browser, e.g. http://printer.local:7132/')
    args = parser.parse_args()
    add_link(load_config(args.config), args.dashboard_url)


if __name__ == '__main__':
    main()
