"""nextevents — diaporama des événements des Champs Libres.

Modules :
  paths     chemins (racine, assets, cache)
  scrape    scraping leschampslibres.fr (listes, détails, couleurs de card)
  media     fontes, images OpenAgenda, cache
  slide     template HTML + rendu PNG (Playwright / firefox)
  sync      envoi FTP / SMB vers le poste de diffusion
  generate  orchestration de la génération complète
"""

from .generate import generate, SIZES, DEFAULT_SIZE  # noqa: F401
