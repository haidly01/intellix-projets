# -*- coding: utf-8 -*-
import datetime

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from odoo.addons.people_engine.services.disciplinary_config import DELAIS_LEGAUX_MAROC


class PeDisciplinaryProcedure(models.Model):
    _name = "pe.disciplinary.procedure"
    _description = "Procédure disciplinaire"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date_ouverture desc, id desc"

    name = fields.Char(
        string="Référence",
        required=True,
        copy=False,
        default=lambda self: self.env["ir.sequence"].next_by_code("pe.disciplinary.procedure")
        or "PROC",
    )
    employee_id = fields.Many2one("hr.employee", required=True, index=True, tracking=True)
    superviseur_id = fields.Many2one("hr.employee", string="Superviseur", tracking=True)
    incident_ids = fields.One2many("pe.disciplinary.incident", "procedure_id", string="Incidents")
    incident_id = fields.Many2one("pe.disciplinary.incident", string="Incident principal")
    date_ouverture = fields.Date(
        string="Date ouverture",
        default=fields.Date.context_today,
        required=True,
    )
    type_sanction = fields.Selection(
        [
            ("avertissement_verbal", "Avertissement verbal"),
            ("avertissement_ecrit", "Avertissement écrit"),
            ("mise_en_demeure", "Mise en demeure"),
            ("mise_a_pied", "Mise à pied"),
            ("licenciement_faute_grave", "Licenciement faute grave"),
            ("licenciement_insuffisance", "Licenciement insuffisance pro."),
        ],
        required=True,
        tracking=True,
    )
    statut = fields.Selection(
        [
            ("draft", "Brouillon"),
            ("convocation", "Convocation envoyée"),
            ("entretien", "Entretien préalable"),
            ("sanction", "Sanction appliquée"),
            ("closed", "Clôturée"),
            ("cancelled", "Annulée"),
        ],
        default="draft",
        tracking=True,
    )
    date_convocation = fields.Date(string="Date convocation")
    date_entretien = fields.Date(
        string="Date entretien préalable",
        help="Minimum J+8 après convocation (Code du Travail Maroc Art. 62-63).",
    )
    date_sanction = fields.Date(string="Date sanction")
    recidive = fields.Boolean(string="Récidive", compute="_compute_recidive", store=True)
    recidive_count = fields.Integer(string="Incidents similaires 30 j", compute="_compute_recidive", store=True)
    prescription_ok = fields.Boolean(
        string="Prescription respectée",
        compute="_compute_prescription_ok",
        store=True,
    )
    description_faits = fields.Text(string="Faits reprochés", required=True)
    impact_paie = fields.Boolean(string="Impact paie")
    jours_mise_a_pied = fields.Integer(string="Jours mise à pied")
    heures_deduction = fields.Float(string="Heures déduction paie")
    paie_impact_id = fields.Many2one("pe.payroll.bulletin", string="Bulletin impacté", readonly=True)
    montant_impact_paie = fields.Float(string="Montant impact paie", readonly=True)
    lettre_ids = fields.One2many("pe.disciplinary.letter", "procedure_id", string="Lettres")
    lettre_count = fields.Integer(compute="_compute_lettre_count")
    legal_article_id = fields.Many2one("pe.legal.article", string="Article juridique")
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company)

    @api.depends("lettre_ids")
    def _compute_lettre_count(self):
        for rec in self:
            rec.lettre_count = len(rec.lettre_ids)

    @api.depends("incident_ids.type_incident", "incident_id")
    def _compute_recidive(self):
        svc = self.env["pe.disciplinary.service"].sudo()
        for rec in self:
            main_type = rec.incident_id.type_incident if rec.incident_id else False
            if not main_type and rec.incident_ids:
                main_type = rec.incident_ids[0].type_incident
            count = svc.count_incidents_30d(rec.employee_id.id, main_type) if main_type else 0
            rec.recidive_count = count
            rec.recidive = count > 1

    @api.depends("date_ouverture", "incident_id.date_incident")
    def _compute_prescription_ok(self):
        today = fields.Date.today()
        for rec in self:
            ref_date = rec.date_ouverture
            if rec.incident_id and rec.incident_id.date_incident:
                ref_date = rec.incident_id.date_incident.date()
            if not ref_date:
                rec.prescription_ok = True
                continue
            days = (today - ref_date).days
            rec.prescription_ok = days <= 30

    @api.model_create_multi
    def create(self, vals_list):
        svc = self.env["pe.disciplinary.service"].sudo()
        for vals in vals_list:
            if vals.get("type_sanction"):
                svc.enforce_human_validation(vals["type_sanction"], "créer la procédure")
        records = super().create(vals_list)
        for rec, vals in zip(records, vals_list):
            incident = rec.incident_id
            if incident:
                incident.write({"procedure_id": rec.id, "statut": "procedure"})
            for inc in rec.incident_ids:
                if inc.id != (incident.id if incident else 0):
                    inc.write({"procedure_id": rec.id, "statut": "procedure"})
        return records

    def action_send_convocation(self):
        self.ensure_one()
        svc = self.env["pe.disciplinary.service"].sudo()
        letter = svc.generate_letter(self, "convocation")
        conv_date = fields.Date.today()
        entretien_date = conv_date + datetime.timedelta(
            days=DELAIS_LEGAUX_MAROC["delai_min_convocation_entretien"]
        )
        self.write(
            {
                "statut": "convocation",
                "date_convocation": conv_date,
                "date_entretien": entretien_date,
            }
        )
        return letter.action_print_letter()

    def action_generate_avertissement(self):
        self.ensure_one()
        letter_type = (
            "avertissement_ecrit"
            if self.type_sanction in ("avertissement_ecrit", "mise_en_demeure")
            else "avertissement_verbal"
        )
        svc = self.env["pe.disciplinary.service"].sudo()
        letter = svc.generate_letter(self, letter_type)
        self.write({"statut": "sanction", "date_sanction": fields.Date.today()})
        return letter.action_print_letter()

    def action_apply_sanction(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Appliquer sanction"),
            "res_model": "pe.disciplinary.sanction.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_procedure_id": self.id},
        }

    def action_apply_payroll_impact(self):
        self.ensure_one()
        if not self.impact_paie:
            raise UserError(_("Cette procédure n'a pas d'impact paie activé."))
        svc = self.env["pe.disciplinary.service"].sudo()
        bulletin = svc.appliquer_impact_paie(self)
        self.write({"paie_impact_id": bulletin.id})
        return {
            "type": "ir.actions.act_window",
            "name": _("Bulletin impacté"),
            "res_model": "pe.payroll.bulletin",
            "res_id": bulletin.id,
            "view_mode": "form",
        }

    def action_view_letters(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Lettres disciplinaires"),
            "res_model": "pe.disciplinary.letter",
            "view_mode": "list,form",
            "domain": [("procedure_id", "=", self.id)],
            "context": {"default_procedure_id": self.id, "default_employee_id": self.employee_id.id},
        }

    def action_close(self):
        self.write({"statut": "closed"})
        self.incident_ids.filtered(lambda i: i.statut == "procedure").write({"statut": "clos"})
