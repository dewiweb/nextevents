"""Application Flask : page de contrôle (assets/webui.html) + API."""

import io
import threading

from flask import Flask, jsonify, request, send_file, send_from_directory

from .paths import ASSET_DIR
from .runner import run_generation, slides
from .settings import (
    DEFAULTS, OUT_DIR, SETTINGS_FILE, load_settings, save_settings, state,
)
from . import slide as _slide  # tailles disponibles (SIZES)

app = Flask(__name__)


def _page():
    return (ASSET_DIR / "webui.html").read_text(encoding="utf-8")


@app.get("/")
def index():
    return _page()


@app.get("/api/status")
def api_status():
    s = load_settings()
    has_pass = bool(s.pop("ftp_pass"))
    has_smb_pass = bool(s.pop("smb_pass"))
    return jsonify(
        running=state["running"],
        last_run=state["last_run"],
        last_error=state["last_error"],
        log=state["log"],
        slides=slides(),
        settings={**s, "has_pass": has_pass, "has_smb_pass": has_smb_pass},
    )


@app.post("/api/run")
def api_run():
    threading.Thread(target=run_generation, daemon=True).start()
    return jsonify(ok=True)


@app.post("/api/settings")
def api_settings():
    body = request.get_json(force=True, silent=True) or {}
    s = load_settings()
    for k, d in DEFAULTS.items():
        if k not in body:
            continue
        if k in ("ftp_pass", "smb_pass") and body[k] == "":
            continue  # vide = inchangé
        if k == "resolution" and body[k] not in _slide.SIZES:
            continue
        if isinstance(d, int):
            try:
                s[k] = max(0, int(body[k]))
            except (TypeError, ValueError):
                pass
        else:
            s[k] = str(body[k])
    save_settings(s)
    return jsonify(ok=True)


@app.post("/api/ftp/test")
def api_ftp_test():
    import ftplib

    s = load_settings()
    try:
        cls = ftplib.FTP_TLS if s["ftp_tls"] else ftplib.FTP
        ftp = cls()
        ftp.connect(s["ftp_host"], s["ftp_port"], timeout=15)
        ftp.login(s["ftp_user"], s["ftp_pass"])
        if s["ftp_tls"]:
            ftp.prot_p()
        for part in [p for p in s["ftp_path"].split("/") if p]:
            ftp.cwd(part)
        ftp.quit()
        return jsonify(ok=True)
    except Exception as e:
        return jsonify(ok=False, error=str(e))


@app.post("/api/smb/test")
def api_smb_test():
    s = load_settings()
    try:
        from smbclient import listdir, register_session

        register_session(
            s["smb_host"], username=s["smb_user"], password=s["smb_pass"]
        )
        path = f"\\\\{s['smb_host']}\\{s['smb_share']}"
        if s["smb_path"]:
            path += "\\" + s["smb_path"].strip("/\\")
        listdir(path)
        return jsonify(ok=True)
    except Exception as e:
        return jsonify(ok=False, error=str(e))


def _events_meta():
    """Métadonnées des événements écrites par generate() (events.json)."""
    import json
    p = OUT_DIR / "events.json"
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text("utf-8"))
    except Exception:
        return []


@app.get("/api/today/events")
def api_today_events():
    return jsonify([
        {
            "i": i, "title": e["title"], "tag": e.get("tag"),
            "date": e.get("specs", {}).get("Date", ""),
            "lieu": e.get("specs", {}).get("Lieu", ""),
        }
        for i, e in enumerate(_events_meta())
    ])


@app.get("/api/today/event/<int:i>")
def api_today_event(i):
    evs = _events_meta()
    if not 0 <= i < len(evs):
        return jsonify(ok=False, error="index invalide"), 404
    e = evs[i]
    return jsonify(
        title=e["title"], tag=e.get("tag"), color=e.get("color"),
        specs=e.get("specs", {}), desc=e.get("desc", ""),
        desc_long=e.get("desc_long", ""),
        speakers=e.get("speakers", []), moderator=e.get("moderator", ""),
        note=e.get("note", ""),
        audience=e.get("audience", ""), access=e.get("access", ""),
        access_venue=e.get("access_venue", []),
    )


@app.post("/api/today")
def api_today():
    """Génère today/index.html depuis les champs édités dans la webui,
    puis pousse vers les destinations configurées."""
    from .today import push_today, render_today_png, write_today

    body = request.get_json(force=True, silent=True) or {}
    data = {
        "title": str(body.get("title") or "").strip(),
        "tag": str(body.get("tag") or "").strip(),
        "color": body.get("color") or None,
        "bg": str(body.get("bg") or "").strip(),
        "specs": {
            "Date": str(body.get("date") or "").strip(),
            "Lieu": str(body.get("lieu") or "").strip(),
        },
        "speakers": [
            {
                "name": str(s.get("name") or "").strip(),
                "quality": str(s.get("quality") or "").strip(),
            }
            for s in body.get("speakers", [])
            if isinstance(s, dict) and s.get("name")
        ],
        "moderator": str(body.get("moderator") or "").strip(),
        "note": str(body.get("note") or "").strip(),
        "access": str(body.get("access") or "").strip(),
    }
    if not data["title"]:
        return jsonify(ok=False, errors=["titre vide"]), 400
    write_today(data)
    cfg = load_settings()
    errors = []
    try:  # PNG à la même résolution que les autres diapos
        render_today_png(_slide.SIZES.get(
            cfg.get("resolution"), _slide.DEFAULT_SIZE))
    except Exception as e:
        errors.append(f"PNG : {e}")
    errors += push_today(cfg)
    return jsonify(ok=not errors, errors=errors,
                   file="today/index.html")


@app.get("/today/")
@app.get("/today/index.html")
def today_page():
    return send_from_directory(OUT_DIR / "today", "index.html")


@app.get("/api/download")
def api_download():
    """Zippe le dossier de sortie (PNG + html/ + manifeste) à la volée."""
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(OUT_DIR.rglob("*")):
            if p.is_file() and p.name != SETTINGS_FILE.name:
                z.write(p, p.relative_to(OUT_DIR))
    buf.seek(0)
    return send_file(
        buf, as_attachment=True,
        download_name="nextevents-diapos.zip", mimetype="application/zip",
    )


@app.get("/slides/<path:name>")
def slide_file(name):
    return send_from_directory(OUT_DIR, name)
