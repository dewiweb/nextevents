"""Synchro du dossier de sortie vers FTP et/ou partage SMB (poste OBS,
NAS). Ne supprime à distance que les .png/.html absents en local."""

from pathlib import Path


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
