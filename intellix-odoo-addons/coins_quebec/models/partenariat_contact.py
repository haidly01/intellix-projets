# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.tools import html_escape


PHONE_LABELS = [
    ("principal", "Principal"),
    ("cell", "Cellulaire"),
    ("bureau", "Bureau"),
    ("whatsapp", "WhatsApp"),
    ("autre", "Autre"),
]

ADDRESS_LABELS = [
    ("etablissement", "Établissement"),
    ("facturation", "Facturation"),
    ("autre", "Autre"),
]


class CoinsQuebecPartenariatPhone(models.Model):
    _name = "coins.quebec.partenariat.phone"
    _description = "Téléphone fiche partenariat CQ"
    _order = "sequence, id"
    _rec_name = "phone"

    partenariat_id = fields.Many2one(
        "coins.quebec.partenariat",
        required=True,
        ondelete="cascade",
        index=True,
    )
    sequence = fields.Integer(default=10)
    label = fields.Selection(PHONE_LABELS, string="Type", default="principal", required=True)
    phone = fields.Char(string="Numéro", required=True)

    def _cq_touch_parent(self):
        parents = self.mapped("partenariat_id")
        if parents:
            parents._cq_sync_principal_from_lines()

    @api.model_create_multi
    def create(self, vals_list):
        recs = super().create(vals_list)
        recs._cq_touch_parent()
        return recs

    def write(self, vals):
        res = super().write(vals)
        if {"phone", "sequence", "partenariat_id"} & set(vals):
            self._cq_touch_parent()
        return res

    def unlink(self):
        parents = self.mapped("partenariat_id")
        res = super().unlink()
        parents._cq_sync_principal_from_lines()
        return res


class CoinsQuebecPartenariatAddress(models.Model):
    _name = "coins.quebec.partenariat.address"
    _description = "Adresse fiche partenariat CQ"
    _order = "sequence, id"

    partenariat_id = fields.Many2one(
        "coins.quebec.partenariat",
        required=True,
        ondelete="cascade",
        index=True,
    )
    sequence = fields.Integer(default=10)
    label = fields.Selection(
        ADDRESS_LABELS, string="Type", default="etablissement", required=True
    )
    street = fields.Char(string="Adresse")
    city = fields.Char(string="Ville")
    zip = fields.Char(string="Code postal")

    def display_line(self):
        self.ensure_one()
        bits = [self.street, self.city, self.zip]
        return ", ".join(b.strip() for b in bits if b and str(b).strip())

    def _cq_touch_parent(self):
        parents = self.mapped("partenariat_id")
        if parents:
            parents._cq_sync_principal_from_lines()

    @api.model_create_multi
    def create(self, vals_list):
        recs = super().create(vals_list)
        recs._cq_touch_parent()
        return recs

    def write(self, vals):
        res = super().write(vals)
        if {"street", "city", "zip", "sequence", "partenariat_id"} & set(vals):
            self._cq_touch_parent()
        return res

    def unlink(self):
        parents = self.mapped("partenariat_id")
        res = super().unlink()
        parents._cq_sync_principal_from_lines()
        return res


