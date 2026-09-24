# -*- coding: utf-8 -*-
from odoo import api, fields, models


class PeEmploymentContract(models.Model):
    _name = "pe.employment.contract"
    _description = "Contrat de travail IntelliX"
    _inherit = ["mail.thread", "mail.activity.mixin", "pe.variable.prime.mixin"]
    _order = "date_start desc, id desc"

    name = fields.Char(
        string="Référence",
        required=True,
        copy=False,
        default=lambda self: self.env["ir.sequence"].next_by_code("pe.employment.contract")
        or "CONTRAT",
    )
    employee_id = fields.Many2one(
        "hr.employee", required=True, index=True, tracking=True
    )
    profile_id = fields.Many2one(
        "pe.employee.profile",
        compute="_compute_profile",
        store=True,
    )
    contract_type = fields.Selection(
        [
            ("cdd", "CDD"),
            ("cdi", "CDI"),
            ("freelance", "Freelance"),
        ],
        string="Type",
        required=True,
        default="cdi",
        tracking=True,
    )
    date_start = fields.Date(string="Date début", required=True, tracking=True)
    date_end = fields.Date(string="Date fin", tracking=True)
    salaire_base = fields.Float(string="Salaire de base", tracking=True)
    montant_variable = fields.Float(
        string="Part variable (cible)",
        tracking=True,
        help="Montant variable cible ou estimé, dans la devise du contrat.",
    )
    taux_commission = fields.Float(
        string="Taux variable (%)",
        tracking=True,
        help="Pourcentage de commission ou part variable sur objectifs.",
    )
    description_variable = fields.Text(
        string="Description du variable",
        tracking=True,
        help="Structure de commission, plafond, critères d'attribution…",
    )
    type_remuneration = fields.Selection(
        related="profile_id.type_remuneration",
        store=True,
        readonly=False,
        string="Type rémunération",
    )
    devise = fields.Selection(
        [("MAD", "MAD"), ("EUR", "EUR"), ("USD", "USD"), ("CAD", "CAD")],
        default="MAD",
    )
    # --- Freelance ---
    taux_horaire_freelance = fields.Float(string="Taux horaire freelance")
    taux_journalier = fields.Float(string="TJM (taux journalier)")
    montant_forfait = fields.Float(string="Montant forfait")
    heures_forfait_min = fields.Float(string="Heures min. forfait")
    type_facturation = fields.Selection(
        [
            ("horaire", "Horaire"),
            ("journalier", "Journalier"),
            ("forfait", "Forfait"),
        ],
        string="Type facturation",
    )
    delai_paiement = fields.Integer(
        string="Délai paiement (jours)",
        default=30,
        help="Échéance = date émission + délai.",
    )
    ice_numero = fields.Char(string="ICE")
    rc_numero = fields.Char(string="RC")
    challenges_eligible = fields.Boolean(
        string="Éligible primes challenges",
        default=False,
    )
    prime_performance_base = fields.Float(
        string="Prime performance base (KPI)",
        help="Prime conditionnelle selon snapshots KPI hebdomadaires.",
    )
    is_freelance = fields.Boolean(compute="_compute_is_freelance", store=True)
    statut = fields.Selection(
        [
            ("draft", "Brouillon"),
            ("active", "Actif"),
            ("expired", "Expiré"),
            ("terminated", "Résilié"),
        ],
        default="draft",
        tracking=True,
        index=True,
    )
    modalite = fields.Selection(
        [
            ("call_center", "Call center"),
            ("bureau", "Bureau"),
            ("terrain", "Terrain"),
            ("mixte", "Mixte"),
        ],
        string="Modalité",
        default="call_center",
    )
    rib = fields.Char(string="RIB / IBAN")
    objectifs_text = fields.Html(
        string="Objectifs du poste",
        help="Objectifs contractuels et KPI qualitatifs inscrits au contrat.",
        sanitize=True,
    )
    description_poste = fields.Html(
        string="Description du poste",
        sanitize=True,
    )
    notes_rh = fields.Text(
        string="Notes internes RH",
        help="Notes internes, non visibles sur le document contractuel.",
    )
    lieu_travail = fields.Char(
        string="Lieu de travail",
        help="Site, bureau ou modalité précise (ex. Casablanca, télétravail).",
    )
    objective_ids = fields.One2many(
        "pe.objective",
        "contract_id",
        string="Objectifs mesurables",
    )
    objective_count = fields.Integer(compute="_compute_objective_count")
    profile_objective_ids = fields.One2many(
        related="profile_id.operational_objective_ids",
        string="Objectifs opérationnels (profil)",
    )
    company_id = fields.Many2one(
        "res.company",
        related="employee_id.company_id",
        store=True,
    )
    days_to_expiry = fields.Integer(compute="_compute_days_to_expiry")
    expiry_alert = fields.Boolean(compute="_compute_days_to_expiry")


    @api.depends("employee_id", "objective_ids", "profile_id.objective_ids")
    def _compute_objective_count(self):
        Objective = self.env["pe.objective"]
        for rec in self:
            if rec.profile_id:
                rec.objective_count = Objective.search_count(
                    [("profile_id", "=", rec.profile_id.id)]
                )
            else:
                rec.objective_count = len(rec.objective_ids)

    def action_apply_objective_template(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Appliquer modèle d'objectifs",
            "res_model": "pe.apply.objective.template.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_contract_id": self.id,
                "default_profile_id": self.profile_id.id if self.profile_id else False,
                "default_target": "contract",
            },
        }

    def action_save_objectives_as_template(self):
        self.ensure_one()
        objectives = self.objective_ids
        if not objectives:
            from odoo.exceptions import UserError

            raise UserError(
                "Aucun objectif contractuel à enregistrer. Ajoutez des objectifs ou appliquez un modèle."
            )
        return objectives.action_save_as_template()

    def action_view_objectives(self):
        self.ensure_one()
        domain = [("employee_id", "=", self.employee_id.id)]
        if self.profile_id:
            domain = ["|", ("contract_id", "=", self.id), ("profile_id", "=", self.profile_id.id)]
        return {
            "type": "ir.actions.act_window",
            "name": "Objectifs — %s" % (self.employee_id.name or self.name),
            "res_model": "pe.objective",
            "view_mode": "list,form",
            "domain": domain,
            "context": {
                "default_profile_id": self.profile_id.id if self.profile_id else False,
                "default_contract_id": self.id,
                "default_employee_id": self.employee_id.id,
            },
        }

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        employee_id = res.get("employee_id") or self.env.context.get("default_employee_id")
        if not employee_id:
            return res
        profile = self.env["pe.employee.profile"].search(
            [("employee_id", "=", employee_id)], limit=1
        )
        if not profile:
            return res
        if "description_poste" in fields_list and not res.get("description_poste"):
            parts = []
            if profile.job_id:
                parts.append("<p><strong>Poste :</strong> %s</p>" % profile.job_id.name)
            if profile.department_id:
                parts.append(
                    "<p><strong>Département :</strong> %s</p>"
                    % profile.department_id.name
                )
            if parts:
                res["description_poste"] = "".join(parts)
        if "objectifs_text" in fields_list and not res.get("objectifs_text"):
            if self.env.context.get("default_objectifs_text"):
                res["objectifs_text"] = self.env.context["default_objectifs_text"]
            elif self.env.context.get("copy_profile_objectives"):
                res["objectifs_text"] = profile._format_objectives_for_contract()
        return res

    @api.depends("contract_type")
    def _compute_is_freelance(self):
        for rec in self:
            rec.is_freelance = rec.contract_type == "freelance"

    @api.depends("employee_id")
    def _compute_profile(self):
        Profile = self.env["pe.employee.profile"]
        for rec in self:
            rec.profile_id = (
                Profile.search([("employee_id", "=", rec.employee_id.id)], limit=1).id
                if rec.employee_id
                else False
            )

    @api.depends("date_end", "contract_type", "statut")
    def _compute_days_to_expiry(self):
        today = fields.Date.today()
        for rec in self:
            rec.days_to_expiry = 0
            rec.expiry_alert = False
            if (
                rec.contract_type == "cdd"
                and rec.date_end
                and rec.statut == "active"
            ):
                rec.days_to_expiry = (rec.date_end - today).days
                rec.expiry_alert = 0 <= rec.days_to_expiry <= 30

    letter_html_preview = fields.Html(
        string="Aperçu contrat",
        compute="_compute_letter_html_preview",
        store=False,
    )
    contenu_html = fields.Html(
        string="Contenu contrat",
        help="Contenu éditable du contrat.",
    )

    def _compute_letter_html_preview(self):
        for rec in self:
            try:
                if rec.contenu_html:
                    rec.letter_html_preview = rec.contenu_html
                    continue
                template = self.env["pe.document.template"].search([
                    ("contract_subtype", "=", rec.contract_type),
                    ("active", "=", True),
                ], limit=1)
                profile = self.env["pe.employee.profile"].search([
                    ("employee_id", "=", rec.employee_id.id)
                ], limit=1)
                if template and profile:
                    html = template.render_letter_html(profile)
                    rec.letter_html_preview = html
                    if not rec.contenu_html:
                        rec.contenu_html = html
                else:
                    rec.letter_html_preview = "<p>Aperçu non disponible</p>"
            except Exception:
                rec.letter_html_preview = "<p>Aperçu non disponible</p>"

    def action_request_signature(self):
        """Crée une demande de signature électronique et envoie le lien."""
        self.ensure_one()
        employee = self.employee_id
        if not employee:
            from odoo.exceptions import UserError
            raise UserError("Aucun employé lié à ce contrat.")
        
        # Trouver email du signataire
        user = employee.sudo().user_id or False
        signer_email = (user and user.login) or employee.work_email or employee.private_email
        if not signer_email:
            from odoo.exceptions import UserError
            raise UserError("Aucun email trouvé pour cet employé.")
        
        signer_name = employee.name
        doc_name = self.name or ("Contrat " + (self.contract_type or "").upper())
        
        # Pré-remplir contenu_html si vide
        if not self.contenu_html:
            template = self.env["pe.document.template"].search([
                ("contract_subtype", "=", self.contract_type),
                ("active", "=", True),
            ], limit=1)
            profile = self.env["pe.employee.profile"].search([
                ("employee_id", "=", employee.id)
            ], limit=1)
            if template and profile:
                self.contenu_html = template.render_letter_html(profile)
        
        # Créer la demande de signature
        sig = self.env["pe.electronic.signature"].create_for_contract(
            self, signer_email, signer_name, doc_name
        )
        sig.action_send_signature_request()
        
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Demande de signature envoyée",
                "message": f"Lien de signature envoyé à {signer_email}",
                "type": "success",
                "sticky": False,
            },
        }

    def action_activate(self):
        for rec in self:
            others = self.search(
                [
                    ("employee_id", "=", rec.employee_id.id),
                    ("statut", "=", "active"),
                    ("id", "!=", rec.id),
                ]
            )
            others.write({"statut": "terminated"})
            rec.statut = "active"
            if rec.profile_id:
                profile_vals = {
                    "devise_remuneration": rec.devise,
                    "montant_variable": rec.montant_variable,
                    "taux_commission": rec.taux_commission,
                    "description_variable": rec.description_variable,
                    "variable_prime_template_id": rec.variable_prime_template_id.id,
                    "variable_prime_customize": rec.variable_prime_customize,
                }
                if rec.contract_type != "freelance" and rec.salaire_base:
                    profile_vals["salaire_base"] = rec.salaire_base
                rec.profile_id.sudo().write(profile_vals)

    def action_terminate(self):
        self.write({"statut": "terminated"})

    @api.model
    def cron_check_cdd_expiry(self):
        """Alerte CDD expirant sous 30 jours."""
        expiring = self.search(
            [
                ("contract_type", "=", "cdd"),
                ("statut", "=", "active"),
                ("expiry_alert", "=", True),
            ]
        )
        for contract in expiring:
            contract.message_post(
                body="⚠️ CDD expire dans %s jour(s) (%s)."
                % (contract.days_to_expiry, contract.date_end)
            )
        return True
