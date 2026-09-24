from odoo import api, fields, models

GUIDE_HTML = """
<div class="o_project_ai_guide">
    <h2>🤖 Guide des fonctionnalités IA — Gestion de projet</h2>
    <div class="alert alert-info">
        <b>Prérequis :</b> activez l'IA dans
        <i>Paramètres → Rénovation Conciergerie → Intelligence Artificielle</i>,
        renseignez votre clé Anthropic, puis cliquez sur <b>Tester la connexion</b>.
        Sans clé, les fonctions « par charge / heuristiques » restent disponibles.
    </div>

    <h3>1. Génération de tâches par IA</h3>
    <p>Sur un projet, cliquez sur <b>Générer des tâches (IA)</b>, collez un brief,
    un e-mail ou un compte-rendu. L'IA propose une liste de tâches (titre, description,
    échéance, priorité, assigné). Vous <b>relisez et ajustez</b> avant de cliquer
    <b>Créer les tâches</b>. Rien n'est créé sans votre validation.</p>

    <h3>2. Assistant de tâche</h3>
    <p>Sur une tâche : <b>Résumer (IA)</b> synthétise la description et l'historique ;
    <b>Prochaines étapes (IA)</b> propose les actions à mener. Le résultat est publié
    dans le fil de discussion de la tâche.</p>

    <h3>3. Suggestion d'assignation</h3>
    <p>Sur une tâche, <b>Suggérer un assigné (IA)</b> recommande la personne la plus
    adaptée d'après l'<b>historique</b> : expérience sur des tâches similaires,
    ponctualité passée et charge actuelle. Le classement détaillé est publié dans le
    fil (transparence totale).</p>

    <h3>4. Alertes de retard</h3>
    <p>La colonne <b>Retard (j)</b> signale les tâches en retard dans les listes.
    Chaque jour, un automatisme alerte les assignés (note + activité) pour les tâches
    dont l'échéance est dépassée.</p>

    <h3>5. Analyse IA du projet (prédictif)</h3>
    <p>Sur un projet, <b>Analyse IA du projet</b> calcule la <b>santé</b>
    (Sur la bonne voie / À risque / Critique), une <b>date de fin estimée</b> basée
    sur la vélocité, et — avec l'IA — des <b>risques et recommandations</b>.
    Tout est consultable dans l'onglet <b>Analyse IA</b>.</p>

    <h3>6. Tâches depuis les e-mails</h3>
    <p>Dans l'onglet <b>Analyse IA</b> du projet, activez
    <b>Générer des tâches via l'IA depuis les e-mails</b>. Tout e-mail reçu sur
    l'alias du projet est alors transformé en sous-tâches automatiquement.</p>

    <h3>7. Mes recommandations IA</h3>
    <p>Menu <b>Projet → Mes recommandations IA</b> : votre tableau du jour (rythme,
    projet principal, tâches en retard / du jour / prioritaires) et un
    <b>plan d'action priorisé</b> personnalisé selon vos habitudes.</p>

    <h3>8. Webhook externe → tâches</h3>
    <p>Des outils externes (Zapier, Make, formulaires, autres agents IA) peuvent
    envoyer un brief par <code>POST</code> sur l'URL de webhook (voir Paramètres → IA).
    Exemple de charge utile JSON :</p>
    <pre>{
  "token": "VOTRE_TOKEN",
  "project_id": 12,
  "text": "Organiser le lancement produit : page web, e-mailing, relance presse",
  "source": "Zapier"
}</pre>
    <p>En-tête alternatif pour le token : <code>X-Project-AI-Token</code>.</p>

    <h3>9. Transparence &amp; éthique</h3>
    <p>Chaque appel à l'IA est journalisé dans <b>Rénovation → Journal IA</b>
    (utilisateur, objet, modèle, tokens, statut). Les suggestions de l'IA sont
    toujours <b>proposées</b> et restent sous votre contrôle : aucune décision
    automatique irréversible n'est prise sans validation humaine.</p>
</div>
"""


class ProjectAiHelp(models.TransientModel):
    _name = "project.ai.help"
    _description = "Aide & formation IA"

    content_html = fields.Html(string="Guide", readonly=True, sanitize=False)

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        values["content_html"] = GUIDE_HTML
        return values
