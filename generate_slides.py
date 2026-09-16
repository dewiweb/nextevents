#!/usr/bin/env python3
"""
Génère un diaporama OBS (PNG 1920x1080) des rencontres à venir
aux Champs Libres, à partir de la page :
https://www.leschampslibres.fr/au-programme/categorie/rencontres-aux-champs-libres

Sortie : dossier `diaporama/` dont les PNG et HTML sont remplacés
à chaque exécution, contenant
  - slide-XX-*.png   images 1920x1080 (source "Diaporama" d'OBS)
  - html/slide-XX-*.html  sources HTML autonomes (utilisables via source "Navigateur")

Dépendances : requests, beautifulsoup4, pillow, firefox (rendu headless).
"""

import argparse
import base64
import html
import io
import re
import shutil
import subprocess
import sys
import tempfile
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

    og = soup.select_one('meta[property="og:image"]')
    if og and og.get("content"):
        ev["image"] = og["content"]
    else:
        img = soup.select_one("img.v-banner__picture")
        ev["image"] = urljoin(BASE, img["src"]) if img else ev.get("card_img")

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


def download_image(ev):
    """Télécharge l'image et la retourne en data URI (HTML autonome)."""
    url = ev.get("image") or ev.get("card_img")
    if not url:
        ev["img_data"] = None
        return ev
    try:
        r = get(url)
        mime = r.headers.get("Content-Type", "image/jpeg").split(";")[0]
        ev["img_data"] = f"data:{mime};base64,{base64.b64encode(r.content).decode()}"
    except Exception as e:
        print(f"  ! image KO {url} : {e}")
        ev["img_data"] = None
    return ev


def icon_svg(name):
    path = ICONS.get(name, ICONS["calendar"])
    return (
        f'<svg viewBox="0 0 24 24" width="34" height="34" '
        f'aria-hidden="true"><path d="{path}" fill="currentColor"/></svg>'
    )


def truncate(text, limit=520):
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return cut.rstrip(".,;:!?") + "…"


def slide_html(ev, idx, fonts):
    bg, dark = PALETTE[idx % len(PALETTE)]
    tag = ev["specs"].get("Catégorie", "Rencontre")
    specs_html = "".join(
        f'<div class="spec">{icon_svg(SPEC_ICONS[k])}'
        f'<span>{html.escape(ev["specs"][k])}</span></div>'
        for k in SPEC_ORDER
        if k in ev["specs"]
    )
    if ev.get("img_data"):
        media = (
            f'<img class="photo" src="{ev["img_data"]}" alt="">'
            f'<div class="credit">{html.escape(ev.get("credit", ""))}</div>'
        )
    else:
        media = f'<div class="photo photo--empty" style="background:{dark}"></div>'

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
.card{{position:relative;flex:1;background:{bg};border-radius:48px;
 overflow:hidden;display:flex;flex-direction:column}}
.deco{{position:absolute;top:-260px;right:-160px;width:900px;height:900px;
 border-radius:50%;background:radial-gradient(circle at 35% 35%,
 rgba(255,255,255,.55),rgba(255,255,255,.12) 70%);z-index:0}}
.deco2{{position:absolute;bottom:-320px;left:520px;width:760px;height:760px;
 border-radius:50%;background:radial-gradient(circle at 60% 40%,
 rgba(255,255,255,.35),rgba(255,255,255,0) 70%);z-index:0}}
main{{position:relative;z-index:1;flex:1;display:flex;align-items:center;
 gap:90px;padding:60px 80px}}
.left{{flex:0 0 720px;display:flex;flex-direction:column;gap:18px}}
.photo{{width:720px;height:540px;object-fit:cover;border-radius:28px;
 box-shadow:0 30px 80px rgba(20,20,20,.18);background:{dark}}}
.photo--empty{{display:block}}
.credit{{font-size:20px;color:rgba(20,20,20,.55)}}
.right{{flex:1;display:flex;flex-direction:column;gap:30px;
 padding-bottom:20px}}
.tag{{align-self:flex-start;background:#fff;border-radius:2em;
 padding:8px 30px;font-size:26px;font-weight:500;
 box-shadow:0 8px 30px rgba(20,20,20,.10)}}
h1{{font-size:66px;font-weight:500;line-height:1.08;letter-spacing:-.01em}}
.desc{{font-size:29px;line-height:1.42;color:rgba(20,20,20,.82);
 max-width:880px}}
.specs{{margin-top:auto;display:flex;flex-wrap:wrap;gap:16px 44px}}
.spec{{display:flex;align-items:center;gap:14px;font-size:30px;
 font-weight:500}}
