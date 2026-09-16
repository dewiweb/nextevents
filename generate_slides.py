#!/usr/bin/env python3
"""
Génère un diaporama OBS (PNG 16:9, UHD 3840x2160 par défaut,
HD 1920x1080 via --size hd) des rencontres à venir
aux Champs Libres, à partir de la page :
https://www.leschampslibres.fr/au-programme/categorie/rencontres-aux-champs-libres

Sortie : dossier `diaporama/` dont les PNG et HTML sont remplacés
à chaque exécution, contenant
  - slide-*.png   images 16:9 (source "Diaporama" d'OBS)
  - html/slide-*.html  sources HTML autonomes (utilisables via source "Navigateur")

Dépendances : requests, beautifulsoup4, pillow, firefox (rendu headless).
"""

import argparse
import base64
import html
import io
import json
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from PIL import Image

BASE = "https://www.leschampslibres.fr"
LIST_URL = f"{BASE}/au-programme/categorie/rencontres-aux-champs-libres"
ROOT = Path(__file__).resolve().parent
OUT_DIR = ROOT / "diaporama"
FONT_DIR = ROOT / "assets" / "fonts"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 nextevents/1.0"

FONTS = {
    "regular": (
        "OldschoolGrotesk-Regular-subset.914288c7.woff2",
        "/build/app/shop/fonts/OldschoolGrotesk-Regular-subset.914288c7.woff2",
    ),
    "medium": (
        "OldschoolGrotesk-Medium-subset.1b1f1e8e.woff2",
        "/build/app/shop/fonts/OldschoolGrotesk-Medium-subset.1b1f1e8e.woff2",
    ),
}

# Palette pastel du site (variantes de bannière)
PALETTE = [
    ("#f6e3bb", "#d5bb85"),  # jaune
    ("#c6d2c9", "#9daa9f"),  # vert
    ("#e3c2b7", "#c99483"),  # rouge
    ("#e2dff0", "#beb7e1"),  # bleu
]
INK = "#141414"

ICONS = {
    "calendar": "M8 5.75c-.41 0-.75-.34-.75-.75V2c0-.41.34-.75.75-.75s.75.34.75.75v3c0 .41-.34.75-.75.75Zm8 0c-.41 0-.75-.34-.75-.75V2c0-.41.34-.75.75-.75s.75.34.75.75v3c0 .41-.34.75-.75.75Zm4.5 4.09h-17c-.41 0-.75-.34-.75-.75s.34-.75.75-.75h17c.41 0 .75.34.75.75s-.34.75-.75.75ZM16 22.75H8c-3.65 0-5.75-2.1-5.75-5.75V8.5c0-3.65 2.1-5.75 5.75-5.75h8c3.65 0 5.75 2.1 5.75 5.75V17c0 3.65-2.1 5.75-5.75 5.75ZM8 4.25c-2.86 0-4.25 1.39-4.25 4.25V17c0 2.86 1.39 4.25 4.25 4.25h8c2.86 0 4.25-1.39 4.25-4.25V8.5c0-2.86-1.39-4.25-4.25-4.25H8Z",
    "pin": "M12 14.17c-2.13 0-3.87-1.73-3.87-3.87S9.87 6.44 12 6.44s3.87 1.73 3.87 3.87-1.74 3.86-3.87 3.86Zm0-6.23c-1.3 0-2.37 1.06-2.37 2.37s1.06 2.37 2.37 2.37 2.37-1.06 2.37-2.37S13.3 7.94 12 7.94ZM12 22.76a5.97 5.97 0 0 1-4.13-1.67c-2.95-2.84-6.21-7.37-4.98-12.76C4 3.44 8.27 1.25 12 1.25h.01c3.73 0 8 2.19 9.11 7.09 1.22 5.39-2.04 9.91-4.99 12.75A5.97 5.97 0 0 1 12 22.76Zm0-20.01c-2.91 0-6.65 1.55-7.64 5.91C3.28 13.37 6.24 17.43 8.92 20a4.426 4.426 0 0 0 6.17 0c2.67-2.57 5.63-6.63 4.57-11.34-1-4.36-4.75-5.91-7.66-5.91Z",
    "ticket": "M17 20.75H7c-4.41 0-5.75-1.34-5.75-5.75v-.5c0-.41.34-.75.75-.75.96 0 1.75-.79 1.75-1.75S2.96 10.25 2 10.25c-.41 0-.75-.34-.75-.75V9c0-4.41 1.34-5.75 5.75-5.75h10c4.41 0 5.75 1.34 5.75 5.75v1c0 .41-.34.75-.75.75-.96 0-1.75.79-1.75 1.75s.79 1.75 1.75 1.75c.41 0 .75.34.75.75 0 4.41-1.34 5.75-5.75 5.75ZM2.75 15.16c.02 3.44.73 4.09 4.25 4.09h10c3.34 0 4.15-.59 4.24-3.59a3.25 3.25 0 0 1-2.49-3.16c0-1.53 1.07-2.82 2.5-3.16V9c0-3.57-.67-4.25-4.25-4.25H7c-3.52 0-4.23.65-4.25 4.09 1.43.34 2.5 1.63 2.5 3.16 0 1.53-1.07 2.82-2.5 3.16ZM10 7.25c-.41 0-.75-.34-.75-.75V4c0-.41.34-.75.75-.75s.75.34.75.75v2.5c0 .41-.34.75-.75.75Zm0 7.33c-.41 0-.75-.34-.75-.75v-3.67c0-.41.34-.75.75-.75s.75.34.75.75v3.67c0 .42-.34.75-.75.75Zm0 6.17c-.41 0-.75-.34-.75-.75v-2.5c0-.41.34-.75.75-.75s.75.34.75.75V20c0 .41-.34.75-.75.75Z",
    "timer": "M12 22.75c-5.24 0-9.5-4.26-9.5-9.5s4.26-9.5 9.5-9.5 9.5-4.26 9.5-9.5-9.5-9.5-9.5-9.5ZM12 5.25c-4.41 0-8 3.59-8 8s3.59 8 8 8 8-3.59 8-8-3.59-8-8-8Zm0 8.5c-.41 0-.75-.34-.75-.75V8c0-.41.34-.75.75-.75s.75.34.75.75v5c0 .41-.34.75-.75.75Zm3-11H9c-.41 0-.75-.34-.75-.75s.34-.75.75-.75h6c.41 0 .75.34.75.75s-.34.75-.75.75Z",
}

