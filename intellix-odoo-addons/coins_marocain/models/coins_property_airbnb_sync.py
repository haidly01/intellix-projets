# -*- coding: utf-8 -*-
"""Import iCal Airbnb → coins.property.blocage (+ recalcul disponibilités)."""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

import requests

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


def _as_date(value):
    """Normalise DTSTART/DTEND iCal en date Python."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    # icalendar v5 peut exposer .dt
    dt = getattr(value, "dt", value)
    if isinstance(dt, datetime):
        return dt.date()
    if isinstance(dt, date):
        return dt
    return None


class CoinsPropertyAirbnbSync(models.Model):
    _inherit = "coins.property"

    def action_sync_airbnb_ical(self):
        """Bouton formulaire : sync iCal pour la/les propriétés sélectionnées."""
        stats = self._sync_airbnb_icals()
        msg = _(
            "Import Airbnb : %(fetched)s événements, %(created)s créés, "
            "%(updated)s mis à jour, %(cancelled)s annulés, %(errors)s erreurs."
        ) % stats
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Sync Airbnb"),
                "message": msg,
                "type": "success" if not stats.get("errors") else "warning",
                "sticky": False,
            },
        }

    @api.model
    def cron_import_airbnb_icals(self):
        """Cron toutes les 3 h — sync toutes les propriétés avec URL iCal."""
        props = self.search([("airbnb_ical_export_url", "!=", False), ("active", "=", True)])
        stats = props._sync_airbnb_icals()
        _logger.info(
            "cron_import_airbnb_icals done fetched=%s created=%s updated=%s "
            "cancelled=%s errors=%s",
            stats["fetched"],
            stats["created"],
            stats["updated"],
            stats["cancelled"],
            stats["errors"],
        )
        return stats

    def _sync_airbnb_icals(self):
        stats = {
            "fetched": 0,
            "created": 0,
            "updated": 0,
            "cancelled": 0,
            "errors": 0,
        }
        for prop in self:
            if not (prop.airbnb_ical_export_url or "").strip():
                continue
            try:
                part = prop._import_one_airbnb_ical()
                for k in ("fetched", "created", "updated", "cancelled"):
                    stats[k] += part.get(k, 0)
            except Exception:
                stats["errors"] += 1
                _logger.exception(
                    "Airbnb iCal import failed property_id=%s url=%s",
                    prop.id,
                    prop.airbnb_ical_export_url,
                )
        return stats

    def _import_one_airbnb_ical(self):
        """Fetch + parse + upsert blocages source=airbnb pour une propriété."""
        self.ensure_one()
        try:
            from icalendar import Calendar
        except ImportError as exc:
            raise RuntimeError(
                "Paquet Python 'icalendar' manquant — pip install icalendar"
            ) from exc

        url = (self.airbnb_ical_export_url or "").strip()
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        cal = Calendar.from_ical(resp.content)

        seen_uids = set()
        created = updated = 0
        Blocage = self.env["coins.property.blocage"].sudo()

        for component in cal.walk():
            if component.name != "VEVENT":
                continue
            uid = str(component.get("UID") or "").strip()
            if not uid:
                continue
            dtstart = _as_date(component.get("DTSTART"))
            dtend = _as_date(component.get("DTEND"))
            if not dtstart:
                continue
            # Airbnb all-day : DTEND exclusif (jour du checkout)
            end_param = component.get("DTEND")
            is_date_only = False
            if end_param is not None:
                raw = getattr(end_param, "dt", end_param)
                is_date_only = isinstance(raw, date) and not isinstance(raw, datetime)
            if dtend and is_date_only:
                date_fin = dtend - timedelta(days=1)
            elif dtend:
                date_fin = dtend
            else:
                date_fin = dtstart
            if date_fin < dtstart:
                date_fin = dtstart

            summary = str(component.get("SUMMARY") or "").strip() or False
            seen_uids.add(uid)
            existing = Blocage.search(
                [
                    ("property_id", "=", self.id),
                    ("uid_externe", "=", uid),
                    ("source", "=", "airbnb"),
                ],
                limit=1,
            )
            vals = {
                "property_id": self.id,
                "date_debut": dtstart,
                "date_fin": date_fin,
                "source": "airbnb",
                "uid_externe": uid,
                "statut": "confirme",
                "summary": summary,
            }
            if existing:
                existing.write(vals)
                updated += 1
            else:
                Blocage.create(vals)
                created += 1

        # UIDs disparus du flux → annulation Airbnb
        stale = Blocage.search(
            [
                ("property_id", "=", self.id),
                ("source", "=", "airbnb"),
                ("statut", "=", "confirme"),
                ("uid_externe", "!=", False),
                ("uid_externe", "not in", list(seen_uids) or [""]),
            ]
        )
        cancelled = len(stale)
        if stale:
            stale.write({"statut": "annule"})

        self.write({"airbnb_ical_last_sync": fields.Datetime.now()})
        # Recalcul même si seuls des cancels (write sur blocage le fait déjà,
        # mais un ical vide sans write nécessite un appel explicite)
        self._recalculer_disponibilites()

        _logger.info(
            "Airbnb iCal property_id=%s fetched=%s created=%s updated=%s cancelled=%s",
            self.id,
            len(seen_uids),
            created,
            updated,
            cancelled,
        )
        return {
            "fetched": len(seen_uids),
            "created": created,
            "updated": updated,
            "cancelled": cancelled,
        }
