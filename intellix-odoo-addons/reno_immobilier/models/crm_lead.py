# -*- coding: utf-8 -*-
import re
from datetime import timedelta

from odoo import api, fields, models
from odoo.osv import expression

from .partner_match import (
    VERTICAL_TO_CATEGORY,
    infer_category_names,
    partner_covers_city,
    services_overlap,
)

RENO_IMMO_TEAM_XMLIDS = (
    "reno_immobilier.crm_team_reno_immobilier",
    "renovation_conciergerie.crm_team_renovation",
    "renovation_conciergerie.crm_team_immobilier",
)

RENO_STAGE_XMLIDS = (
    ("nouveau", "reno_immobilier.crm_stage_nouveau"),
    ("attribue", "reno_immobilier.crm_stage_attribue"),
    ("a_relancer", "reno_immobilier.crm_stage_a_relancer"),
    ("en_contact", "reno_immobilier.crm_stage_en_contact"),
    ("gagne", "reno_immobilier.crm_stage_gagne"),
    ("perdu", "reno_immobilier.crm_stage_perdu"),
)

STATUS_FROM_STAGE = (
    (("gagne", "gagné", "won"), "gagne"),
    (("perdu", "lost", "non qualif", "hors cible"), "perdu"),
    (("à relancer", "a relancer", "relance", "rappel"), "a_relancer"),
    (("contacté", "contacte", "en contact", "contact", "social", "retell", "agent ia", "site", "appel", "développ"), "en_contact"),
    (("attrib", "assign", "qualif"), "attribue"),
    (("nouveau", "new", "à traiter", "a traiter"), "nouveau"),
)

_PHONE_ONLY = re.compile(r"^[\d\s().+\-]{6,}$")
_FACILE_NEEDLES = ("renofacile", "reno facile", "marenofacile", "ma renofacile")
_SITE_SOURCE_RE = re.compile(r"Site source:\s*([^\s<]+)", re.I)