SPEC_ICONS = {"Date": "calendar", "Durée": "timer", "Lieu": "pin", "Tarif": "ticket"}
SPRITE_LABELS = {v: k for k, v in SPEC_ICONS.items()}
SPEC_ORDER = ["Date", "Durée", "Lieu", "Tarif"]

session = requests.Session()
session.headers["User-Agent"] = UA


def get(url):
    r = session.get(url, timeout=30)
    r.raise_for_status()
    return r


def b64_file(path):
    return base64.b64encode(Path(path).read_bytes()).decode()


def ensure_fonts():
    FONT_DIR.mkdir(parents=True, exist_ok=True)
    out = {}
    for name, (fname, url) in FONTS.items():
        p = FONT_DIR / fname
        if not p.exists():
            print(f"  fonte {fname}")
            p.write_bytes(get(BASE + url).content)
        out[name] = b64_file(p)
    return out





def parse_card(card):
    """Extrait les infos d'une carte .v-event de la liste."""
    link = card.select_one("a.v-event__link")
    if not link:
        return None
    img = card.select_one("img.v-event__picture")
    specs = {}
    for spec in card.select("p.v-event__spec"):
        icon = spec.select_one("svg[aria-label]")
        text = spec.select_one(".v-event__text")
        if icon and text:
            specs[icon["aria-label"]] = " ".join(text.get_text().split())
    return {
        "title": " ".join(link.get_text().split()),
        "url": urljoin(BASE, link["href"]),
        "card_img": urljoin(BASE, img["src"]) if img else None,
        "specs": specs,
    }


def list_events(max_pages=99):
    """Itère les pages de la catégorie et retourne les événements."""
    events, seen = [], set()
    page = 1
    while page <= max_pages:
        url = LIST_URL if page == 1 else f"{LIST_URL}?page={page}"
        soup = BeautifulSoup(get(url).text, "lxml")
        cards = soup.select("div.v-event")
        if not cards:
            break
        new = 0
        for card in cards:
            ev = parse_card(card)
            if ev and ev["url"] not in seen:
                seen.add(ev["url"])
                events.append(ev)
                new += 1
        if new == 0:
            break
        print(f"  page {page} : {new} événements")
        page += 1
    return events


