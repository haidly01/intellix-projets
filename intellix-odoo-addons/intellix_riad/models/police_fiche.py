# -*- coding: utf-8 -*-

import logging

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

RETENTION_YEARS = 2


class IntellixRiadPoliceFiche(models.Model):
    _name = "intellix.riad.police.fiche"
    _description = "Fiche de police — bulletin individuel de voyageur"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "check_in desc, id desc"

    name = fields.Char(string="Référence", default="Nouveau", copy=False)
    establishment_id = fields.Many2one(
        "intellix.riad.establishment",
        required=True,
        ondelete="restrict",
        index=True,
        tracking=True,
    )
    reservation_id = fields.Many2one(
        "coins.reservation",
        string="Réservation",
        required=True,
        ondelete="restrict",
        index=True,
    )
    sequence = fields.Integer(default=1)
    lastname = fields.Char(string="Nom", tracking=True)
    firstname = fields.Char(string="Prénom", tracking=True)
    birth_date = fields.Date(string="Date de naissance")
    birth_place = fields.Char(string="Lieu de naissance")
    nationality_id = fields.Many2one("res.country", string="Nationalité")
    is_moroccan = fields.Boolean(compute="_compute_is_moroccan", store=True)
    requires_fiche = fields.Boolean(compute="_compute_is_moroccan", store=True)
    passport_number = fields.Char(string="N° de passeport")
    id_document_type = fields.Selection(
        [
            ("passport", "Passeport"),
            ("cin", "CIN (Maroc)"),
        ],
        string="Type de pièce",
    )
    entry_date = fields.Date(string="Date d'entrée au Maroc")
    check_in = fields.Date(related="reservation_id.check_in", store=True)
    check_out = fields.Date(related="reservation_id.check_out", store=True)
    stay_nights = fields.Integer(related="reservation_id.nights", store=True)
    establishment_address = fields.Char(
        compute="_compute_establishment_address",
        store=True,
    )
    phone = fields.Char(string="Téléphone mobile")
    email = fields.Char(string="Adresse électronique")
    passport_image = fields.Binary(string="Photo du passeport", attachment=True)
    passport_filename = fields.Char()
    signature_image = fields.Binary(string="Signature manuscrite", attachment=True)
    signature_id = fields.Many2one(
        "pe.electronic.signature",
        string="Signature électronique",
        copy=False,
        ondelete="set null",
    )
    signed_at = fields.Datetime(string="Signée le", readonly=True)
    signed_ip = fields.Char(string="IP de signature", readonly=True)
    state = fields.Selection(
        [
            ("draft", "À compléter"),
            ("ready", "Prête à transmettre"),
            ("completed", "Fiche complétée"),
            ("exported", "Transmise"),
            ("not_required", "Non applicable (résident marocain)"),
        ],
        default="draft",
        tracking=True,
        required=True,
    )
    exported_at = fields.Datetime(string="Transmise le", readonly=True)
    retention_until = fields.Date(
        string="Conserver jusqu'au",
        compute="_compute_retention_until",
        store=True,
        help="Conservation minimale de 2 ans. Aucune suppression automatique.",
    )
    missing_fields = fields.Char(compute="_compute_missing_fields")

    @api.depends("nationality_id", "nationality_id.code", "id_document_type")
    def _compute_is_moroccan(self):
        for rec in self:
            code = (rec.nationality_id.code or "").upper()
            rec.is_moroccan = code == "MA" or rec.id_document_type == "cin"
            rec.requires_fiche = bool(rec.nationality_id or rec.id_document_type) and not rec.is_moroccan

    @api.depends("establishment_id", "establishment_id.property_id")
    def _compute_establishment_address(self):
        for rec in self:
            prop = rec.establishment_id.property_id
            bits = [prop.street, prop.city, rec.establishment_id.name or prop.name]
            rec.establishment_address = ", ".join([b for b in bits if b]) or ""

    @api.depends("check_in")
    def _compute_retention_until(self):
        for rec in self:
            day = rec.check_in or fields.Date.context_today(rec)
            rec.retention_until = day + relativedelta(years=RETENTION_YEARS)

    @api.depends(
        "lastname",
        "firstname",
        "birth_date",
        "birth_place",
        "nationality_id",
        "passport_number",
        "entry_date",
        "phone",
        "email",
        "is_moroccan",
    )
    def _compute_missing_fields(self):
        labels = {
            "lastname": _("Nom"),
            "firstname": _("Prénom"),
            "birth_date": _("Date de naissance"),
            "birth_place": _("Lieu de naissance"),
            "nationality_id": _("Nationalité"),
            "passport_number": _("N° de passeport"),
            "entry_date": _("Date d'entrée au Maroc"),
            "phone": _("Téléphone"),
            "email": _("E-mail"),
        }
        for rec in self:
            if rec.is_moroccan:
                rec.missing_fields = False
                continue
            missing = [labels[f] for f in labels if not rec[f]]
            rec.missing_fields = ", ".join(missing) if missing else False

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            if rec.name == "Nouveau" or not rec.name:
                rec.name = self.env["ir.sequence"].next_by_code(
                    "intellix.riad.police.fiche"
                ) or ("FP/%s" % rec.id)
            rec._sync_state()
        return records

    def write(self, vals):
        res = super().write(vals)
        if not self.env.context.get("riad_skip_police_state"):
            self._sync_state()
        return res

    def _sync_state(self):
        for rec in self:
            if rec.state in ("exported", "completed"):
                continue
            if rec.is_moroccan:
                rec.with_context(riad_skip_police_state=True).state = "not_required"
                continue
            if rec.requires_fiche and not rec.missing_fields:
                rec.with_context(riad_skip_police_state=True).state = "ready"
            elif rec.state not in ("draft", "not_required"):
                rec.with_context(riad_skip_police_state=True).state = "draft"

    def _get_signature_html(self):
        """Résumé affiché sur /sign/contract/<token> (PE)."""
        self.ensure_one()
        check_in = self.check_in.strftime("%d/%m/%Y") if self.check_in else "—"
        check_out = self.check_out.strftime("%d/%m/%Y") if self.check_out else "—"
        return (
            "<div style='font-family:Georgia,serif;color:#241A12;'>"
            "<p><b>Fiche de police</b> — %s</p>"
            "<p>%s %s · %s</p>"
            "<p>Arrivée %s — Départ %s</p>"
            "<p>Passeport %s</p>"
            "</div>"
        ) % (
            self.establishment_id.name or "",
            self.firstname or "",
            self.lastname or "",
            self.nationality_id.name or "",
            check_in,
            check_out,
            self.passport_number or "—",
        )

    def _on_electronic_signed(self, signature):
        """Callback PE après OTP : la fiche passe à « Fiche complétée »."""
        for rec in self:
            rec.with_context(riad_skip_police_state=True).write(
                {
                    "state": "completed",
                    "signed_at": signature.signed_at,
                    "signed_ip": signature.signed_ip,
                    "signature_id": signature.id,
                }
            )
            if rec.reservation_id:
                rec.reservation_id.riad_checkin_used_at = fields.Datetime.now()

    def action_create_signature_request(self):
        """Réutilise pe.electronic.signature — pas un second moteur."""
        self.ensure_one()
        if self.is_moroccan or not self.requires_fiche:
            raise UserError(
                _("Pas de signature fiche de police pour un résident marocain.")
            )
        if self.missing_fields:
            raise UserError(
                _("Complétez la fiche avant la signature : %s") % self.missing_fields
            )
        Signature = self.env["pe.electronic.signature"].sudo()
        if self.signature_id and self.signature_id.state in ("pending", "otp_sent"):
            return self.signature_id
        sig = Signature.create_for_document(
            self,
            self.email or "",
            ("%s %s" % (self.firstname or "", self.lastname or "")).strip() or self.name,
            _("Fiche de police — %s") % (self.establishment_id.name or self.name),
            signer_phone=self.phone or "",
        )
        self.signature_id = sig.id
        return sig

    def action_mark_exported(self):
        for rec in self:
            if rec.is_moroccan:
                continue
            if rec.missing_fields:
                raise UserError(
                    _("Complétez la fiche %s avant de la marquer transmise : %s")
                    % (rec.name, rec.missing_fields)
                )
            rec.with_context(riad_skip_police_state=True).write(
                {
                    "state": "exported",
                    "exported_at": fields.Datetime.now(),
                }
            )
        return True

    def action_print(self):
        docs = self.filtered(lambda f: f.requires_fiche or f.state == "exported")
        if not docs:
            raise UserError(
                _("Aucune fiche à imprimer : les nationaux marocains ne sont pas concernés.")
            )
        return self.env.ref("intellix_riad.action_report_police_fiche").report_action(docs)

    def unlink(self):
        raise UserError(
            _(
                "Les fiches de police se conservent au moins 2 ans "
                "et ne peuvent pas être supprimées."
            )
        )
