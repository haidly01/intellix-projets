# -*- coding: utf-8 -*-
import json
import logging

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
REQUEST_TIMEOUT = 60
COMMUNITY_PROJECT_NAME = "Gestion Communauté Doorway"
COMMUNITY_STAGES = ["Brouillon", "À publier", "Publié", "Archivé"]


class CommunityPost(models.Model):
    _name = "doorway.community.post"
    _description = "Publication / Action communauté"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date_publication desc"
    _rec_name = "titre_post"

    # Contenu
    plateforme = fields.Selection(
        [
            ("instagram", "Instagram"),
            ("facebook", "Facebook"),
            ("linkedin", "LinkedIn"),
            ("google_business", "Google Business"),
        ],
        string="Plateforme",
        default="instagram",
        required=True,
    )
    type_contenu = fields.Selection(
        [
            ("post", "Post"),
            ("story", "Story"),
            ("reel", "Reel"),
            ("reponse_commentaire", "Réponse commentaire"),
            ("reponse_dm", "Réponse DM"),
        ],
        string="Type de contenu",
        default="post",
        required=True,
    )
    titre_post = fields.Char(string="Titre")
    caption = fields.Text(string="Caption")
    hashtags = fields.Char(string="Hashtags")
    visuel_url = fields.Char(string="URL du visuel")

    # Planification
    date_publication = fields.Datetime(string="Date de publication")
    statut_publication = fields.Selection(
        [
            ("brouillon", "Brouillon"),
            ("approuve", "Approuvé"),
            ("publie", "Publié"),
            ("annule", "Annulé"),
        ],
        string="Statut",
        default="brouillon",
        tracking=True,
    )
    publie_par = fields.Many2one("res.users", string="Publié par")

    # Liens
    signal_id = fields.Many2one("doorway.veille.signal", string="Signal lié")
    lead_id = fields.Many2one("crm.lead", string="Lead lié")
    task_id = fields.Many2one("project.task", string="Tâche projet liée")

    # IA
    genere_par_ia = fields.Boolean(string="Généré par IA")
    prompt_utilise = fields.Text(string="Prompt utilisé")

    # ------------------------------------------------------------------
    # Projet communauté
    # ------------------------------------------------------------------
    @api.model
    def get_community_project(self):
        """Renvoie (et crée si besoin) le projet 'Gestion Communauté Doorway'."""
        Project = self.env["project.project"].sudo()
        project = Project.search([("name", "=", COMMUNITY_PROJECT_NAME)], limit=1)
        if project:
            return project
        Stage = self.env["project.task.type"].sudo()
        stage_ids = []
        for seq, name in enumerate(COMMUNITY_STAGES, start=1):
            stage = Stage.create({"name": name, "sequence": seq})
            stage_ids.append(stage.id)
        project = Project.create(
            {
                "name": COMMUNITY_PROJECT_NAME,
                "type_ids": [(6, 0, stage_ids)],
            }
        )
        return project

    # ------------------------------------------------------------------
    # Génération IA
    # ------------------------------------------------------------------
    def action_generer_caption_ia(self):
        self.ensure_one()
        cfg = self.env["doorway.veille.config"].get_config()
        api_key, model = cfg.get_anthropic_credentials()
        if not api_key:
            raise UserError(
                _(
                    "Aucune clé API Anthropic configurée. "
                    "Renseignez-la dans Veille Sociale → Configuration."
                )
            )

        contexte = [
            "Plateforme : %s" % (self.plateforme or ""),
            "Type de contenu : %s" % (self.type_contenu or ""),
        ]
        if self.titre_post:
            contexte.append("Sujet : %s" % self.titre_post)
        if self.signal_id:
            contexte.append(
                "Signal d'origine : %s" % (self.signal_id.resume or self.signal_id.titre or "")
            )
            if self.signal_id.texte:
                contexte.append("Texte du signal : %s" % self.signal_id.texte[:600])

        system = (
            "Tu es le gestionnaire de communauté de l'Agence Doorway (rénovation "
            "résidentielle au Québec). Rédige un texte de publication engageant, "
            "professionnel et chaleureux en français québécois. Réponds uniquement "
            "avec le texte de la publication, sans préambule."
        )
        user_prompt = (
            "Rédige le contenu de cette publication.\n" + "\n".join(contexte)
        )

        payload = {
            "model": model,
            "max_tokens": 500,
            "system": system,
            "messages": [{"role": "user", "content": user_prompt}],
        }
        headers = {
            "x-api-key": api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        }
        try:
            response = requests.post(
                ANTHROPIC_URL,
                headers=headers,
                data=json.dumps(payload),
                timeout=REQUEST_TIMEOUT,
            )
            if response.status_code != 200:
                raise UserError(
                    _("Erreur API Claude : HTTP %s — %s")
                    % (response.status_code, response.text[:300])
                )
            data = response.json()
            parts = data.get("content") or []
            text = "".join(
                p.get("text", "") for p in parts if p.get("type") == "text"
            ).strip()
        except UserError:
            raise
        except Exception as error:  # noqa: BLE001
            _logger.warning("Génération caption IA impossible : %s", error)
            raise UserError(_("Échec de génération IA : %s") % error)

        self.caption = text
        self.genere_par_ia = True
        self.prompt_utilise = user_prompt
        return True