def parse_detail(ev):
    """Complète un événement avec sa page détail : description, image HD, crédit, durée."""
    try:
        soup = BeautifulSoup(get(ev["url"]).text, "lxml")
    except Exception as e:
        print(f"  ! détail KO {ev['url']} : {e}")
        return ev

    # vraie image de l'événement : bannière, sinon og:image / carte
    # UNIQUEMENT si elles pointent vers /media/ (le site renvoie sinon son
    # logo générique /build/.../share.png)
    img = soup.select_one("img.v-banner__picture")
    og = soup.select_one('meta[property="og:image"]')
    if img and img.get("src"):
        ev["image"] = urljoin(BASE, img["src"])
    elif og and "/media/" in og.get("content", ""):
        ev["image"] = og["content"]
    elif ev.get("card_img") and "/media/" in ev["card_img"]:
        ev["image"] = ev["card_img"]
    else:
        ev["image"] = None

    cap = soup.select_one(".v-banner__caption")
    ev["credit"] = " ".join(cap.get_text().split()) if cap else ""

    intro = soup.select_one(".s-introduction:not(.s-introduction--long)") or soup.select_one(".s-introduction")
    if intro:
        for junk in intro.select("nav, .c-breadcrumb"):
            junk.decompose()
        ev["desc"] = " ".join(intro.get_text(" ").split())

    for spec in soup.select("p.v-banner__spec"):
        use = spec.select_one("use[href]")
        text = spec.select_one(".v-banner__text")
        if use and text:
            m = re.search(r"sprite-([a-z-]+)", use["href"])
            label = SPRITE_LABELS.get(m.group(1)) if m else None
            if label and label not in ev["specs"]:
                ev["specs"][label] = " ".join(text.get_text().split())
    return ev


CACHE_DIR = ROOT / "assets" / "cache"
OA_MAP_FILE = CACHE_DIR / "oa-map.json"
_OA_LOCK = threading.Lock()


def openagenda_image(uid):
    """Résout l'image originale d'un événement OpenAgenda à partir de son
    UID (extrait de l'URL /media/.../open-agenda/<uid>-... du site).
    Retourne l'URL img.openagenda.com en pleine résolution, ou None.
    La correspondance uid → URL est mise en cache (page ~470 Ko)."""
    try:
        m = json.loads(OA_MAP_FILE.read_text())
    except Exception:
        m = {}
    if uid in m:
        return m[uid]
    try:
        h = get(f"https://openagenda.com/events/{uid}").text
        og = next(
            (
                re.search(r'content="([^"]+)"', t).group(1)
                for t in re.findall(r"<meta[^>]+>", h)
                if "og:image" in t and 'content="' in t
            ),
            None,
        )
        if og and "img.openagenda.com" in og:
            url = re.sub(r"/u/[^/]+/", "/u/3840x0/", og)
            with _OA_LOCK:
                try:
                    m = json.loads(OA_MAP_FILE.read_text())
                except Exception:
                    m = {}
                m[uid] = url
                OA_MAP_FILE.parent.mkdir(parents=True, exist_ok=True)
                OA_MAP_FILE.write_text(json.dumps(m, indent=0))
            return url
    except Exception as e:
        print(f"  ! openagenda {uid} : {e}")
    return None


def download_image(ev):
    """Télécharge l'image et la retourne en data URI (HTML autonome).
    Cache local : les URLs d'images sont versionnées, on ne retélécharge
    jamais deux fois la même (sobriété)."""
    url = ev.get("image") or ev.get("card_img")
    uid = re.search(r"open-agenda/(\d+)", url or "")
    if uid:
        url = openagenda_image(uid.group(1)) or url
    if not url:
        ev["img_data"] = None
        return ev
    from urllib.parse import urlsplit

    cache = CACHE_DIR / Path(urlsplit(url).path).name
    try:
        if cache.exists():
            data, mime = cache.read_bytes(), "image/jpeg"
        else:
            r = get(url)
            data = r.content
            mime = r.headers.get("Content-Type", "image/jpeg").split(";")[0]
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_bytes(data)
        ev["img_data"] = f"data:{mime};base64,{base64.b64encode(data).decode()}"
    except Exception as e:
        print(f"  ! image KO {url} : {e}")
        ev["img_data"] = None
    return ev


