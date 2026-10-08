"""Réglages persistés (settings.json dans OUT_DIR) + état runtime partagé."""

import json
import os
import threading
from pathlib import Path

from .paths import OUT_DIR as DEFAULT_OUT

OUT_DIR = Path(os.environ.get("OUT_DIR", DEFAULT_OUT))
SETTINGS_FILE = Path(os.environ.get("SETTINGS_FILE", OUT_DIR / "settings.json"))

DEFAULTS = {
    "interval_hours": 0,       # legacy — converti en interval_min
    "interval_min": 0,
    "sched_times": "",         # heures fixes « HH:MM, HH:MM »
    "gen_categories": "",      # slugs à virgules (vide = 5 vitrine)
    "specs_show": "",          # clés de specs affichées (vide = toutes)
    "spec_overrides": "",      # « Clé = valeur » par ligne
    "spec_drops": "",          # items retirés des specs, à virgules
    "next_label": "",          # préfixe récurrents (vide = défaut)
    "series_map": "",          # « slug = Libellé » séries suivies
    "data_source": "site",     # site | openagenda
    "oa_api_key": "",          # clé API OpenAgenda v2
    "oa_agenda": "leschampslibres",
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
    "ftp_send_landscape": 1,
    "ftp_send_portrait": 0,
    "smb_host": "",
    "smb_share": "",
    "smb_path": "",
    "smb_user": "",
    "smb_pass": "",
    "smb_send_landscape": 1,
    "smb_send_portrait": 0,
    "local_dir": "",
    "out_dir": "",
    "ss_delay": 8,
    "ss_transition": "fade",
    "ss_tdur": 1500,
    "ss_delay_p": 8,
    "ss_transition_p": "fade",
    "ss_tdur_p": 1500,
}

# état runtime du serveur (génération en cours, journal, dernier run)
state = {"running": False, "last_run": None, "last_error": None, "log": []}
lock = threading.Lock()


def atomic_write(path, text):
    """Écriture atomique tmp + rename — un crash en cours d'écriture ne
    laisse pas un JSON tronqué que la prochaine lecture avalerait en
    silence (perte des réglages et des identifiants). Le tmp est unique
    par appel : deux écritures concurrentes ne s'entrelacent pas
    (dernière remplacée gagne — jamais de fichier à moitié écrit)."""
    import tempfile

    path = Path(path)
    fd, tmp = tempfile.mkstemp(
        dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def load_settings():
    try:
        s = json.loads(SETTINGS_FILE.read_text())
    except FileNotFoundError:
        s = {}
    except Exception as e:
        print(f"  ! settings.json illisible ({e}) — réglages par défaut")
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
    # migration : l'ancien réglage en heures alimente interval_min
    # uniquement si la clé est absente du fichier (sinon un
    # interval_min à 0 saisi par l'utilisateur serait réécrit)
    if "interval_min" not in s and out["interval_hours"]:
        out["interval_min"] = out["interval_hours"] * 60
    return out


def resolve_out_dir(cfg=None):
    """Dossier de sortie effectif : réglage `out_dir` (disque local,
    lecteur mappé, UNC) s'il est rempli, sinon OUT_DIR env/défaut."""
    if cfg is None:
        cfg = load_settings()
    d = (cfg.get("out_dir") or "").strip()
    return Path(d) if d else OUT_DIR


def save_settings(s):
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(s)
    if state["last_run"]:
        payload["last_run"] = state["last_run"]
    atomic_write(SETTINGS_FILE, json.dumps(payload, indent=2))


DEFAULT_NEXT_LABEL = "Prochaine séance : "


def parse_kv(text):
    """« Clé = valeur » par ligne → dict (réglage spec_overrides).
    Lignes vides/# ignorées."""
    out = {}
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip()
        if k:
            out[k] = v
    return out
