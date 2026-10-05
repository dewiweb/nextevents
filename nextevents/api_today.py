"""Blueprint « diapo du jour » : API /api/today/* et serving /today/*."""

from flask import Blueprint, jsonify, request, send_from_directory

from . import slide as _slide
from .settings import load_settings, resolve_out_dir
from .webutil import events_meta

bp = Blueprint("today", __name__)


def _today_data(body):
    """Champs du formulaire webui → données de la diapo du jour."""
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
    # libellé canonique + logo éventuel de la série (réglage
    # « slug = Libellé | logo.png ») — le logo remplace le rond de
    # série sur la diapo
    series = data["series"]
    if series:
        from .scrape import series_brand
        smap = (load_settings() or {}).get("series_map", "")
        label, logo = series_brand(smap, series)
        data["series"] = label or series
        if logo:
            data["series_logo"] = logo
    return data


def _today_file():
    """index.html ou qr.html (slide série) — rien d'autre."""
    return "qr.html" if request.args.get("f") == "qr" else "index.html"


@bp.get("/api/today/events")
def api_today_events():
    return jsonify([
        {
            "i": i, "title": e["title"], "tag": e.get("tag"),
            "date": e.get("specs", {}).get("Date", ""),
            "lieu": e.get("specs", {}).get("Lieu", ""),
            "series": e.get("series", ""),
        }
        for i, e in enumerate(events_meta())
    ])


@bp.get("/api/today/event/<int:i>")
def api_today_event(i):
    evs = events_meta()
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


@bp.post("/api/today")
def api_today():
    """Génère today/index.html depuis les champs édités dans la webui,
    puis pousse vers les destinations configurées."""
    from .today import push_today, render_today_png, write_today

    body = request.get_json(force=True, silent=True) or {}
    data = _today_data(body)
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


@bp.post("/api/today/preview")
def api_today_preview():
    """HTML prévisualisé de la diapo du jour — n'écrit rien, ne rend
    pas de PNG, ne pousse rien. Live-preview de la webui."""
    from .media import ensure_fonts
    from .today import today_html

    body = request.get_json(force=True, silent=True) or {}
    data = _today_data(body)
    try:
        return jsonify(ok=True, html=today_html(data, ensure_fonts()))
    except Exception as e:
        return jsonify(ok=False, errors=[str(e)])


@bp.get("/api/today/html")
def api_today_html():
    """HTML actuel de today/index.html (ou qr.html) — chargé par
    l'éditeur de la webui (mode source)."""
    p = resolve_out_dir() / "today" / _today_file()
    if not p.exists():
        return jsonify(ok=False, error="diapo pas encore générée"), 404
    return jsonify(ok=True, html=p.read_text("utf-8"))


@bp.post("/api/today/html")
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
    fname = _today_file()
    if not (d / fname).exists():
        return jsonify(
            ok=False,
            errors=["générer d'abord la diapo depuis les champs"]), 400
    (d / fname).write_text(h, encoding="utf-8")
    errors = []
    try:
        render_today_png(_slide.SIZES.get(
            cfg.get("resolution"), _slide.DEFAULT_SIZE), out)
    except Exception as e:
        errors.append(f"PNG : {e}")
    errors += push_today(cfg, out)
    return jsonify(ok=not errors, errors=errors,
                   file="today/" + fname)


@bp.get("/today/")
@bp.get("/today/index.html")
def today_page():
    return send_from_directory(resolve_out_dir() / "today", "index.html")


@bp.get("/today/<path:f>")
def today_file(f):
    """qr.html (slide série) — l'aperçu de l'éditeur y accède."""
    if f not in ("index.html", "qr.html"):
        return "introuvable", 404
    return send_from_directory(resolve_out_dir() / "today", f)
