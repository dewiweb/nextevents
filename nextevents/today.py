"""Diapo du jour : slide fixe sans visuel pour la diffusion pendant une
rencontre à l'auditorium (titre + intervenants + animateur). Générée à la
demande depuis la webui dans today/index.html, puis poussée vers le
partage SMB / FTP configuré."""

import html
from pathlib import Path
from string import Template

from .media import ensure_fonts
from .paths import ASSET_DIR
from .settings import OUT_DIR
from .scrape import CARD_COLORS

_TEMPLATE = None


def _template():
    global _TEMPLATE
    if _TEMPLATE is None:
        _TEMPLATE = Template(
            (ASSET_DIR / "today_template.html").read_text(encoding="utf-8")
        )
    return _TEMPLATE


def today_html(data, fonts):
    """data : {title, tag, color, speakers[{name, quality}], moderator}.
    Renvoie le HTML autonome (fontes embarquées), version sombre de la
    charte : encre #141414, texte clair, pastel en accent."""
    accent = CARD_COLORS.get(data.get("color"), CARD_COLORS[None])[0]
    speakers_html = "".join(
        f'<div class="speaker"><span class="name">{html.escape(s["name"])}</span>'
        + (f'<span class="qual">{html.escape(s["quality"])}</span>'
           if s.get("quality") else "")
        + "</div>"
        for s in data.get("speakers", [])
        if s.get("name")
    )
    moderator = (data.get("moderator") or "").strip()
    moderator_html = (
        f'<div class="mod">Animé par <b>{html.escape(moderator)}</b></div>'
        if moderator else ""
    )
    logo = ASSET_DIR / "logo-mark.svg"
    n = len(data.get("title", ""))
    return _template().substitute(
        font_regular=fonts["regular"],
        font_medium=fonts["medium"],
        accent=accent,
        light="#efeae6",
        muted="#8f8c8a",
        faint="#bfbbb8",
        tag=html.escape(data.get("tag") or "Événement"),
        h1_size=80 if n < 50 else 64 if n < 80 else 52,
        title=html.escape(data.get("title", "")),
        speakers_label="Avec" if speakers_html else "",
        speakers_html=speakers_html,
        moderator_html=moderator_html,
        logo_mark=logo.read_text("utf-8") if logo.exists() else "",
    )


def write_today(data, out_dir=None):
    """Écrit today/index.html et renvoie son chemin."""
    out = Path(out_dir) if out_dir else OUT_DIR
    d = out / "today"
    d.mkdir(parents=True, exist_ok=True)
    dest = d / "index.html"
    dest.write_text(today_html(data, ensure_fonts()), encoding="utf-8")
    return dest


def push_today(cfg, out_dir=None):
    """Pousse today/index.html vers le sous-dossier today/ des
    destinations configurées (SMB/FTP). Renvoie une liste d'erreurs
    (vide = tout OK)."""
    out = Path(out_dir) if out_dir else OUT_DIR
    src = out / "today" / "index.html"
    if not src.exists():
        return ["today/index.html absent"]
    errors = []

    smb_host = (cfg.get("smb_host") or "").strip()
    smb_share = (cfg.get("smb_share") or "").strip()
    if smb_host and smb_share:
        try:
            from smbclient import makedirs, open_file, register_session
            register_session(
                smb_host,
                username=cfg.get("smb_user") or "",
                password=cfg.get("smb_pass") or "",
            )
            base = f"\\\\{smb_host}\\{smb_share}"
            if cfg.get("smb_path"):
                base += "\\" + str(cfg["smb_path"]).strip("/\\")
            d = base + "\\today"
            makedirs(d, exist_ok=True)
            with open(src, "rb") as f, \
                    open_file(d + "\\index.html", "wb") as dst:
                dst.write(f.read())
        except Exception as e:
            errors.append(f"SMB : {e}")

    if (cfg.get("ftp_host") or "").strip():
        try:
            import ftplib
            cls = ftplib.FTP_TLS if cfg.get("ftp_tls") else ftplib.FTP
            ftp = cls()
            ftp.connect(cfg["ftp_host"].strip(),
                        int(cfg.get("ftp_port") or 21), timeout=30)
            try:
                ftp.login(cfg.get("ftp_user") or "", cfg.get("ftp_pass") or "")
                if cfg.get("ftp_tls"):
                    ftp.prot_p()
                for part in [p for p in
                             (cfg.get("ftp_path") or "/").split("/") if p]:
                    try:
                        ftp.mkd(part)
                    except ftplib.error_perm:
                        pass
                    ftp.cwd(part)
                try:
                    ftp.mkd("today")
                except ftplib.error_perm:
                    pass
                ftp.cwd("today")
                with open(src, "rb") as f:
                    ftp.storbinary("STOR index.html", f)
            finally:
                try:
                    ftp.quit()
                except Exception:
                    ftp.close()
        except Exception as e:
            errors.append(f"FTP : {e}")

    return errors
