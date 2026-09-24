# -*- coding: utf-8 -*-
"""Fuseau RDV Réno : mur Toronto → UTC. Ne jamais traiter l’heure saisie
comme le fuseau de l’utilisatrice (Leila = Africa/Lagos → 6 h de trop)."""
from datetime import datetime

import pytz

from odoo.exceptions import UserError

RENO_CANADA_TZ = "America/Toronto"
RENO_MARTIN_LOGIN = "martin@agencedoorway.com"
RENO_MARTIN_CALENDAR_COLOR = 10
RENO_SLOT_MINUTES = 30
RENO_SLOT_HOURS = (9, 10, 11, 13, 14)

RENO_MARTIN_RDV_TEAM_XMLIDS = (
    "reno_immobilier.crm_team_reno_immobilier",
    "renovation_conciergerie.crm_team_renovation",
    "renovation_conciergerie.crm_team_immobilier",
)


def reno_format_canada_short(dt):
    """UTC naïf Odoo → jj/mm/aaaa HHhMM (Toronto)."""
    if not dt:
        return False
    tz = pytz.timezone(RENO_CANADA_TZ)
    if getattr(dt, "tzinfo", None):
        local = dt.astimezone(tz)
    else:
        local = pytz.UTC.localize(dt).astimezone(tz)
    return local.strftime("%d/%m/%Y %Hh%M")


def reno_parse_utc_slot(value):
    """Créneau widget : déjà en UTC naïf ``YYYY-MM-DD HH:MM:SS``."""
    try:
        return datetime.strptime((value or "").strip(), "%Y-%m-%d %H:%M:%S")
    except ValueError as err:
        raise UserError("Créneau invalide.") from err


def reno_toronto_wall_to_utc(value):
    """Interprète date/heure comme mur America/Toronto, retourne UTC naïf.

    ``fields.Datetime`` / widget datetime Odoo convertissent dans le TZ
    utilisateur. Hors créneau doit ignorer Africa/Lagos (Leila) et Casablanca.
    """
    if not value:
        raise UserError("Indiquez une date et une heure (Toronto).")
    if isinstance(value, datetime):
        naive = value.replace(tzinfo=None) if getattr(value, "tzinfo", None) else value
    else:
        raw = (value or "").strip()
        naive = None
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
            try:
                naive = datetime.strptime(raw, fmt)
                break
            except ValueError:
                continue
        if naive is None:
            raise UserError(
                "Heure Toronto invalide. Format : 2026-09-15 09:00"
            )
    tz = pytz.timezone(RENO_CANADA_TZ)
    try:
        local = tz.localize(naive, is_dst=None)
    except pytz.AmbiguousTimeError:
        local = tz.localize(naive, is_dst=True)
    except pytz.NonExistentTimeError:
        local = tz.localize(naive, is_dst=False)
    return local.astimezone(pytz.UTC).replace(tzinfo=None)
