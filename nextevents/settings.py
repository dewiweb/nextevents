"""Réglages persistés (settings.json dans OUT_DIR) + état runtime partagé."""

import json
import os
import threading
from pathlib import Path

from .paths import OUT_DIR as DEFAULT_OUT

OUT_DIR = Path(os.environ.get("OUT_DIR", DEFAULT_OUT))
SETTINGS_FILE = Path(os.environ.get("SETTINGS_FILE", OUT_DIR / "settings.json"))

DEFAULTS = {
    "interval_hours": 0,
    "max_events": 0,
    "resolution": "uhd",
    "gen_landscape": 1,
    "gen_portrait": 0,
    "ftp_host": "",
    "ftp_port": 21,
    "ftp_user": "",
    "ftp_pass": "",
    "ftp_path": "/",
    "ftp_tls": 0,
    "smb_host": "",
    "smb_share": "",
    "smb_path": "",
    "smb_user": "",
    "smb_pass": "",
}

# état runtime du serveur (génération en cours, journal, dernier run)
state = {"running": False, "last_run": None, "last_error": None, "log": []}
lock = threading.Lock()


def load_settings():
    try:
        s = json.loads(SETTINGS_FILE.read_text())
    except Exception:
        s = {}
    out = dict(DEFAULTS)
    for k, d in DEFAULTS.items():
        v = s.get(k, d)
        if isinstance(d, int):
            try:
                out[k] = int(v)
            except (TypeError, ValueError):
                pass
        else:
            out[k] = str(v)
    if s.get("last_run"):
        state["last_run"] = s["last_run"]
    return out


def save_settings(s):
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(s)
    if state["last_run"]:
        payload["last_run"] = state["last_run"]
    SETTINGS_FILE.write_text(json.dumps(payload, indent=2))
