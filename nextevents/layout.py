"""Topologie du dossier de sortie : où vivent les PNG, le HTML source
et les manifestes d'intégrité — partagée par la génération, l'API
(ajout/retrait de diapos) et les synchros."""

from pathlib import Path

from .settings import atomic_write


def render_sets(cfg, out):
    """Jeux de diapos à produire : [(orientation, dossier PNG)].

    Paysage à la racine, portrait dans portrait/ ; today/ (diapo du
    jour) n'en fait pas partie — write_today la gère à part."""
    out = Path(out)
    sets = []
    if cfg is None or cfg.get("gen_landscape", 1):
        sets.append(("landscape", out))
    if cfg and cfg.get("gen_portrait"):
        sets.append(("portrait", out / "portrait"))
    return sets


def write_manifest(dest):
    """manifest.txt = noms des PNG du jeu, un par ligne (vide si aucun).

    Écrit en dernier à la génération et poussé en dernier par les
    synchros : sa présence à distance marque un jeu intègre — les
    fichiers manquants ou en trop sont signalés à la vérification.
    Un manifeste vide propage un retrait (diapo du jour supprimée)."""
    dest = Path(dest)
    pngs = sorted(dest.glob("*.png"))
    atomic_write(
        dest / "manifest.txt",
        "\n".join(p.name for p in pngs) + ("\n" if pngs else ""),
    )
