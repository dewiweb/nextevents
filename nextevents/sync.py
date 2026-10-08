"""Synchro du dossier de sortie vers FTP, partage SMB et/ou dossier
local (disque, lecteur réseau mappé, chemin UNC). Ne supprime à
distance que les .png/.html absents en local.

Un seul algorithme de miroir (_push_dir) — chaque destination ne
fournit que ses primitives distantes (ls / put / delete / ensure) via
une classe _*Remote.

Chaque destination choisit ce qu'elle reçoit via ses réglages :
`<proto>_send_landscape` (défaut oui — racine) et `<proto>_send_portrait`
(défaut non — sous-dossier distant `portrait/`)."""

import shutil
from pathlib import Path


def _dirs(out_dir, cfg, proto):
    """Dossiers locaux à pousser : (sous-chemin distant, chemin local).
    today/ (diapo du jour) est toujours poussé quand il existe — les
    réglages *_send_* ne concernent que le diaporama d'événements."""
    out_dir = Path(out_dir)
    dirs = []
    if cfg.get(f"{proto}_send_landscape", 1):
        dirs.append(("", out_dir))
    if cfg.get(f"{proto}_send_portrait") and (out_dir / "portrait").exists():
        dirs.append(("portrait", out_dir / "portrait"))
    # today/ existe même vide après un retrait : le pousser vide est ce
    # qui supprime la diapo du jour à distance
    if (out_dir / "today").is_dir():
        dirs.append(("today", out_dir / "today"))
    return dirs


def _push_dir(src, remote):
    """Miroir d'un dossier généré vers `remote` : *.png + *.html à la
    racine, html/*.html, puis manifest.txt en dernier — marqueur
    d'intégrité poussé après le contenu. Les .html racine servent à
    today/ (la racine du diaporama n'en a pas — glob vide, no-op).

    Règles partagées par les trois protocoles :
    - upload quand la taille distante diffère (taille inconnue → upload)
    - suppression distante des fichiers absents en local
    - le sous-dossier html/ n'est visité que s'il contient des fichiers
      locaux (ses orphelins distants ne sont alors purgés que là)
    - vérification finale : l'ensemble distant des .png == le jeu local
    """
    for pattern, hsub in (("*.png", ""), ("*.html", ""), ("*.html", "html")):
        sdir = src if not hsub else src / hsub
        local = {p.name: p for p in sdir.glob(pattern)}
        if hsub and not local:
            continue
        if hsub:
            remote.ensure(hsub)
        remote_files = remote.ls(hsub, pattern[1:])   # {nom: taille|None}
        for name, p in sorted(local.items()):
            if remote_files.get(name) == p.stat().st_size:
                continue  # déjà à jour à distance
            remote.put(p, hsub, name)
            print(f"  ↑ {remote.tag} {remote.join(hsub, name)}")
        for name in sorted(set(remote_files) - set(local)):
            remote.delete(hsub, name)
            print(f"  - {remote.tag} : {name} supprimé")
    manifest = src / "manifest.txt"
    if manifest.exists():
        remote.put(manifest, "", "manifest.txt")
    remote_pngs = set(remote.ls("", ".png"))
    expected = {p.name for p in src.glob("*.png")}
    if remote_pngs == expected:
        print(f"  synchro {remote.tag} vérifiée : "
              f"{len(expected)} fichiers conformes")
    else:
        print(
            f"  ⚠ divergence {remote.tag} — manquants : "
            f"{sorted(expected - remote_pngs)} / "
            f"en trop : {sorted(remote_pngs - expected)}")


class _FtpRemote:
    """Dossier distant atteint par chemins relatifs depuis le cwd de la
    session (ftp_path) — « today/index.png » — sans navigation cwd
    aller-retour : une erreur en cours de synchro ne laisse plus la
    session dans un dossier intermédiaire."""

    tag = "FTP"

    def __init__(self, ftp, sub):
        self.ftp, self.sub = ftp, sub
        if sub:
            try:
                ftp.mkd(sub)
            except Exception:
                pass

    def join(self, *parts):
        return "/".join(x for x in (self.sub, *parts) if x)

    def ensure(self, hsub):
        try:
            self.ftp.mkd(self.join(hsub))
        except Exception:
            pass

    def ls(self, hsub, suffix):
        d = self.join(hsub)
        try:
            names = self.ftp.nlst(d) if d else self.ftp.nlst()
        except Exception:
            return {}
        out = {}
        for n in names:
            # nlst(d) rend selon le serveur « file » ou « d/file »
            b = n.rsplit("/", 1)[-1]
            if not b.endswith(suffix):
                continue
            try:
                out[b] = self.ftp.size(self.join(hsub, b))
            except Exception:
                out[b] = None   # taille inconnue → ré-upload
        return out

    def put(self, src, hsub, name):
        with open(src, "rb") as f:
            self.ftp.storbinary(f"STOR {self.join(hsub, name)}", f)

    def delete(self, hsub, name):
        self.ftp.delete(self.join(hsub, name))


