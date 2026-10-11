#!/usr/bin/env python3
"""Standalone, read-only Moonraker temperature recorder. Python standard library only."""
import argparse
from contextlib import contextmanager
import csv
import io
import json
import logging
import math
import os
from pathlib import Path
import sqlite3
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def load_config(path):
    path = Path(path).resolve()
    config = json.loads(path.read_text(encoding="utf-8-sig"))
    for name, default in (("sample_seconds", 10), ("retention_days", 30), ("port", 7132)):
        config.setdefault(name, default)
        if not number(config[name]) or config[name] <= 0:
            raise ValueError(f"{name} must be positive")
    if config["sample_seconds"] < 1 or config["retention_days"] > 365:
        raise ValueError("Minimum sample interval is 1 second; maximum retention is 365 days")
    if not isinstance(config["port"], int) or config["port"] > 65535:
        raise ValueError("Invalid port")
    config.setdefault("bind", "127.0.0.1")
    config.setdefault("exclude_sensors", [])
    config.setdefault("include_nonstandard_sensors", [])
    config.setdefault("api_key_env", "MOONRAKER_API_KEY")
    endpoint = urlparse(config["moonraker_url"])
    if endpoint.scheme not in ("http", "https") or not endpoint.hostname or endpoint.username or endpoint.password:
        raise ValueError("moonraker_url must be an HTTP(S) endpoint without embedded credentials")
    config["moonraker_url"] = config["moonraker_url"].rstrip("/")
    database = Path(config.get("database", "data/history.sqlite3"))
    config["database"] = str(database if database.is_absolute() else path.parent / database)
    return config


