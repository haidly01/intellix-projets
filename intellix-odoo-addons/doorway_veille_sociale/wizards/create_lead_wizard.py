# -*- coding: utf-8 -*-
from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError

PIPELINE_TEAM_XMLIDS = {
    "renovation": "renovation_conciergerie.crm_team_renovation",
    "driven": "renovation_conciergerie.crm_team_driven",
    "marketing": "renovation_conciergerie.crm_team_marketing",
}

STAGE_VEILLE_NAME = "Nouveau lead — Veille sociale"
STAGE_FALLBACK_NAME = "Réseaux Sociaux"


class CreateLeadWizard(models.TransientModel):
    _name = "doorway.create.lead.wizard"
    _description = "Créer un lead CRM depuis un signal de veille"

    signal_id = fields.Many2one(
        "doorway.veille.signal", string="Signal", required=True, ondelete="cascade"
    )
    nom_prospect = fields.Char(string="Nom du prospect", required=True)
    pipeline_type = fields.Selection(
        [
            ("renovation", "Rénovation"),
            ("driven", "Driven"),
            ("marketing", "Marketing"),
        ],
        string="Pipeline",
        default="renovation",
        required=True,
    )
    type_projet = fields.Char(string="Type de projet")
    priorite = fields.Selection(
        [
            ("0", "Normale"),
            ("1", "Basse"),
            ("2", "Haute"),
            ("3", "Très haute"),
        ],
        string="Priorité",
        default="2",
    )
    notes = fields.Text(string="Notes")
    assigner_a = fields.Many2one("res.users", string="Assigner à")

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        signal = self.env["doorway.veille.signal"].browse(
            self.env.context.get("default_signal_id")
        )
        if signal:
            res.setdefault("signal_id", signal.id)
            res.setdefault("nom_prospect", signal.auteur or signal.titre or _("Prospect veille"))
            res.setdefault("type_projet", signal.type_projet)
            note_parts = []
            if signal.resume:
                note_parts.append(signal.resume)
            if signal.action_suggeree:
                note_parts.append(signal.action_suggeree)
            res.setdefault("notes", "\n".join(note_parts))
            if signal.temperature == "hot":
                res.setdefault("priorite", "3")
            elif signal.temperature == "warm":
                res.setdefault("priorite", "2")
        return res

    def _resolve_team(self):
        self.ensure_one()
        xmlid = PIPELINE_TEAM_XMLIDS.get(self.pipeline_type)
        if xmlid:
            team = self.env.ref(xmlid, raise_if_not_found=False)
            if team:
                return team
        return self.env["crm.team"].search([], limit=1)

    def _resolve_stage(self, team):
        Stage = self.env["crm.stage"].sudo()
        for name in (STAGE_VEILLE_NAME, STAGE_FALLBACK_NAME):
            stage = Stage.search(
                [("name", "=", name), ("team_ids", "in", team.id)],
                limit=1,
            )
            if stage:
                return stage
        return Stage.search([("team_ids", "in", team.id)], order="sequence", limit=1)

    def _build_chatter_body(self):
        self.ensure_one()
        signal = self.signal_id
        parts = ["<p><b>Lead créé depuis la veille sociale</b></p>"]
        if signal.resume:
            parts.append("<p><b>Résumé IA :</b> %s</p>" % signal.resume)
        if signal.texte:
            parts.append("<p><b>Texte original :</b><br/>%s</p>" % (signal.texte or ""))
        if signal.url:
            parts.append(
                '<p><a href="%s" target="_blank">Source</a></p>' % signal.url
            )
        if signal.plateforme or signal.source:
            parts.append(
                "<p><b>Source :</b> %s / %s</p>"
                % (signal.plateforme or "", signal.source or "")
            )
        if self.notes:
            parts.append("<p><b>Notes :</b><br/>%s</p>" % self.notes)
        return Markup("".join(parts))

    def action_creer_lead(self):
        self.ensure_one()
        signal = self.signal_id
        if signal.statut == "cree_odoo" and signal.odoo_lead_id:
            return {
                "type": "ir.actions.act_window",
                "name": _("Lead CRM"),
                "res_model": "crm.lead",
                "view_mode": "form",
                "res_id": signal.odoo_lead_id.id,
                "target": "current",
            }

        team = self._resolve_team()
        if not team:
            raise UserError(_("Aucune équipe CRM disponible."))

        lead = self.signal_id._create_crm_lead(
            pipeline_type=self.pipeline_type,
            assign_user=self.assigner_a,
            name=self.nom_prospect,
            notes=self.notes,
            priorite=self.priorite,
        )

        return {
            "type": "ir.actions.act_window",
            "name": _("Lead CRM"),
            "res_model": "crm.lead",
            "view_mode": "form",
            "res_id": lead.id,
            "target": "current",
        }

    def action_ignorer_signal(self):
        """Ferme le wizard et ignore le signal sans créer de lead."""
        self.ensure_one()
        self.signal_id.action_ignorer()
        return {"type": "ir.actions.act_window_close"}

