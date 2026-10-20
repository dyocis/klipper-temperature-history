# Install Temperature History

Temperature History runs on the printer's Linux host or another always-on Linux
machine. Raspberry Pi and other ARM or x86 Linux systems use the same package.
Requires Python 3.9+, systemd, and sudo. No Python packages need to be downloaded.
Git is optional.

## Install from a release download

1. Download `temperature-history-0.1.0.tar.gz` and `SHA256SUMS` from the
   [v0.1.0 release](https://github.com/dyocis/klipper-temperature-history/releases/tag/v0.1.0).
   Place them in your home directory on the printer host. A ZIP is also available
   if you prefer extracting it with a file manager.
2. Log in as your normal printer user, not root. From the download directory:

   ```sh
   sha256sum --ignore-missing --check SHA256SUMS
   tar -xzf temperature-history-0.1.0.tar.gz
   cd temperature-history-0.1.0
   bash install.sh
   ```

   Verify that the checksum reports `OK` before installing. If using the ZIP,
   verify its checksum, extract it, then run `bash install.sh` in its folder.

3. Open `http://<printer-address>:7132/` in your browser.

The default Moonraker address is `http://127.0.0.1:7125`. For a different address,
copy `config.example.json` to `config.local.json`, edit `moonraker_url`, and then
run the installer. See [README.md](README.md#configuration) for all settings and
optional API-key authentication. Choose a permanent installation directory with
no spaces in its path; the service runs from that directory.

The installer creates its own systemd service and starts recording. It preserves
existing local settings and data and does not restart Klipper or Moonraker.
History begins when recording starts. The dashboard has no login and is intended
for a trusted local network.

Channels and their readings are deleted after six hours without a valid
temperature by default. Set `"stale_channel_hours": 0` in local configuration
before starting if you want to keep inactive channels indefinitely.

## Install from Git

```sh
git clone https://github.com/dyocis/klipper-temperature-history.git
cd klipper-temperature-history
bash install.sh
```

For updates to a Git installation, use `git pull --ff-only`, then `bash install.sh`.
Do not replace a working Git installation with a release download merely to update.

## Update a download installation

Back up the SQLite database using its backup API, or stop the service before
copying the database and any WAL files. Extract the new release separately,
review its notes, then copy its program files into your permanent installation
folder without replacing `config.local.json`, `.env`, or `data/`. Run
`bash install.sh` in that permanent folder to restart with the updated code.

## Troubleshooting

```sh
systemctl status klipper-temperature-history
journalctl -u klipper-temperature-history -n 50
```

The recorder host must be able to reach Moonraker. A recording error usually
indicates that Moonraker is unavailable, Klipper is not ready, or authentication
is required. If port 7132 is occupied, choose a different `port` in local settings
and restart the service. Refresh the browser with Ctrl+F5 after an update.

The [README](README.md) describes groups, retention, sidebar integration, backups,
and service removal.