.spec svg{{flex:0 0 auto}}
</style></head><body>
<div class="card">
<div class="deco"></div><div class="deco2"></div>
<main>
  <div class="left">{media}</div>
  <div class="right">
    <span class="tag">{html.escape(tag)}</span>
    <h1>{html.escape(ev['title'])}</h1>
    <p class="desc">{html.escape(truncate(ev.get('desc','')))}</p>
    <div class="specs">{specs_html}</div>
  </div>
</main>
</div>
</body></html>"""


def render_png_firefox(html_path, png_path):
    """Repli : capture via firefox --screenshot (dev local sans Playwright)."""
    png_path = Path(png_path)
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp_out = Path(tmp.name)
    tmp_out.unlink()
    cmd = [
        "firefox", "--headless", "--window-size=1920,1080",
        "--screenshot", str(tmp_out), Path(html_path).as_uri(),
    ]
    for _ in range(2):
        r = subprocess.run(cmd, capture_output=True, timeout=120)
        if tmp_out.exists() and tmp_out.stat().st_size > 0:
            break
    else:
        raise RuntimeError(f"firefox screenshot KO : {r.stderr.decode()[:400]}")
    img = Image.open(tmp_out).convert("RGB")
    img = img.resize((1920, 1080)) if img.size != (1920, 1080) else img
    img.save(png_path, "PNG")
    tmp_out.unlink()


def render_all(slides):
    """Rend toutes les diapos. Playwright/Chromium si dispo (capture x2 puis
    downscale LANCZOS = texte très net), sinon repli Firefox."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        for hp, pp in slides:
            try:
                render_png_firefox(hp, pp)
                yield pp
            except Exception as e:
                print(f"  ✗ {pp.name} : {e}")
        return

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(
            viewport={"width": 1920, "height": 1080},
            device_scale_factor=2,
        )
        for hp, pp in slides:
            try:
                page.goto(Path(hp).as_uri())
                page.wait_for_function("document.fonts.status === 'loaded'")
                shot = page.screenshot()
                img = Image.open(io.BytesIO(shot)).convert("RGB")
                if img.size != (1920, 1080):
                    img = img.resize((1920, 1080), Image.LANCZOS)
                img.save(pp, "PNG")
                yield pp
            except Exception as e:
                print(f"  ✗ {pp.name} : {e}")
        browser.close()


def slugify(text, maxlen=40):
    s = re.sub(r"[^a-z0-9]+", "-", text.lower())
    s = re.sub(r"['’]", "", s).strip("-")
    return s[:maxlen].strip("-") or "event"


def generate(out_dir=None, max_events=0, pages=99, cfg=None):
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
    for p in out.glob("*.png"):
        p.unlink()
    html_dir = out / "html"
    shutil.rmtree(html_dir, ignore_errors=True)
    html_dir.mkdir()

    slides = []  # (html_path, png_path)
    for i, ev in enumerate(events, start=1):
        name = f"slide-{i:02d}-{slugify(ev['title'])}"
        hp = html_dir / f"{name}.html"
        hp.write_text(slide_html(ev, i - 1, fonts), encoding="utf-8")
        slides.append((hp, out / f"{name}.png"))

    print("5/5 Rendu PNG…")
    pngs = []
    for pp in render_all(slides):
        pngs.append(pp)
        print(f"  ✓ {pp.name}")

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
            for name in sorted(remote - set(local)):
                ftp.delete(name)
                print(f"  - distant : {name} supprimé")
            for name, p in sorted(local.items()):
                with open(p, "rb") as f:
                    ftp.storbinary(f"STOR {name}", f)
                print(f"  ↑ {name}")
            if sub:
                ftp.cwd("..")
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
    from smbclient import listdir, makedirs, open_file, register_session, remove

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
        for name in sorted(remote - set(local)):
            remove(d + "\\" + name)
            print(f"  - smb : {name} supprimé")
        for name, p in sorted(local.items()):
            with open(p, "rb") as f, open_file(d + "\\" + name, "wb") as dst:
                dst.write(f.read())
            print(f"  ↑ smb {name}")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--max", type=int, default=0, help="limiter à N événements (test)")
    ap.add_argument("--pages", type=int, default=99, help="nb max de pages à scraper")
    ap.add_argument("--out", default=None, help="dossier de sortie (défaut: diaporama/)")
    args = ap.parse_args()
    try:
        generate(out_dir=args.out, max_events=args.max, pages=args.pages)
    except RuntimeError as e:
        sys.exit(str(e))
    print("Dans OBS : ajoutez une source « Diaporama » pointant sur ce dossier.")


if __name__ == "__main__":
    main()
