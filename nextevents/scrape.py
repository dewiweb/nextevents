"""Scraping de leschampslibres.fr : listes catégories et pages de détail."""

import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE = "https://www.leschampslibres.fr"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 nextevents/1.0"

# (libellé de secours, slug de la page catégorie)
CATEGORIES = [
    ("Rencontre", "rencontres-aux-champs-libres"),
    ("Concert", "concerts-aux-champs-libres"),
    ("Projection", "projections-aux-champs-libres"),
]

# Couleurs de card du site : nom du modifieur CSS -> (fond, variante foncée).
# Reflète les classes .v-event--{couleur} / .v-banner--{couleur} du site
# (cf. app-shop-entry.*.css : --color-pale-*). None = fond neutre par défaut.
CARD_COLORS = {
    None:      ("#efeae6", "#bfbbb8"),  # pale-grey / grey-600 (défaut)
    "yellow":  ("#f6e3bb", "#d5bb85"),  # pale-yellow / pale-yellow-600
    "beige":   ("#f6e3bb", "#d5bb85"),  # pale-beige (= pale-yellow)
    "green":   ("#c6d2c9", "#9daa9f"),  # pale-green / pale-green-600
    "red":     ("#e3c2b7", "#c99483"),  # pale-red / pale-red-600
    "blue":    ("#e2dff0", "#beb7e1"),  # pale-blue / pale-blue-600
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


def _color_from_classes(classes, prefix):
    """Extrait 'yellow' de classes comme 'v-event--yellow'."""
    for c in classes or []:
        if c.startswith(prefix + "--"):
            name = c.split("--", 1)[1]
            if name in CARD_COLORS:
                return name
    return None


def parse_card(card):
    """Extrait les infos d'une carte .v-event de la liste."""
    link = card.select_one("a.v-event__link")
    if not link:
        return None
    img = card.select_one("img.v-event__picture")
    tag = card.select_one(".c-tag__label")
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
        "tag": " ".join(tag.get_text().split()) if tag else None,
        "color": _color_from_classes(card.get("class"), "v-event"),
        "specs": specs,
    }


def event_dt(ev):
    """Clé de tri chronologique à partir du spec Date 'JJ/MM/AA à HHhMM'."""
    d = ev["specs"].get("Date", "")
    m = re.search(r"(\d{2})/(\d{2})/(\d{2})\D*(\d{1,2})h(\d{2})?", d)
    if m:
        return (2000 + int(m.group(3)), int(m.group(2)), int(m.group(1)),
                int(m.group(4)), int(m.group(5) or 0))
    return (9999, 12, 31, 23, 59)


def list_events(max_pages=99):
    """Itère les pages de chaque catégorie et retourne les événements
    dédupliqués, triés chronologiquement."""
    events, seen = [], set()
    for cat_label, slug in CATEGORIES:
        list_url = f"{BASE}/au-programme/categorie/{slug}"
        page = 1
        while page <= max_pages:
            url = list_url if page == 1 else f"{list_url}?page={page}"
            soup = BeautifulSoup(get(url).text, "lxml")
            cards = soup.select("div.v-event")
            if not cards:
                break
            new = 0
            for card in cards:
                ev = parse_card(card)
                if ev and ev["url"] not in seen:
                    seen.add(ev["url"])
                    if not ev.get("tag"):
                        ev["tag"] = cat_label
                    events.append(ev)
                    new += 1
            if new == 0:
                break
            print(f"  {cat_label} p{page} : {new} événements")
            page += 1
    events.sort(key=event_dt)
    return events


def parse_detail(ev):
    """Complète un événement avec sa page détail : description, image HD,
    crédit, durée, couleur de bannière."""
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

    # la couleur de bannière l'emporte sur celle de la card si définie
    banner = soup.select_one(".v-banner")
    color = _color_from_classes(banner.get("class") if banner else [], "v-banner")
    if color:
        ev["color"] = color

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
