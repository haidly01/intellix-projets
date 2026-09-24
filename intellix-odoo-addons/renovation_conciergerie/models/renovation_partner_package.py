from odoo import api, fields, models
from odoo.exceptions import ValidationError


class RenovationPartnerPackage(models.Model):
    _name = "renovation.partner.package"
    _description = "Forfait partenaire rénovation"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date_start desc, id desc"

    name = fields.Char(compute="_compute_name", store=True, readonly=False)
    partner_id = fields.Many2one("res.partner", string="Partenaire", required=True, ondelete="cascade", tracking=True)
    partner_tag_ids = fields.Many2many(
        related="partner_id.category_id",
        string="Étiquettes partenaire",
    )
    package_type_id = fields.Many2one("renovation.package.type", string="Type de forfait", tracking=True)
    forfait_type_id = fields.Many2one(
        "renovation.forfait.type",
        string="Type de forfait",
        tracking=True,
        domain="[('secteur', '=', secteur)]",
    )
    @api.model
    def _default_secteur_tarif(self):
        return self.env["renovation.secteur.tarif"].search([("secteur", "=", "reno")], limit=1)

    secteur_tarif_id = fields.Many2one(
        "renovation.secteur.tarif",
        string="Secteur",
        default=_default_secteur_tarif,
    )
    secteur = fields.Selection(
        related="secteur_tarif_id.secteur",
        store=True,
    )
    category_ids = fields.Many2many(
        "renovation.service.category",
        "renovation_package_category_rel",
        "package_id", "category_id",
        string="Catégories de services",
    )
    state = fields.Selection([
        ("draft", "Brouillon"),
        ("active", "Actif"),
        ("expired", "Expiré"),
        ("cancelled", "Annulé"),
    ], default="draft", required=True, tracking=True)
    date_start = fields.Date(tracking=True)
    date_end = fields.Date(tracking=True)
    leads_total = fields.Integer(string="Leads inclus", default=0)
    leads_used = fields.Integer(string="Leads utilisés", default=0, tracking=True)
    credit_ids = fields.One2many(
        "renovation.forfait.credit",
        "forfait_id",
        string="Crédits",
    )
    credit_leads_total = fields.Integer(
        string="Leads crédités",
        compute="_compute_credit_leads_total",
        store=True,
    )
    credit_badge = fields.Char(
        string="Crédits",
        compute="_compute_credit_leads_total",
    )
    leads_remaining = fields.Integer(string="Leads restants", compute="_compute_leads_remaining", store=True)
    leads_remaining_pct = fields.Float(
        string="% leads restants",
        compute="_compute_exhaustion",
        store=True,
    )
    exhaustion_state = fields.Selection(
        [
            ("sain", "Actif — sain"),
            ("renouveler", "À renouveler bientôt"),
            ("epuise", "Épuisé"),
        ],
        string="Santé du forfait",
        compute="_compute_exhaustion",
        store=True,
        index=True,
    )
    alert_sent = fields.Boolean(string="Alerte envoyée", default=False)
    notes = fields.Html(translate=True)
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company)
    currency_id = fields.Many2one(
        related="company_id.currency_id",
        store=True,
    )
    forfait_prix = fields.Monetary(
        string="Prix",
        compute="_compute_forfait_prix",
        store=True,
        currency_field="currency_id",
    )
    en_pause = fields.Boolean(string="Partenaire en pause", default=False, tracking=True)
    pause_debut = fields.Date(string="Début de pause")
    pause_fin = fields.Date(string="Fin de pause")
    is_paused_now = fields.Boolean(
        string="En pause maintenant",
        compute="_compute_is_paused_now",
    )
    pause_badge = fields.Char(
        string="Pause",
        compute="_compute_is_paused_now",
    )

    # Région couverte (reliée à la fiche partenaire, modifiable depuis le forfait)
    coverage_mode = fields.Selection(
        related="partner_id.coverage_mode", readonly=False,
        string="Zone de couverture",
    )
    province_ids = fields.Many2many(
        related="partner_id.province_ids", readonly=False,
        string="Provinces desservies",
    )
    city_text = fields.Char(
        related="partner_id.city_text", readonly=False,
        string="Villes desservies",
    )
    coverage_radius_km = fields.Float(
        related="partner_id.coverage_radius_km", readonly=False,
        string="Rayon de couverture (km)",
    )
    postal_code_ids = fields.One2many(
        related="partner_id.postal_code_ids", readonly=False,
        string="Codes postaux desservis",
    )
    postal_codes_text = fields.Char(
        related="partner_id.postal_codes_text", readonly=False,
        string="Codes postaux (saisie rapide)",
    )

    @api.depends("credit_ids.nombre_leads")
    def _compute_credit_leads_total(self):
        for rec in self:
            rec.credit_leads_total = sum(rec.credit_ids.mapped("nombre_leads"))
            rec.credit_badge = "+%s" % rec.credit_leads_total

    @api.depends("leads_total", "leads_used", "credit_leads_total")
    def _compute_leads_remaining(self):
        for rec in self:
            rec.leads_remaining = (rec.leads_total or 0) + (rec.credit_leads_total or 0) - (rec.leads_used or 0)

    @api.depends(
        "leads_total",
        "secteur_tarif_id",
        "secteur_tarif_id.prix_par_lead",
        "forfait_type_id",
        "forfait_type_id.secteur",
    )
    def _compute_forfait_prix(self):
        Tarif = self.env["renovation.secteur.tarif"]
        tarifs = {t.secteur: t.prix_par_lead for t in Tarif.search([])}
        for rec in self:
            rate = rec.secteur_tarif_id.prix_par_lead if rec.secteur_tarif_id else 0
            if not rate:
                secteur = rec.forfait_type_id.secteur if rec.forfait_type_id else False
                rate = tarifs.get(secteur) or 0
            rec.forfait_prix = (rec.leads_total or 0) * (rate or 0)

    @api.depends("leads_total", "leads_used", "leads_remaining", "state", "credit_leads_total")
    def _compute_exhaustion(self):
        for rec in self:
            total = (rec.leads_total or 0) + (rec.credit_leads_total or 0)
            remaining = rec.leads_remaining if rec.leads_remaining is not False else 0
            rec.leads_remaining_pct = (remaining / total * 100.0) if total else 0.0
            if rec.state == "expired" or remaining <= 0:
                rec.exhaustion_state = "epuise"
            elif total and (remaining / total) <= 0.2:
                rec.exhaustion_state = "renouveler"
            else:
                rec.exhaustion_state = "sain"

    @api.depends("en_pause", "pause_debut", "pause_fin")
    def _compute_is_paused_now(self):
        today = fields.Date.context_today(self)
        for rec in self:
            rec.is_paused_now = rec._is_paused_on(today)
            rec.pause_badge = "En pause" if rec.is_paused_now else False

    def _is_paused_on(self, day):
        self.ensure_one()
        if self.en_pause:
            return True
        if self.pause_debut and self.pause_fin and self.pause_debut <= day <= self.pause_fin:
            return True
        return False

    def leads_restants(self):
        """Quota restant (crédits inclus). 0 si le partenaire est en pause."""
        self.ensure_one()
        if self._is_paused_on(fields.Date.context_today(self)):
            return 0
        return self.leads_remaining or 0

    def _has_available_leads(self):
        """Même garde-fou que la conso : leads_restants avant attribution."""
        self.ensure_one()
        return self.leads_restants() > 0

    @api.depends("partner_id", "package_type_id", "forfait_type_id")
    def _compute_name(self):
        for record in self:
            type_name = (
                record.forfait_type_id.name
                or (record.package_type_id.name if record.package_type_id else False)
            )
            if record.partner_id and type_name:
                record.name = f"{record.partner_id.name} — {type_name}"
            elif record.partner_id:
                record.name = record.partner_id.name
            else:
                record.name = False

    @api.onchange("secteur_tarif_id")
    def _onchange_secteur_tarif_id(self):
        if (
            self.forfait_type_id
            and self.secteur_tarif_id
            and self.forfait_type_id.secteur != self.secteur_tarif_id.secteur
        ):
            self.forfait_type_id = False

    @api.onchange("forfait_type_id")
    def _onchange_forfait_type_id(self):
        if not self.forfait_type_id:
            return
        ftype = self.forfait_type_id
        self.leads_total = ftype.leads_inclus
        self.category_ids = ftype.categories_services_ids
        if ftype.secteur:
            tarif = self.env["renovation.secteur.tarif"].search(
                [("secteur", "=", ftype.secteur)], limit=1
            )
            if tarif:
                self.secteur_tarif_id = tarif
        package_type = self._package_type_for_forfait(ftype)
        if package_type:
            self.package_type_id = package_type

    def _package_type_for_forfait(self, ftype):
        PackageType = self.env["renovation.package.type"]
        existing = PackageType.search([("name", "=", ftype.name)], limit=1)
        if existing:
            return existing
        return PackageType.create({
            "name": ftype.name,
            "leads_included": ftype.leads_inclus or 0,
        })

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            ftype_id = vals.get("forfait_type_id")
            if ftype_id and not vals.get("package_type_id"):
                ftype = self.env["renovation.forfait.type"].browse(ftype_id)
                vals["package_type_id"] = self._package_type_for_forfait(ftype).id
        return super().create(vals_list)

    @api.constrains("date_start", "date_end")
    def _check_dates(self):
        for record in self:
            if record.date_start and record.date_end and record.date_start > record.date_end:
                raise ValidationError("La date de fin doit être postérieure à la date de début.")

    @api.constrains("pause_debut", "pause_fin")
    def _check_pause_dates(self):
        for record in self:
            if record.pause_debut and record.pause_fin and record.pause_debut > record.pause_fin:
                raise ValidationError("La fin de pause doit être postérieure au début.")

    @api.constrains("leads_used", "leads_total", "credit_leads_total")
    def _check_leads_used(self):
        for record in self:
            cap = (record.leads_total or 0) + (record.credit_leads_total or 0)
            if cap and record.leads_used > cap:
                raise ValidationError("Le nombre de leads utilisés ne peut pas dépasser le quota inclus.")

    def action_consume_lead(self):
        for rec in self:
            if not rec._has_available_leads():
                if rec._is_paused_on(fields.Date.context_today(rec)):
                    raise ValidationError(
                        "Ce partenaire est en pause — aucun nouveau lead n'est attribué."
                    )
                raise ValidationError("Ce partenaire n'a plus de leads disponibles dans son forfait.")
            rec.leads_used += 1
            if rec.leads_remaining <= 2 and not rec.alert_sent:
                rec._send_renewal_alert()
                rec.alert_sent = True
        self._update_state_from_leads()

    def _send_renewal_alert(self):
        template = self.env.ref(
            "renovation_conciergerie.mail_template_renewal_alert",
            raise_if_not_found=False,
        )
        if template:
            template.send_mail(
                self.id,
                force_send=True,
                email_values={"email_to": "comptabilite@agencedoorway.com"},
            )

    def action_activate(self):
        self.write({"state": "active"})
        self._update_state_from_leads()

    def _update_state_from_leads(self):
        for rec in self:
            if rec.state == "active" and rec.leads_remaining <= 0:
                rec.state = "expired"

    def action_expire(self):
        self.write({"state": "expired"})

    def action_cancel(self):
        self.write({"state": "cancelled"})

    def action_set_draft(self):
        self.write({"state": "draft"})

    def action_view_package_leads(self):
        self.ensure_one()
        Assignment = self.env["renovation.lead.service.assignment"]
        leads = Assignment.search([("partner_id", "=", self.partner_id.id)]).mapped(
            "lead_id"
        )
        return {
            "type": "ir.actions.act_window",
            "name": "Leads du partenaire",
            "res_model": "crm.lead",
            "view_mode": "kanban,list,form",
            "domain": [("id", "in", leads.ids)],
            "context": {"default_partner_id": self.partner_id.id},
        }

    def action_send_welcome_email(self):
        template = self.env.ref(
            "renovation_conciergerie.mail_template_partner_package_welcome",
            raise_if_not_found=False,
        )
        if template:
            for record in self:
                template.send_mail(record.id, force_send=True)
        return True

    def action_create_reno_partner(self):
        cat = self.env.ref(
            "renovation_conciergerie.partner_category_reno_immo",
            raise_if_not_found=False,
        )
        return {
            "type": "ir.actions.act_window",
            "name": "Nouvel entrepreneur / agence partenaire",
            "res_model": "res.partner",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_is_company": True,
                "default_category_id": [(6, 0, cat.ids)] if cat else [],
            },
        }

    def action_add_credit(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Ajouter un crédit",
            "res_model": "renovation.forfait.credit",
            "view_mode": "form",
            "target": "new",
            "context": {"default_forfait_id": self.id},
        }

    def action_view_credits(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Crédits",
            "res_model": "renovation.forfait.credit",
            "view_mode": "list,form",
            "domain": [("forfait_id", "=", self.id)],
            "context": {"default_forfait_id": self.id},
        }
