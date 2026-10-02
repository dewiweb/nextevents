"""Application Flask : page de contrôle (assets/webui.html) + API."""

import io
import threading
from datetime import datetime

from flask import Flask, jsonify, request, send_file, send_from_directory

from .paths import ASSET_DIR
from .runner import run_generation, slides, slides_portrait
from .settings import (
    DEFAULTS, OUT_DIR, SETTINGS_FILE, load_settings, resolve_out_dir,
    save_settings, state,
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
    has_oa_key = bool(s.pop("oa_api_key"))
    sl = slides()
    sl_p = slides_portrait()
    lr = state["last_run"]
    return jsonify(
        running=state["running"],
        last_run=lr,
        last_run_iso=(
            datetime.fromtimestamp(lr).isoformat(timespec="seconds")
            if lr else None
        ),
        last_error=state["last_error"],
        log=state["log"],
        slides=sl,
        slides_count=len(sl),
        slides_portrait=sl_p,
        settings={**s, "has_pass": has_pass, "has_smb_pass": has_smb_pass,
                  "has_oa_key": has_oa_key},
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
        if k in ("ftp_pass", "smb_pass", "oa_api_key") and body[k] == "":
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
    p = resolve_out_dir() / "events.json"
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
            "series": e.get("series", ""),
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
        series=e.get("series", ""),
    )


@app.post("/api/today")
def api_today():
    """Génère today/index.html depuis les champs édités dans la webui,
    puis pousse vers les destinations configurées."""
    from .today import push_today, render_today_png, write_today

    body = request.get_json(force=True, silent=True) or {}
    data = {
        "title": str(body.get("title") or "").strip(),
        "subtitle": str(body.get("subtitle") or "").strip(),
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
        "series": str(body.get("series") or "").strip(),
    }
    if not data["title"]:
        return jsonify(ok=False, errors=["titre vide"]), 400
    cfg = load_settings()
    out = resolve_out_dir(cfg)
    write_today(data, out)
    errors = []
    try:  # PNG à la même résolution que les autres diapos
        render_today_png(_slide.SIZES.get(
            cfg.get("resolution"), _slide.DEFAULT_SIZE), out)
    except Exception as e:
        errors.append(f"PNG : {e}")
    errors += push_today(cfg, out)
    return jsonify(ok=not errors, errors=errors,
                   file="today/index.html")


@app.get("/api/today/html")
def api_today_html():
    """HTML actuel de today/index.html — chargé par l'éditeur de la
    webui (mode source)."""
    p = resolve_out_dir() / "today" / "index.html"
    if not p.exists():
        return jsonify(ok=False, error="diapo pas encore générée"), 404
    return jsonify(ok=True, html=p.read_text("utf-8"))


@app.post("/api/today/html")
def api_today_html_save():
    """Écrit un HTML retouché dans l'éditeur WYSIWYG, re-rend le PNG
    et pousse vers les destinations configurées — mêmes effets que
    POST /api/today, sans passer par les champs du formulaire."""
    from .today import push_today, render_today_png

    body = request.get_json(force=True, silent=True) or {}
    h = body.get("html") or ""
    if "<html" not in h or "</html>" not in h:
        return jsonify(ok=False, errors=["HTML invalide"]), 400
    # les fontes base64 embarquées font ~500 ko — cap large au-delà
    if len(h) > 8 * 1024 * 1024:
        return jsonify(ok=False, errors=["HTML trop volumineux"]), 413
    cfg = load_settings()
    out = resolve_out_dir(cfg)
    d = out / "today"
    if not (d / "index.html").exists():
        return jsonify(
            ok=False,
            errors=["générer d'abord la diapo depuis les champs"]), 400
    (d / "index.html").write_text(h, encoding="utf-8")
    errors = []
    try:
        render_today_png(_slide.SIZES.get(
            cfg.get("resolution"), _slide.DEFAULT_SIZE), out)
    except Exception as e:
        errors.append(f"PNG : {e}")
    errors += push_today(cfg, out)
    return jsonify(ok=not errors, errors=errors,
                   file="today/index.html")


@app.get("/today/")
@app.get("/today/index.html")
def today_page():
    return send_from_directory(resolve_out_dir() / "today", "index.html")


@app.get("/api/download")
def api_download():
    """Zippe le dossier de sortie (PNG + html/ + manifeste) à la volée."""
    import zipfile

    buf = io.BytesIO()
    out = resolve_out_dir()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(out.rglob("*")):
            if p.is_file() and p.name != SETTINGS_FILE.name:
                z.write(p, p.relative_to(out))
    buf.seek(0)
    return send_file(
        buf, as_attachment=True,
        download_name="nextevents-diapos.zip", mimetype="application/zip",
    )


@app.get("/slides/<path:name>")
def slide_file(name):
    return send_from_directory(resolve_out_dir(), name)


def _slide_files(name):
    """Tous les fichiers d'une diapo (PNG + HTML, paysage + portrait)."""
    from pathlib import Path
    stem = Path(name).stem
    out = resolve_out_dir()
    return [out / name, out / "html" / f"{stem}.html",
            out / "portrait" / name,
            out / "portrait" / "html" / f"{stem}.html"]


def _resync():
    """Reproduit la suppression/modification sur les destinations
    actives (FTP/SMB/local) — les synchros suppriment les extras."""
    from .sync import sync_ftp, sync_local, sync_smb
    s = load_settings()
    out = resolve_out_dir(s)
    for fn in (sync_ftp, sync_smb, sync_local):
        try:
            fn(out, s)
        except Exception:
            pass


@app.delete("/api/slides/<path:name>")
def api_slide_delete(name):
    """Supprime une diapo (PNG + HTML des deux layouts) et resynchronise
    les partages pour que la diapo y disparaisse aussi."""
    from pathlib import Path
    name = Path(name).name
    if not name.endswith(".png"):
        return jsonify(error="png attendu"), 400
    removed = 0
    for p in _slide_files(name):
        if p.exists():
            p.unlink()
            removed += 1
    if not removed:
        return jsonify(error="diapo introuvable"), 404
    threading.Thread(target=_resync, daemon=True).start()
    return jsonify(ok=True, removed=removed)


@app.post("/api/slides/<path:name>/regen")
def api_slide_regen(name):
    """Re-rend le PNG d'une diapo depuis son HTML existant — paysage,
    et portrait si le HTML portrait existe (même échelle que la
    génération complète)."""
    from pathlib import Path
    name = Path(name).name
    out = resolve_out_dir()
    stem = Path(name).stem
    s = load_settings()
    size = _slide.SIZES.get(s["resolution"], _slide.DEFAULT_SIZE)
    rendered = []
    try:
        hp = out / "html" / f"{stem}.html"
        if hp.exists():
            list(_slide.render_all([(hp, out / name)], size))
            rendered.append(name)
        hpp = out / "portrait" / "html" / f"{stem}.html"
        if hpp.exists():
            scale = size[0] / 1920
            psize = tuple(round(d * scale)
                          for d in _slide.DESIGNS["portrait"])
            list(_slide.render_all(
                [(hpp, out / "portrait" / name)], psize))
            rendered.append("portrait/" + name)
    except Exception as e:
        return jsonify(error=str(e)), 500
    if not rendered:
        return jsonify(error="html introuvable"), 404
    threading.Thread(target=_resync, daemon=True).start()
    return jsonify(ok=True, rendered=rendered)


@app.get("/api/slide-list")
def api_slide_list():
    """Liste des diapos HTML + réglages de lecture, pour le player
    /slideshow (pollé : la liste se met à jour toute seule après une
    régénération)."""
    layout = request.args.get("layout")
    sfx = "_p" if layout == "portrait" else ""
    d = resolve_out_dir()
    d = (d / "portrait" if layout == "portrait" else d) / "html"
    names = sorted(p.name for p in d.glob("*.html")) if d.exists() else []
    s = load_settings()
    return jsonify(
        slides=names,
        delay=s.get(f"ss_delay{sfx}") or 8,
        transition=s.get(f"ss_transition{sfx}") or "fade",
        tdur=s.get(f"ss_tdur{sfx}") or 1500,
    )


@app.get("/slideshow")
@app.get("/slideshow/portrait")
def slideshow():
    """Player plein écran des diapos HTML (OBS : Browser Source →
    /slideshow ou /slideshow/portrait)."""
    return (ASSET_DIR / "slideshow.html").read_text(encoding="utf-8")
