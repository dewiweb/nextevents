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