class _SmbRemote:
    """Dossier d'un partage SMB via smbclient (chemins \\)."""

    tag = "SMB"

    def __init__(self, base, sub):
        self.d = base if not sub else base + "\\" + sub
        if sub:
            self.ensure("")

    def join(self, *parts):
        return "\\".join(x for x in (self.d, *parts) if x)

    def ensure(self, hsub):
        from smbclient import makedirs
        makedirs(self.join(hsub), exist_ok=True)

    def ls(self, hsub, suffix):
        from smbclient import listdir, stat
        dd = self.join(hsub)
        try:
            names = listdir(dd)
        except Exception:
            return {}
        out = {}
        for n in names:
            if not n.endswith(suffix):
                continue
            try:
                out[n] = stat(dd + "\\" + n).st_size
            except Exception:
                out[n] = None
        return out

    def put(self, src, hsub, name):
        from smbclient import open_file
        with open(src, "rb") as f, \
                open_file(self.join(hsub, name), "wb") as dst:
            dst.write(f.read())

    def delete(self, hsub, name):
        from smbclient import remove
        remove(self.join(hsub, name))


class _LocalRemote:
    """Dossier du système de fichiers — lecteur réseau mappé (X:\\…) ou
    chemin UNC (\\\\hôte\\partage) inclus : pas besoin de smbprotocol
    ni d'identifiants, Windows gère l'auth."""

    tag = "local"

    def __init__(self, base, sub):
        self.d = Path(base) / sub if sub else Path(base)
        self.d.mkdir(parents=True, exist_ok=True)

    def join(self, *parts):
        return str(self.d.joinpath(*parts)) if parts else str(self.d)

    def ensure(self, hsub):
        (self.d / hsub).mkdir(parents=True, exist_ok=True)

    def ls(self, hsub, suffix):
        dd = self.d / hsub if hsub else self.d
        if not dd.is_dir():
            return {}
        return {p.name: p.stat().st_size for p in dd.glob("*" + suffix)}

    def put(self, src, hsub, name):
        shutil.copy2(src, self.d / hsub / name if hsub else self.d / name)

    def delete(self, hsub, name):
        (self.d / hsub / name if hsub else self.d / name).unlink()


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
        for sub, src in _dirs(out_dir, cfg, "ftp"):
            _push_dir(src, _FtpRemote(ftp, sub))
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
    from smbclient import makedirs, register_session

    register_session(
        host,
        username=cfg.get("smb_user") or "",
        password=cfg.get("smb_pass") or "",
    )
    base = f"\\\\{host}\\{share}"
    if cfg.get("smb_path"):
        base += "\\" + str(cfg["smb_path"]).strip("/\\")
    makedirs(base, exist_ok=True)

    for sub, src in _dirs(out_dir, cfg, "smb"):
        _push_dir(src, _SmbRemote(base, sub))


def sync_local(out_dir, cfg):
    """Copie miroir de tout ce qui a été généré vers un dossier du
    système de fichiers — lecteur réseau mappé ou chemin UNC."""
    dest = (cfg.get("local_dir") or "").strip()
    if not dest:
        return
    out_dir = Path(out_dir)
    dirs = [("", out_dir)]
    if (out_dir / "portrait").exists():
        dirs.append(("portrait", out_dir / "portrait"))
    if (out_dir / "today").is_dir():
        dirs.append(("today", out_dir / "today"))
    for sub, src in dirs:
        _push_dir(src, _LocalRemote(Path(dest), sub))


def push_all(out_dir, cfg):
    """Pousse le dossier de sortie vers toutes les destinations
    configurées (FTP, SMB, dossier local — today/ inclus). Renvoie la
    liste d'erreurs, vide = tout OK."""
    errors = []
    for label, fn in (("FTP", sync_ftp), ("SMB", sync_smb),
                      ("local", sync_local)):
        try:
            fn(out_dir, cfg)
        except Exception as e:
            errors.append(f"{label} : {e}")
    return errors