def icon_svg(name):
    path = ICONS.get(name, ICONS["calendar"])
    return (
        f'<svg viewBox="0 0 24 24" width="42" height="42" '
        f'aria-hidden="true"><path d="{path}" fill="currentColor"/></svg>'
    )


def truncate(text, limit=400):
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return cut.rstrip(".,;:!?") + "…"


def asset_svg(name):
    p = ROOT / "assets" / name
    return p.read_text(encoding="utf-8") if p.exists() else ""


def slide_html(ev, idx, fonts):
    bg, dark = "#efeae6", "#bfbbb8"
    tag = ev["specs"].get("Catégorie", "Rencontre")
    specs_html = "".join(
        f'<div class="spec">{icon_svg(SPEC_ICONS[k])}'
        f'<span>{html.escape(ev["specs"][k])}</span></div>'
        for k in SPEC_ORDER
        if k in ev["specs"]
    )
    n_title = len(ev["title"])
    h1_size = 80 if n_title < 50 else 64 if n_title < 80 else 52
    n_specs = sum(1 for k in SPEC_ORDER if k in ev["specs"])
    specs_cls = "specs specs--tight" if n_specs >= 4 else "specs"

    credit = html.escape(ev.get("credit", ""))
    if ev.get("img_data"):
        media = (
            f'<img class="photo" src="{ev["img_data"]}" alt="">'
            + (f'<div class="credit">{credit}</div>' if credit else "")
        )
    else:
        arc_color = PALETTE[idx % len(PALETTE)][1]
        media = f"""<div class="photo photo--empty" style="background:{dark}">
<svg viewBox="0 0 780 970" preserveAspectRatio="xMidYMid slice">
 <g fill="none" stroke="rgba(255,255,255,.42)" stroke-width="86">
  <circle cx="-60" cy="1030" r="340"/><circle cx="-60" cy="1030" r="560"/>
  <circle cx="-60" cy="1030" r="780"/>
 </g>
 <g fill="none" stroke="{arc_color}" stroke-width="60" opacity=".55">
  <circle cx="850" cy="-40" r="260"/><circle cx="850" cy="-40" r="440"/>
 </g>
</svg>
<div class="ph-logo">{asset_svg('logo-full.svg')}</div></div>"""

    return f"""<!DOCTYPE html>
<html lang="fr"><head><meta charset="utf-8">
<style>
@font-face{{font-family:'Oldschool Grotesk';font-weight:400;
 src:url(data:font/woff2;base64,{fonts['regular']}) format('woff2')}}
@font-face{{font-family:'Oldschool Grotesk';font-weight:500;
 src:url(data:font/woff2;base64,{fonts['medium']}) format('woff2')}}
*{{margin:0;box-sizing:border-box}}
html,body{{width:1920px;height:1080px;overflow:hidden}}
body{{font-family:'Oldschool Grotesk',Arial,sans-serif;color:{INK};
 background:#000;display:flex;flex-direction:column}}
.card{{position:relative;flex:1;background:{bg};border-radius:72px;
 overflow:hidden;display:flex;flex-direction:column}}
main{{flex:1;display:flex;gap:70px;padding:54px 64px;min-height:0}}
.left{{flex:0 0 780px;position:relative;min-height:0}}
.photo{{position:absolute;inset:0;width:100%;height:100%;
 object-fit:cover;border-radius:48px;display:block;background:{dark}}}
.photo--empty{{display:block}}
.photo--empty>svg{{position:absolute;inset:0;width:100%;height:100%}}
.ph-logo{{position:absolute;inset:0;display:flex;align-items:center;
 justify-content:center;color:rgba(20,20,20,.75)}}
.ph-logo svg{{width:52%}}
.tag{{position:absolute;left:32px;bottom:32px;z-index:2;background:#fff;
 border-radius:2em;padding:12px 36px;font-size:31px;font-weight:500;
 box-shadow:0 10px 34px rgba(20,20,20,.14)}}
.credit{{position:absolute;right:24px;bottom:24px;z-index:2;font-size:18px;
 line-height:1.3;max-width:420px;text-align:right;color:#fff;
 background:rgba(20,20,20,.45);border-radius:1.2em;padding:5px 16px}}
.right{{flex:1;display:flex;flex-direction:column;padding:40px 0;
 min-height:0}}
h1{{font-size:80px;font-weight:500;line-height:1.06;letter-spacing:-.01em;
 display:-webkit-box;-webkit-line-clamp:4;-webkit-box-orient:vertical;
 overflow:hidden}}
.desc{{font-size:34px;line-height:1.38;color:rgba(20,20,20,.78);
 margin-top:36px;max-width:860px;display:-webkit-box;
 -webkit-line-clamp:6;-webkit-box-orient:vertical;overflow:hidden}}
.specs{{margin-top:auto;display:flex;flex-direction:column;gap:26px}}
.specs--tight{{gap:16px}}
.specs--tight .spec{{font-size:33px}}
.spec{{display:flex;align-items:center;gap:18px;font-size:38px;
 font-weight:500}}
.spec svg{{flex:0 0 auto}}
.attrib{{position:absolute;right:44px;bottom:30px;font-size:19px;
 color:rgba(20,20,20,.45);display:flex;align-items:center;gap:10px}}
.attrib svg{{height:26px;width:auto}}
</style></head><body>
<div class="card">
<main>
  <div class="left">
    {media}
    <span class="tag">{html.escape(tag)}</span>
  </div>
  <div class="right">
    <h1 style="font-size:{h1_size}px">{html.escape(ev['title'])}</h1>
    <p class="desc">{html.escape(truncate(ev.get('desc','')))}</p>
    <div class="{specs_cls}">{specs_html}</div>
  </div>
</main>
<div class="attrib">{asset_svg('logo-mark.svg')}© Les Champs Libres — leschampslibres.fr — CC BY-SA</div>
</div>
</body></html>"""


