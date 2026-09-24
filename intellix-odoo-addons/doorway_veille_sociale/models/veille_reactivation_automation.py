# -*- coding: utf-8 -*-
from odoo import _, fields, models
from odoo.exceptions import ValidationError


class VeilleReactivationAutomation(models.Model):
    _name = "doorway.veille.reactivation.automation"
    _description = "Automatisation de réactivation douce (veille)"
    _order = "sequence, name"

    name = fields.Char(string="Nom", required=True)
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)
    action_type = fields.Selection(
        [
            ("reponse_douce", "Réponse douce (commentaire)"),
            ("like", "Like / Upvote"),
            ("tache", "Créer une tâche"),
            ("notification", "Notifier un utilisateur"),
        ],
        string="Action",
        required=True,
        default="reponse_douce",
    )
    delay_jours = fields.Integer(
        string="Délai après refroidissement (jours)",
        default=3,
        help="Nombre de jours après le passage en froid avant exécution.",
    )
    message_modele = fields.Text(
        string="Message (réponse douce)",
        default=(
            "Merci pour votre message ! N'hésitez pas si vous avez des questions "
            "sur la rénovation au Québec — on est là pour vous orienter."
        ),
    )
    source_filtre = fields.Selection(
        [
            ("all", "Toutes les sources"),
            ("reddit", "Reddit"),
            ("facebook", "Facebook"),
            ("instagram", "Instagram"),
            ("google_alerts", "Google Alerts"),
        ],
        string="Source",
        default="all",
    )
    auto_executer = fields.Boolean(
        string="Exécution automatique (cron)",
        default=False,
        help="Si activé, le cron applique cette règle aux signaux froids éligibles.",
    )
    notify_user_id = fields.Many2one(
        "res.users",
        string="Utilisateur à notifier",
        help="Pour l'action « Notifier un utilisateur ».",
    )
    tache_nom = fields.Char(
        string="Titre de tâche",
        default="Réactivation douce — signal veille",
    )
    signal_count = fields.Integer(compute="_compute_signal_count")

    def _compute_signal_count(self):
        Signal = self.env["doorway.veille.signal"]
        for rec in self:
            rec.signal_count = Signal.search_count(
                [("reactivation_automation_id", "=", rec.id)]
            )

    def action_voir_signaux(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Signaux — %s") % self.name,
            "res_model": "doorway.veille.signal",
            "view_mode": "list,form,kanban",
            "domain": [("reactivation_automation_id", "=", self.id)],
        }

    def _match_signal(self, signal):
        self.ensure_one()
        if self.source_filtre == "all":
            return True
        if self.source_filtre == "facebook":
            return signal.source in ("facebook", "instagram")
        return signal.source == self.source_filtre
