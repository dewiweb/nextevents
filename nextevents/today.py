"""Diapo du jour : slide fixe sans visuel pour la diffusion pendant une
rencontre à l'auditorium (titre + intervenants + animateur). Générée à la
demande depuis la webui dans today/index.html, puis poussée vers le
partage SMB / FTP configuré."""

import base64
import html
import io
import re
from pathlib import Path
from string import Template

from .media import ensure_fonts
from .paths import ASSET_DIR
from .settings import OUT_DIR, atomic_write
from .scrape import BASE, CARD_COLORS

_TEMPLATE = None
_TEMPLATE_QR = None


def _template():
    global _TEMPLATE
    if _TEMPLATE is None:
        _TEMPLATE = Template(
            (ASSET_DIR / "today_template.html").read_text(encoding="utf-8")
        )
    return _TEMPLATE


def _template_qr():
    global _TEMPLATE_QR
    if _TEMPLATE_QR is None:
        _TEMPLATE_QR = Template(
            (ASSET_DIR / "today_qr_template.html").read_text("utf-8")
        )
    return _TEMPLATE_QR


def today_html(data, fonts):
    """data : {title, tag, color, bg, speakers[{name, quality}],
    moderator, series}. Renvoie le HTML autonome (fontes embarquées),
    version sombre de la charte : fond sombre, texte clair, pastel en
    accent. Si `series` est renseigné (ex. « Les grands témoins »), le
    modèle com de la série est transposé en sombre : rond marine,
    titre majuscule, composition à gauche."""
    accent = CARD_COLORS.get(data.get("color"), CARD_COLORS[None])[0]
    series = (data.get("series") or "").strip()
    # série (ex. Les grands témoins) : modèle com transposé en sombre —
    # fond bleu nuit, rond marine, titre clair majuscule
    bg = data.get("bg") or ("#16203f" if series else "#141414")
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", bg):
        bg = "#16203f" if series else "#141414"
    speakers_html = "".join(
        f'<div class="speaker"><span class="name">{html.escape(s["name"])}</span>'
        + (f'<span class="qual">{html.escape(s["quality"])}</span>'
           if s.get("quality") else "")
        + "</div>"
        for s in data.get("speakers", [])
        if s.get("name")
    )
    moderator = (data.get("moderator") or "").strip()
    # accord avec le nom de la catégorie : rencontre/projection animée,
    # concert/spectacle/temps fort animé
    fem = (data.get("tag") or "").lower() in (
        "rencontre", "projection", "conférence", "lecture", "visite")
    footer_bits = []
    if moderator:
        footer_bits.append(
            f'<div class="mod-line">{"Animée" if fem else "Animé"} par '
            f"<b>{html.escape(moderator)}</b></div>")
    # lignes libres (partenaires, séance de dédicace…) — aucun espace
    # occupé si le champ est vide
    for ln in (data.get("note") or "").splitlines():
        ln = ln.strip()
        if ln:
            footer_bits.append(
                f'<div class="note-line">{html.escape(ln)}</div>')
    # mentions d'accessibilité (LSF, audiodescription…) — idem : aucun
    # espace occupé si le champ est vide
    for ln in (data.get("access") or "").splitlines():
        ln = ln.strip()
        if ln:
            footer_bits.append(
                f'<div class="access-line">{html.escape(ln)}</div>')
    footer_html = (
        f'<div class="mod">{"".join(footer_bits)}</div>'
        if footer_bits else ""
    )
    logo = ASSET_DIR / "logo-mark.svg"
    logo_full = ASSET_DIR / "logo-full.svg"
    series_logo_uri = None
    if series and data.get("series_logo"):
        series_logo_uri = _img_uri(data["series_logo"])
    if series_logo_uri:
        # identité propre de la série : le logo remplace le rond GT
        badge_html = (f'<div class="gt-badge gt-badge--img">'
                      f'<img src="{series_logo_uri}"></div>')
    elif series:
        badge_html = (
            f'<div class="gt-badge"><span class="gt-name">'
            f'{html.escape(series)}</span><span class="gt-logo">'
            f'{logo_full.read_text("utf-8") if logo_full.exists() else ""}'
            "</span></div>"
        )
    else:
        badge_html = (
            f'<span class="tag">'
            f'{html.escape(data.get("tag") or "Événement")}</span>'
        )
    title = data.get("title", "")
    # espace insécable avant la ponctuation double : évite un « ? »
    # orphelin en fin de ligne et respecte la typographie française
    title_esc = re.sub(r"\s+([?!:;»])", "&nbsp;\\1", html.escape(title))
    # ligne(s) libres sous le titre — réalisateur, année, production…
    # pour les projections ; vide = rien d'affiché
    sub_html = "".join(
        f'<div class="subtitle">{html.escape(ln)}</div>'
        for ln in (data.get("subtitle") or "").splitlines()
        if ln.strip())
    n = len(title)
    return _template().substitute(
        font_regular=fonts["regular"],
        font_medium=fonts["medium"],
        accent=accent,
        bg=bg,
        light="#efeae6",
        muted="#8f8c8a",
        faint="#bfbbb8",
        variant=" gt" if series else "",
        badge_html=badge_html,
        h1_size=80 if n < 42 else 64 if n < 80 else 52,
        # nom de série : taille dégressive pour tenir dans le rond
        # 250px (≈200px utiles) — le gabarit « Les grands témoins »
        # reste à 36px
        gt_size=(36 if len(series or "") <= 20
                 else 30 if len(series or "") <= 30
                 else 22 if len(series or "") <= 44
                 else 18 if len(series or "") <= 60 else 15),
        title=title_esc,
        subtitle_html=sub_html,
        speakers_label="Avec" if speakers_html else "",
        speakers_html=speakers_html,
        footer_html=footer_html,
        logo_mark=logo.read_text("utf-8") if logo.exists() else "",
    )