class CoinsQuebecPartenariatContact(models.Model):
    _inherit = "coins.quebec.partenariat"

    contact_firstname = fields.Char(string="Prénom")
    contact_lastname = fields.Char(string="Nom de famille")
    phone_ids = fields.One2many(
        "coins.quebec.partenariat.phone",
        "partenariat_id",
        string="Téléphones",
    )
    address_ids = fields.One2many(
        "coins.quebec.partenariat.address",
        "partenariat_id",
        string="Adresses",
    )

    def _cq_join_contact_name(self, firstname=None, lastname=None):
        fn = (firstname if firstname is not None else self.contact_firstname or "").strip()
        ln = (lastname if lastname is not None else self.contact_lastname or "").strip()
        return " ".join(p for p in [fn, ln] if p)

    @api.onchange("contact_firstname", "contact_lastname")
    def _onchange_cq_contact_parts(self):
        joined = self._cq_join_contact_name()
        if joined:
            self.contact_name = joined

    @api.onchange("contact_name")
    def _onchange_cq_contact_name(self):
        raw = (self.contact_name or "").strip()
        current = self._cq_join_contact_name()
        if raw and raw != current:
            parts = raw.split(None, 1)
            self.contact_firstname = parts[0]
            self.contact_lastname = parts[1] if len(parts) > 1 else False

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            fn = (vals.get("contact_firstname") or "").strip()
            ln = (vals.get("contact_lastname") or "").strip()
            if (fn or ln) and not vals.get("contact_name"):
                vals["contact_name"] = " ".join(p for p in [fn, ln] if p)
            elif vals.get("contact_name") and not fn and not ln:
                parts = (vals.get("contact_name") or "").strip().split(None, 1)
                if parts:
                    vals["contact_firstname"] = parts[0]
                    if len(parts) > 1:
                        vals["contact_lastname"] = parts[1]
        recs = super().create(vals_list)
        recs.with_context(cq_skip_line_seed=True)._cq_seed_phone_address_lines()
        return recs

    def write(self, vals):
        skip_split = self.env.context.get("cq_skip_contact_split")
        if not skip_split and {"contact_firstname", "contact_lastname"} & set(vals):
            # Recalcule contact_name après le write (valeurs mixtes par fiche).
            res = super().write(vals)
            for rec in self:
                joined = rec._cq_join_contact_name()
                if joined and rec.contact_name != joined:
                    rec.with_context(cq_skip_contact_split=True).write(
                        {"contact_name": joined}
                    )
            if {"phone", "street", "city"} & set(vals) and not self.env.context.get(
                "cq_skip_line_seed"
            ):
                self._cq_seed_phone_address_lines()
            return res
        if not skip_split and "contact_name" in vals:
            res = super().write(vals)
            for rec in self:
                if rec.contact_firstname or rec.contact_lastname:
                    continue
                raw = (rec.contact_name or "").strip()
                if not raw:
                    continue
                parts = raw.split(None, 1)
                rec.with_context(cq_skip_contact_split=True).write(
                    {
                        "contact_firstname": parts[0],
                        "contact_lastname": parts[1] if len(parts) > 1 else False,
                    }
                )
            if {"phone", "street", "city"} & set(vals) and not self.env.context.get(
                "cq_skip_line_seed"
            ):
                self._cq_seed_phone_address_lines()
            return res
        res = super().write(vals)
        if {"phone", "street", "city"} & set(vals) and not self.env.context.get(
            "cq_skip_line_seed"
        ):
            self._cq_seed_phone_address_lines()
        return res

    def _cq_seed_phone_address_lines(self):
        """Recopie téléphone / adresse principaux dans les listes (sans doublon)."""
        Phone = self.env["coins.quebec.partenariat.phone"].sudo()
        Addr = self.env["coins.quebec.partenariat.address"].sudo()
        for rec in self:
            if rec.phone:
                existing = {(p.phone or "").strip() for p in rec.phone_ids}
                num = rec.phone.strip()
                if num not in existing:
                    Phone.create(
                        {
                            "partenariat_id": rec.id,
                            "label": "principal",
                            "phone": num,
                            "sequence": 1,
                        }
                    )
            if rec.street or rec.city:
                key = (
                    (rec.street or "").strip().lower(),
                    (rec.city or "").strip().lower(),
                )
                have = {
                    (
                        (a.street or "").strip().lower(),
                        (a.city or "").strip().lower(),
                    )
                    for a in rec.address_ids
                }
                if key not in have and (key[0] or key[1]):
                    Addr.create(
                        {
                            "partenariat_id": rec.id,
                            "label": "etablissement",
                            "street": rec.street or False,
                            "city": rec.city or False,
                            "sequence": 1,
                        }
                    )

    def _cq_sync_principal_from_lines(self):
        """Le 1er téléphone / la 1re adresse restent les champs principaux (appel, scrape)."""
        if self.env.context.get("cq_skip_principal_sync"):
            return
        for rec in self:
            vals = {}
            if rec.phone_ids:
                first = rec.phone_ids.sorted(key=lambda p: (p.sequence, p.id))[0]
                if first.phone and first.phone != rec.phone:
                    vals["phone"] = first.phone
            if rec.address_ids:
                first = rec.address_ids.sorted(key=lambda a: (a.sequence, a.id))[0]
                if first.street and first.street != rec.street:
                    vals["street"] = first.street
                if first.city and first.city != rec.city:
                    vals["city"] = first.city
            if vals:
                rec.with_context(
                    cq_skip_line_seed=True, cq_skip_principal_sync=True
                ).write(vals)

    def _cq_all_phones(self):
        self.ensure_one()
        seen = []
        for raw in [self.phone] + list(self.phone_ids.mapped("phone")):
            num = (raw or "").strip()
            if num and num not in seen:
                seen.append(num)
        return seen

    def _cq_all_addresses(self):
        self.ensure_one()
        seen = []
        primary = ", ".join(
            p for p in [(self.street or "").strip(), (self.city or "").strip()] if p
        )
        if primary:
            seen.append(primary)
        for line in self.address_ids:
            txt = line.display_line()
            if txt and txt not in seen:
                seen.append(txt)
        return seen

    def _cq_contact_display_name(self):
        self.ensure_one()
        return (
            self._cq_join_contact_name()
            or (self.contact_name or "").strip()
            or ""
        )

    def _cq_rdv_contact_block(self):
        """Texte à coller dans le RDV — prénom, nom, tous les tél. et adresses."""
        self.ensure_one()
        lines = []
        contact = self._cq_contact_display_name()
        lines.append("Contact : %s" % (contact or "—"))
        labeled = []
        if self.phone:
            labeled.append(self.phone.strip())
        labels = dict(PHONE_LABELS)
        for line in self.phone_ids:
            num = (line.phone or "").strip()
            if not num:
                continue
            lab = labels.get(line.label or "", "")
            item = "%s (%s)" % (num, lab) if lab else num
            if item not in labeled and num not in labeled:
                labeled.append(item)
        if labeled:
            uniq = []
            for item in labeled:
                if item not in uniq:
                    uniq.append(item)
            lines.append("Téléphones : %s" % " ; ".join(uniq))
        addrs = self._cq_all_addresses()
        if addrs:
            lines.append("Adresses : %s" % " ; ".join(addrs))
        if (self.email or "").strip():
            lines.append("Email : %s" % self.email.strip())
        return "\n".join(lines)

    def _cq_rdv_contact_block_html(self):
        self.ensure_one()
        return "<br/>".join(
            html_escape(line) for line in self._cq_rdv_contact_block().split("\n")
        )

    def _cq_ensure_contact_partner(self):
        """Contact personne (prénom/nom/tél) — invité du RDV, pas seulement l’établissement."""
        self.ensure_one()
        Partner = self.env["res.partner"].sudo()
        company = False
        if hasattr(self, "_ensure_partner"):
            company = self._ensure_partner()
        elif self.partner_id:
            company = self.partner_id
        display = self._cq_contact_display_name()
        phones = self._cq_all_phones()
        addrs = self._cq_all_addresses()
        street = self.street or (
            self.address_ids[:1].street if self.address_ids else False
        )
        city = self.city or (self.address_ids[:1].city if self.address_ids else False)
        if company:
            upd = {}
            if self.phone and company.phone != self.phone:
                upd["phone"] = self.phone
            if self.email and not company.email:
                upd["email"] = self.email
            if street and not company.street:
                upd["street"] = street
            if city and not company.city:
                upd["city"] = city
            extra = []
            if len(phones) > 1:
                extra.append("Autres tél. : %s" % " ; ".join(phones[1:]))
            if len(addrs) > 1:
                extra.append("Autres adresses : %s" % " ; ".join(addrs[1:]))
            if extra:
                note = company.comment or ""
                block = "\n".join(extra)
                if block not in note:
                    upd["comment"] = ((note + "\n") if note else "") + block
            if upd:
                company.write(upd)
        person_name = display or (self.name or "").strip()
        if not person_name:
            return company
        # Pas de doublon personne = établissement
        if company and person_name == (company.name or "").strip():
            return company
        person = False
        if company:
            person = company.child_ids.filtered(
                lambda p: (p.name or "").strip() == person_name
            )[:1]
        if not person and (self.email or phones):
            domain = [("is_company", "=", False)]
            if self.email:
                person = Partner.search(
                    domain + [("email", "=ilike", self.email.strip())], limit=1
                )
            if not person and phones:
                tail = "".join(ch for ch in phones[0] if ch.isdigit())[-10:]
                if tail:
                    for cand in Partner.search(
                        domain + [("phone", "!=", False)], limit=80
                    ):
                        digits = "".join(
                            ch for ch in (cand.phone or "") if ch.isdigit()
                        )
                        if digits[-10:] == tail:
                            person = cand
                            break
        vals = {
            "name": person_name,
            "phone": phones[0] if phones else False,
            "email": (self.email or "").strip() or False,
            "street": street or False,
            "city": city or False,
            "type": "contact",
            "is_company": False,
        }
        if len(phones) > 1:
            extra_tel = "Autres tél. : %s" % " ; ".join(phones[1:])
            vals["comment"] = extra_tel
        if company:
            vals["parent_id"] = company.id
        if person:
            person.write({k: v for k, v in vals.items() if v and k != "parent_id"})
        else:
            person = Partner.create(vals)
        if company and not self.partner_id:
            self.sudo().write({"partner_id": company.id})
        return person

    def _cq_split_existing_contact_names(self):
        """Découpe contact_name → prénom / nom pour les fiches déjà là."""
        for rec in self:
            if rec.contact_firstname or rec.contact_lastname:
                continue
            raw = (rec.contact_name or "").strip()
            if not raw:
                continue
            parts = raw.split(None, 1)
            rec.with_context(cq_skip_contact_split=True).write(
                {
                    "contact_firstname": parts[0],
                    "contact_lastname": parts[1] if len(parts) > 1 else False,
                }
            )

    @api.model
    def _cq_find_for_booking(self, email=None, phone=None):
        rec = super()._cq_find_for_booking(email=email, phone=phone)
        if rec:
            return rec
        digits = "".join(ch for ch in (phone or "") if ch.isdigit())
        if digits and len(digits) >= 10:
            tail = digits[-10:]
            Phone = self.env["coins.quebec.partenariat.phone"].sudo()
            for line in Phone.search([("phone", "!=", False)]):
                rec_digits = "".join(ch for ch in (line.phone or "") if ch.isdigit())
                parent = line.partenariat_id
                if (
                    rec_digits
                    and rec_digits[-10:] == tail
                    and parent
                    and parent.active
                ):
                    return parent
        return self.browse()
