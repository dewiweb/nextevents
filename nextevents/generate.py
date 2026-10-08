"""Orchestration : scraping → images → HTML → PNG → manifeste → synchros."""

import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image

from .media import download_image, ensure_fonts
from .paths import OUT_DIR
from .scrape import (
    DEFAULT_CATEGORIES, _norm_title, group_sessions,
    list_events, mark_series, parse_detail, parse_series_map,
    site_card_index, site_detail_enrich, series_event_ids_for, SERIES,
    _unique_series_rows,
)
from .settings import atomic_write, parse_kv
from .slide import (
    DESIGNS, render_all, slide_html, slide_names, SIZES, DEFAULT_SIZE,
)
from .sync import push_all


def _png_ok(png, size):
    """Le PNG existe et a les dimensions attendues — un fichier
    corrompu (rendu interrompu, disque plein) est re-rendu, jamais
    fatale pour le reste du jeu."""
    try:
        return Image.open(png).size == size
    except Exception:
        return False


def _render_set(events, fonts, dest, size, orientation="landscape"):
    """Génère un jeu de diapos (HTML + PNG) dans `dest` et y supprime
    les fichiers obsolètes. Retourne la liste des PNG du jeu."""
    dest.mkdir(parents=True, exist_ok=True)
    html_dir = dest / "html"
    html_dir.mkdir(exist_ok=True)

    # ne re-rendre que les diapos nouvelles ou modifiées ; supprimer
    # celles qui n'existent plus (sobriété : pas de wipe systématique)
    to_render, expected_png, expected_html = [], set(), set()
    for i, (ev, name) in enumerate(zip(events, slide_names(events)),
                                   start=1):
        expected_png.add(f"{name}.png")
        expected_html.add(f"{name}.html")
        hp, pp = html_dir / f"{name}.html", dest / f"{name}.png"
        content = slide_html(ev, i - 1, fonts, orientation)
        if (
            pp.exists()
            and hp.exists()
            and hp.read_text("utf-8") == content
            and _png_ok(pp, size)
        ):
            continue
        atomic_write(hp, content)
        # le PNG existant ne correspond plus au HTML : le retirer pour
        # ne pas publier une diapo périmée si le rendu échoue
        if pp.exists():
            pp.unlink()
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
    atomic_write(
        dest / "manifest.txt",
        "\n".join(p.name for p in pngs) + "\n")
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
    series_map = parse_series_map((cfg or {}).get("series_map")) or None
    series_tbl = series_map or SERIES   # table de détection (clé→libellé)
    use_oa = cfg and cfg.get("data_source") == "openagenda"
    if use_oa:
        try:
            from .oa import filter_categories, oa_list_events
            events = filter_categories(oa_list_events(cfg), cats)
            # couleur de bannière et intervenants/animateur sont des
            # données du site absentes d'OA (html souvent vide) — on les
            # réinjecte via la page détail retrouvée par titre
            # (URLs OA ≠ URLs du site), une seule requête par événement
            idx = site_card_index(cats)
            def _enrich(e):
                u = idx.get(_norm_title(e.get("title")))
                if not u:
                    return e
                d = site_detail_enrich(u, e.get("title"), series_tbl)
                if d.get("color"):
                    e["color"] = d["color"]
                if not e.get("series") and d.get("series"):
                    e["series"] = d["series"]
                for k in ("speakers", "moderator", "note"):
                    if not e.get(k) and d.get(k):
                        e[k] = d[k]
                return e
            with ThreadPoolExecutor(max_workers=6) as ex:
                events = list(ex.map(_enrich, events))
            # séries : OA ne porte pas l'appartenance — chaque page
            # série du site liste ses événements (IDs dans les URLs) ;
            # on matche via la page site retrouvée par titre
            id_cache = {}
            for slug, label in _unique_series_rows(series_tbl):
                ids = series_event_ids_for(slug, label, id_cache)
                if not ids:
                    continue
                for e in events:
                    if e.get("series"):
                        continue
                    u = idx.get(_norm_title(e.get("title")))
                    m = re.search(r"/(\d+)/?$", u or "")
                    if m and m.group(1) in ids:
                        e["series"] = label
            events.sort(key=lambda e: (
                0 if e.get("pinned") else 1,
                e.get("_dt") or (9999, 12, 31, 23, 59)))
        except Exception as e:
            # OA injoignable/clé invalide → repli site
            print(f"  ! OpenAgenda KO ({e}) — repli scraping du site")
            use_oa = False
    if not use_oa:
        events = list_events(max_pages=pages, categories=cats)
        # une carte par séance sur le site → une diapo par événement
        events = group_sessions(events, (cfg or {}).get("next_label"))
        mark_series(events, series_map)
    if max_events:
        events = events[:max_events]
    print(f"  {len(events)} événements trouvés")
    if not events:
        raise RuntimeError(
            "Aucun événement trouvé — la page a peut-être changé de structure."
        )

    print("2/5 Pages de détail + images…")
    if use_oa:
        # OA donne déjà desc/speakers/image — on télécharge juste
        # l'image, pas de page détail à scraper
        with ThreadPoolExecutor(max_workers=6) as ex:
            events = list(ex.map(download_image, events))
    else:
        with ThreadPoolExecutor(max_workers=6) as ex:
            events = list(
                ex.map(lambda e: download_image(
                    parse_detail(e, series_tbl)), events))
    _apply_spec_prefs(events, cfg)

    # métadonnées pour la webui (« diapo du jour », étiquettes de la
    # galerie) — « slide » est le nom de fichier calculé par
    # slide_names : la webui n'a pas à le recalculer par index
    import json
    out.mkdir(parents=True, exist_ok=True)
    atomic_write(
        out / "events.json",
        json.dumps(
            [
                {
                    "title": e["title"], "url": e["url"],
                    "slide": name,
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
                for e, name in zip(events, slide_names(events))
            ],
            ensure_ascii=False, indent=1,
        ),
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
        print("6/6 Synchronisation…")
        # push_all isole les erreurs par destination : une panne FTP
        # n'empêche pas le push SMB/local vers les écrans
        for err in push_all(out, cfg):
            print(f"  ! synchro : {err}")

    n = len(pngs) + len(list((out / "portrait").glob("*.png")))
    print(f"\nTerminé : {n} diapos dans {out}/")
    return pngs
