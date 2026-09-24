# -*- coding: utf-8 -*-
"""Garde de publication : une description de chambre publique n'est pas un brouillon.

Même logique côté Odoo (write) et prerender HTML — sans dépendre d'Odoo.
"""
from __future__ import annotations

import re
import unicodedata

# Notices internes / voix de rédaction. Jamais sur coinsmarocain.com.
_DRAFT_PATTERNS = (
    r"en attendant",
    r"reste a ecrire",
    r"a preciser",
    r"\bkarine\b",
    r"\bplaceholder\b",
    r"\btodo\b",
    r"a valider",
    r"notice reste",
    r"maisonnee",
    r"rien d.invente ici",
    r"le reste de la notice",
    r"\bbrouillon\b",
    r"\[draft\]",
    r"meta[- ]draft",
)

_DRAFT_RE = re.compile("|".join(_DRAFT_PATTERNS), re.IGNORECASE)


def fold_public_copy(text: str) -> str:
    """Minuscule, sans accents, pour matcher les marqueurs."""
    raw = unicodedata.normalize("NFD", text or "")
    stripped = "".join(ch for ch in raw if unicodedata.category(ch) != "Mn")
    return stripped.lower()


def is_internal_draft(text: str) -> bool:
    """True si le texte est une notice interne, pas une description voyageur."""
    blob = fold_public_copy(text)
    if not blob.strip():
        return False
    return bool(_DRAFT_RE.search(blob))


def public_room_description(text: str) -> str:
    """Texte public, ou vide si notice interne. Ne jamais inventer."""
    if is_internal_draft(text):
        return ""
    return (text or "").strip()
