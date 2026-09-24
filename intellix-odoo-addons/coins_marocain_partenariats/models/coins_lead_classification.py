# -*- coding: utf-8 -*-
"""Classification des fiches Coins — rapport seulement, aucune écriture."""
import re

from odoo import api, fields, models


_PLACE_NEEDLES = (
    "villa nafsi",
    "riad ines",
    "dar sacada",
    "dar saada",
    "casa alma",
    "villa michelle",
    "casa ysabella",
    "riad ysabella",
    "riad de la semaine",
    "hotel mimosa",
    "maison dar saada",
    "diamond of marrakech",
    "café de france",
    "cafe de france",
    "riad anna",
)


class CoinsLeadClassification(models.TransientModel):
    _name = "coins.lead.classification"
    _description = "Rapport classification pipelines Coins (sans migration)"

    line_ids = fields.One2many(
        "coins.lead.classification.line",
        "wizard_id",
        string="Fiches",
    )
    count_etablissement = fields.Integer(readonly=True)
    count_voyageur = fields.Integer(readonly=True)
    count_manuel = fields.Integer(readonly=True)
    count_evenement = fields.Integer(readonly=True)
    count_ignore = fields.Integer(readonly=True)
    note = fields.Html(readonly=True)

    def _place_names(self):
        names = {n.lower() for n in _PLACE_NEEDLES}
        Prop = self.env["coins.property"].sudo()
        for p in Prop.search([("name", "!=", False)]):
            names.add((p.name or "").strip().lower())
        Entente = self.env["coins.entente"].sudo()
        if "etablissement" in Entente._fields:
            for e in Entente.search([("etablissement", "!=", False)]):
                names.add((e.etablissement or "").strip().lower())
        return {n for n in names if n and n not in {"test property - intellix"}}

    def _looks_like_place(self, lead, places):
        blob = " ".join(
            [
                lead.name or "",
                lead.partner_name or "",
                lead.contact_name or "",
                getattr(lead, "coins_etablissement", None) or "",
            ]
        ).lower()
        for place in places:
            if place and place in blob:
                return place
        return False

    def _is_person_name(self, lead):
        name = (lead.contact_name or lead.partner_name or lead.name or "").strip()
        if not name or name.startswith("[") or "🔥" in name:
            return False
        if re.search(r"https?://|@|www\.", name, re.I):
            return False
        words = [w for w in re.split(r"\s+", name) if w]
        return 1 <= len(words) <= 4

    def _classify_lead(self, lead, places):
        tags = set(lead.tag_ids.mapped("name"))
        name = (lead.name or "").strip()
        desc = (lead.description or "") + " " + (lead.coins_notes_visite or "")
        fiche = lead.coins_fiche_type or ""
        team_name = lead.team_id.name or ""

        if name.startswith("[Événement]") or team_name == "Événements" or fiche == "evenement":
            return "evenement", "Lead pipeline Événements — ne pas déplacer"
        if (lead.lost_reason_id.name or "").lower().find("spam") >= 0:
            return "ignore", "Déjà perdu : spam / newsletter"
        if name.startswith("[TEST]") or name.startswith("[À valider]"):
            return "ignore", "Test interne"

        place = self._looks_like_place(lead, places)
        if place or (lead.coins_commission_pct and fiche != "voyageur") or (
            fiche == "partenariat" and lead.coins_etablissement
        ):
            motif = "Lieu partenaire connu : %s" % (place or lead.coins_etablissement or "tarif/commission")
            return "etablissement", motif

        hot_tags = {"Coins — Hot", "Coins — Concierge"}
        if tags & hot_tags or fiche == "voyageur" or "concierge" in name.lower():
            if place:
                return "manuel", "Tag voyageur + nom de lieu — à trancher"
            return "voyageur", "Tag Hot/Concierge ou fiche voyageur, sans lieu"

        if "transcript" in desc.lower() or "hammam" in (name + desc).lower():
            return "voyageur", "Conversation / hammam en note"

        if self._is_person_name(lead) and not lead.coins_etablissement and not place:
            if team_name == "Coins Marocain":
                return "manuel", "Nom de personne sur pipeline établissements — à trancher"
            return "manuel", "Nom de personne, pas de tag voyageur ni lieu"

        if team_name == "Coins Marocain":
            return "manuel", "Sur Coins Marocain sans critère net"
        return "ignore", "Hors périmètre Coins (autre pipeline)"

    @api.model
    def _collect_leads(self):
        team_cm = self.env.ref(
            "coins_marocain_partenariats.crm_team_coins_marocain",
            raise_if_not_found=False,
        )
        team_ev = self.env.ref(
            "coins_marocain.crm_team_evenements",
            raise_if_not_found=False,
        )
        team_voy = self.env.ref(
            "coins_marocain_partenariats.crm_team_coins_voyageurs",
            raise_if_not_found=False,
        )
        tags = self.env["crm.tag"].sudo().search([("name", "ilike", "Coins")])
        domain = ["|", "|", "|"]
        team_ids = [t.id for t in (team_cm, team_ev, team_voy) if t]
        domain.append(("team_id", "in", team_ids or [0]))
        domain.append(("tag_ids", "in", tags.ids or [0]))
        domain.append(("coins_fiche_type", "in", ["partenariat", "voyageur", "evenement"]))
        domain.append(("name", "ilike", "Concierge"))
        return self.env["crm.lead"].with_context(active_test=False).sudo().search(domain)

    @api.model
    def action_open_report(self):
        wizard = self.create({})
        places = wizard._place_names()
        leads = wizard._collect_leads()
        counts = {
            "etablissement": 0,
            "voyageur": 0,
            "manuel": 0,
            "evenement": 0,
            "ignore": 0,
        }
        Line = self.env["coins.lead.classification.line"]
        for lead in leads.sorted("id"):
            dest, motif = wizard._classify_lead(lead, places)
            counts[dest] = counts.get(dest, 0) + 1
            Line.create(
                {
                    "wizard_id": wizard.id,
                    "lead_id": lead.id,
                    "lead_name": lead.name,
                    "active_lead": lead.active,
                    "current_team": lead.team_id.name,
                    "current_type": lead.coins_fiche_type,
                    "proposed": dest,
                    "motif": motif,
                    "phone": lead.phone or lead.coins_whatsapp or "",
                    "tags": ", ".join(lead.tag_ids.mapped("name")),
                }
            )
        wizard.write(
            {
                "count_etablissement": counts["etablissement"],
                "count_voyageur": counts["voyageur"],
                "count_manuel": counts["manuel"],
                "count_evenement": counts["evenement"],
                "count_ignore": counts["ignore"],
                "note": (
                    "<p><strong>Aucune fiche n’a été déplacée.</strong> "
                    "Valider ce rapport avant la migration finale.</p>"
                    "<p>Établissements : %s · Voyageurs : %s · À classer : %s · "
                    "Événements (intouchables) : %s · Ignorés : %s · Total : %s</p>"
                    % (
                        counts["etablissement"],
                        counts["voyageur"],
                        counts["manuel"],
                        counts["evenement"],
                        counts["ignore"],
                        len(leads),
                    )
                ),
            }
        )
        return {
            "type": "ir.actions.act_window",
            "name": "Classification Coins (à valider)",
            "res_model": "coins.lead.classification",
            "res_id": wizard.id,
            "view_mode": "form",
            "target": "current",
        }


class CoinsLeadClassificationLine(models.TransientModel):
    _name = "coins.lead.classification.line"
    _description = "Ligne rapport classification Coins"
    _order = "proposed, lead_id"

    wizard_id = fields.Many2one(
        "coins.lead.classification", ondelete="cascade", required=True
    )
    lead_id = fields.Many2one("crm.lead", string="Fiche", readonly=True)
    lead_name = fields.Char(readonly=True)
    active_lead = fields.Boolean(string="Active", readonly=True)
    current_team = fields.Char(string="Équipe actuelle", readonly=True)
    current_type = fields.Char(string="Type actuel", readonly=True)
    proposed = fields.Selection(
        [
            ("etablissement", "Pipeline établissements"),
            ("voyageur", "Pipeline voyageurs"),
            ("manuel", "À classer manuellement"),
            ("evenement", "Événements (ne pas toucher)"),
            ("ignore", "Ignorer"),
        ],
        readonly=True,
    )
    motif = fields.Char(readonly=True)
    phone = fields.Char(readonly=True)
    tags = fields.Char(readonly=True)