class Store:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.path = str(path)
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS sensors(name TEXT PRIMARY KEY, label TEXT, kind TEXT);
                CREATE TABLE IF NOT EXISTS samples(ts REAL, sensor TEXT, value REAL, target REAL,
                    PRIMARY KEY(ts, sensor));
                CREATE INDEX IF NOT EXISTS samples_sensor_time ON samples(sensor, ts);
                CREATE TABLE IF NOT EXISTS events(ts REAL, state TEXT, filename TEXT, kind TEXT NOT NULL DEFAULT 'state');
            """)
            if 'kind' not in [row[1] for row in db.execute('PRAGMA table_info(events)')]:
                db.execute("ALTER TABLE events ADD COLUMN kind TEXT NOT NULL DEFAULT 'state'")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        try:
            with db:
                yield db
        finally:
            db.close()

    def record(self, ts, readings, sensors, event=None):
        with self.connect() as db:
            db.executemany("INSERT OR REPLACE INTO sensors VALUES(?,?,?)", sensors)
            db.executemany("INSERT INTO samples VALUES(?,?,?,?)", [(ts, name, value, target) for name, value, target in readings])
            if event:
                previous = db.execute("SELECT state,filename FROM events ORDER BY ts DESC LIMIT 1").fetchone()
                if previous == event:
                    return
                state, filename = event
                kind = {"complete": "print_finished", "cancelled": "print_cancelled", "error": "print_error", "paused": "print_paused"}.get(state, "state") if previous else "status_observed"
                if state == 'printing':
                    kind = 'print_resumed' if previous and previous[0] == 'paused' and previous[1] == filename else 'print_started' if previous else 'printing_detected'
                db.execute("INSERT INTO events(ts,state,filename,kind) VALUES(?,?,?,?)", (ts, state, filename, kind))

    def prune(self, cutoff):
        with self.connect() as db:
            db.execute("DELETE FROM samples WHERE ts < ?", (cutoff,))
            db.execute("DELETE FROM events WHERE ts < ?", (cutoff,))

    def sensors(self):
        with self.connect() as db:
            return [dict(zip(("name", "label", "kind"), row)) for row in db.execute("SELECT name,label,kind FROM sensors ORDER BY name")]

    def history(self, start, end, names, buckets=1200):
        # Preserve min/max and null gaps in long-range views rather than losing peaks.
        width = max(1, (end - start) / buckets)
        result = {}
        with self.connect() as db:
            for name in names:
                rows = db.execute("""SELECT CAST((ts-?)/? AS INTEGER), MIN(ts), AVG(value),
                    MIN(value), MAX(value), AVG(target), COUNT(*), COUNT(value)
                    FROM samples WHERE sensor=? AND ts>=? AND ts<=?
                    GROUP BY 1 ORDER BY 1""", (start, width, name, start, end)).fetchall()
                result[name] = [{"ts": r[1], "value": r[2] if r[6] == r[7] else None,
                                 "min": r[3], "max": r[4], "target": r[5]} for r in rows]
            events = [dict(zip(("ts", "state", "filename", "kind"), row)) for row in db.execute(
                "SELECT ts,state,filename,kind FROM events WHERE ts>=? AND ts<=? ORDER BY ts", (start, end))]
        return {"series": result, "events": events, "bucket_seconds": width}

    def export(self, start, end, names):
        placeholders = ",".join("?" for _ in names)
        with self.connect() as db:
            yield from db.execute(f"SELECT ts,sensor,value,target FROM samples WHERE ts>=? AND ts<=? AND sensor IN ({placeholders}) ORDER BY ts,sensor", (start, end, *names))


class Recorder:
    def __init__(self, config, store):
        self.config, self.store = config, store
        self.stop = threading.Event()
        self.lock = threading.Lock()
        self.status = {"state": "starting", "last_sample": None, "readings": {}, "excluded": []}
        self.last_event = None

    def get(self, route, params=None):
        url = self.config["moonraker_url"] + route
        if params:
            url += "?" + urlencode(params)
        headers = {}
        key = os.environ.get(self.config["api_key_env"])
        if key:
            headers["X-Api-Key"] = key
        with urlopen(Request(url, headers=headers), timeout=8) as response:
            payload = json.load(response)
        if "error" in payload:
            raise RuntimeError("Moonraker returned an error")
        return payload["result"]

    def sample(self):
        discovered = self.get("/printer/objects/query", {"heaters": "", "configfile": "settings", "webhooks": "state"})["status"]
        if discovered.get("webhooks", {}).get("state", "ready") != "ready":
            raise RuntimeError("Klipper is not ready")
        heaters = discovered.get("heaters", {})
        settings = {key.lower(): value for key, value in discovered.get("configfile", {}).get("settings", {}).items()}
        names = sorted(set(heaters.get("available_sensors", []) + heaters.get("available_monitors", [])))
        excluded = []
        selected = []
        for name in names:
            sensor_settings = settings.get(name.lower(), {})
            sensor_type = str(sensor_settings.get("sensor_type", "")).upper()
            # Klipper can expose volts, watts and VOC through temperature interfaces.
            nonstandard = sensor_type in {"HOT_P", "HOT_V", "HOT_I"} or bool(sensor_settings.get("plot_voc"))
            if name in self.config["exclude_sensors"] or (nonstandard and name not in self.config["include_nonstandard_sensors"]):
                excluded.append(name)
            else:
                selected.append(name)
        status = self.get("/printer/objects/query", {**{name: "" for name in selected}, "print_stats": ""})["status"]
        ts = time.time()
        readings, metadata, current = [], [], {}
        for name in selected:
            sensor = status.get(name, {})
            value, target = sensor.get("temperature"), sensor.get("target")
            value = value if number(value) else None
            target = target if number(target) else None
            kind = "heater" if name in heaters.get("available_heaters", []) else "sensor"
            label = name.split(" ", 1)[-1].lstrip("_").replace("_", " ")
            if name.startswith("tmc"):
                label = name.replace("_", " ") + " driver"
            metadata.append((name, label, kind))
            readings.append((name, value, target))
            current[name] = {"value": value, "target": target}
        # Former sensors are explicitly marked missing after disconnect/removal.
        for sensor in self.store.sensors():
            if sensor["name"] not in selected:
                readings.append((sensor["name"], None, None))
        print_stats = status.get("print_stats", {})
        event = (str(print_stats.get("state", "unknown")), str(print_stats.get("filename", "")))
        self.store.record(ts, readings, metadata, event if event != self.last_event else None)
        self.last_event = event
        with self.lock:
            self.status = {"state": "recording", "last_sample": ts, "readings": current,
                           "excluded": excluded, "print_state": event[0], "filename": event[1]}

    def run(self):
        last_prune = 0
        while not self.stop.is_set():
            started = time.monotonic()
            try:
                self.sample()
            except Exception as exc:
                logging.warning("Sample unavailable (%s)", type(exc).__name__)
                ts = time.time()
                try:
                    self.store.record(ts, [(s["name"], None, None) for s in self.store.sensors()], [])
                except sqlite3.Error:
                    logging.exception("Unable to record continuity gap")
                with self.lock:
                    self.status = {**self.status, "state": "offline", "readings": {}, "error": "Moonraker telemetry unavailable"}
            if time.monotonic() - last_prune > 3600:
                try:
                    self.store.prune(time.time() - self.config["retention_days"] * 86400)
                    last_prune = time.monotonic()
                except sqlite3.Error:
                    logging.exception("Retention cleanup failed")
            self.stop.wait(max(0, self.config["sample_seconds"] - (time.monotonic() - started)))


def handler_for(recorder, store):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            logging.info(fmt, *args)

        def send_bytes(self, payload, content_type, status=200):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(payload)

        def json(self, payload, status=200):
            self.send_bytes(json.dumps(payload, allow_nan=False).encode(), "application/json", status)

        def do_GET(self):
            parsed = urlparse(self.path)
            try:
                if parsed.path == "/api/status":
                    with recorder.lock:
                        status = dict(recorder.status)
                    self.json({**status, "sensors": store.sensors(), "sample_seconds": recorder.config["sample_seconds"], "retention_days": recorder.config["retention_days"]})
                elif parsed.path in ("/api/history", "/api/export"):
                    query = parse_qs(parsed.query)
                    end = float(query.get("end", [time.time()])[0])
                    start = float(query.get("start", [end - 3600])[0])
                    if not math.isfinite(start) or not math.isfinite(end) or start >= end or end-start > 366*86400:
                        raise ValueError("Invalid time range")
                    known = [s["name"] for s in store.sensors()]
                    names = query.get("sensor", known)
                    if len(names) > 100 or any(name not in known for name in names):
                        raise ValueError("Unknown sensor")
                    if parsed.path == "/api/history":
                        self.json(store.history(start, end, names))
                    else:
                        self.send_response(200)
                        self.send_header("Content-Type", "text/csv; charset=utf-8")
                        self.send_header("Content-Disposition", 'attachment; filename="temperature-history.csv"')
                        self.send_header("Connection", "close")
                        self.send_header("Cache-Control", "no-store")
                        self.end_headers()
                        self.close_connection = True
                        buf = io.StringIO()
                        writer = csv.writer(buf)
                        writer.writerow(["unix_seconds", "sensor", "temperature_c", "target_c"])
                        for row in store.export(start, end, names):
                            # Prevent formula execution when a sensor name is opened in a spreadsheet.
                            row = list(row)
                            if row[1].startswith(("=", "+", "-", "@")):
                                row[1] = "'" + row[1]
                            writer.writerow(row)
                            if buf.tell() > 32768:
                                self.wfile.write(buf.getvalue().encode())
                                buf.seek(0)
                                buf.truncate(0)
                        self.wfile.write(buf.getvalue().encode())
                elif parsed.path in ("/", "/app.js", "/styles.css", "/favicon.svg"):
                    name = {"/": "index.html", "/app.js": "app.js", "/styles.css": "styles.css", "/favicon.svg": "favicon.svg"}[parsed.path]
                    mime = {"index.html": "text/html; charset=utf-8", "app.js": "text/javascript", "styles.css": "text/css", "favicon.svg": "image/svg+xml"}[name]
                    self.send_bytes((ROOT / "web" / name).read_bytes(), mime)
                else:
                    self.json({"error": "Not found"}, 404)
            except (ValueError, KeyError):
                self.json({"error": "Invalid request"}, 400)
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception:
                logging.exception("Request failed")
                self.json({"error": "Request failed"}, 500)
    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(ROOT / "config.local.json"))
    parser.add_argument("--once", action="store_true", help="Record one sample and exit")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    config = load_config(args.config)
    store = Store(config["database"])
    recorder = Recorder(config, store)
    if args.once:
        recorder.sample()
        print(json.dumps({"state": recorder.status["state"], "sensors": store.sensors(), "excluded": recorder.status["excluded"]}, indent=2))
        return
    server = ThreadingHTTPServer((config["bind"], config["port"]), handler_for(recorder, store))
    thread = threading.Thread(target=recorder.run, daemon=True)
    thread.start()
    logging.info("Dashboard listening on %s:%s", config["bind"], config["port"])
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        recorder.stop.set()
        server.server_close()
        thread.join(timeout=20)


if __name__ == "__main__":
    main()
