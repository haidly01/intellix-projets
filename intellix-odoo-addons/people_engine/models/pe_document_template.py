# -*- coding: utf-8 -*-
from odoo import _, api, fields, models


class PeDocumentTemplate(models.Model):
    _name = "pe.document.template"
    _description = "Modèle — banque de documents RH"
    _inherit = ["mail.thread"]
    _order = "sequence, name"

    name = fields.Char(required=True, tracking=True)
    description = fields.Text()
    document_type = fields.Selection(
        [
            ("contract", "Contrat"),
            ("letter", "Lettre RH"),
            ("disciplinary", "Disciplinaire"),
            ("form", "Formulaire"),
            ("policy", "Politique / règlement"),
            ("procedure", "Procédure"),
            ("other", "Autre"),
        ],
        default="letter",
        required=True,
    )
    contract_subtype = fields.Selection(
        [
            ("cdd", "CDD"),
            ("cdi", "CDI"),
            ("freelance", "Freelance"),
            ("subcontract", "Sous-traitance"),
        ],
        string="Sous-type contrat",
    )
    disciplinary_letter_type = fields.Selection(
        [
            ("convocation", "Convocation entretien préalable"),
            ("avertissement_verbal", "Avertissement verbal"),
            ("avertissement_ecrit", "Avertissement écrit"),
            ("mise_en_demeure", "Mise en demeure"),
            ("mise_a_pied", "Notification mise à pied"),
            ("licenciement", "Notification licenciement"),
            ("solde_tout_compte", "Solde de tout compte"),
        ],
        string="Type lettre disciplinaire",
    )
    legal_article_id = fields.Many2one(
        "pe.legal.article",
        string="Modèle juridique",
        help="Article de la bibliothèque juridique source de ce modèle.",
    )
    stage_ids = fields.Many2many(
        "pe.employee.lifecycle.stage",
        "pe_document_template_stage_rel",
        "template_id",
        "stage_id",
        string="Stades applicables",
        help="Vide = disponible à tous les stades.",
    )
    attachment_id = fields.Many2one(
        "ir.attachment",
        string="Fichier modèle",
        domain="[('res_model', 'in', [False, 'pe.document.template'])]",
    )
    letter_html = fields.Html(
        string="Contenu du document",
        sanitize_attributes=False,
        help="Corps du document (lettre, contrat, politique…) avec variables : "
        "{{prenom}}, {{nom}}, {{name}}, {{date}}, {{poste}}, {{company}}, "
        "{{date_debut}}, [DATE], [PRÉNOM NOM], [TITRE DU POSTE], [DATE DE DÉBUT], etc.",
    )
    body_html = fields.Html(
        string="Message e-mail d'accompagnement",
        sanitize_attributes=False,
        help="Texte court personnalisable ajouté dans le courriel lors de l'envoi.",
    )
    is_arrival_pack = fields.Boolean(
        string="Pack d'arrivée",
        help="Inclus dans l'envoi rapide « Pack arrivée ».",
    )
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        "res.company",
        string="Organisation",
        default=lambda self: self.env.company,
    )
    document_count = fields.Integer(compute="_compute_document_count")
    supports_personalization = fields.Boolean(
        compute="_compute_document_capabilities",
        string="Personnalisable",
    )
    has_letter_content = fields.Boolean(
        compute="_compute_document_capabilities",
        string="Contenu HTML",
    )
    has_file_attachment = fields.Boolean(
        compute="_compute_document_capabilities",
        string="Fichier joint",
    )
    is_file_only = fields.Boolean(
        compute="_compute_document_capabilities",
        string="Fichier seul",
    )

    @api.depends("name")
    def _compute_document_count(self):
        data = self.env["pe.employee.document"].read_group(
            [("template_id", "in", self.ids)],
            ["template_id"],
            ["template_id"],
        )
        counts = {row["template_id"][0]: row["template_id_count"] for row in data}
        for rec in self:
            rec.document_count = counts.get(rec.id, 0)

    @api.depends("letter_html", "body_html", "attachment_id")
    def _compute_document_capabilities(self):
        for rec in self:
            rec.has_letter_content = bool(rec.letter_html)
            rec.has_file_attachment = bool(rec.attachment_id)
            rec.supports_personalization = bool(rec.letter_html or rec.body_html)
            rec.is_file_only = bool(rec.attachment_id and not rec.letter_html)

    def _applies_to_stage(self, stage):
        self.ensure_one()
        if not self.stage_ids:
            return True
        return stage in self.stage_ids

    def _letter_source_html(self):
        self.ensure_one()
        return self.letter_html or self.body_html or ""

    def _placeholder_service(self):
        from odoo.addons.people_engine.services.document_placeholder_service import (
            DocumentPlaceholderService,
        )

        return DocumentPlaceholderService(self.env)

    def render_document_html(self, profile, letter_date=None):
        """Contenu principal du document (PDF) — letter_html uniquement."""
        self.ensure_one()
        if not self.letter_html:
            return ""
        return self._placeholder_service().render(
            self.letter_html,
            profile,
            letter_date=letter_date,
        )

    def render_email_intro_html(self, profile, letter_date=None):
        """Message d'accompagnement courriel — body_html avec variables."""
        self.ensure_one()
        if not self.body_html:
            return ""
        return self._placeholder_service().render(
            self.body_html,
            profile,
            letter_date=letter_date,
        )

    def render_letter_html(self, profile, letter_date=None):
        """Contenu personnalisé : letter_html en priorité, sinon body_html."""
        self.ensure_one()
        source = self._letter_source_html()
        if not source:
            return ""
        return self._placeholder_service().render(
            source,
            profile,
            letter_date=letter_date,
        )

    def default_email_intro_html(self, profile, letter_date=None):
        """Intro courriel par défaut selon le type de modèle."""
        self.ensure_one()
        intro = self.render_email_intro_html(profile, letter_date=letter_date)
        if intro:
            return intro
        if self.is_file_only:
            return _(
                "<p>Bonjour,</p><p>Veuillez trouver ci-joint le document « %s ».</p>"
            ) % self.name
        return _(
            "<p>Bonjour,</p><p>Veuillez trouver ci-joint votre document personnalisé.</p>"
        )

    @api.model
    def search_for_stage(self, stage, arrival_pack_only=False):
        """Modèles actifs filtrés par stade (ou tous si stage_ids vide)."""
        domain = [("active", "=", True)]
        if arrival_pack_only:
            domain.append(("is_arrival_pack", "=", True))
        templates = self.search(domain)
        if not stage:
            return templates
        return templates.filtered(lambda t: t._applies_to_stage(stage))

    @api.model
    def default_template_for_stage(self, stage, arrival_pack_only=False):
        templates = self.search_for_stage(stage, arrival_pack_only=arrival_pack_only)
        if not templates:
            return self.browse()
        welcome = templates.filtered(lambda t: "bienvenue" in (t.name or "").lower())
        return welcome[:1] or templates[:1]

    @api.model
    def _catalog_stage_ids(self, codes):
        Stage = self.env["pe.employee.lifecycle.stage"].sudo()
        return Stage.search([("code", "in", codes)]).ids

    @api.model
    def _legal_article_html(self, code):
        article = self.env["pe.legal.article"].sudo().search([("code", "=", code)], limit=1)
        if not article or not article.content:
            return ""
        lines = [line.strip() for line in article.content.splitlines() if line.strip()]
        return "".join("<p>%s</p>" % line for line in lines)

    @api.model
    def _find_catalog_template(self, entry):
        Template = self.sudo()
        if entry.get("name_match"):
            found = Template.search(
                [("name", "ilike", entry["name_match"])], limit=1
            )
            if found:
                return found
        if entry.get("disciplinary_letter_type"):
            found = Template.search(
                [
                    ("disciplinary_letter_type", "=", entry["disciplinary_letter_type"]),
                    ("document_type", "=", entry.get("document_type", "disciplinary")),
                ],
                limit=1,
            )
            if found:
                return found
        if entry.get("contract_subtype"):
            found = Template.search(
                [("contract_subtype", "=", entry["contract_subtype"])], limit=1
            )
            if found:
                return found
        if entry.get("legal_code"):
            article = self.env["pe.legal.article"].sudo().search(
                [("code", "=", entry["legal_code"])], limit=1
            )
            if article:
                domain = [("legal_article_id", "=", article.id)]
                if entry.get("document_type"):
                    domain.append(("document_type", "=", entry["document_type"]))
                found = Template.search(domain, limit=1)
                if found:
                    return found
        return Template.browse()

    @api.model
    def sync_catalog_templates(self):
        """Assure la présence des modèles RH (contrats, lettres, disciplinaire)."""
        catalog = [
            {
                "name": "Contrat CDD",
                "document_type": "contract",
                "contract_subtype": "cdd",
                "stage_codes": ["arrival", "probation", "active"],
                "sequence": 50,
                "name_match": "Contrat CDD",
            },
            {
                "name": "Contrat CDI",
                "document_type": "contract",
                "contract_subtype": "cdi",
                "stage_codes": ["arrival", "probation", "active"],
                "sequence": 51,
                "name_match": "Contrat CDI",
            },
            {
                "name": "Contrat Freelance",
                "document_type": "contract",
                "contract_subtype": "freelance",
                "stage_codes": ["arrival", "probation", "active"],
                "sequence": 52,
                "name_match": "Contrat Freelance",
            },
            {
                "name": "Sous-traitance — Cahier des charges",
                "document_type": "letter",
                "contract_subtype": "subcontract",
                "stage_codes": ["active"],
                "sequence": 53,
                "name_match": "Sous-Traitance",
            },
            {
                "name": "Offre d'embauche",
                "document_type": "letter",
                "stage_codes": ["candidate", "arrival"],
                "sequence": 60,
                "name_match": "OFFRE D'EMBAUCHE",
            },
            {
                "name": "Lettre — Certificat de travail",
                "document_type": "letter",
                "legal_code": "MA-MDL-CERT",
                "stage_codes": ["departure"],
                "sequence": 70,
                "name_match": "CERTIFICAT DE TRAVAIL",
            },
            {
                "name": "Convocation entretien préalable",
                "document_type": "disciplinary",
                "legal_code": "MA-MDL-CONV",
                "disciplinary_letter_type": "convocation",
                "stage_codes": ["active"],
                "sequence": 80,
            },
            {
                "name": "Avertissement écrit",
                "document_type": "disciplinary",
                "legal_code": "MA-MDL-AVERT",
                "disciplinary_letter_type": "avertissement_ecrit",
                "stage_codes": ["active"],
                "sequence": 81,
            },
            {
                "name": "Mise en demeure",
                "document_type": "disciplinary",
                "legal_code": "MA-MDL-MED",
                "disciplinary_letter_type": "mise_en_demeure",
                "stage_codes": ["active"],
                "sequence": 82,
            },
            {
                "name": "Licenciement faute grave",
                "document_type": "disciplinary",
                "legal_code": "MA-MDL-LIC",
                "disciplinary_letter_type": "licenciement",
                "stage_codes": ["departure"],
                "sequence": 83,
            },
            {
                "name": "Attestation d'emploi",
                "document_type": "letter",
                "stage_codes": ["active", "departure"],
                "sequence": 90,
                "name_match": "ATTESTATION D'EMPLOI",
            },
            {
                "name": "Attestation de salaire",
                "document_type": "letter",
                "stage_codes": ["active"],
                "sequence": 91,
                "name_match": "ATTESTATION DE SALAIRE",
            },
            {
                "name": "Reçu pour solde de tout compte",
                "document_type": "letter",
                "stage_codes": ["departure"],
                "sequence": 92,
                "name_match": "SOLDE DE TOUT COMPTE",
            },
            {
                "name": "Lettre de recommandation",
                "document_type": "letter",
                "stage_codes": ["departure"],
                "sequence": 93,
                "name_match": "RECOMMANDATION",
            },
            {
                "name": "Avenant au contrat",
                "document_type": "letter",
                "stage_codes": ["active", "probation"],
                "sequence": 94,
                "name_match": "Avenant",
            },
            {
                "name": "Mise à pied conservatoire",
                "document_type": "disciplinary",
                "legal_code": "MA-MDL-AVERT",
                "disciplinary_letter_type": "mise_a_pied",
                "stage_codes": ["active"],
                "sequence": 95,
                "name_match": "MISE À PIED CONSERVATOIRE",
            },
            {
                "name": "Mise à pied disciplinaire",
                "document_type": "disciplinary",
                "legal_code": "MA-MDL-AVERT",
                "disciplinary_letter_type": "mise_a_pied",
                "stage_codes": ["active"],
                "sequence": 96,
                "name_match": "MISE À PIED DISCIPLINAIRE",
            },
        ]
        Template = self.sudo()
        Legal = self.env["pe.legal.article"].sudo()
        for entry in catalog:
            template = self._find_catalog_template(entry)
            article = (
                Legal.search([("code", "=", entry["legal_code"])], limit=1)
                if entry.get("legal_code")
                else Legal.browse()
            )
            stage_ids = (
                [(6, 0, self._catalog_stage_ids(entry["stage_codes"]))]
                if entry.get("stage_codes")
                else False
            )
            letter_html = self._legal_article_html(entry["legal_code"]) if article else ""
            vals = {
                "name": entry["name"],
                "document_type": entry["document_type"],
                "sequence": entry.get("sequence", 10),
                "contract_subtype": entry.get("contract_subtype") or False,
                "disciplinary_letter_type": entry.get("disciplinary_letter_type") or False,
                "legal_article_id": article.id if article else False,
            }
            if template:
                update_vals = {}
                metadata_fields = {
                    "document_type",
                    "contract_subtype",
                    "disciplinary_letter_type",
                    "legal_article_id",
                    "sequence",
                }
                for field, value in vals.items():
                    if field == "name":
                        continue
                    if field in metadata_fields:
                        if value and template[field] != value:
                            update_vals[field] = value
                    elif value and not template[field]:
                        update_vals[field] = value
                if stage_ids and not template.stage_ids:
                    update_vals["stage_ids"] = stage_ids
                if letter_html and not template.letter_html:
                    update_vals["letter_html"] = letter_html
                if update_vals:
                    template.write(update_vals)
            else:
                create_vals = dict(vals)
                if stage_ids:
                    create_vals["stage_ids"] = stage_ids
                if letter_html:
                    create_vals["letter_html"] = letter_html
                Template.create(create_vals)
        return True
