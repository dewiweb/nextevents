"""Utilitaires partagés entre les blueprints de la webapp."""

import json

from .settings import resolve_out_dir


def events_meta():
    """Métadonnées des événements écrites par generate() (events.json)."""
    p = resolve_out_dir() / "events.json"
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text("utf-8"))
    except Exception:
        return []