SIZES = {"hd": (1920, 1080), "uhd": (3840, 2160)}
DEFAULT_SIZE = SIZES["uhd"]


def render_png_firefox(html_path, png_path, size=DEFAULT_SIZE):
    """Repli : firefox --screenshot avec zoom + fenêtre aux dimensions
    voulues (le HTML est dessiné pour 1920x1080)."""
    w, h = size
    html_path = Path(html_path).resolve()
    png_path = Path(png_path)
    zoomed = html_path.with_suffix(".zoom.html")
    zoomed.write_text(
        html_path.read_text("utf-8").replace(
            "</head>", f"<style>html{{zoom:{w / 1920}}}</style></head>"
        ),
        encoding="utf-8",
    )
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp_out = Path(tmp.name)
    tmp_out.unlink()
    cmd = [
        "firefox", "--headless", f"--window-size={w},{h}",
        "--screenshot", str(tmp_out), zoomed.as_uri(),
    ]
    for _ in range(2):
        r = subprocess.run(cmd, capture_output=True, timeout=120)
        if tmp_out.exists() and tmp_out.stat().st_size > 0:
            break
    else:
        raise RuntimeError(f"firefox screenshot KO : {r.stderr.decode()[:400]}")
    img = Image.open(tmp_out).convert("RGB")
    img = img.resize(size) if img.size != size else img
    img.save(png_path, "PNG")
    tmp_out.unlink()
    zoomed.unlink()


def render_all(slides, size=DEFAULT_SIZE):
    """Rend les diapos via Playwright/Chromium (viewport 1920 +
    device_scale_factor = size/1920 → texte vectoriel ultra net).
    Repli Firefox si Playwright est absent."""
    w, h = size
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        for hp, pp in slides:
            try:
                render_png_firefox(hp, pp, size)
                yield pp
            except Exception as e:
                print(f"  ✗ {pp.name} : {e}")
        return

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(
            viewport={"width": 1920, "height": 1080},
            device_scale_factor=w / 1920,
        )
        for hp, pp in slides:
            try:
                page.goto(Path(hp).resolve().as_uri())
                page.wait_for_function("document.fonts.status === 'loaded'")
                shot = page.screenshot()
                img = Image.open(io.BytesIO(shot)).convert("RGB")
                if img.size != size:
                    img = img.resize(size, Image.LANCZOS)
                img.save(pp, "PNG")
                yield pp
            except Exception as e:
                print(f"  ✗ {pp.name} : {e}")
        browser.close()


def slugify(text, maxlen=40):
    s = re.sub(r"[^a-z0-9]+", "-", text.lower())
    s = re.sub(r"['’]", "", s).strip("-")
    return s[:maxlen].strip("-") or "event"


