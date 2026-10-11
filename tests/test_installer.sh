#!/usr/bin/env bash
# Exercise installer rendering and repeat-run preservation without touching systemd.
set -euo pipefail
repo="$(cd "$(dirname "$0")/.." && pwd)"
test_dir="$(mktemp -d)"
trap 'rm -rf "$test_dir"' EXIT
mkdir -p "$test_dir/project" "$test_dir/bin"
cp "$repo/install.sh" "$repo/server.py" "$repo/config.example.json" "$test_dir/project/"
export INSTALL_TEST_DIR="$test_dir"
cat > "$test_dir/bin/id" <<'EOF'
#!/usr/bin/env bash
case "$1" in -u) echo 1000;; -un) echo printeruser;; *) exit 1;; esac
EOF
cat > "$test_dir/bin/systemctl" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
cat > "$test_dir/bin/sudo" <<'EOF'
#!/usr/bin/env bash
if [ "$1" = install ]; then
  cp "$4" "$INSTALL_TEST_DIR/rendered.service"
elif [ "$1" = systemctl ]; then
  echo "$*" >> "$INSTALL_TEST_DIR/calls"
else
  exit 1
fi
EOF
chmod +x "$test_dir/bin/"*
export PATH="$test_dir/bin:$PATH"
bash "$test_dir/project/install.sh"
grep -q 'User=printeruser' "$test_dir/rendered.service"
grep -q 'server.py --config' "$test_dir/rendered.service"
grep -q 'enable --now klipper-temperature-history.service' "$test_dir/calls"
python3 - "$test_dir/project/config.local.json" <<'PY'
import json, sys
path = sys.argv[1]
with open(path) as stream:
    config = json.load(stream)
config['port'] = 7140
with open(path, 'w') as stream:
    json.dump(config, stream)
PY
echo saved-data > "$test_dir/project/data/keep.txt"
bash "$test_dir/project/install.sh"
grep -q '7140' "$test_dir/project/config.local.json"
grep -q saved-data "$test_dir/project/data/keep.txt"
echo 'Installer smoke test passed'
