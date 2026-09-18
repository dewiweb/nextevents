"""Chemins du projet — racine, assets, cache."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSET_DIR = ROOT / "assets"
FONT_DIR = ASSET_DIR / "fonts"
CACHE_DIR = ASSET_DIR / "cache"
OA_MAP_FILE = CACHE_DIR / "oa-map.json"
OUT_DIR = ROOT / "diaporama"
