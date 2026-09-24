# -*- coding: utf-8 -*-
"""Cibles de backlinks WHITE-HAT + génération d'emails d'approche.

⚠️ Ce module ne fait AUCUNE génération automatisée de liens, aucun spam,
aucun envoi automatique. Il s'agit uniquement d'opportunités légitimes
(prospection) avec suivi de statut et brouillons d'emails d'approche.
"""
import logging

from odoo import fields, models

from ..services import claude_seo

_logger = logging.getLogger(__name__)


class SeoBacklinkTarget(models.Model):
    _name = "doorway.seo.backlink.target"
    _description = "Cible de backlink (white-hat) — SEO IA"
    _order = "id desc"

    workspace_id = fields.Many2one(
        "doorway.seo.workspace", string="Espace SEO", ondelete="cascade", index=True
    )
    name = fields.Char(string="Cible", required=True)
    target_type = fields.Selection(
        [
            ("blog_sectoriel", "Blog sectoriel"),
            ("partenaire", "Partenaire"),
            ("presse_locale", "Presse / média local"),
            ("page_ressource", "Page ressource"),
            ("annuaire", "Annuaire"),
            ("association", "Association"),
            ("evenement", "Événement"),
            ("institution", "Institution"),
            ("autre", "Autre"),
        ],
        string="Type",
        default="autre",
    )
    url = fields.Char(string="Site / URL")
    approach = fields.Text(string="Approche suggérée")
    rationale = fields.Text(string="Pertinence / autorité")

    status = fields.Selection(
        [
            ("a_contacter", "À contacter"),
            ("contacte", "Contacté"),
            ("obtenu", "Obtenu"),
            ("refuse", "Refusé"),
        ],
        string="Statut",
        default="a_contacter",
        required=True,
    )

    outreach_subject = fields.Char(string="Objet de l'email d'approche")
    outreach_body = fields.Text(string="Corps de l'email d'approche")
    mail_template_id = fields.Many2one("mail.template", string="Modèle d'email généré")
    last_error = fields.Text(string="Dernière erreur")

    # ------------------------------------------------------------------
    def _brief_dict(self):
        ws = self.workspace_id
        return {
            "business_name": ws.business_name or "",
            "niche": ws.niche or "",
            "geo": ws.geo or "",
            "description": ws.description or "",
            "language": ws.language or "fr",
            "website_url": ws.website_url or "",
        }

    def generate_outreach(self):
        """Génère (et stocke) un email d'approche + un mail.template idempotent."""
        self.ensure_one()
        target = {
            "name": self.name,
            "type": self.target_type,
            "url": self.url or "",
            "approach": self.approach or "",
            "rationale": self.rationale or "",
        }
        language = (self.workspace_id.language or "fr") if self.workspace_id else "fr"
        data, message = claude_seo.generate_outreach_email(
            self.env, self._brief_dict(), target, language=language
        )
        if data is None:
            self.write({"last_error": message})
            return self.read_dict()
        self.write(
            {
                "outreach_subject": data["subject"],
                "outreach_body": data["body"],
                "last_error": False,
            }
        )
        self._sync_mail_template(data)
        return self.read_dict()

    def _sync_mail_template(self, data):
        """Crée/MAJ un mail.template (+ doorway.message.template si présent)."""
        body_html = "<p>%s</p>" % (data["body"] or "").replace("\n", "<br/>")
        Template = self.env["mail.template"].sudo()
        model = self.env["ir.model"].sudo().search([("model", "=", "res.partner")], limit=1)
        vals = {
            "name": "[SEO Outreach] %s" % self.name,
            "subject": data["subject"] or ("Collaboration — %s" % self.name),
            "body_html": body_html,
            "model_id": model.id if model else False,
            "use_default_to": True,
            "auto_delete": False,
        }
        try:
            if self.mail_template_id and self.mail_template_id.exists():
                self.mail_template_id.write(vals)
            else:
                self.mail_template_id = Template.create(vals).id
        except Exception as exc:  # noqa: BLE001
            _logger.info("SEO IA : mail.template outreach non créé : %s", exc)

        # Intégration douce avec doorway_messaging si disponible.
        if self.env["ir.model"].sudo().search(
            [("model", "=", "doorway.message.template")], limit=1
        ):
            try:
                MsgTpl = self.env["doorway.message.template"].sudo()
                MsgTpl.create(
                    {
                        "name": "[SEO Outreach] %s" % self.name,
                        "canal": "email",
                        "sujet": vals["subject"],
                        "corps": body_html,
                        "corps_text": data["body"] or "",
                        "actif": True,
                    }
                )
            except Exception:  # noqa: BLE001
                _logger.info("SEO IA : doorway.message.template outreach ignoré")

    def set_status(self, status):
        valid = dict(self._fields["status"].selection)
        if status in valid:
            self.write({"status": status})
        return self.read_dict()

    def read_dict(self):
        self.ensure_one()
        return {
            "id": self.id,
            "name": self.name,
            "target_type": self.target_type,
            "url": self.url or "",
            "approach": self.approach or "",
            "rationale": self.rationale or "",
            "status": self.status,
            "outreach_subject": self.outreach_subject or "",
            "outreach_body": self.outreach_body or "",
            "mail_template_id": self.mail_template_id.id if self.mail_template_id else False,
            "last_error": self.last_error or "",
        }
