# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class PeCoachingCall(models.Model):
    _name = "pe.coaching.call"
    _description = "Analyse appel + coaching"
    _order = "date_appel desc"

    employee_id = fields.Many2one("hr.employee", required=True, index=True)
    date_appel = fields.Datetime(required=True, index=True)
    source = fields.Selection(
        [
            ("vicidial", "VICIdial (sortant)"),
            ("agent_ia", "Agent IA (entrant qualifié)"),
            ("twilio", "Twilio direct"),
        ]
    )
    vicidial_call_id = fields.Char(string="ID appel VICIdial")
    retell_call_id = fields.Char(string="ID appel Retell/ElevenLabs")
    duree_secondes = fields.Integer(string="Durée (secondes)")
    duree_affichee = fields.Char(compute="_compute_duree", store=True)
    numero_appele = fields.Char(string="Numéro appelé")
    lead_id = fields.Many2one("crm.lead")
    audio_url = fields.Char(string="URL enregistrement audio")
    transcript = fields.Text(string="Transcription")
    score_global = fields.Integer(string="Score global (/100)")
    score_accroche = fields.Integer(string="Accroche (/25)")
    score_qualification = fields.Integer(string="Qualification (/25)")
    score_gestion_objections = fields.Integer(
        string="Gestion objections (/25)"
    )
    score_closing = fields.Integer(string="Closing / transfert (/25)")
    points_positifs = fields.Text(string="Points positifs")
    points_ameliorer = fields.Text(string="Points à améliorer")
    conseil_claude = fields.Text(string="Conseil personnalisé Claude")
    note_manager = fields.Text(string="Note du manager")
    visible_employe = fields.Boolean(
        string="Visible par l'employé", default=True
    )
    lu_par_employe = fields.Boolean(string="Lu par l'employé", default=False)
    date_lecture = fields.Datetime()
    analyse_done = fields.Boolean(string="Analysé", default=False)

    @api.depends("duree_secondes")
    def _compute_duree(self):
        for rec in self:
            if rec.duree_secondes:
                m = rec.duree_secondes // 60
                s = rec.duree_secondes % 60
                rec.duree_affichee = "%s:%02d" % (m, s)
            else:
                rec.duree_affichee = "0:00"

    def action_marquer_lu(self):
        self.write(
            {
                "lu_par_employe": True,
                "date_lecture": fields.Datetime.now(),
            }
        )

    def action_analyser_claude(self):
        for rec in self.filtered("transcript"):
            rec._run_claude_analysis()

    def _run_claude_analysis(self):
        self.ensure_one()
        try:
            service = self.env["pe.claude.coaching.service"]
            result = service.analyze_call_transcript(self.transcript)
        except Exception as exc:  # noqa: BLE001
            _logger.warning("Claude call analysis failed: %s", exc)
            return False
        if not result:
            return False
        self.write(
            {
                "score_global": result.get("score_global", 0),
                "score_accroche": result.get("score_accroche", 0),
                "score_qualification": result.get("score_qualification", 0),
                "score_gestion_objections": result.get(
                    "score_gestion_objections", 0
                ),
                "score_closing": result.get("score_closing", 0),
                "points_positifs": result.get("points_positifs", ""),
                "points_ameliorer": result.get("points_ameliorer", ""),
                "conseil_claude": result.get("conseil", ""),
                "analyse_done": True,
            }
        )
        return True

    @api.model
    def analyser_appels_non_traites(self):
        pending = self.search(
            [
                ("transcript", "!=", False),
                ("analyse_done", "=", False),
            ],
            limit=50,
        )
        for rec in pending:
            rec._run_claude_analysis()
