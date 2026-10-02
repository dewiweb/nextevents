"""Orchestration : scraping → images → HTML → PNG → manifeste → synchros."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image

from .media import download_image, ensure_fonts
from .paths import OUT_DIR
from .scrape import (
    DEFAULT_CATEGORIES, group_sessions, list_events, mark_series,
    parse_detail, parse_series_map,
)
from .settings import parse_kv
from .slide import (
    DESIGNS, render_all, slide_html, slide_name, SIZES, DEFAULT_SIZE,
)
from .sync import sync_ftp, sync_local, sync_smb


def _render_set(events, fonts, dest, size, orientation="landscape"):
    """Génère un jeu de diapos (HTML + PNG) dans `dest` et y supprime
    les fichiers obsolètes. Retourne la liste des PNG du jeu."""
    dest.mkdir(parents=True, exist_ok=True)
    html_dir = dest / "html"
    html_dir.mkdir(exist_ok=True)

    # ne re-rendre que les diapos nouvelles ou modifiées ; supprimer
    # celles qui n'existent plus (sobriété : pas de wipe systématique)
    to_render, expected_png, expected_html = [], set(), set()
    used = set()
    for i, ev in enumerate(events, start=1):
        name = slide_name(ev, i)
        while name in used:  # collision date+titre : suffixe
            name += f"-{i}"
        used.add(name)
        expected_png.add(f"{name}.png")
        expected_html.add(f"{name}.html")
        hp, pp = html_dir / f"{name}.html", dest / f"{name}.png"
        content = slide_html(ev, i - 1, fonts, orientation)
        if (
            pp.exists()
            and hp.exists()
            and hp.read_text("utf-8") == content
            and Image.open(pp).size == size
        ):
            continue
        hp.write_text(content, encoding="utf-8")
        to_render.append((hp, pp))

    for p in dest.glob("*.png"):
        if p.name not in expected_png:
            p.unlink()
            print(f"  - {p.name} supprimée")
    for p in html_dir.glob("*.html"):
        if p.name not in expected_html:
            p.unlink()

    print(f"  rendu {orientation} — {len(to_render)} à rendre "
          f"({len(expected_png) - len(to_render)} inchangées)…")
    for pp in render_all(to_render, size):
        print(f"  ✓ {pp.name}")

    pngs = sorted(dest.glob("*.png"))

    # manifeste du jeu attendu — uploadé en dernier par les synchros
    (dest / "manifest.txt").write_text(
        "\n".join(p.name for p in pngs) + "\n", encoding="utf-8"
    )
    return pngs


def _apply_spec_prefs(events, cfg):
    """Réglages des specs affichées : specs_show (liste de clés à
    garder — vide = tout), spec_drops (items retirés des valeurs
    composées, p. ex. « Dispositifs d'écoute amplifiée ») et
    spec_overrides (« Clé = valeur » par ligne — ajout ou remplace).
    'Date' est toujours conservée : elle sert au nommage et est
    l'information centrale de la diapo."""
    cfg = cfg or {}
    shown = [t.strip() for t in
             (cfg.get("specs_show") or "").split(",") if t.strip()]
    show = set(shown) if shown else None
    drops = {t.strip() for t in
             (cfg.get("spec_drops") or "").split(",") if t.strip()}
    over = parse_kv(cfg.get("spec_overrides") or "")
    if show is None and not drops and not over:
        return
    for e in events:
        specs = e.get("specs")
        if specs is None:
            continue
        if show is not None:
            specs = {k: v for k, v in specs.items()
                     if k in show or k == "Date"}
        if drops:
            for k, v in list(specs.items()):
                if k == "Date":
                    continue
                kept = [t for t in (s.strip() for s in v.split(" · "))
                        if t and t not in drops]
                if len(kept) < len(v.split(" · ")):
                    if kept:
                        specs[k] = " · ".join(kept)
                    else:
                        del specs[k]
        specs.update(over)
        e["specs"] = specs


def generate(out_dir=None, max_events=0, pages=99, cfg=None, size=DEFAULT_SIZE):
    """Génère le diaporama complet. Retourne la liste des PNG produits.
    cfg peut contenir les réglages ftp_* et smb_* pour pousser le
    dossier vers un FTP et/ou un partage SMB après génération."""
    out = Path(out_dir) if out_dir else OUT_DIR

    print("1/5 Récupération des événements…")
    cats = DEFAULT_CATEGORIES
    if cfg and (cfg.get("gen_categories") or "").strip():
        cats = [c.strip() for c in cfg["gen_categories"].split(",")
                if c.strip()]
    events = list_events(max_pages=pages, categories=cats)
    # une carte par séance sur le site → une diapo par événement
    events = group_sessions(events, (cfg or {}).get("next_label"))
    if max_events:
        events = events[:max_events]
    print(f"  {len(events)} événements trouvés")
    if not events:
        raise RuntimeError(
            "Aucun événement trouvé — la page a peut-être changé de structure."
        )

    print("2/5 Pages de détail + images…")
    with ThreadPoolExecutor(max_workers=6) as ex:
        events = list(ex.map(lambda e: download_image(parse_detail(e)), events))
    mark_series(events, parse_series_map((cfg or {}).get("series_map"))
                  or None)
    _apply_spec_prefs(events, cfg)

    # métadonnées pour la « diapo du jour » de la webui
    import json
    out.mkdir(parents=True, exist_ok=True)
    (out / "events.json").write_text(
        json.dumps(
            [
                {
                    "title": e["title"], "url": e["url"],
                    "tag": e.get("tag"), "color": e.get("color"),
                    "specs": e["specs"],
                    "desc": e.get("desc", ""),
                    "desc_long": e.get("desc_long", ""),
                    "speakers": e.get("speakers", []),
                    "moderator": e.get("moderator", ""),
                    "note": e.get("note", ""),
                    "audience": e.get("audience", ""),
                    "access": e.get("access", ""),
                    "access_venue": e.get("access_venue", []),
                    "series": e.get("series", ""),
                }
                for e in events
            ],
            ensure_ascii=False, indent=1,
        ),
        encoding="utf-8",
    )

    print("3/5 Fontes…")
    fonts = ensure_fonts()

    print(f"4/5 Génération du dossier {out}/…")
    gen_landscape = cfg is None or cfg.get("gen_landscape", 1)
    gen_portrait = cfg and cfg.get("gen_portrait")
    pngs = []
    if gen_landscape:
        pngs = _render_set(events, fonts, out, size)
    if gen_portrait:
        # format A4 portrait (HD → 1240×1754 à 150 dpi, UHD → 2480×3508
        # à 300 dpi) dans un sous-dossier : pas poussé par les synchros,
        # destiné à la com (impression / écrans verticaux)
        scale = size[0] / DESIGNS["landscape"][0]
        psize = tuple(round(d * scale) for d in DESIGNS["portrait"])
        _render_set(events, fonts, out / "portrait", psize, "portrait")

    if cfg:
        if cfg.get("ftp_host"):
            print("6/6 Envoi FTP…")
            sync_ftp(out, cfg)
        if cfg.get("smb_host"):
            print("    Envoi SMB…")
            sync_smb(out, cfg)
        if cfg.get("local_dir"):
            print("    Copie dossier local…")
            sync_local(out, cfg)

    n = len(pngs) + len(list((out / "portrait").glob("*.png")))
    print(f"\nTerminé : {n} diapos dans {out}/")
    return pngs
