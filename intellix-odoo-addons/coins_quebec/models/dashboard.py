# -*- coding: utf-8 -*-
from odoo import api, fields, models


class CoinsQuebecDashboard(models.TransientModel):
    _name = "coins.quebec.dashboard"
    _description = "Tableau de bord Coins Québec"
    _inherit = ["coins.quebec.cad.mixin"]
    _rec_name = "name"

    currency_id = fields.Many2one(
        "res.currency", default=lambda self: self._cq_cad().id, readonly=True
    )
    name = fields.Char(default="Tableau de bord", readonly=True)
    tax_label = fields.Char(
        string="Source",
        readonly=True,
        default="Fiches coins.quebec.partenariat · hors démo",
    )
    partenariat_count = fields.Integer(string="Partenariats", compute="_compute_cq_kpis")
    en_rdv_count = fields.Integer(string="En RDV", compute="_compute_cq_kpis")
    rdv_count = fields.Integer(string="RDV planifiés", compute="_compute_cq_kpis")
    rdv_upcoming_count = fields.Integer(string="RDV à venir", compute="_compute_cq_kpis")
    hebergement_count = fields.Integer(string="Hébergement", compute="_compute_cq_kpis")
    resto_count = fields.Integer(string="Restaurants", compute="_compute_cq_kpis")
    activite_count = fields.Integer(string="Activités", compute="_compute_cq_kpis")
    spa_count = fields.Integer(string="Spas", compute="_compute_cq_kpis")
    nouveau_count = fields.Integer(string="Nouveau", compute="_compute_cq_kpis")
    contacte_count = fields.Integer(string="Contacté", compute="_compute_cq_kpis")
    suivi_count = fields.Integer(string="Suivis partenariats", compute="_compute_cq_kpis")
    voyageur_count = fields.Integer(string="Voyageurs", compute="_compute_cq_kpis")
    present_count = fields.Integer(string="RDV validés Martin", compute="_compute_cq_kpis")
    # Tables ops (property / reservation / partner.activity) : souvent 0, pas le pipeline.
    property_count = fields.Integer(string="Biens module", compute="_compute_cq_kpis")
    reservation_count = fields.Integer(
        string="Réservations module", compute="_compute_cq_kpis"
    )
    ops_note = fields.Char(string="Note ops", compute="_compute_cq_kpis")

    def _cq_real_partenariat_domain(self):
        return [("is_demo", "=", False)]

    def _cq_collect_kpis(self):
        """Compteurs sur coins.quebec.partenariat uniquement (pas crm.lead)."""
        Part = self.env["coins.quebec.partenariat"]
        real = self._cq_real_partenariat_domain()
        now = fields.Datetime.now()

        def _count(extra=None):
            return Part.search_count(real + list(extra or []))

        property_count = self.env["coins.quebec.property"].search_count(
            [("is_demo", "=", False)]
        )
        reservation_count = self.env["coins.quebec.reservation"].search_count(
            [("is_demo", "=", False)]
        )
        if property_count or reservation_count:
            ops_note = (
                "Module biens/résas : %s biens · %s réservations (hors démo)."
                % (property_count, reservation_count)
            )
        else:
            ops_note = (
                "Aucun bien ni réservation hors démo dans coins.quebec.property / "
                "coins.quebec.reservation — les volumes ci-dessus viennent du pipeline."
            )
        return {
            "partenariat_count": _count(),
            "en_rdv_count": _count([("stage", "=", "en_rdv")]),
            "rdv_count": _count([("cq_rdv_event_id", "!=", False)]),
            "rdv_upcoming_count": _count(
                [
                    ("cq_rdv_event_id", "!=", False),
                    ("cq_rdv_event_id.active", "=", True),
                    ("cq_rdv_event_id.start", ">=", now),
                ]
            ),
            "hebergement_count": _count([("type_partenaire", "=", "hebergement")]),
            "resto_count": _count([("type_partenaire", "=", "resto")]),
            "activite_count": _count([("type_partenaire", "=", "activite")]),
            "spa_count": _count([("type_partenaire", "=", "spa")]),
            "nouveau_count": _count([("stage", "=", "nouveau")]),
            "contacte_count": _count([("stage", "=", "contacte")]),
            "suivi_count": _count([("stage", "=", "suivi")]),
            "voyageur_count": self._cq_voyageur_count(),
            "present_count": _count([("statut_presence", "=", "present")]),
            "property_count": property_count,
            "reservation_count": reservation_count,
            "ops_note": ops_note,
        }

    @api.depends()
    def _compute_cq_kpis(self):
        values = self._cq_collect_kpis()
        for rec in self:
            rec.partenariat_count = values["partenariat_count"]
            rec.en_rdv_count = values["en_rdv_count"]
            rec.rdv_count = values["rdv_count"]
            rec.rdv_upcoming_count = values["rdv_upcoming_count"]
            rec.hebergement_count = values["hebergement_count"]
            rec.resto_count = values["resto_count"]
            rec.activite_count = values["activite_count"]
            rec.spa_count = values["spa_count"]
            rec.nouveau_count = values["nouveau_count"]
            rec.contacte_count = values["contacte_count"]
            rec.suivi_count = values["suivi_count"]
            rec.voyageur_count = values["voyageur_count"]
            rec.present_count = values["present_count"]
            rec.property_count = values["property_count"]
            rec.reservation_count = values["reservation_count"]
            rec.ops_note = values["ops_note"]

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        res.update(
            {
                "name": "Tableau de bord",
                "currency_id": self._cq_cad().id,
                "tax_label": "Fiches coins.quebec.partenariat · hors démo",
            }
        )
        return res

    @api.model
    def action_open(self):
        wiz = self.create({})
        view = self.env.ref("coins_quebec.view_cq_dashboard_form")
        return {
            "type": "ir.actions.act_window",
            "name": "Tableau de bord Coins Québec",
            "res_model": "coins.quebec.dashboard",
            "res_id": wiz.id,
            "view_mode": "form",
            "view_id": view.id,
            "views": [(view.id, "form")],
            "target": "current",
            "path": "cq-dashboard",
        }

    def _cq_voyageur_teams(self):
        teams = self.env["crm.team"].sudo().browse()
        t = self.env.ref("coins_quebec.crm_team_cq_voyageurs", raise_if_not_found=False)
        if t:
            teams |= t
        extra = self.env["crm.team"].sudo().search(
            [("name", "ilike", "voyageur")]
        )
        return teams | extra

    def _cq_voyageur_count(self):
        native = self.env["coins.quebec.voyageur"].search_count([])
        if native:
            return native
        teams = self._cq_voyageur_teams()
        if not teams:
            return 0
        cq_teams = teams.filtered(
            lambda t: "québec" in (t.name or "").lower()
            or "quebec" in (t.name or "").lower()
        )
        Lead = self.env["crm.lead"]
        for group in (cq_teams, teams):
            if not group:
                continue
            n = Lead.search_count(
                [("team_id", "in", group.ids), ("active", "=", True)]
            )
            if n:
                return n
        return 0

    def action_open_properties(self):
        return self.env["ir.actions.act_window"]._for_xml_id(
            "coins_quebec.action_cq_property_action"
        )

    def action_open_reservations(self):
        return self.env["ir.actions.act_window"]._for_xml_id(
            "coins_quebec.action_cq_reservation_action"
        )

    def action_open_partners(self):
        return self.env["ir.actions.act_window"]._for_xml_id(
            "coins_quebec.action_cq_partner_action"
        )

    def _cq_open_partenariats(self, extra_domain=None, name=None):
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "coins_quebec.action_cq_pipeline_partenariats"
        )
        domain = list(self._cq_real_partenariat_domain())
        if extra_domain:
            domain = domain + list(extra_domain)
        action.update(
            {
                "name": name or "Partenariats Coins Québec",
                "display_name": name or "Partenariats Coins Québec",
                "res_model": "coins.quebec.partenariat",
                "path": "cq-partenariats",
                "domain": domain,
            }
        )
        return action

    def action_open_pipeline_partenariats(self):
        return self._cq_open_partenariats()

    def action_open_en_rdv(self):
        return self._cq_open_partenariats(
            [("stage", "=", "en_rdv")], "En RDV — Coins Québec"
        )

    def action_open_suivis(self):
        return self._cq_open_partenariats(
            [("stage", "=", "suivi")], "Suivis partenariats — Coins Québec"
        )

    def action_open_presents(self):
        return self._cq_open_partenariats(
            [("statut_presence", "=", "present")],
            "RDV validés Martin — Coins Québec",
        )

    def action_open_rdv(self):
        return self._cq_open_partenariats(
            [("cq_rdv_event_id", "!=", False)], "RDV planifiés — Coins Québec"
        )

    def action_open_hebergement(self):
        return self._cq_open_partenariats(
            [("type_partenaire", "=", "hebergement")],
            "Hébergement — Coins Québec",
        )

    def action_open_restos(self):
        return self._cq_open_partenariats(
            [("type_partenaire", "=", "resto")], "Restaurants — Coins Québec"
        )

    def action_open_activites(self):
        return self._cq_open_partenariats(
            [("type_partenaire", "=", "activite")], "Activités — Coins Québec"
        )

    def action_open_spas(self):
        return self._cq_open_partenariats(
            [("type_partenaire", "=", "spa")], "Spas — Coins Québec"
        )

    def action_open_pipeline_voyageurs(self):
        native = self.env["coins.quebec.voyageur"].search_count([])
        if native:
            action = self.env["ir.actions.act_window"]._for_xml_id(
                "coins_quebec.action_cq_pipeline_voyageurs"
            )
            action.update(
                {
                    "name": "Voyageurs Coins Québec",
                    "display_name": "Voyageurs Coins Québec",
                    "res_model": "coins.quebec.voyageur",
                    "path": "cq-voyageurs",
                    "domain": [],
                }
            )
            return action
        teams = self._cq_voyageur_teams()
        return {
            "type": "ir.actions.act_window",
            "name": "Voyageurs Coins Québec",
            "res_model": "crm.lead",
            "view_mode": "kanban,list,form",
            "domain": [("team_id", "in", teams.ids), ("active", "=", True)],
            "context": {"default_team_id": teams[:1].id if teams else False},
            "target": "current",
        }

    @api.model
    def _cq_detach_demo_leads(self):
        from ..hooks import (
            _detach_demo_crm_leads_from_cq_teams,
            _hide_legacy_crm_coins_quebec_tab,
        )

        _detach_demo_crm_leads_from_cq_teams(self.env)
        _hide_legacy_crm_coins_quebec_tab(self.env)
        self._cq_align_pipeline_stages()

    @api.model
    def _cq_align_pipeline_stages(self):
        """Kanban gauche→droite : Nouveau, Contacté, En RDV, Suivis, Entente."""
        Part = (
            self.env["coins.quebec.partenariat"]
            .sudo()
            .with_context(active_test=False)
        )
        signed = Part.search([("stage", "=", "signe")])
        if signed:
            signed.write({"stage": "gagne"})
        Voy = self.env["coins.quebec.voyageur"].sudo().with_context(active_test=False)
        voy_map = {"qualifie": "contacte", "reserve": "gagne"}
        for old, new in voy_map.items():
            recs = Voy.search([("stage", "=", old)])
            if recs:
                recs.write({"stage": new})
        canamex = Part.search(
            [("name", "ilike", "canamex"), ("active", "=", True)]
        )
        if canamex:
            canamex.action_archive()
        self._cq_align_selection_sequences()
        self._cq_align_crm_stage_order()
        if hasattr(Part, "_cq_sync_upcoming_rdv_stages"):
            Part._cq_sync_upcoming_rdv_stages()

    @api.model
    def _cq_align_selection_sequences(self):
        """Ordre des colonnes kanban = sequence, jamais ORDER BY clé SQL."""
        try:
            from .partenariat import CQ_PIPELINE_OBSOLETE, CQ_PIPELINE_STAGES
        except ImportError:
            CQ_PIPELINE_STAGES = [
                ("nouveau", "Nouveau"),
                ("contacte", "Contacté"),
                ("en_rdv", "En RDV"),
                ("suivi", "Suivis"),
                ("entente", "Entente"),
                ("gagne", "Gagné"),
                ("perdu", "Perdu"),
            ]
            CQ_PIPELINE_OBSOLETE = ()
        wanted = [
            (value, label, idx)
            for idx, (value, label) in enumerate(CQ_PIPELINE_STAGES, start=1)
        ]
        cr = self.env.cr
        for model in ("coins.quebec.partenariat", "coins.quebec.voyageur"):
            field = self.env["ir.model.fields"].sudo().search(
                [("model", "=", model), ("name", "=", "stage")], limit=1
            )
            if not field:
                continue
            if CQ_PIPELINE_OBSOLETE:
                cr.execute(
                    """
                    DELETE FROM ir_model_fields_selection
                    WHERE field_id = %s AND value IN %s
                    """,
                    [field.id, tuple(CQ_PIPELINE_OBSOLETE)],
                )
            cr.execute(
                """
                SELECT id, value FROM ir_model_fields_selection
                WHERE field_id = %s
                """,
                [field.id],
            )
            have = {row[1]: row[0] for row in cr.fetchall()}
            for value, label, seq in wanted:
                name_json = '{"en_US": "%s"}' % label.replace('"', '\\"')
                if value in have:
                    cr.execute(
                        """
                        UPDATE ir_model_fields_selection
                        SET sequence = %s, name = %s::jsonb, write_date = NOW()
                        WHERE id = %s
                        """,
                        [seq, name_json, have[value]],
                    )
                else:
                    cr.execute(
                        """
                        INSERT INTO ir_model_fields_selection
                            (field_id, value, name, sequence, create_date, write_date)
                        VALUES (%s, %s, %s::jsonb, %s, NOW(), NOW())
                        """,
                        [field.id, value, name_json, seq],
                    )
            self.env["ir.model.fields.selection"].sudo().invalidate_model()

    @api.model
    def _cq_align_crm_stage_order(self):
        env = self.env
        team = env.ref(
            "coins_quebec.crm_team_cq_partenariats", raise_if_not_found=False
        )
        updates = (
            ("coins_quebec.stage_cq_p_nouveau", {"name": "Nouveau", "sequence": 1}),
            ("coins_quebec.stage_cq_p_contacte", {"name": "Contacté", "sequence": 2}),
            ("coins_quebec.stage_cq_p_en_rdv", {"name": "En RDV", "sequence": 3}),
            ("coins_quebec.stage_cq_p_suivi", {"name": "Suivis", "sequence": 4}),
            (
                "coins_quebec.stage_cq_p_entente",
                {"name": "Entente", "sequence": 5, "fold": False},
            ),
            (
                "coins_quebec.stage_cq_p_signe",
                {"name": "Gagné", "sequence": 6, "is_won": True, "fold": True},
            ),
            (
                "coins_quebec.stage_cq_p_perdu",
                {"name": "Perdu", "sequence": 7, "fold": True},
            ),
            ("coins_quebec.stage_cq_v_nouveau", {"name": "Nouveau", "sequence": 10}),
            (
                "coins_quebec.stage_cq_v_qualifie",
                {"name": "Contacté", "sequence": 20},
            ),
            (
                "coins_quebec.stage_cq_v_entente",
                {"name": "Entente", "sequence": 30},
            ),
            (
                "coins_quebec.stage_cq_v_suivi",
                {"name": "Suivis", "sequence": 40},
            ),
            (
                "coins_quebec.stage_cq_v_reserve",
                {"name": "Gagné", "sequence": 50, "is_won": True, "fold": False},
            ),
            (
                "coins_quebec.stage_cq_v_perdu",
                {"name": "Perdu", "sequence": 60, "fold": True},
            ),
        )
        for xmlid, vals in updates:
            rec = env.ref(xmlid, raise_if_not_found=False)
            if rec:
                rec.write(vals)
        entente = env.ref(
            "coins_quebec.stage_cq_p_entente", raise_if_not_found=False
        )
        if team and entente and team not in entente.team_ids:
            entente.write({"team_ids": [(4, team.id)]})
