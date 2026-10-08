"""Primitives partagées d'identification des séries éditoriales.

Une même série circule sous plusieurs formes — slug de page site
(« fete-de-la-science »), keyword OpenAgenda (« fetedelascience »),
libellé (« Fête de la science »), casse et séparateurs variables.
Toutes se rejoignent après normalisation : c'est l'unique endroit où
la règle de comparaison vit (autrefois dupliquée dans scrape et oa).
"""

import re
import unicodedata


def norm_series(s):
    """Minuscules, sans accents ni séparateurs — tolère « Grandstemoins »
    vs « grandstemoins » ou « Les grands témoins »."""
    s = unicodedata.normalize("NFD", s or "")
    return "".join(
        c for c in s
        if not unicodedata.combining(c) and c.isalnum()
    ).lower()


def slugify(s):
    """« Fête de la science » → « fete-de-la-science » — variante de
    slug plausible pour sonder une page du site."""
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", s)).strip("-")


def series_match(ident, candidates):
    """Premier candidat qui désigne la même série que `ident`, ou None.

    Égalité des formes normalisées d'abord, puis sous-chaîne ≥4
    caractères (« nosfuturs » ⊂ « nosfuturs2027 ») — le seuil écarte
    les faux positifs des identifiants très courts (« jdh »)."""
    h = norm_series(ident)
    if not h:
        return None
    normed = [(c, norm_series(c)) for c in candidates]
    for c, n in normed:
        if n == h:
            return c
    for c, n in normed:
        if len(n) >= 4 and len(h) >= 4 and (n in h or h in n):
            return c
    return None