def slide_name(ev, idx):
    """Nom stable dérivé de la date + titre : l'ordre alphabétique suit la
    chronologie et un événement garde son nom entre deux générations."""
    d = ev["specs"].get("Date", "")
    m = re.search(r"(\d{2})/(\d{2})/(\d{2})", d)
    t = re.search(r"(\d{1,2})h(\d{2})?", d)
    prefix = f"20{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else f"zz{idx:02d}"
    if t:
        prefix += f"-{int(t.group(1)):02d}h{t.group(2) or '00'}"
    return f"slide-{prefix}-{slugify(ev['title'])}"


def generate(out_dir=None, max_events=0, pages=99, cfg=None, size=DEFAULT_SIZE):
    """Génère le diaporama complet. Retourne la liste des PNG produits.
    cfg peut contenir les réglages ftp_* et smb_* pour pousser le
    dossier vers un FTP et/ou un partage SMB après génération."""
    out = Path(out_dir) if out_dir else OUT_DIR

    print("1/5 Récupération des événements…")
    events = list_events(max_pages=pages)
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

    print("3/5 Fontes…")
    fonts = ensure_fonts()

    print(f"4/5 Génération du dossier {out}/…")
    out.mkdir(parents=True, exist_ok=True)
    html_dir = out / "html"
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
        hp, pp = html_dir / f"{name}.html", out / f"{name}.png"
        content = slide_html(ev, i - 1, fonts)
        if (
            pp.exists()
            and hp.exists()
            and hp.read_text("utf-8") == content
            and Image.open(pp).size == size
        ):
            continue
        hp.write_text(content, encoding="utf-8")
        to_render.append((hp, pp))

    for p in out.glob("*.png"):
        if p.name not in expected_png:
            p.unlink()
            print(f"  - {p.name} supprimée")
    for p in html_dir.glob("*.html"):
        if p.name not in expected_html:
            p.unlink()

    print(f"5/5 Rendu PNG — {len(to_render)} à rendre "
          f"({len(expected_png) - len(to_render)} inchangées)…")
    for pp in render_all(to_render, size):
        print(f"  ✓ {pp.name}")

    pngs = sorted(out.glob("*.png"))

    # manifeste du jeu attendu — uploadé en dernier par les synchros
    (out / "manifest.txt").write_text(
        "\n".join(p.name for p in pngs) + "\n", encoding="utf-8"
    )

    if cfg:
        if cfg.get("ftp_host"):
            print("6/6 Envoi FTP…")
            sync_ftp(out, cfg)
        if cfg.get("smb_host"):
            print("    Envoi SMB…")
            sync_smb(out, cfg)

    print(f"\nTerminé : {len(pngs)} diapos dans {out}/")
    return pngs


def sync_ftp(out_dir, cfg):
    """Pousse le dossier de sortie vers un FTP. Supprime à distance les
    fichiers absents en local (mêmes règles de rafraîchissement)."""
    import ftplib

    host = (cfg.get("ftp_host") or "").strip()
    if not host:
        return
    cls = ftplib.FTP_TLS if cfg.get("ftp_tls") else ftplib.FTP
    ftp = cls()
    ftp.connect(host, int(cfg.get("ftp_port") or 21), timeout=30)
    try:
        ftp.login(cfg.get("ftp_user") or "", cfg.get("ftp_pass") or "")
        if cfg.get("ftp_tls"):
            ftp.prot_p()
        for part in [p for p in (cfg.get("ftp_path") or "/").split("/") if p]:
            try:
                ftp.mkd(part)
            except ftplib.error_perm:
                pass
            ftp.cwd(part)

        out_dir = Path(out_dir)
        for pattern, sub in (("*.png", None), ("*.html", "html")):
            src = out_dir if sub is None else out_dir / sub
            local = {p.name: p for p in src.glob(pattern)}
            if sub:
                if local:
                    try:
                        ftp.mkd(sub)
                    except ftplib.error_perm:
                        pass
                    ftp.cwd(sub)
                else:
                    continue
            remote = {n for n in ftp.nlst() if n.endswith(pattern[1:])}
            remote_size = {}
            for n in remote:
                try:
                    remote_size[n] = ftp.size(n)
                except Exception:
                    pass
            for name, p in sorted(local.items()):
                if remote_size.get(name) == p.stat().st_size:
                    continue  # déjà à jour à distance
                with open(p, "rb") as f:
                    ftp.storbinary(f"STOR {name}", f)
                print(f"  ↑ {name}")
            for name in sorted(remote - set(local)):
                ftp.delete(name)
                print(f"  - distant : {name} supprimé")
            if sub:
                ftp.cwd("..")
        manifest = out_dir / "manifest.txt"
        if manifest.exists():
            with open(manifest, "rb") as f:
                ftp.storbinary("STOR manifest.txt", f)
        remote_pngs = {n for n in ftp.nlst() if n.endswith(".png")}
        expected = {p.name for p in out_dir.glob("*.png")}
        if remote_pngs == expected:
            print(f"  synchro FTP vérifiée : {len(expected)} fichiers conformes")
        else:
            print(
                "  ⚠ divergence FTP — manquants : "
                f"{sorted(expected - remote_pngs)} / en trop : {sorted(remote_pngs - expected)}"
            )
    finally:
        try:
            ftp.quit()
        except Exception:
            ftp.close()


