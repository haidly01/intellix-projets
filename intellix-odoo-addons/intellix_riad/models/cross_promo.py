# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError


def _riad_readonly_calendar_action(env, property_id, name=None):
    """Calendrier d'occupation du riad, sans créer ni modifier de réservation."""
    if not property_id:
        raise UserError(
            _("Aucun bien hébergement lié. La disponibilité se lit depuis Module Hébergement.")
        )
    calendar = env.ref(
        "intellix_riad.view_riad_availability_calendar_readonly",
        raise_if_not_found=False,
    )
    listing = env.ref(
        "intellix_riad.view_riad_availability_list_readonly",
        raise_if_not_found=False,
    )
    views = []
    if calendar:
        views.append((calendar.id, "calendar"))
    if listing:
        views.append((listing.id, "list"))
    return {
        "type": "ir.actions.act_window",
        "name": name or _("Disponibilités riad (lecture seule)"),
        "res_model": "coins.reservation",
        "view_mode": "calendar,list",
        "views": views or False,
        "domain": [
            ("property_id", "=", property_id),
            ("state", "!=", "cancelled"),
        ],
        "context": {
            "create": False,
            "edit": False,
            "delete": False,
            "default_property_id": property_id,
        },
        "target": "current",
    }


class CoinsPropertyRiadVenue(models.Model):
    _inherit = "coins.property"

    riad_listed_as_event_venue = fields.Boolean(
        string="Lieu partenaire événements (Coins Marocain)",
        help="Visible comme lieu pour les événements / privatisations Coins. "
        "Le calendrier se lit ici ; la réservation reste dans Module Hébergement.",
    )
    riad_establishment_id = fields.Many2one(
        "intellix.riad.establishment",
        compute="_compute_riad_establishment",
        string="Établissement Hébergement",
    )

    @api.depends()
    def _compute_riad_establishment(self):
        Estab = self.env["intellix.riad.establishment"]
        for rec in self:
            rec.riad_establishment_id = Estab.search(
                [("property_id", "=", rec.id)], limit=1
            )

    def action_open_riad_availability_readonly(self):
        self.ensure_one()
        if not self.riad_establishment_id:
            raise UserError(
                _("Ce bien n'est pas un établissement Module Hébergement.")
            )
        return _riad_readonly_calendar_action(self.env, self.id)

    def get_riad_availability_payload(self, days=14):
        """RPC lecture seule pour Coins Marocain — pas de réservation ici."""
        self.ensure_one()
        estab = self.riad_establishment_id
        if not estab:
            return {"ok": False, "error": "not_a_riad", "readonly": True}
        dash = self.env["intellix.riad.dashboard"]
        today = fields.Date.context_today(self)
        return {
            "ok": True,
            "readonly": True,
            "bookable": False,
            "establishment": {
                "id": estab.id,
                "name": estab.name or self.name,
            },
            "property_id": self.id,
            "grid": dash._week_grid(estab, today, days=int(days or 14)),
        }


class CoinsPartnerActivityRiad(models.Model):
    _inherit = "coins.partner_activity"

    riad_establishment_id = fields.Many2one(
        "intellix.riad.establishment",
        string="Établissement Hébergement",
        ondelete="set null",
        index=True,
        help="Lien de listing uniquement. Pas de fusion des dossiers événement.",
    )
    riad_property_id = fields.Many2one(
        related="riad_establishment_id.property_id",
        string="Bien riad",
        readonly=True,
    )

    def action_open_riad_availability_readonly(self):
        self.ensure_one()
        if not self.riad_establishment_id:
            raise UserError(
                _("Ce partenaire n'est pas lié à un établissement Hébergement.")
            )
        return _riad_readonly_calendar_action(
            self.env, self.riad_establishment_id.property_id.id, self.name
        )


class CoinsEvenementRiad(models.Model):
    _inherit = "coins.evenement"

    riad_has_availability_calendar = fields.Boolean(
        compute="_compute_riad_has_availability_calendar",
    )

    @api.depends("property_id", "partner_activity_id", "partner_activity_id.riad_establishment_id")
    def _compute_riad_has_availability_calendar(self):
        Estab = self.env["intellix.riad.establishment"]
        for rec in self:
            linked = False
            if rec.partner_activity_id and rec.partner_activity_id.riad_establishment_id:
                linked = True
            elif rec.property_id and Estab.search(
                [("property_id", "=", rec.property_id.id)], limit=1
            ):
                linked = True
            rec.riad_has_availability_calendar = linked

    def action_open_riad_availability_readonly(self):
        self.ensure_one()
        activity = self.partner_activity_id
        if activity and activity.riad_establishment_id:
            return activity.action_open_riad_availability_readonly()
        if self.property_id and self.property_id.riad_establishment_id:
            return self.property_id.action_open_riad_availability_readonly()
        raise UserError(
            _("Aucun calendrier riad lié à ce lieu. Choisissez le partenaire Anna Sweety "
              "ou le bien Module Hébergement — sans y créer de réservation.")
        )
