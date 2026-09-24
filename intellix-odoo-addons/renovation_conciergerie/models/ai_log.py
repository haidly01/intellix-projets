from odoo import fields, models


class RenovationAiLog(models.Model):
    """Journal des appels IA (transparence / éthique).

    Chaque appel au LLM est tracé : objet, utilisateur, modèle, résumé de la
    requête et de la réponse, consommation de tokens et statut.
    """

    _name = "renovation.ai.log"
    _description = "Journal des appels IA"
    _order = "create_date desc"
    _rec_name = "purpose"

    purpose = fields.Char(string="Objet", readonly=True)
    user_id = fields.Many2one(
        "res.users",
        string="Utilisateur",
        default=lambda self: self.env.user,
        readonly=True,
    )
    ai_provider = fields.Char(string="Fournisseur", readonly=True)
    model_used = fields.Char(string="Modèle", readonly=True)
    request_summary = fields.Text(string="Requête (résumé)", readonly=True)
    response_summary = fields.Text(string="Réponse (résumé)", readonly=True)
    input_tokens = fields.Integer(string="Tokens entrée", readonly=True)
    output_tokens = fields.Integer(string="Tokens sortie", readonly=True)
    status = fields.Selection(
        selection=[("success", "Succès"), ("error", "Erreur")],
        string="Statut",
        readonly=True,
    )
    error_message = fields.Text(string="Message d'erreur", readonly=True)
