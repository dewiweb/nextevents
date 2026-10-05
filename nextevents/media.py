"""Médias : fontes du site, images d'événements, cache, résolution OpenAgenda."""

import base64
import json
import re
import threading
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from .paths import FONT_DIR, CACHE_DIR, OA_MAP_FILE
from .scrape import BASE, get

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

_OA_LOCK = threading.Lock()


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


def round_logo(src, dst=None, size=512):
    """Recadre un logo uploadé en vignette ronde façon badge de série :
    disque à la couleur dominante de l'image, logo contenu dans le
    carré inscrit (image opaque) ou à ~78 % (logo avec transparence,
    dont le fond laisse voir le disque).

    Un logo quasi monochrome sur fond transparent recevrait un disque
    de sa propre couleur — illisible : on inverse alors vers un fond
    contrasté blanc/anthracite. Écrit un PNG ; retourne son chemin."""
    from collections import Counter
    from PIL import Image, ImageDraw

    src = Path(src)
    dst = Path(dst) if dst else src.with_suffix(".png")
    img = Image.open(src).convert("RGBA")

    # couleur dominante des pixels opaques (quantifiée par pas de 32)
    sample = img.resize((64, 64))
    px = [p[:3] for p in sample.getdata() if p[3] > 32]
    opaque = len(px) / (64 * 64)
    if px:
        buckets = Counter(tuple(c // 32 * 32 + 16 for c in p)
                          for p in px)
        bucket, freq = buckets.most_common(1)[0]
        # moyenne réelle des pixels du bucket dominant — le fond doit
        # fusionner avec le fond propre du logo (blanc pur vs ~240)
        same = [p for p in px
                if all((c // 32 * 32 + 16) == b for c, b in zip(p, bucket))]
        dom = tuple(round(sum(p[i] for p in same) / len(same))
                    for i in range(3))
        if opaque < 0.6 and freq > 0.6 * len(px):
            # logo monochrome sur fond transparent : fond contrasté
            lum = (.2126 * dom[0] + .7152 * dom[1] + .0722 * dom[2]) / 255
            dom = (255, 255, 255) if lum < .55 else (38, 37, 36)
    else:
        dom = (255, 255, 255)

    badge = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(badge).ellipse((0, 0, size - 1, size - 1),
                                  fill=dom + (255,))
    logo = img.copy()
    box = int(size * (0.70 if opaque > 0.85 else 0.78))
    logo.thumbnail((box, box), Image.LANCZOS)
    badge.alpha_composite(logo, ((size - logo.width) // 2,
                                 (size - logo.height) // 2))
    # sécurité : rien ne dépasse du disque
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size - 1, size - 1), fill=255)
    badge = Image.composite(badge, Image.new("RGBA", (size, size)), mask)
    badge.save(dst)
    return dst


def download_image(ev):
    """Télécharge l'image et la retourne en data URI (HTML autonome).
    Cache local : les URLs d'images sont versionnées, on ne retélécharge
    jamais deux fois la même (sobriété)."""
    url = ev.get("image") or ev.get("card_img")
    uid = re.search(r"open-agenda/(\d+)", url or "")
    # candidats dans l'ordre : original OpenAgenda pleine résolution,
    # puis repli sur l'image du site si son téléchargement échoue
    urls = ([openagenda_image(uid.group(1))] if uid else []) + [url]
    for u in urls:
        if not u:
            continue
        cache = CACHE_DIR / Path(urlsplit(u).path).name
        try:
            if cache.exists():
                data, mime = cache.read_bytes(), "image/jpeg"
            else:
                r = get(u)
                data = r.content
                mime = r.headers.get("Content-Type", "image/jpeg").split(";")[0]
                cache.parent.mkdir(parents=True, exist_ok=True)
                cache.write_bytes(data)
            ev["img_data"] = f"data:{mime};base64,{base64.b64encode(data).decode()}"
            return ev
        except Exception as e:
            print(f"  ! image KO {u} : {e}")
    ev["img_data"] = None
    return ev
