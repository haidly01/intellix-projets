# -*- coding: utf-8 -*-

from datetime import datetime, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import html_escape

from ..models.partenariat import CQ_MARTIN_CALENDAR_COLOR, CQ_MARTIN_LOGIN


class CoinsQuebecBookRdvWizard(models.TransientModel):
    """Réunions CQ → calendrier Martin uniquement.

    Réutilise les créneaux `calendar.event.doorway_martin_slots_ui` (Hiba)
    sans écrire sur crm.lead ni sur hiba.book.martin.wizard.
    """

    _name = "coins.quebec.book.rdv.wizard"
    _description = "Planifier une réunion Coins Québec (Martin)"

    partenariat_id = fields.Many2one(
        "coins.quebec.partenariat",
        string="Fiche partenariat",
        required=True,
        ondelete="cascade",
    )
    slot = fields.Char(string="Créneau")
    start = fields.Datetime(string="Date / heure (si hors créneau)")
    note = fields.Text(string="Note pour Martin")
    contact_firstname = fields.Char(
        related="partenariat_id.contact_firstname",
        readonly=False,
        string="Prénom du contact",
    )
    contact_lastname = fields.Char(
        related="partenariat_id.contact_lastname",
        readonly=False,
        string="Nom du contact",
    )
    phone_ids = fields.One2many(
        related="partenariat_id.phone_ids",
        readonly=False,
        string="Téléphones",
    )
    address_ids = fields.One2many(
        related="partenariat_id.address_ids",
        readonly=False,
        string="Adresses",
    )

    def onchange(self, values, field_names, fields_spec):
        known = set(self._fields)
        values = {k: v for k, v in (values or {}).items() if k in known or k == "id"}
        field_names = [n for n in (field_names or []) if n in known]
        fields_spec = {k: v for k, v in (fields_spec or {}).items() if k in known}
        return super().onchange(values, field_names, fields_spec)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        pid = res.get("partenariat_id") or self.env.context.get("default_partenariat_id")
        if pid:
            part = self.env["coins.quebec.partenariat"].browse(pid)
            if part.exists():
                if hasattr(part, "_cq_split_existing_contact_names"):
                    part._cq_split_existing_contact_names()
                if hasattr(part, "_cq_seed_phone_address_lines"):
                    part._cq_seed_phone_address_lines()
        return res

    @api.model
    def get_slots_ui(self):
        Event = self.env["calendar.event"].sudo()
        if hasattr(Event, "doorway_martin_slots_ui"):
            return Event.doorway_martin_slots_ui()
        return []

    def _cq_martin_host(self):
        host = self.env["res.users"].sudo().search(
            [("login", "=", CQ_MARTIN_LOGIN)], limit=1
        )
        if not host:
            raise UserError(
                _("Compte Martin introuvable (%s).") % CQ_MARTIN_LOGIN
            )
        return host

    def _cq_event_title(self, part):
        contact = ""
        if hasattr(part, "_cq_contact_display_name"):
            contact = part._cq_contact_display_name()
        else:
            contact = (part.contact_name or "").strip()
        etab = (part.name or "partenariat").strip()
        if contact and contact != etab:
            return "RDV %s — %s — Martin" % (contact, etab)
        return "RDV %s — Martin (Coins Québec)" % etab

    def action_confirm(self):
        self.ensure_one()
        martin = self._cq_martin_host()
        if self.slot:
            try:
                start = datetime.strptime(self.slot, "%Y-%m-%d %H:%M:%S")
            except ValueError as err:
                raise UserError(_("Créneau invalide.")) from err
        elif self.start:
            start = self.start
        else:
            raise UserError(_("Choisissez un jour, puis une heure."))
        Event = self.env["calendar.event"].sudo()
        busy_domain = (
            Event.doorway_martin_busy_domain(martin, start)
            if hasattr(Event, "doorway_martin_busy_domain")
            else [
                ("user_id", "=", martin.id),
                ("start", "<", start + timedelta(minutes=30)),
                ("stop", ">", start),
            ]
        )
        if Event.search_count(busy_domain):
            raise UserError(
                _("Ce créneau vient d'être pris — choisissez-en un autre.")
            )
        stop = start + timedelta(minutes=30)
        part = self.partenariat_id
        if hasattr(part, "_cq_split_existing_contact_names"):
            part._cq_split_existing_contact_names()
        if hasattr(part, "_cq_seed_phone_address_lines"):
            part._cq_seed_phone_address_lines()
        booker = self.env.user
        attendees = [(4, martin.partner_id.id), (4, booker.partner_id.id)]
        person = False
        if hasattr(part, "_cq_ensure_contact_partner"):
            try:
                person = part._cq_ensure_contact_partner()
            except Exception:
                person = part.partner_id
            if person:
                attendees.append((4, person.id))
        if part.partner_id and (not person or part.partner_id.id != person.id):
            attendees.append((4, part.partner_id.id))
        desc_bits = [
            html_escape("Coins Québec — réunion partenariat"),
            html_escape("Hôte calendrier : Martin Houle (décision Karine Barmaki)."),
            html_escape("Fiche : %s (id %s)" % (part.name or "", part.id)),
        ]
        if hasattr(part, "_cq_rdv_contact_block_html"):
            desc_bits.append(part._cq_rdv_contact_block_html())
        if self.note:
            desc_bits.append(
                html_escape(self.note.strip()).replace("\n", "<br/>")
            )
        model = self.env["ir.model"].sudo()._get("coins.quebec.partenariat")
        event_vals = {
            "name": self._cq_event_title(part),
            "start": start,
            "stop": stop,
            "user_id": martin.id,
            "event_tz": "America/Toronto",
            "partner_ids": attendees,
            "res_id": part.id,
            "description": "<br/>".join(desc_bits),
        }
        if model:
            event_vals["res_model_id"] = model.id
        if "color" in Event._fields and not Event._fields["color"].compute:
            event_vals["color"] = CQ_MARTIN_CALENDAR_COLOR
        event = Event.create(event_vals)
        part.sudo()._cq_ensure_martin_calendar_color()
        # Commercial = qui clique Booker (Leila / Yamina / Martin).
        # Hôte calendar.event reste Martin. Pas de défaut silencieux.
        part_vals = {
            "cq_rdv_event_id": event.id,
            "coins_commercial_assigne": booker.id,
        }
        if part.stage not in ("gagne", "perdu"):
            part_vals["stage"] = "en_rdv"
        part.sudo().write(part_vals)
        return {"type": "ir.actions.act_window_close"}