_IMG_EXTS = {".png", ".svg", ".jpg", ".jpeg", ".webp", ".gif"}


def _img_uri(path_str):
    """Fichier image → data URI. Les chemins relatifs sont résolus
    depuis le dossier de sortie configuré, son parent, puis les assets
    et la racine du projet — et le fichier doit rester dans l'une de
    ces racines : le chemin vient du réglage series_map, rien ne
    justifie de lire un fichier arbitraire (| /etc/…)."""
    from .paths import ROOT
    from .settings import resolve_out_dir
    out = resolve_out_dir()
    roots = tuple(b.resolve()
                  for b in (out, out.parent, ASSET_DIR, ROOT))
    p = Path(path_str).expanduser()
    cands = [p] if p.is_absolute() else [b / p for b in roots]
    for cand in cands:
        if cand.suffix.lower() not in _IMG_EXTS or not cand.is_file():
            continue
        cand = cand.resolve()
        if any(cand.is_relative_to(b) for b in roots):
            import mimetypes
            mime = mimetypes.guess_type(cand.name)[0] or "image/png"
            return ("data:" + mime + ";base64,"
                    + base64.b64encode(cand.read_bytes()).decode())
    return None


_SERIES_URL_CACHE = {}


def _series_url(series, series_map_text=""):
    """URL de la page série sur le site. Les identifiants sont des
    slugs de page série *ou* des keywords OA : on essaie chaque clé
    dont le libellé correspond (series_map d'abord, puis les tables
    par défaut — résolution additive comme series_brand), la première
    qui répond gagne. Retombe sur la page programme générique.
    Le résultat est mis en cache pour la durée du process : le sondage
    HTTP ne se paie qu'une fois par série."""
    from .scrape import get, series_tables
    key = (series, series_map_text or "")
    if key in _SERIES_URL_CACHE:
        return _SERIES_URL_CACHE[key]
    seen, cands = set(), []
    for rows in series_tables(series_map_text):
        for k, l, _ in rows:
            if l == series and k not in seen:
                seen.add(k)
                cands.append(k)
    url = f"{BASE}/au-programme"
    for slug in cands:
        try:
            get(f"{BASE}/au-programme/{slug}")
            url = f"{BASE}/au-programme/{slug}"
            break
        except Exception:
            continue  # keyword OA sans page série équivalente
    _SERIES_URL_CACHE[key] = url
    return url