class CrmLeadRenoImmobilierApp(models.Model):
    _inherit = "crm.lead"

    reno_immo_lead = fields.Boolean(
        compute="_compute_reno_immo_lead",
        search="_search_reno_immo_lead",
    )
    reno_gestion_status = fields.Selection(
        [
            ("nouveau", "Nouveau"),
            ("en_contact", "Contacté"),
            ("attribue", "Attribué"),
            ("a_relancer", "Relance"),
            ("gagne", "Gagné"),
            ("perdu", "Perdu"),
        ],
        string="Statut Réno Immobilier",
        compute="_compute_reno_gestion_status",
        inverse="_inverse_reno_gestion_status",
        store=True,
        index=True,
    )
    reno_source_label = fields.Char(
        string="Source / établissement",
        compute="_compute_reno_card_fields",
    )
    reno_relance_due = fields.Boolean(
        string="À relancer",
        compute="_compute_reno_relance_due",
        store=True,
        help="Badge unique Réno Immobilier. Ne pas redéfinir dans renovation_conciergerie.",
    )
    reno_card_title = fields.Char(
        string="Nom du contact",
        compute="_compute_reno_card_fields",
    )
    reno_card_subtitle = fields.Char(
        string="Établissement / source",
        compute="_compute_reno_card_fields",
    )
    reno_category_badge = fields.Char(
        string="Catégorie",
        compute="_compute_reno_card_fields",
    )
    reno_user_badge = fields.Char(
        string="Commercial",
        compute="_compute_reno_card_fields",
    )
    reno_facile_paused = fields.Boolean(
        string="RénoFacile (pause)",
        compute="_compute_reno_facile_paused",
        search="_search_reno_facile_paused",
    )
    reno_card_tone = fields.Char(compute="_compute_reno_card_fields")
    reno_assigned_partner_id = fields.Many2one(
        "res.partner",
        string="Partenaire",
        tracking=True,
        index=True,
        domain="[('id', 'in', reno_covering_partner_ids)]",
        help="Partenaire Réno (fiche Partenaires). Filtré par couverture géographique.",
    )
    reno_covering_partner_ids = fields.Many2many(
        "res.partner",
        compute="_compute_reno_covering_partners",
        string="Partenaires qui couvrent la région",
    )
    reno_assigned_package_id = fields.Many2one(
        "renovation.partner.package",
        string="Forfait partenaire",
        compute="_compute_reno_partner_card",
    )
    reno_partner_package_label = fields.Char(
        string="Forfait",
        compute="_compute_reno_partner_card",
    )
    reno_partner_region_label = fields.Char(
        string="Couverture",
        compute="_compute_reno_partner_card",
    )
    reno_partner_initials = fields.Char(
        compute="_compute_reno_partner_card",
    )
    reno_partner_covers_lead = fields.Boolean(
        string="Couvre la région du lead",
        compute="_compute_reno_partner_card",
    )
    reno_recurring_revenue = fields.Monetary(
        string="Récurrent (ex. mensuel)",
        compute="_compute_reno_recurring_revenue",
        inverse="_inverse_reno_recurring_revenue",
        currency_field="company_currency",
    )
    reno_details_open = fields.Boolean(
        string="Plus de détails",
        default=False,
    )
    reno_assignee_label = fields.Char(
        string="Assigné par",
        compute="_compute_reno_assignee_label",
    )
    reno_assign_origin = fields.Selection(
        [
            ("auto", "Auto"),
            ("manual", "Manuel"),
        ],
        string="Origine jumelage",
        copy=False,
        index=True,
    )

    def _reno_immo_team_ids(self):
        ids = []
        for xmlid in RENO_IMMO_TEAM_XMLIDS:
            team = self.env.ref(xmlid, raise_if_not_found=False)
            if team:
                ids.append(team.id)
        return ids

    def _reno_immo_gestion_stages(self):
        stages = self.env["crm.stage"]
        for _key, xmlid in RENO_STAGE_XMLIDS:
            stage = self.env.ref(xmlid, raise_if_not_found=False)
            if stage:
                stages |= stage
        return stages.sorted(lambda s: (s.sequence, s.id))

    @api.depends("team_id")
    def _compute_reno_immo_lead(self):
        team_ids = set(self._reno_immo_team_ids())
        for lead in self:
            lead.reno_immo_lead = bool(lead.team_id.id in team_ids)

    def _search_reno_immo_lead(self, operator, value):
        team_ids = self._reno_immo_team_ids()
        wanted = bool(value) if operator in ("=", "!=") else True
        if operator == "=" and not wanted:
            return [("team_id", "not in", team_ids)]
        return [("team_id", "in", team_ids)]

    def _reno_status_from_stage(self, stage):
        name = (stage.name or "").lower()
        for needles, status in STATUS_FROM_STAGE:
            if any(n in name for n in needles):
                return status
        return "nouveau"

    @api.depends("stage_id", "stage_id.name")
    def _compute_reno_gestion_status(self):
        for lead in self:
            lead.reno_gestion_status = lead._reno_status_from_stage(lead.stage_id)

    def _inverse_reno_gestion_status(self):
        for lead in self:
            stage = lead._reno_stage_for_status(lead.reno_gestion_status)
            if stage and lead.stage_id != stage:
                lead.stage_id = stage.id

    def _reno_stage_for_status(self, status):
        xmlid = dict(RENO_STAGE_XMLIDS).get(status or "")
        if xmlid:
            stage = self.env.ref(xmlid, raise_if_not_found=False)
            if stage:
                return stage
        return self.env["crm.stage"]

    def _reno_maison_recherchee_source(self):
        Source = self.env["utm.source"].sudo()
        source = Source.search([("name", "=", "Maison Recherchée")], limit=1)
        return source or Source.create({"name": "Maison Recherchée"})

    def _reno_fill_maison_recherchee_source(self):
        """Leads Maison Recherchée (Meta / Instant Form) : source + Leads Gestion."""
        mr = self._reno_maison_recherchee_source()
        gestion = self.env.ref(
            "reno_immobilier.crm_team_reno_immobilier", raise_if_not_found=False
        )
        skip = {
            "soumissiontoitures.com",
            "reseaucuisineqc.com",
            "isolationqc.com",
            "Soumission Toiture",
            "Cuisine",
            "Isolation QC",
            "Soumission Entrepreneurs",
            "Portes et Fenêtres QC",
            "ICI Thermopompe",
        }
        old_immo = set()
        for xmlid in (
            "renovation_conciergerie.crm_team_immobilier",
            "renovation_conciergerie.crm_team_renovation",
        ):
            rec = self.env.ref(xmlid, raise_if_not_found=False)
            if rec:
                old_immo.add(rec.id)
        for lead in self:
            name = lead.name or ""
            is_mr = "Facebook Immobilier" in name or lead.team_id.id in (7, 93)
            if not is_mr:
                continue
            current = (lead.source_id.name or "").strip()
            writes = {}
            if current != "Maison Recherchée" and current not in skip:
                writes["source_id"] = mr.id
            if gestion and lead.team_id.id in old_immo | {7, 93}:
                writes["team_id"] = gestion.id
                if gestion.company_id:
                    writes["company_id"] = gestion.company_id.id
            if writes:
                lead.write(writes)

    @api.model_create_multi
    def create(self, vals_list):
        """Nouveaux leads web + Instant Forms MR → Leads Gestion (116).

        Ne touche pas Coins, Driven, ITEX, Marketing, RénoFacile (team 6).
        """
        team = self.env.ref(
            "reno_immobilier.crm_team_reno_immobilier", raise_if_not_found=False
        )
        stage = self.env.ref(
            "reno_immobilier.crm_stage_nouveau", raise_if_not_found=False
        )
        old_ids = set()
        for xmlid in (
            "renovation_conciergerie.crm_team_renovation",
            "renovation_conciergerie.crm_team_immobilier",
        ):
            rec = self.env.ref(xmlid, raise_if_not_found=False)
            if rec:
                old_ids.add(rec.id)
        for vals in vals_list:
            if not team:
                continue
            name = vals.get("name") or ""
            is_mr_meta = "Facebook Immobilier" in name or vals.get(
                "lead_provenance"
            ) in ("social", "meta")
            provenance = vals.get("lead_provenance")
            team_id = vals.get("team_id")
            reno_92 = self.env.ref(
                "renovation_conciergerie.crm_team_renovation",
                raise_if_not_found=False,
            )
            # Ma Reno Facile reste sur le kanban Rénovation 92.
            if provenance == "website" and reno_92 and team_id == reno_92.id:
                pass
            elif provenance == "website" and (team_id in old_ids or team_id == team.id):
                vals["team_id"] = team.id
                if stage:
                    vals["stage_id"] = stage.id
            elif is_mr_meta and (
                team_id in old_ids
                or team_id in (7, 93, team.id)
                or not team_id
            ):
                vals["team_id"] = team.id
            if vals.get("team_id") == team.id and stage:
                # Meta/webhook peut poser le stage CRM « New » (1) ou Agent IA.
                # Le kanban Réno Immobilier ne montre que les 6 colonnes.
                reno_ids = set(self._reno_immo_gestion_stages().ids)
                sid = vals.get("stage_id")
                if not sid or sid not in reno_ids:
                    vals["stage_id"] = stage.id
            if vals.get("team_id") == team.id and team.company_id and not vals.get(
                "company_id"
            ):
                vals["company_id"] = team.company_id.id
        records = super().create(vals_list)
        records._reno_init_partner_from_assignment()
        records._reno_fill_maison_recherchee_source()
        return records

    def write(self, vals):
        if "reno_assigned_partner_id" in vals and not self.env.context.get(
            "reno_skip_assign_origin"
        ):
            if vals.get("reno_assigned_partner_id") and "reno_assign_origin" not in vals:
                vals = dict(vals, reno_assign_origin="manual")
        res = super().write(vals)
        if "reno_assigned_partner_id" in vals:
            self._sync_reno_partner_to_assignment()
        return res

    def _partner_covers_lead(self, partner):
        """Couverture conciergerie + filet ville/région (Longueuil ⊂ Rive-Sud)."""
        self.ensure_one()
        covered = False
        parent = super()
        if hasattr(parent, "_partner_covers_lead"):
            try:
                covered = bool(parent._partner_covers_lead(partner))
            except Exception:
                covered = False
        if covered:
            return True
        return partner_covers_city(
            self.city,
            partner.city or "",
            getattr(partner, "city_text", None) or "",
            getattr(partner, "coverage_mode", None) or "",
        )

    def _reno_city_covers_partner(self, partner):
        return partner_covers_city(
            self.city,
            partner.city or "",
            getattr(partner, "city_text", None) or "",
            getattr(partner, "coverage_mode", None) or "",
        )

    def _find_partners_for_service(self, service):
        partners = self.env["res.partner"].search(
            [("package_ids.state", "=", "active")]
        )
        lead_names = [service.name] if service else []
        return partners.filtered(
            lambda p: services_overlap(
                lead_names, p.service_category_ids.mapped("name")
            )
            and self._partner_covers_lead(p)
        )

    def _reno_package_remaining(self, partner):
        package = getattr(partner, "active_package_id", False)
        if not package:
            Package = self.env["renovation.partner.package"].sudo()
            package = Package.search(
                [("partner_id", "=", partner.id), ("state", "=", "active")],
                limit=1,
            )
        if not package:
            return 0
        return getattr(package, "leads_remaining", 0) or 0

    def _reno_best_partner(self, partners):
        if not partners:
            return partners
        ranked = sorted(
            partners,
            key=lambda p: (-self._reno_package_remaining(p), p.id),
        )
        return partners.browse(ranked[0].id)

    def _reno_ensure_service_categories(self):
        Category = self.env["renovation.service.category"].sudo()
        for lead in self:
            if lead.service_category_ids:
                continue
            names = infer_category_names(
                source_label=lead.source_id.name if lead.source_id else "",
                description=lead.description or "",
                lead_name=lead.name or "",
            )
            found = Category.browse()
            for name in names:
                found |= Category.search([("name", "=ilike", name)], limit=1)
            if found:
                lead.service_category_ids = [(6, 0, found.ids)]

    def _reno_primary_category(self):
        self.ensure_one()
        if self.service_category_ids:
            return self.service_category_ids[:1]
        return self.env["renovation.service.category"]

    def _reno_add_need_from_vertical(self, vertical_key):
        """Ajoute une ligne d'assignation pour un besoin cross-sell (isolation, etc.)."""
        self.ensure_one()
        name = VERTICAL_TO_CATEGORY.get(vertical_key)
        if not name:
            return self.env["renovation.lead.service.assignment"]
        category = self.env["renovation.service.category"].sudo().search(
            [("name", "=ilike", name)], limit=1
        )
        if not category:
            return self.env["renovation.lead.service.assignment"]
        if category not in self.service_category_ids:
            self.service_category_ids = [(4, category.id)]
        existing = self.service_assignment_ids.filtered(
            lambda line: line.service_category_id == category
        )
        if existing:
            return existing[:1]
        return self.env["renovation.lead.service.assignment"].create(
            {
                "lead_id": self.id,
                "service_category_id": category.id,
                "status": "pending",
            }
        )

    def _reno_write_assignment_lines(self, picked_by_service, extras_note=""):
        self.ensure_one()
        Assignment = self.env["renovation.lead.service.assignment"]
        for service, matches in picked_by_service.items():
            partner = self._reno_best_partner(matches)
            line = self.service_assignment_ids.filtered(
                lambda rec, svc=service: rec.service_category_id == svc
            )[:1]
            vals = {
                "partner_id": partner.id if partner else False,
                "status": "assigned" if partner else "no_match",
                "assignment_date": fields.Datetime.now() if partner else False,
            }
            if line:
                line.sudo().write(vals)
            else:
                Assignment.create(
                    dict(vals, lead_id=self.id, service_category_id=service.id)
                )
        if extras_note:
            self.message_post(body=extras_note)

    def action_assign_partner(self):
        """Assigne le meilleur partenaire par service (plus le seul unique)."""
        for lead in self:
            lead._reno_ensure_service_categories()
            services = lead.service_category_ids
            if not services:
                lead.write({"assignment_status": "no_match"})
                continue
            picked = {}
            notes = []
            assigned_partners = self.env["res.partner"]
            for service in services:
                matches = lead._find_partners_for_service(service)
                picked[service] = matches
                partner = lead._reno_best_partner(matches)
                if partner:
                    assigned_partners |= partner
                if len(matches) > 1:
                    names = ", ".join(matches.mapped("name"))
                    notes.append(
                        "Plusieurs partenaires pour <b>%s</b> : %s. Assigné : <b>%s</b>."
                        % (service.name, names, partner.name if partner else "—")
                    )
            lead._reno_write_assignment_lines(picked, extras_note="<br/>".join(notes))
            lead._recompute_partner_assignment_status()
            if assigned_partners:
                stage = lead._reno_stage_for_status("attribue")
                pick = lead._reno_best_partner(assigned_partners)
                write_vals = {
                    "reno_assigned_partner_id": pick.id,
                    "reno_assign_origin": "auto",
                    "assignment_status": "assigned",
                }
                if stage:
                    write_vals["stage_id"] = stage.id
                lead.with_context(reno_skip_assign_origin=True).write(write_vals)
        return True

    def action_reno_suggest_partner(self):
        """Propose le meilleur partenaire qui couvre ville × service (liste s'il y en a plusieurs)."""
        last_message = "Aucun partenaire à proposer."
        last_type = "warning"
        for lead in self:
            lead._reno_ensure_service_categories()
            if not lead.service_category_ids:
                last_message = (
                    "Aucune catégorie de service sur le lead. "
                    "Ajoutez Toiture (ou le besoin) puis relancez la suggestion."
                )
                lead.message_post(body=last_message)
                continue
            matches = self.env["res.partner"]
            for service in lead.service_category_ids:
                matches |= lead._find_partners_for_service(service)
            if not matches:
                last_message = (
                    "Aucun partenaire actif ne couvre %s à %s "
                    "(Toiture inclut aussi rénovation extérieure ; "
                    "Longueuil est dans la Rive-Sud / Montérégie)."
                    % (
                        ", ".join(lead.service_category_ids.mapped("name")),
                        lead.city or "cette ville",
                    )
                )
                last_type = "warning"
                lead.message_post(body=last_message)
                continue
            pick = lead._reno_best_partner(matches)
            lead.action_assign_partner()
            if pick and not lead.reno_assigned_partner_id:
                lead.with_context(reno_skip_assign_origin=True).write(
                    {
                        "reno_assigned_partner_id": pick.id,
                        "reno_assign_origin": "auto",
                    }
                )
            others = matches - pick
            extra = (
                " Autres : %s." % ", ".join(others.mapped("name")) if others else ""
            )
            last_message = "Assigné : <b>%s</b>.%s Changez le partenaire d’une ligne pour un autre besoin." % (
                pick.name,
                extra,
            )
            last_type = "success"
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Suggestion partenaires",
                "message": last_message,
                "type": last_type,
                "sticky": False,
            },
        }

    def action_reno_focus_partner(self):
        """Client JS scrolls to the unique partner card. No data change."""
        return True

    def _reno_package_partners(self):
        Package = self.env["renovation.partner.package"].sudo()
        return Package.search([("state", "in", ("active", "draft"))]).mapped(
            "partner_id"
        )

    def _reno_partner_covers(self, partner):
        """Reuse renovation_conciergerie coverage — do not reimplement."""
        self.ensure_one()
        if not partner:
            return False
        if hasattr(self, "_partner_covers_lead"):
            try:
                return bool(self._partner_covers_lead(partner))
            except Exception:
                return True
        cover = getattr(partner, "_covers_lead", None) or getattr(
            partner, "covers_lead", None
        )
        if callable(cover):
            try:
                return bool(cover(self))
            except Exception:
                return True
        return True

    def _reno_init_partner_from_assignment(self):
        for lead in self.filtered(lambda l: not l.reno_assigned_partner_id):
            assigned = False
            if "service_assignment_ids" in lead._fields:
                assigned = lead.service_assignment_ids.filtered("partner_id")[:1]
            partner = assigned.partner_id if assigned else getattr(
                lead, "assigned_partner_id", False
            )
            if partner:
                super(CrmLeadRenoImmobilierApp, lead).write(
                    {"reno_assigned_partner_id": partner.id}
                )

    def _sync_reno_partner_to_assignment(self):
        """Miroir sur la ligne du service d'origine seulement — pas les autres besoins."""
        for lead in self:
            partner = lead.reno_assigned_partner_id
            if not partner:
                continue
            if "assigned_partner_id" in lead._fields and lead.assigned_partner_id != partner:
                super(CrmLeadRenoImmobilierApp, lead).write(
                    {"assigned_partner_id": partner.id}
                )
            if "service_assignment_ids" not in lead._fields:
                continue
            lines = lead.service_assignment_ids
            if not lines:
                continue
            primary = lead._reno_primary_category()
            target = lines.filtered(
                lambda rec, cat=primary: cat and rec.service_category_id == cat
            )[:1] or lines.filtered(lambda rec: not rec.partner_id)[:1]
            if not target:
                continue
            if target.partner_id != partner:
                target.sudo().write({"partner_id": partner.id, "status": "assigned"})

    @api.depends(
        "city",
        "zip",
        "state_id",
        "partner_id",
        "partner_id.city",
        "partner_id.zip",
        "partner_id.state_id",
    )
    def _compute_reno_covering_partners(self):
        all_partners = self._reno_package_partners()
        if not all_partners:
            all_partners = self.env["res.partner"].search(
                [("is_company", "=", True)], limit=80
            )
        for lead in self:
            covered = all_partners.filtered(lambda p, l=lead: l._reno_partner_covers(p))
            lead.reno_covering_partner_ids = covered or all_partners

    @api.depends(
        "reno_assigned_partner_id",
        "reno_assigned_partner_id.name",
        "reno_assigned_partner_id.city",
        "reno_assigned_partner_id.state_id",
        "city",
        "zip",
        "state_id",
    )
    def _compute_reno_partner_card(self):
        Package = self.env["renovation.partner.package"].sudo()
        for lead in self:
            partner = lead.reno_assigned_partner_id
            package = Package.search(
                [
                    ("partner_id", "=", partner.id),
                    ("state", "in", ("active", "draft", "expired")),
                ],
                order="state, date_end desc, id desc",
                limit=1,
            ) if partner else Package
            lead.reno_assigned_package_id = package
            if package:
                total = package.leads_total or 0
                lead.reno_partner_package_label = "%s — %s leads" % (
                    package.package_type_id.name or package.name or "Forfait",
                    total,
                )
            else:
                lead.reno_partner_package_label = False
            region = False
            if partner:
                region = (
                    (getattr(partner, "city_text", None) or "").strip()
                    or (partner.city or "").strip()
                    or (partner.state_id.name if partner.state_id else "")
                )
            lead.reno_partner_region_label = region or False
            name = (partner.name or "").strip()
            bits = [p[0] for p in name.replace("-", " ").split() if p]
            lead.reno_partner_initials = ("".join(bits[:2]) or "?").upper()
            lead.reno_partner_covers_lead = bool(
                partner and lead._reno_partner_covers(partner)
            )

    @api.depends("expected_revenue")
    def _compute_reno_recurring_revenue(self):
        has = "recurring_revenue" in self._fields
        for lead in self:
            lead.reno_recurring_revenue = (lead.recurring_revenue or 0.0) if has else 0.0

    def _inverse_reno_recurring_revenue(self):
        if "recurring_revenue" not in self._fields:
            return
        for lead in self:
            lead.recurring_revenue = lead.reno_recurring_revenue

    @api.depends("user_id", "user_id.name")
    def _compute_reno_assignee_label(self):
        for lead in self:
            label = False
            if "coins_assignee_display" in lead._fields:
                label = lead.coins_assignee_display
            if not label and "assignee_kind" in lead._fields and lead.assignee_kind == "ia":
                label = "IA"
            lead.reno_assignee_label = label or lead.user_id.name or False

    def action_toggle_reno_details(self):
        for lead in self:
            lead.reno_details_open = not lead.reno_details_open
        return True

    def action_reno_set_won(self):
        if hasattr(self, "action_set_won"):
            return self.action_set_won()
        won = self._reno_stage_for_status("gagne")
        if won:
            self.write({"stage_id": won.id})
        return True

    def action_reno_call_ia(self):
        for name in (
            "action_doorway_call_agent",
            "action_ai_call",
            "action_call_agent_ia",
            "action_launch_ai_call",
        ):
            method = getattr(self, name, None)
            if callable(method):
                return method()
        return True

    def action_reno_compose_email(self):
        self.ensure_one()
        for name in (
            "action_lead_mail_compose",
            "action_preview_mail",
        ):
            method = getattr(self, name, None)
            if callable(method):
                return method()
        return {
            "type": "ir.actions.act_window",
            "name": "Email",
            "res_model": "mail.compose.message",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_model": "crm.lead",
                "default_res_ids": [self.id],
                "default_composition_mode": "comment",
            },
        }

    def action_reno_compose_sms(self):
        """SMS depuis la carte contact. Ne change pas les boutons d'en-tête."""
        self.ensure_one()
        if "sms.composer" not in self.env:
            return True
        return {
            "type": "ir.actions.act_window",
            "name": "SMS",
            "res_model": "sms.composer",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_composition_mode": "comment",
                "default_res_model": "crm.lead",
                "default_res_ids": [self.id],
                "default_number_field_name": "phone",
            },
        }

    def _reno_site_source_from_notes(self):
        """Domaine prouvé dans la note webhook (`Site source:`). Ne pas inventer."""
        self.ensure_one()
        text = re.sub(r"<[^>]+>", " ", self.description or "")
        match = _SITE_SOURCE_RE.search(text)
        if not match:
            return ""
        return match.group(1).strip().rstrip(".,;")

    def _reno_source_display(self):
        self.ensure_one()
        source = (self.source_id.name or "").strip()
        if source:
            return source
        noted = self._reno_site_source_from_notes()
        if noted:
            return noted
        if self.lead_provenance == "website" or (self.name or "").startswith("Site web"):
            return "Site web"
        return ""

    @api.depends(
        "name",
        "contact_name",
        "partner_name",
        "partner_id",
        "partner_id.name",
        "phone",
        "source_id",
        "source_id.name",
        "description",
        "lead_provenance",
        "team_id",
        "team_id.name",
        "user_id",
        "user_id.name",
        "service_category_ids",
        "service_category_ids.name",
        "service_assignment_ids.service_category_id",
        "reno_relance_due",
        "stage_id",
    )
    def _compute_reno_card_fields(self):
        for lead in self:
            contact = (
                (lead.contact_name or "").strip()
                or (lead.partner_name or "").strip()
                or (lead.partner_id.name or "").strip()
            )
            raw_name = (lead.name or "").strip()
            if not contact:
                if raw_name and "—" in raw_name:
                    contact = raw_name.split("—")[-1].strip()
                elif raw_name and not _PHONE_ONLY.match(raw_name):
                    contact = raw_name
                else:
                    contact = raw_name or lead.phone or "Sans nom"
            lead.reno_card_title = contact

            establishment = (lead.partner_name or "").strip()
            if establishment and establishment.lower() == contact.lower():
                establishment = ""
            source = lead._reno_source_display()
            team = (lead.team_id.name or "").strip()
            subtitle_bits = [b for b in (establishment, source or team) if b]
            lead.reno_card_subtitle = " · ".join(subtitle_bits) or "—"
            lead.reno_source_label = lead.reno_card_subtitle

            category = False
            if "service_category_ids" in lead._fields and lead.service_category_ids:
                category = lead.service_category_ids[:1].name
            if not category and "service_assignment_ids" in lead._fields:
                category = next(
                    (
                        a.service_category_id.name
                        for a in lead.service_assignment_ids
                        if a.service_category_id
                    ),
                    False,
                )
            lead.reno_category_badge = category or False
            lead.reno_user_badge = lead.user_id.name or False

            status = lead._reno_status_from_stage(lead.stage_id)
            if status == "gagne":
                lead.reno_card_tone = "won"
            elif lead.reno_relance_due:
                lead.reno_card_tone = "hot"
            else:
                lead.reno_card_tone = ""

    @api.depends("date_last_stage_update", "write_date", "create_date", "stage_id")
    def _compute_reno_relance_due(self):
        for lead in self:
            status = lead._reno_status_from_stage(lead.stage_id)
            lead.reno_relance_due = (
                status not in ("gagne", "perdu") and lead._reno_is_stale()
            )

    def _reno_relance_business_days(self):
        raw = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("renovation_conciergerie.relance_business_days", "3")
        )
        try:
            return max(1, int(raw))
        except (TypeError, ValueError):
            return 3

    def _reno_is_stale(self):
        self.ensure_one()
        start = self.date_last_stage_update or self.write_date or self.create_date
        if not start:
            return False
        start_d = fields.Datetime.context_timestamp(self, start).date()
        today = fields.Date.context_today(self)
        return self._reno_business_days_between(start_d, today) >= self._reno_relance_business_days()

    @staticmethod
    def _reno_business_days_between(start, end):
        if end < start:
            return 0
        days = 0
        cursor = start
        while cursor < end:
            cursor += timedelta(days=1)
            if cursor.weekday() < 5:
                days += 1
        return days

    def _reno_is_facile_record(self):
        self.ensure_one()
        hay = " ".join(
            [
                self.name or "",
                self.contact_name or "",
                self.partner_name or "",
                self.team_id.name or "",
                self.source_id.name or "",
                self.medium_id.name or "",
                self.campaign_id.name or "",
                self.email_from or "",
            ]
        ).lower()
        compact = hay.replace(" ", "").replace("-", "")
        return any(n.replace(" ", "") in compact for n in _FACILE_NEEDLES)

    @api.depends(
        "name",
        "contact_name",
        "partner_name",
        "team_id",
        "team_id.name",
        "source_id",
        "source_id.name",
        "medium_id",
        "medium_id.name",
        "campaign_id",
        "campaign_id.name",
        "email_from",
    )
    def _compute_reno_facile_paused(self):
        for lead in self:
            lead.reno_facile_paused = lead._reno_is_facile_record()

    def _search_reno_facile_paused(self, operator, value):
        wanted = bool(value) if operator in ("=", "!=") else True
        if operator == "!=":
            wanted = not wanted
        leads = self.search([("reno_immo_lead", "=", True)]).filtered(
            lambda l: l._reno_is_facile_record()
        )
        # Odoo 19 optimizes ('id', 'not in', []) to an empty set — never use that.
        if wanted:
            return [("id", "in", leads.ids or [0])]
        if not leads:
            return [(1, "=", 1)]
        return [("id", "not in", leads.ids)]

    def _reno_immobilier_forced_domain(self):
        """Leads Gestion = équipe Réno Immobilier uniquement (pas Sales / Driven / CQ)."""
        if not self.env.context.get("reno_immobilier_pipeline"):
            return []
        team = self.env.ref(
            "reno_immobilier.crm_team_reno_immobilier", raise_if_not_found=False
        )
        if not team:
            return []
        return [
            ("team_id", "=", team.id),
            ("type", "=", "opportunity"),
            ("name", "not ilike", "RénoFacile"),
        ]

    def _reno_immobilier_with_forced_domain(self, domain):
        extra = self._reno_immobilier_forced_domain()
        if extra:
            return expression.AND([domain or [], extra])
        return domain

    @api.model
    def search(self, domain, offset=0, limit=None, order=None):
        return super().search(
            self._reno_immobilier_with_forced_domain(domain),
            offset=offset,
            limit=limit,
            order=order,
        )

    @api.model
    def search_count(self, domain, limit=None):
        return super().search_count(
            self._reno_immobilier_with_forced_domain(domain), limit=limit
        )

    @api.model
    def read_group(self, domain, fields, groupby, offset=0, limit=None, orderby=False, lazy=True):
        return super().read_group(
            self._reno_immobilier_with_forced_domain(domain),
            fields,
            groupby,
            offset=offset,
            limit=limit,
            orderby=orderby,
            lazy=lazy,
        )

    @api.model
    def _read_group_stage_ids(self, stages, domain):
        if self.env.context.get("reno_immobilier_pipeline"):
            return self._reno_immo_gestion_stages()
        return super()._read_group_stage_ids(stages, domain)
