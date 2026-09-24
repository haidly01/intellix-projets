# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class CoinsPropertyBlocage(models.Model):
    """Table technique des périodes indisponibles (entrée du calcul de disponibilités)."""

    _name = "coins.property.blocage"
    _description = "Blocage disponibilité bien (technique)"
    _order = "date_debut desc, id desc"

    property_id = fields.Many2one(
        "coins.property",
        string="Propriété",
        required=True,
        ondelete="cascade",
        index=True,
    )
    date_debut = fields.Date(string="Début", required=True, index=True)
    date_fin = fields.Date(string="Fin", required=True, index=True)
    evenement_id = fields.Many2one(
        "coins.evenement",
        string="Événement Coins",
        ondelete="set null",
        index=True,
    )
    source = fields.Selection(
        [
            ("airbnb", "Airbnb"),
            ("direct", "Direct (Coins Marocain)"),
            ("evenement", "Événement Coins"),
            ("ota", "OTA / Channex"),
            ("manuel", "Manuel"),
        ],
        string="Source",
        required=True,
        default="manuel",
        index=True,
    )
    uid_externe = fields.Char(
        string="UID iCal externe",
        index=True,
        help="UID VEVENT Airbnb — sert à dédupliquer lors des resync.",
    )
    reservation_id = fields.Many2one(
        "coins.reservation",
        string="Réservation",
        ondelete="set null",
        help="Renseigné si source = direct.",
    )
    statut = fields.Selection(
        [
            ("confirme", "Confirmé"),
            ("annule", "Annulé"),
        ],
        string="Statut",
        required=True,
        default="confirme",
        index=True,
    )
    summary = fields.Char(string="Résumé iCal")
    name = fields.Char(string="Libellé")

    def _compute_name(self):
        for rec in self:
            bits = [rec.source or "?", str(rec.date_debut or ""), "→", str(rec.date_fin or "")]
            if rec.summary:
                bits.append(rec.summary)
            rec.name = " ".join(bits)

    def _log_overlap_warnings(self):
        """Chevauchement = signal à vérifier manuellement, pas une erreur bloquante."""
        for rec in self:
            if rec.statut != "confirme" or not rec.property_id or not rec.date_debut or not rec.date_fin:
                continue
            overlaps = self.search(
                [
                    ("id", "!=", rec.id),
                    ("property_id", "=", rec.property_id.id),
                    ("statut", "=", "confirme"),
                    ("date_debut", "<=", rec.date_fin),
                    ("date_fin", ">=", rec.date_debut),
                ],
                limit=5,
            )
            if overlaps:
                _logger.warning(
                    "coins.property.blocage overlap property_id=%s blocage=%s dates=%s→%s "
                    "avec ids=%s (vérifier manuellement avec le propriétaire)",
                    rec.property_id.id,
                    rec.id,
                    rec.date_debut,
                    rec.date_fin,
                    overlaps.ids,
                )

    def _recalc_properties(self):
        props = self.mapped("property_id")
        if props:
            props._recalculer_disponibilites()

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._log_overlap_warnings()
        records._recalc_properties()
        return records

    def write(self, vals):
        res = super().write(vals)
        self._log_overlap_warnings()
        self._recalc_properties()
        return res

    def unlink(self):
        props = self.mapped("property_id")
        res = super().unlink()
        if props:
            props._recalculer_disponibilites()
        return res