def qr_html(series, bg, fonts, series_map=""):
    """Slide QR d'une série (modèle com : « Retrouvez … en scannant le
    QR code ») — même fond sombre que la diapo du jour."""
    url = _series_url(series, series_map)
    import qrcode
    qr = qrcode.QRCode(border=0, box_size=18)
    qr.add_data(url)
    qr.make()
    img = qr.make_image(fill_color="#16203f", back_color="#ffffff")
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "PNG")
    logo = ASSET_DIR / "logo-mark.svg"
    name = series[0].lower() + series[1:]
    i = name.find(" ") + 1
    name = name[:i] + name[i].upper() + name[i + 1:]
    return _template_qr().substitute(
        font_regular=fonts["regular"],
        font_medium=fonts["medium"],
        bg=bg,
        sentence=html.escape(
            f"Retrouvez {name} à venir "
            "et le Mag des Champs Libres en scannant le QR code"),
        qr_data="data:image/png;base64," + base64.b64encode(
            buf.getvalue()).decode(),
        arrow_data="data:image/png;base64," + base64.b64encode(
            (ASSET_DIR / "qr_arrow.png").read_bytes()).decode(),
        logo_mark=logo.read_text("utf-8") if logo.exists() else "",
    )


def write_today(data, out_dir=None):
    """Écrit today/index.html (+ today/qr.html si l'événement appartient
    à une série) et renvoie le chemin de l'index."""
    out = Path(out_dir) if out_dir else OUT_DIR
    d = out / "today"
    d.mkdir(parents=True, exist_ok=True)
    dest = d / "index.html"
    series = (data.get("series") or "").strip()
    bg = data.get("bg") or ("#16203f" if series else "#141414")
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", bg):
        # le fond vient du POST et atterrit dans le CSS des deux
        # templates — hex strict ou repli (même règle que today_html)
        bg = "#16203f" if series else "#141414"
    fonts = ensure_fonts()
    atomic_write(dest, today_html(data, fonts))
    if series:
        from .settings import load_settings
        smap = (load_settings() or {}).get("series_map", "")
        atomic_write(d / "qr.html", qr_html(series, bg, fonts, smap))
    else:
        # pas de série : pas de slide QR — on supprime les restes d'une
        # éventuelle génération précédente
        for f in ("qr.html", "qr.png"):
            p = d / f
            if p.exists():
                p.unlink()
    return dest


def render_today_png(size, out_dir=None):
    """Rend today/index.html en today/index.png (+ qr.html → qr.png si
    présent) à la résolution `size` (même réglage que les autres
    diapos). Renvoie le chemin du PNG principal."""
    from .slide import render_all

    out = Path(out_dir) if out_dir else OUT_DIR
    src = out / "today" / "index.html"
    png = out / "today" / "index.png"
    jobs = [(src, png)]
    qr_src = out / "today" / "qr.html"
    if qr_src.exists():
        jobs.append((qr_src, out / "today" / "qr.png"))
    list(render_all(jobs, size=size))
    if not png.exists():
        raise RuntimeError("rendu de la diapo du jour impossible")
    # manifeste du jeu — les synchros le poussent en dernier comme
    # marqueur d'intégrité, comme pour le diaporama principal
    d = out / "today"
    atomic_write(
        d / "manifest.txt",
        "\n".join(p.name for p in sorted(d.glob("*.png"))) + "\n")
    return png