def sync_smb(out_dir, cfg):
    """Pousse le dossier de sortie vers un partage SMB (poste OBS, NAS…)
    via smbprotocol — aucun montage système requis."""
    host = (cfg.get("smb_host") or "").strip()
    share = (cfg.get("smb_share") or "").strip()
    if not host or not share:
        return
    from smbclient import (
        listdir, makedirs, open_file, register_session, remove, stat,
    )

    register_session(
        host,
        username=cfg.get("smb_user") or "",
        password=cfg.get("smb_pass") or "",
    )
    base = f"\\\\{host}\\{share}"
    if cfg.get("smb_path"):
        base += "\\" + str(cfg["smb_path"]).strip("/\\")
    makedirs(base, exist_ok=True)

    out_dir = Path(out_dir)
    for pattern, sub in (("*.png", None), ("*.html", "html")):
        src = out_dir if sub is None else out_dir / sub
        local = {p.name: p for p in src.glob(pattern)}
        if sub and not local:
            continue
        d = base if sub is None else base + "\\" + sub
        if sub:
            makedirs(d, exist_ok=True)
        remote = {n for n in listdir(d) if n.endswith(pattern[1:])}
        remote_size = {}
        for n in remote:
            try:
                remote_size[n] = stat(d + "\\" + n).st_size
            except Exception:
                pass
        for name, p in sorted(local.items()):
            if remote_size.get(name) == p.stat().st_size:
                continue  # déjà à jour à distance
            with open(p, "rb") as f, open_file(d + "\\" + name, "wb") as dst:
                dst.write(f.read())
            print(f"  ↑ smb {name}")
        for name in sorted(remote - set(local)):
            remove(d + "\\" + name)
            print(f"  - smb : {name} supprimé")
    manifest = out_dir / "manifest.txt"
    if manifest.exists():
        with open(manifest, "rb") as f, open_file(base + "\\manifest.txt", "wb") as dst:
            dst.write(f.read())
    remote_pngs = {n for n in listdir(base) if n.endswith(".png")}
    expected = {p.name for p in out_dir.glob("*.png")}
    if remote_pngs == expected:
        print(f"  synchro SMB vérifiée : {len(expected)} fichiers conformes")
    else:
        print(
            "  ⚠ divergence SMB — manquants : "
            f"{sorted(expected - remote_pngs)} / en trop : {sorted(remote_pngs - expected)}"
        )


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--max", type=int, default=0, help="limiter à N événements (test)")
    ap.add_argument("--pages", type=int, default=99, help="nb max de pages à scraper")
    ap.add_argument("--out", default=None, help="dossier de sortie (défaut: diaporama/)")
    ap.add_argument(
        "--size", choices=sorted(SIZES), default="uhd",
        help="résolution des diapos : uhd=3840x2160, hd=1920x1080",
    )
    args = ap.parse_args()
    try:
        generate(
            out_dir=args.out, max_events=args.max, pages=args.pages,
            size=SIZES[args.size],
        )
    except RuntimeError as e:
        sys.exit(str(e))
    print("Dans OBS : ajoutez une source « Diaporama » pointant sur ce dossier.")


if __name__ == "__main__":
    main()
