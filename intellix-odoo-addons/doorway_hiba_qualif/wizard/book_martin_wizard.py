# -*- coding: utf-8 -*-

from datetime import datetime, timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import html_escape

HIBA_LOGIN = "hiba@agencedoorway.com"
LEILA_LOGIN = "leiladaouadi@gmail.com"
MARTIN_LOGIN = "martin@agencedoorway.com"
MICHEL_LOGIN = "michel@coinsquebec.com"


class HibaBookMartinWizard(models.TransientModel):
    _name = "hiba.book.martin.wizard"
    _description = "Prendre un RDV Martin"

    lead_id = fields.Many2one("crm.lead", required=True, ondelete="cascade")
    host_choice = fields.Selection(
        [("martin", "Martin Houle"), ("michel", "Michel (Coins Québec)")],
        string="RDV pour",
        default="martin",
        required=True,
    )
    slot = fields.Char(string="Créneau")
    start = fields.Datetime(string="Date / heure (si hors créneau)")
    note = fields.Text(string="Note pour Martin ou Michel")

    def onchange(self, values, field_names, fields_spec):
        # Vue cachee navigateur : ignore les champs retires (ex. start).
        known = set(self._fields)
        values = {k: v for k, v in (values or {}).items() if k in known or k == "id"}
        field_names = [n for n in (field_names or []) if n in known]
        fields_spec = {k: v for k, v in (fields_spec or {}).items() if k in known}
        return super().onchange(values, field_names, fields_spec)

    @api.model
    def get_slots_ui(self):
        return self.env["calendar.event"].sudo().doorway_martin_slots_ui()

    def action_confirm(self):
        self.ensure_one()
        host_login = MARTIN_LOGIN if self.host_choice != "michel" else MICHEL_LOGIN
        host = self.env["res.users"].sudo().search([("login", "=", host_login)], limit=1)
        if not host:
            raise UserError("Compte %s introuvable." % ("Martin" if host_login == MARTIN_LOGIN else "Michel"))
        martin = host
        if self.slot:
            try:
                start = datetime.strptime(self.slot, "%Y-%m-%d %H:%M:%S")
            except ValueError as err:
                raise UserError("Créneau invalide.") from err
        elif self.start:
            start = self.start
        else:
            raise UserError("Choisis un jour, puis une heure.")
        if self.env["calendar.event"].sudo().search_count(
            self.env["calendar.event"].doorway_martin_busy_domain(martin, start)
        ):
            raise UserError("Ce créneau vient d’être pris — choisis-en un autre.")
        stop = start + timedelta(minutes=30)
        lead = self.lead_id
        booker = self.env.user
        attendees = [(4, martin.partner_id.id), (4, booker.partner_id.id)]
        if lead.partner_id:
            attendees.append((4, lead.partner_id.id))
        contact_lines = []
        contact = (lead.contact_name or lead.partner_name or "").strip()
        if contact:
            contact_lines.append("Contact : %s" % contact)
        phones = []
        for raw in (lead.phone, lead.mobile):
            num = (raw or "").strip()
            if num and num not in phones:
                phones.append(num)
        if phones:
            contact_lines.append("Téléphones : %s" % " ; ".join(phones))
        addr = ", ".join(
            x
            for x in [
                (lead.street or "").strip(),
                (getattr(lead, "street2", None) or "").strip(),
                (lead.city or "").strip(),
                (lead.zip or "").strip(),
            ]
            if x
        )
        if addr:
            contact_lines.append("Adresse : %s" % addr)
        email = (lead.email_from or "").strip()
        if email:
            contact_lines.append("Email : %s" % email)
        interests = []
        for flag, label in (
            ("hiba_interest_coins", "Coins Québec"),
            ("hiba_interest_itex", "ITEX"),
            ("hiba_interest_driven", "Driven"),
            ("hiba_interest_marketing", "Marketing général"),
            ("hiba_interest_intellix", "IntelliX"),
            ("hiba_interest_immobilier", "Immobilier"),
            ("hiba_interest_renovation", "Rénovation"),
        ):
            if lead[flag]:
                interests.append(label)
        desc_bits = [html_escape(x) for x in contact_lines]
        if interests:
            desc_bits.append(html_escape("Intérêts : " + ", ".join(interests)))
        note = (self.note or lead.hiba_comment or "").strip()
        if note:
            desc_bits.append(html_escape(note).replace("\n", "<br/>"))
        desc = "<br/>".join(desc_bits)
        event = self.env["calendar.event"].sudo().create(
            {
                "name": f"RDV {lead.contact_name or lead.name} — {martin.name} ({booker.name})",
                "start": start,
                "stop": stop,
                "user_id": martin.id,
                "event_tz": "America/Toronto",
                "partner_ids": attendees,
                "opportunity_id": lead.id,
                "description": desc,
                "hiba_booked_by": self.env.uid,
                "hiba_presence": "booked",
            }
        )
        vals = {
            "hiba_rdv_event_id": event.id,
            "hiba_rdv_state": "booked",
        }
        if self.note and not lead.hiba_comment:
            vals["hiba_comment"] = self.note
        stage = self.env.ref(
            "doorway_hiba_qualif.stage_coins_quebec_booked", raise_if_not_found=False
        )
        coins = self.env.ref(
            "doorway_hiba_qualif.crm_team_coins_quebec", raise_if_not_found=False
        )
        if stage and coins and lead.team_id == coins:
            vals["stage_id"] = stage.id
        lead.sudo().write(vals)
        if "coins.quebec.partenariat" in self.env:
            Part = self.env["coins.quebec.partenariat"].sudo()
            part = Part._cq_find_for_booking(
                email=lead.email_from,
                phone=lead.phone or lead.mobile,
            )
            if part:
                part._cq_mark_en_rdv_from_event(event)
                model = self.env["ir.model"].sudo()._get("coins.quebec.partenariat")
                if model and not event.res_model_id:
                    event.with_context(doorway_skip_activity_sync=True).write(
                        {"res_model_id": model.id, "res_id": part.id}
                    )
        return {"type": "ir.actions.act_window_close"}
