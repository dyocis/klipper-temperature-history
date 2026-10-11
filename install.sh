#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [ "$(id -u)" -eq 0 ]; then
  echo 'Run as your normal printer user; sudo will be requested for the service.' >&2
  exit 1
fi
command -v python3 >/dev/null
command -v systemctl >/dev/null
root_dir="$(pwd -P)"
if [[ "$root_dir" == *' '* || "$root_dir" == *'%'* || "$root_dir" == *'"'* || "$root_dir" == *'\\'* ]]; then
  echo 'Install into a path without spaces, percent signs, quotes, or backslashes.' >&2
  exit 1
fi
python3 -c 'import sys; assert sys.version_info >= (3,9), "Python 3.9+ required"'
if [ ! -f config.local.json ]; then
  cp config.example.json config.local.json
  chmod 600 config.local.json
fi
mkdir -p data
python3 -c 'from server import load_config; load_config("config.local.json")'
service_file="$(mktemp)"
trap 'rm -f "$service_file"' EXIT
cat > "$service_file" <<EOF
[Unit]
Description=Klipper Temperature History
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$(id -un)
WorkingDirectory=$root_dir
ExecStart=$(command -v python3) $root_dir/server.py --config $root_dir/config.local.json
EnvironmentFile=-$root_dir/.env
Restart=on-failure
RestartSec=10
NoNewPrivileges=true
ProtectSystem=full
PrivateTmp=true
UMask=0077

[Install]
WantedBy=multi-user.target
EOF
sudo install -m 644 "$service_file" /etc/systemd/system/klipper-temperature-history.service
sudo systemctl daemon-reload
sudo systemctl enable --now klipper-temperature-history.service
sudo systemctl is-active --quiet klipper-temperature-history.service
echo 'Installed. Dashboard: http://<printer-address>:7132/'
echo 'Settings: config.local.json. Restart after edits: sudo systemctl restart klipper-temperature-history'
