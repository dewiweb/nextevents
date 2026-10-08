"""Application Flask : page de contrôle (assets/webui.*) + API.

Routes spécialisées : api_today.py (diapo du jour, /today/*) et
api_slides.py (galerie, regen/suppression, /slides/*, slide-list)."""

import io
import threading
from datetime import datetime

from flask import Flask, jsonify, request, send_file, send_from_directory

from .media import round_logo
from .paths import ASSET_DIR
from .runner import next_run, run_generation, slides, slides_portrait
from .settings import (
    DEFAULTS, SETTINGS_FILE, load_settings, resolve_out_dir, save_settings,
    state,
)
from . import slide as _slide  # tailles disponibles (SIZES)
from .api_slides import bp as _slides_bp
from .api_today import bp as _today_bp
from .webutil import events_meta

app = Flask(__name__)
app.register_blueprint(_today_bp)
app.register_blueprint(_slides_bp)


@app.get("/")
def index():
    return (ASSET_DIR / "webui.html").read_text(encoding="utf-8")


@app.get("/webui.css")
def webui_css():
    return send_from_directory(ASSET_DIR, "webui.css")


@app.get("/webui.js")
def webui_js():
    return send_from_directory(ASSET_DIR, "webui.js")


@app.get("/api/status")
def api_status():
    s = load_settings()
    has_pass = bool(s.pop("ftp_pass"))
    has_smb_pass = bool(s.pop("smb_pass"))
    has_oa_key = bool(s.pop("oa_api_key"))
    sl = slides()
    sl_p = slides_portrait()
    # nom.png → étiquette lisible pour la galerie (titre complet, accents
    # inclus — le nom de fichier est slugifié)
    meta = {}
    for i, e in enumerate(events_meta()):
        try:
            label = " — ".join(
                x for x in (e.get("specs", {}).get("Date", ""),
                            e.get("title", "")) if x)
            # nom de fichier stocké à la génération ; le recalcul
            # (slide_name, index à partir de 1 comme _render_set) ne
            # sert que de repli pour un vieux events.json
            stem = e.get("slide") or _slide.slide_name(e, i + 1)
            meta[stem + ".png"] = label
        except Exception:
            pass
    lr = state["last_run"]
    from .scrape import CATEGORIES, _series_label_for, series_tables
    # libellés canoniques des séries connues (réglage + tables par
    # défaut), dédupliqués : « grandstemoins » et « les-grands-temoins »
    # ne font qu'une entrée — le libellé du réglage l'emporte
    series_opts, canon = [], {}
    for rows in series_tables(s.get("series_map", "")):
        for k, l, _ in rows:
            if _series_label_for(k, canon):
                continue
            canon[k] = l
            series_opts.append(l)
    series_opts.sort(key=str.lower)
    return jsonify(
        running=state["running"],
        last_run=lr,
        last_run_iso=(
            datetime.fromtimestamp(lr).isoformat(timespec="seconds")
            if lr else None
        ),
        last_error=state["last_error"],
        next_run=next_run(s, lr),
        log=state["log"],
        slides=sl,
        slides_count=len(sl),
        slides_portrait=sl_p,
        slide_meta=meta,
        categories=[{"label": l, "slug": c} for l, c in CATEGORIES],
        series_options=series_opts,
        settings={**s, "has_pass": has_pass, "has_smb_pass": has_smb_pass,
                  "has_oa_key": has_oa_key},
    )


@app.post("/api/run")
def api_run():
    threading.Thread(target=run_generation, daemon=True).start()
    return jsonify(ok=True)


def _safe_local_path(v):
    """Chemin local de réglage plausible : absolu (posix, UNC ou
    lettre de lecteur Windows), sans segment « .. » — la synchro
    miroir supprime des fichiers dans ces dossiers, un chemin échappé
    serait destructeur."""
    import re
    v = (v or "").strip()
    if not v:
        return ""
    if ".." in [p for p in re.split(r"[/\\]+", v) if p]:
        return None
    if v.startswith(("/", "\\", "~")) or re.match(
            r"^[a-zA-Z]:[/\\]", v):
        return v
    return None


def _safe_remote_path(v):
    """Chemin distant (FTP/SMB) : relatif, sans segment « .. » — la
    synchro miroir navigue et supprime sous ce préfixe."""
    import re
    v = (v or "").strip().strip("/\\")
    if ".." in [p for p in re.split(r"[/\\]+", v) if p]:
        return None
    return v


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
        if k in ("out_dir", "local_dir"):
            v = _safe_local_path(body[k])
            if v is not None:
                s[k] = v
            continue
        if k in ("ftp_path", "smb_path"):
            v = _safe_remote_path(body[k])
            if v is not None:
                s[k] = v
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


@app.post("/api/series/detect")
def api_series_detect():
    """Détecte les séries éditoriales (pages série liées depuis les
    pages détail du site + keywords OpenAgenda non techniques) pour
    préremplir le réglage series_map. Peut prendre une minute —
    plusieurs pages du site et l'export OA sont parcourus."""
    from .oa import detect_series

    s = load_settings()
    try:
        found = detect_series((s.get("oa_agenda") or "").strip()
                              or "leschampslibres")
    except Exception as e:
        return jsonify(ok=False, error=str(e))
    return jsonify(ok=True,
                   series=[{"key": k, "label": l} for k, l in found])


@app.post("/api/series/logo")
def api_series_logo():
    """Upload d'un logo de série — enregistré dans <sortie>/logos/, à
    référencer dans series_map : « slug = Libellé | logos/fichier.png »."""
    from werkzeug.utils import secure_filename

    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify(ok=False, error="aucun fichier"), 400
    name = secure_filename(f.filename)
    if not name or "." not in name:
        return jsonify(ok=False, error="nom de fichier invalide"), 400
    if name.rsplit(".", 1)[1].lower() not in (
            "png", "svg", "jpg", "jpeg", "webp", "gif"):
        return jsonify(ok=False, error="format image attendu"), 400
    d = resolve_out_dir(load_settings()) / "logos"
    d.mkdir(parents=True, exist_ok=True)
    f.save(d / name)
    # vignette ronde (couleur dominante en fond) pour respecter la
    # charte du badge série — le SVG passe tel quel
    if not name.lower().endswith(".svg"):
        try:
            out = round_logo(d / name)
            if out != d / name:
                (d / name).unlink()
            name = out.name
        except Exception:
            pass   # image illisible : l'original reste utilisable
    return jsonify(ok=True, name=f"logos/{name}")


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


@app.get("/slideshow")
@app.get("/slideshow/portrait")
def slideshow():
    """Player plein écran des diapos HTML (OBS : Browser Source →
    /slideshow ou /slideshow/portrait)."""
    return (ASSET_DIR / "slideshow.html").read_text(encoding="utf-8")
