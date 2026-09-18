#!/usr/bin/env python3
"""
UI web de pilotage du diaporama OBS.

- Bouton « Générer maintenant », rafraîchissement auto toutes les N heures
- Galerie des diapos, journal en direct, téléchargement .zip
- Sert aussi les PNG sur le réseau (/slides/<nom>)

Écoute sur 0.0.0.0:$PORT (défaut 8080). Dossier de sortie : $OUT_DIR
(défaut ./diaporama). Réglages persistés dans <out>/settings.json.

Entry point minimal — la logique vit dans le package `nextevents/` :
  settings.py (réglages + état), runner.py (génération + planificateur),
  webapp.py (routes Flask). Page : assets/webui.html.
"""

import os
import threading

from nextevents.runner import scheduler
from nextevents.settings import load_settings
from nextevents.webapp import app

PORT = int(os.environ.get("PORT", "8080"))

if __name__ == "__main__":
    load_settings()
    threading.Thread(target=scheduler, daemon=True).start()
    app.run(host="0.0.0.0", port=PORT)
