"""Blueprint « diapos » : galerie, régénération/suppression, slide-list."""

import json
import threading
from pathlib import Path

from flask import Blueprint, jsonify, request, send_from_directory

from . import slide as _slide
from .settings import load_settings, resolve_out_dir

bp = Blueprint("slides", __name__)


@bp.get("/slides/<path:name>")
def slide_file(name):
    return send_from_directory(resolve_out_dir(), name)


def _slide_files(name):
    """Tous les fichiers d'une diapo (PNG + HTML, paysage + portrait)."""
    stem = Path(name).stem
    out = resolve_out_dir()
    return [out / name, out / "html" / f"{stem}.html",
            out / "portrait" / name,
            out / "portrait" / "html" / f"{stem}.html"]


def _rewrite_manifests():
    """Réécrit manifest.txt (paysage + portrait) après une retouche —
    les synchros le poussent en dernier comme marqueur d'intégrité."""
    out = resolve_out_dir()
    for d in (out, out / "portrait"):
        if d.exists():
            (d / "manifest.txt").write_text(
                "\n".join(p.name for p in sorted(d.glob("*.png"))) + "\n",
                encoding="utf-8")


def _drop_from_events_json(name):
    """Retire l'événement correspondant de events.json (liste « diapo
    du jour »). La clé « slide » porte le nom de fichier calculé à la
    génération ; pour un vieux events.json on retombe sur le recalcul
    par index (à partir de 1 comme _render_set)."""
    out = resolve_out_dir()
    meta = out / "events.json"
    if not meta.exists():
        return
    try:
        events = json.loads(meta.read_text(encoding="utf-8"))
    except Exception:
        return
    kept = [e for i, e in enumerate(events)
            if (e.get("slide") or _slide.slide_name(e, i + 1))
            != Path(name).stem]
    if len(kept) < len(events):
        meta.write_text(json.dumps(kept, ensure_ascii=False, indent=2),
                        encoding="utf-8")


def _resync():
    """Reproduit la suppression/modification sur les destinations
    actives (FTP/SMB/local) — les synchros suppriment les extras."""
    _rewrite_manifests()
    from .sync import push_all
    s = load_settings()
    for e in push_all(resolve_out_dir(s), s):
        print(f"  ! resynchro : {e}")


@bp.delete("/api/slides/<path:name>")
def api_slide_delete(name):
    """Supprime une diapo (PNG + HTML des deux layouts) et resynchronise
    les partages pour que la diapo y disparaisse aussi."""
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
    _drop_from_events_json(name)
    threading.Thread(target=_resync, daemon=True).start()
    return jsonify(ok=True, removed=removed)


@bp.post("/api/slides/<path:name>/regen")
def api_slide_regen(name):
    """Re-rend le PNG d'une diapo depuis son HTML existant — paysage,
    et portrait si le HTML portrait existe (même échelle que la
    génération complète)."""
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


@bp.get("/api/slide-list")
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
