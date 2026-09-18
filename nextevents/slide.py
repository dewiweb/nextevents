"""Rendu des diapos : template HTML (assets/slide_template.html) puis
capture Playwright/Chromium (repli firefox --headless)."""

import html
import io
import re
import subprocess
import tempfile
from pathlib import Path
from string import Template

from PIL import Image

from .paths import ASSET_DIR
from .scrape import CARD_COLORS, SPEC_ICONS, SPEC_ORDER

SIZES = {"hd": (1920, 1080), "uhd": (3840, 2160)}
DEFAULT_SIZE = SIZES["uhd"]

INK = "#141414"

ICONS = {
    "calendar": "M8 5.75c-.41 0-.75-.34-.75-.75V2c0-.41.34-.75.75-.75s.75.34.75.75v3c0 .41-.34.75-.75.75Zm8 0c-.41 0-.75-.34-.75-.75V2c0-.41.34-.75.75-.75s.75.34.75.75v3c0 .41-.34.75-.75.75Zm4.5 4.09h-17c-.41 0-.75-.34-.75-.75s.34-.75.75-.75h17c.41 0 .75.34.75.75s-.34.75-.75.75ZM16 22.75H8c-3.65 0-5.75-2.1-5.75-5.75V8.5c0-3.65 2.1-5.75 5.75-5.75h8c3.65 0 5.75 2.1 5.75 5.75V17c0 3.65-2.1 5.75-5.75 5.75ZM8 4.25c-2.86 0-4.25 1.39-4.25 4.25V17c0 2.86 1.39 4.25 4.25 4.25h8c2.86 0 4.25-1.39 4.25-4.25V8.5c0-2.86-1.39-4.25-4.25-4.25H8Z",
    "pin": "M12 14.17c-2.13 0-3.87-1.73-3.87-3.87S9.87 6.44 12 6.44s3.87 1.73 3.87 3.87-1.74 3.86-3.87 3.86Zm0-6.23c-1.3 0-2.37 1.06-2.37 2.37s1.06 2.37 2.37 2.37 2.37-1.06 2.37-2.37S13.3 7.94 12 7.94ZM12 22.76a5.97 5.97 0 0 1-4.13-1.67c-2.95-2.84-6.21-7.37-4.98-12.76C4 3.44 8.27 1.25 12 1.25h.01c3.73 0 8 2.19 9.11 7.09 1.22 5.39-2.04 9.91-4.99 12.75A5.97 5.97 0 0 1 12 22.76Zm0-20.01c-2.91 0-6.65 1.55-7.64 5.91C3.28 13.37 6.24 17.43 8.92 20a4.426 4.426 0 0 0 6.17 0c2.67-2.57 5.63-6.63 4.57-11.34-1-4.36-4.75-5.91-7.66-5.91Z",
    "ticket": "M17 20.75H7c-4.41 0-5.75-1.34-5.75-5.75v-.5c0-.41.34-.75.75-.75.96 0 1.75-.79 1.75-1.75S2.96 10.25 2 10.25c-.41 0-.75-.34-.75-.75V9c0-4.41 1.34-5.75 5.75-5.75h10c4.41 0 5.75 1.34 5.75 5.75v1c0 .41-.34.75-.75.75-.96 0-1.75.79-1.75 1.75s.79 1.75 1.75 1.75c.41 0 .75.34.75.75 0 4.41-1.34 5.75-5.75 5.75ZM2.75 15.16c.02 3.44.73 4.09 4.25 4.09h10c3.34 0 4.15-.59 4.24-3.59a3.25 3.25 0 0 1-2.49-3.16c0-1.53 1.07-2.82 2.5-3.16V9c0-3.57-.67-4.25-4.25-4.25H7c-3.52 0-4.23.65-4.25 4.09 1.43.34 2.5 1.63 2.5 3.16 0 1.53-1.07 2.82-2.5 3.16ZM10 7.25c-.41 0-.75-.34-.75-.75V4c0-.41.34-.75.75-.75s.75.34.75.75v2.5c0 .41-.34.75-.75.75Zm0 7.33c-.41 0-.75-.34-.75-.75v-3.67c0-.41.34-.75.75-.75s.75.34.75.75v3.67c0 .42-.34.75-.75.75Zm0 6.17c-.41 0-.75-.34-.75-.75v-2.5c0-.41.34-.75.75-.75s.75.34.75.75V20c0 .41-.34.75-.75.75Z",
    "timer": "M12 22.75c-5.24 0-9.5-4.26-9.5-9.5s4.26-9.5 9.5-9.5 9.5-4.26 9.5-9.5-9.5-9.5-9.5-9.5ZM12 5.25c-4.41 0-8 3.59-8 8s3.59 8 8 8 8-3.59 8-8-3.59-8-8-8Zm0 8.5c-.41 0-.75-.34-.75-.75V8c0-.41.34-.75.75-.75s.75.34.75.75v5c0 .41-.34.75-.75.75Zm3-11H9c-.41 0-.75-.34-.75-.75s.34-.75.75-.75h6c.41 0 .75.34.75.75s-.34.75-.75.75Z",
}

_TEMPLATE = None


def _template():
    global _TEMPLATE
    if _TEMPLATE is None:
        _TEMPLATE = Template(
            (ASSET_DIR / "slide_template.html").read_text(encoding="utf-8")
        )
    return _TEMPLATE


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
    p = ASSET_DIR / name
    return p.read_text(encoding="utf-8") if p.exists() else ""


def slide_html(ev, idx, fonts):
    bg, dark = CARD_COLORS.get(ev.get("color"), CARD_COLORS[None])
    tag = ev.get("tag") or ev["specs"].get("Catégorie") or "Événement"
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
        media = f"""<div class="photo photo--empty" style="background:{dark}">
<svg viewBox="0 0 780 970" preserveAspectRatio="xMidYMid slice">
 <g fill="none" stroke="rgba(255,255,255,.42)" stroke-width="86">
  <circle cx="-60" cy="1030" r="340"/><circle cx="-60" cy="1030" r="560"/>
  <circle cx="-60" cy="1030" r="780"/>
 </g>
 <g fill="none" stroke="{dark}" stroke-width="60" opacity=".55">
  <circle cx="850" cy="-40" r="260"/><circle cx="850" cy="-40" r="440"/>
 </g>
</svg>
<div class="ph-logo">{asset_svg('logo-full.svg')}</div></div>"""

    return _template().substitute(
        font_regular=fonts["regular"],
        font_medium=fonts["medium"],
        ink=INK,
        bg=bg,
        dark=dark,
        media=media,
        tag=html.escape(tag),
        h1_size=h1_size,
        title=html.escape(ev["title"]),
        desc=html.escape(truncate(ev.get("desc", ""))),
        specs_cls=specs_cls,
        specs_html=specs_html,
        logo_mark=asset_svg("logo-mark.svg"),
    )


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
