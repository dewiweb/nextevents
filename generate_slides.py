#!/usr/bin/env python3
"""
Génère un diaporama OBS (PNG 16:9, UHD 3840x2160 par défaut,
HD 1920x1080 via --size hd) des événements à venir
aux Champs Libres, à partir des pages catégories :
https://www.leschampslibres.fr/au-programme/categorie/rencontres-aux-champs-libres
https://www.leschampslibres.fr/au-programme/categorie/concerts-aux-champs-libres
https://www.leschampslibres.fr/au-programme/categorie/projections-aux-champs-libres

CLI minimal — la logique vit dans le package `nextevents/` :
  scrape (site), media (images/fontes), slide (rendu), sync (FTP/SMB),
  generate (orchestration). Layout des diapos : assets/slide_template.html.

Sortie : dossier `diaporama/` dont les PNG et HTML sont remplacés
à chaque exécution, contenant
  - slide-*.png   images 16:9 (source "Diaporama" d'OBS)
  - html/slide-*.html  sources HTML autonomes (utilisables via source "Navigateur")

Dépendances : requests, beautifulsoup4, pillow, playwright (ou firefox).
"""

import argparse
import sys

from nextevents.generate import DEFAULT_SIZE, SIZES, generate

# compat : webui.py importe generate_slides et utilise ses attributs
__all__ = ["generate", "SIZES", "DEFAULT_SIZE"]


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
