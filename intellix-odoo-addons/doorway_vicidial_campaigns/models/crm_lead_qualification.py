# -*- coding: utf-8 -*-
import datetime
from datetime import timedelta

import re

from odoo import _, api, fields, models


class CrmLeadQualificationFrance(models.Model):
    _inherit = "crm.lead"

    source_vicidial = fields.Boolean("Appel entrant", default=False, index=True)
    vicidial_call_uid = fields.Char("ID appel", readonly=True, copy=False)
    campagne_vicidial = fields.Char("Campagne d'appels", readonly=True, copy=False)

    type_projet = fields.Selection(
        [
            ("pac", "PAC — Pompe à chaleur"),
            ("photovoltaique", "Panneaux photovoltaïques"),
            ("reno_globale", "Rénovation globale"),
            ("b2b_partenaire", "B2B — Partenaire potentiel"),
        ],
        string="Type de projet",
    )

    est_proprietaire = fields.Selection(
        [
            ("oui", "Propriétaire"),
            ("non", "Locataire"),
            ("autre", "Autre (copropriété, SCI…)"),
        ],
        string="Propriétaire ?",
    )
    type_logement = fields.Selection(
        [
            ("maison", "Maison individuelle"),
            ("appartement", "Appartement"),
            ("immeuble", "Immeuble / copropriété"),
            ("local_pro", "Local professionnel"),
        ]
    )
    age_logement = fields.Selection(
        [
            ("moins2", "< 2 ans (neuf)"),
            ("2_15", "2 à 15 ans"),
            ("15_25", "15 à 25 ans"),
            ("plus25", "> 25 ans"),
        ],
        string="Âge du logement",
    )
    chauffage_actuel = fields.Selection(
        [
            ("fioul", "Fioul / mazout"),
            ("gaz", "Gaz naturel"),
            ("electrique", "Électrique"),
            ("bois", "Bois / poêle"),
            ("pac", "PAC existante"),
            ("autre", "Autre"),
        ],
        string="Chauffage actuel",
    )
    surface_m2 = fields.Integer("Surface (m²)")
    budget_estime = fields.Selection(
        [
            ("moins5k", "< 5 000 €"),
            ("5k_15k", "5 000 — 15 000 €"),
            ("15k_30k", "15 000 — 30 000 €"),
            ("plus30k", "> 30 000 €"),
            ("inconnu", "Ne sait pas encore"),
        ]
    )
    delai_projet = fields.Selection(
        [
            ("urgent", "< 3 mois"),
            ("6mois", "3 — 6 mois"),
            ("1an", "6 mois — 1 an"),
            ("plus1an", "> 1 an"),
            ("reflexion", "En réflexion"),
        ]
    )

    connait_maprimerenov = fields.Boolean("Connaît MaPrimeRénov ?")
    deja_fait_travaux = fields.Boolean("Déjà fait des travaux aidés ?")

    consentement_recontact_renov = fields.Boolean(
        "Consentement rappel projet rénovation"
    )
    consentement_recontact_artisans = fields.Boolean(
        "Consentement contact artisans partenaires"
    )
    consentement_recontact_date = fields.Datetime(
        "Date consentement rappel"
    )
    consentement_recontact_preuve = fields.Char(
        "Preuve consentement (URL enregistrement ou ID appel)"
    )
    consentement_recontact_source = fields.Char(
        "Source consentement",
        default="marenofacile",
    )

    type_pac = fields.Selection(
        [
            ("air_air", "Air/Air"),
            ("air_eau", "Air/Eau"),
            ("geothermie", "Géothermie"),
            ("ne_sait", "Ne sait pas"),
        ],
        string="Type PAC souhaité",
    )

    orientation_toit = fields.Selection(
        [
            ("sud", "Sud"),
            ("est_ouest", "Est/Ouest"),
            ("nord", "Nord"),
            ("ne_sait", "Ne sait pas"),
        ]
    )
    ombre_toit = fields.Boolean("Ombrage sur le toit ?")
    puissance_souhaitee = fields.Selection(
        [
            ("3kwc", "3 kWc"),
            ("6kwc", "6 kWc"),
            ("9kwc", "9 kWc"),
            ("plus", "> 9 kWc"),
            ("ne_sait", "Ne sait pas"),
        ]
    )

    type_partenaire = fields.Selection(
        [
            ("artisan_rge", "Artisan certifié RGE"),
            ("installateur", "Installateur PAC/PV"),
            ("bureau_etudes", "Bureau d'études"),
            ("franchiseur", "Réseau / franchiseur"),
            ("autre_b2b", "Autre B2B"),
        ],
        string="Type de partenaire",
    )
    nb_techniciens = fields.Integer("Nombre techniciens")
    zones_intervention = fields.Char("Zones d'intervention")
    certifications = fields.Char("Certifications (RGE, QualiPAC…)")

    qualification_statut = fields.Selection(
        [
            ("non_fait", "Pas encore qualifié"),
            ("qualifie", "Qualifié — lead chaud"),
            ("a_rappeler", "Rappel"),
            ("rdv", "RDV planifié"),
            ("pas_interesse", "Pas intéressé"),
            ("deja_servi", "Déjà servi"),
            ("locataire", "Locataire"),
            ("dnc", "DNC — Ne plus appeler"),
            ("messagerie", "Boîte vocale"),
            ("hors_cible", "Hors cible"),
            ("faux_num", "Faux numéro"),
            ("b2b_valide", "B2B validé pour Karine"),
        ],
        string="Résultat qualification",
        default="non_fait",
        tracking=True,
        index=True,
    )
    vicidial_sync_ids = fields.One2many(
        "doorway.vicidial.call.sync", "lead_id", string="Historique appels"
    )
    call_log_ids = fields.One2many(
        "doorway.call.log", "lead_id", string="Enregistrements"
    )
    coaching_call_count = fields.Integer(compute="_compute_call_counts")
    call_log_count = fields.Integer(compute="_compute_call_counts")
    last_call_date = fields.Datetime(compute="_compute_call_counts")
    notes_qualification = fields.Text("Notes qualification")
    prochaine_etape = fields.Char("Prochaine étape")
    rappel_datetime = fields.Datetime("Date/heure rappel")
    score_qualification = fields.Integer(
        "Score /100", compute="_compute_score_qualification", store=True
    )

    @api.depends("vicidial_sync_ids", "call_log_ids")
    def _compute_call_counts(self):
        Coaching = self.env.get("pe.coaching.call")
        for lead in self:
            lead.call_log_count = len(lead.call_log_ids)
            if Coaching:
                lead.coaching_call_count = Coaching.sudo().search_count(
                    [("lead_id", "=", lead.id)]
                )
            else:
                lead.coaching_call_count = 0
            dates = []
            if lead.call_log_ids:
                dates.extend(lead.call_log_ids.mapped("call_date"))
            if lead.vicidial_sync_ids:
                dates.extend(lead.vicidial_sync_ids.mapped("date_debut"))
            lead.last_call_date = max(dates) if dates else False

    @api.depends(
        "est_proprietaire",
        "type_projet",
        "delai_projet",
        "budget_estime",
        "type_logement",
    )
    def _compute_score_qualification(self):
        for rec in self:
            score = 0
            if rec.est_proprietaire == "oui":
                score += 30
            if rec.type_projet:
                score += 20
            if rec.delai_projet in ("urgent", "6mois"):
                score += 20
            elif rec.delai_projet == "1an":
                score += 10
            if rec.budget_estime and rec.budget_estime != "inconnu":
                score += 15
            if rec.type_logement == "maison":
                score += 15
            rec.score_qualification = min(score, 100)

    def _action_set_qualification(self, statut, extra_vals=None):
        for lead in self:
            vals = {"qualification_statut": statut}
            if extra_vals:
                vals.update(extra_vals)
            lead.write(vals)
            lead._sync_vicidial_qualification_done()
            lead._sync_coaching_qualification(statut)
        return True

    def _sync_coaching_qualification(self, statut):
        Coaching = self.env.get("pe.coaching.call")
        if not Coaching:
            return
        for lead in self:
            calls = Coaching.sudo().search([("lead_id", "=", lead.id)])
            if calls:
                calls.write({"qualification_appel": statut})
            syncs = self.env["doorway.vicidial.call.sync"].sudo().search(
                [("lead_id", "=", lead.id), ("statut_vicidial", "=", "INCALL")]
            )
            for sync in syncs:
                sync.qualification_faite = statut not in ("non_fait",)

    def write(self, vals):
        track_qual = "qualification_statut" in vals
        old_stats = (
            {lead.id: lead.qualification_statut for lead in self}
            if track_qual
            else {}
        )
        res = super().write(vals)
        if track_qual:
            for lead in self.filtered("source_vicidial"):
                if old_stats.get(lead.id) != lead.qualification_statut:
                    lead._bus_notify_qualification_updated()
            self.filtered("source_vicidial")._sync_pe_call_log_from_qualification()
        return res

    def _bus_notify_qualification_updated(self):
        self.ensure_one()
        payload = {
            "lead_id": self.id,
            "qualification_statut": self.qualification_statut,
            "campagne_vicidial": self.campagne_vicidial or "",
            "user_id": self.user_id.id,
        }
        partner_ids = set()
        if self.user_id.partner_id:
            partner_ids.add(self.user_id.partner_id.id)
        supervisor_group = self.env.ref(
            "doorway_vicidial_campaigns.group_vicidial_supervisor",
            raise_if_not_found=False,
        )
        if supervisor_group:
            partner_ids.update(supervisor_group.users.mapped("partner_id").ids)
        Bus = self.env["bus.bus"]
        for partner_id in partner_ids:
            Bus._sendone(
                partner_id,
                "doorway/vicidial/qualification_updated",
                payload,
            )

    def action_qualif_pas_interesse(self):
        self._action_set_qualification("pas_interesse", {"active": True})
        return True

    def action_qualif_deja_servi(self):
        self._action_set_qualification("deja_servi")
        return True

    def action_qualif_locataire(self):
        self._action_set_qualification(
            "locataire", {"est_proprietaire": "non"}
        )
        return True

    def action_qualif_rdv(self):
        for lead in self:
            lead._action_set_qualification("rdv", {"type": "opportunity"})
            stage = self.env["crm.stage"].search(
                [
                    ("team_id", "=", lead.team_id.id),
                    ("name", "ilike", "RDV"),
                ],
                limit=1,
            )
            if stage:
                lead.stage_id = stage.id
        return True

    def action_qualif_dnc(self):
        for lead in self:
            lead._action_set_qualification("dnc", {"active": False})
        return True

    def action_qualif_messagerie(self):
        self._action_set_qualification("messagerie")
        return True

    def action_view_coaching_calls(self):
        self.ensure_one()
        Coaching = self.env.get("pe.coaching.call")
        if not Coaching:
            return True
        return {
            "type": "ir.actions.act_window",
            "name": _("Coaching — %s") % self.name,
            "res_model": "pe.coaching.call",
            "view_mode": "list,form",
            "domain": [("lead_id", "=", self.id)],
            "context": {"default_lead_id": self.id},
        }

    def action_play_last_recording(self):
        self.ensure_one()
        log = self.call_log_ids.filtered("recording_url")[:1]
        if not log:
            return True
        return {
            "type": "ir.actions.act_url",
            "url": log.recording_url,
            "target": "new",
        }

    @api.model
    def _dashboard_kpi_keys(self):
        return (
            "pas_interesse",
            "deja_servi",
            "locataire",
            "a_rappeler",
            "rdv",
            "dnc",
            "messagerie",
            "faux_num",
            "hors_cible",
            "b2b_valide",
            "non_fait",
            "qualifie",
            "total",
        )

    @api.model
    def _dashboard_campaign_lookup(self):
        """Map vicidial_campaign_id → nom + statut Odoo."""
        Campaign = self.env["doorway.campaign"].sudo()
        state_labels = dict(Campaign._fields["state"].selection)
        lookup = {}
        for camp in Campaign.search([("vicidial_campaign_id", "!=", False)]):
            lookup[camp.vicidial_campaign_id] = {
                "id": camp.id,
                "name": camp.name,
                "state": camp.state,
                "state_label": state_labels.get(camp.state, camp.state),
            }
        return lookup, state_labels

    @api.model
    def get_dashboard_campaign_options(self):
        """Options filtre campagne pour les tableaux de bord OWL."""
        Campaign = self.env["doorway.campaign"].sudo()
        state_labels = dict(Campaign._fields["state"].selection)
        return [
            {
                "id": camp.id,
                "vicidial_id": camp.vicidial_campaign_id or "",
                "name": camp.name,
                "state": camp.state,
                "state_label": state_labels.get(camp.state, camp.state),
                "operational_label": camp.operational_label or "",
                "dial_site": camp.dial_site or "",
                "is_dialing_prod": bool(camp.is_dialing_prod),
            }
            for camp in Campaign.search([], order="name")
        ]

    @api.model
    def _dashboard_campaign_vicidial_ids(self, campaign_vicidial_id=None, campaign_state=None):
        """Résout les IDs VICIdial à inclure selon filtre campagne / statut."""
        if campaign_vicidial_id and campaign_vicidial_id not in ("all", ""):
            return [campaign_vicidial_id]
        if campaign_state and campaign_state not in ("all", ""):
            Campaign = self.env["doorway.campaign"].sudo()
            camps = Campaign.search(
                [("state", "=", campaign_state), ("vicidial_campaign_id", "!=", False)]
            )
            ids = [c.vicidial_campaign_id for c in camps if c.vicidial_campaign_id]
            return ids or ["__none__"]
        return None

    @api.model
    def _enrich_dashboard_row_campaign(self, row_data, campaign_lookup):
        camp_id = row_data.get("campagne") or ""
        info = campaign_lookup.get(camp_id) if camp_id else None
        row_data["campagne_name"] = info["name"] if info else (camp_id or "—")
        row_data["campagne_state"] = info["state"] if info else ""
        row_data["campagne_state_label"] = info["state_label"] if info else "—"
        return row_data

    @api.model
    def _format_call_duration(self, seconds, live=False):
        if live:
            return "En cours"
        if not seconds:
            return "0:00"
        return "%s:%02d" % (seconds // 60, seconds % 60)

    @api.model
    def _coaching_maps_for_syncs(self, syncs):
        Coaching = self.env.get("pe.coaching.call")
        by_call = {}
        by_lead = {}
        if not Coaching or not syncs:
            return by_call, by_lead
        call_ids = [s.vicidial_call_id for s in syncs if s.vicidial_call_id]
        lead_ids = [s.lead_id.id for s in syncs if s.lead_id]
        domain = ["|"]
        if call_ids:
            domain.append(("vicidial_call_id", "in", call_ids))
        if lead_ids:
            domain.append(("lead_id", "in", lead_ids))
        if len(domain) == 1:
            return by_call, by_lead
        for call in Coaching.sudo().search(domain):
            if call.vicidial_call_id:
                by_call[call.vicidial_call_id] = call
            if call.lead_id:
                by_lead[call.lead_id.id] = call
        return by_call, by_lead

    @api.model
    def _append_dashboard_row(
        self, rows, kpis, qual_labels, row_data, qualifications, seen
    ):
        row_id = row_data.get("id")
        if row_id in seen:
            return
        qual = row_data.get("qualification") or "non_fait"
        if (
            qualifications
            and "all" not in qualifications
            and qual not in qualifications
        ):
            return
        seen.add(row_id)
        kpis["total"] += 1
        if qual in kpis:
            kpis[qual] += 1
        row_data["qualification_label"] = qual_labels.get(qual, qual)
        rows.append(row_data)

    @api.model
    def get_calls_coaching_dashboard(
        self,
        date_from=None,
        date_to=None,
        qualifications=None,
        user_id=None,
        campaign_vicidial_id=None,
        campaign_state=None,
    ):
        """Données tableau de bord appels — sync VICIdial temps réel + coaching."""
        Sync = self.env["doorway.vicidial.call.sync"].sudo()
        qual_labels = dict(self._fields["qualification_statut"].selection)
        campaign_lookup, state_labels = self._dashboard_campaign_lookup()
        kpis = {k: 0 for k in self._dashboard_kpi_keys()}
        rows = []
        seen = set()

        camp_vicidial_ids = self._dashboard_campaign_vicidial_ids(
            campaign_vicidial_id, campaign_state
        )

        sync_domain = []
        if date_from:
            sync_domain.append(("date_debut", ">=", date_from))
        if date_to:
            sync_domain.append(("date_debut", "<=", date_to + " 23:59:59"))
        if camp_vicidial_ids is not None:
            sync_domain.append(("campagne_vicidial", "in", camp_vicidial_ids))
        if user_id:
            employee = Sync._resolve_employee_for_user(
                self.env["res.users"].browse(user_id)
            )
            if employee:
                sync_domain.append(("employee_id", "=", employee.id))
            else:
                sync_domain.append(("user_id", "=", user_id))

        syncs = Sync.search(sync_domain, order="date_debut desc", limit=500)
        by_call, by_lead = self._coaching_maps_for_syncs(syncs)

        for sync in syncs:
            qual = (
                sync.lead_id.qualification_statut
                if sync.lead_id
                else "non_fait"
            )
            live = sync.statut_vicidial == "INCALL"
            coaching = (
                by_call.get(sync.vicidial_call_id)
                or (by_lead.get(sync.lead_id.id) if sync.lead_id else None)
            )
            row_data = self._enrich_dashboard_row_campaign(
                {
                    "id": "sync-%s" % sync.id,
                    "date_appel": fields.Datetime.to_string(sync.date_debut),
                    "lead_id": sync.lead_id.id if sync.lead_id else False,
                    "lead_name": sync.lead_name
                    or (sync.lead_id.name if sync.lead_id else ""),
                    "phone": sync.phone or "",
                    "employee": sync.employee_id.name
                    or (sync.user_id.name if sync.user_id else ""),
                    "duree": self._format_call_duration(
                        sync.duree_secondes, live=live
                    ),
                    "qualification": qual,
                    "score_global": sync.lead_id.score_qualification
                    if sync.lead_id
                    else 0,
                    "campagne": sync.campagne_vicidial or "",
                    "audio_url": coaching.audio_url if coaching else "",
                    "analyse_done": coaching.analyse_done if coaching else False,
                    "conseil_claude": (coaching.conseil_claude or "")[:200]
                    if coaching
                    else "",
                    "live": live,
                },
                campaign_lookup,
            )
            self._append_dashboard_row(
                rows,
                kpis,
                qual_labels,
                row_data,
                qualifications,
                seen,
            )

        lead_domain = [("source_vicidial", "=", True)]
        if date_from:
            lead_domain.append(("write_date", ">=", date_from))
        if date_to:
            lead_domain.append(("write_date", "<=", date_to + " 23:59:59"))
        if camp_vicidial_ids is not None:
            lead_domain.append(("campagne_vicidial", "in", camp_vicidial_ids))
        if user_id:
            lead_domain.append(("user_id", "=", user_id))
        leads = self.sudo().search(lead_domain, order="write_date desc", limit=200)
        for lead in leads:
            sync = lead.vicidial_sync_ids[:1]
            row_id = "lead-%s" % lead.id
            if sync and ("sync-%s" % sync.id) in seen:
                continue
            call_date = (
                sync.date_debut
                if sync
                else (lead.last_call_date or lead.write_date)
            )
            row_data = self._enrich_dashboard_row_campaign(
                {
                    "id": row_id,
                    "date_appel": fields.Datetime.to_string(call_date),
                    "lead_id": lead.id,
                    "lead_name": lead.name,
                    "phone": lead.phone or "",
                    "employee": lead.user_id.name if lead.user_id else "",
                    "duree": self._format_call_duration(
                        sync.duree_secondes if sync else 0,
                        live=bool(sync and sync.statut_vicidial == "INCALL"),
                    ),
                    "qualification": lead.qualification_statut,
                    "score_global": lead.score_qualification,
                    "campagne": lead.campagne_vicidial or "",
                    "audio_url": "",
                    "analyse_done": False,
                    "conseil_claude": "",
                    "live": bool(sync and sync.statut_vicidial == "INCALL"),
                },
                campaign_lookup,
            )
            self._append_dashboard_row(
                rows,
                kpis,
                qual_labels,
                row_data,
                qualifications,
                seen,
            )

        rows.sort(key=lambda r: r.get("date_appel") or "", reverse=True)
        return {
            "rows": rows[:500],
            "kpis": kpis,
            "campaigns": self.get_dashboard_campaign_options(),
            "campaign_states": [
                {"id": key, "label": label}
                for key, label in state_labels.items()
            ],
        }

    @api.model
    def _campaign_stats_status_columns(self):
        """Colonnes du tableau Campagnes & qualifications (libellés FR courts)."""
        selection = dict(self._fields["qualification_statut"].selection)
        short_labels = {
            "qualifie": "Qualifié",
            "rdv": "RDV",
            "a_rappeler": "Rappel",
            "pas_interesse": "Pas intéressé",
            "messagerie": "Répondeur",
            "faux_num": "Mauvais numéro",
            "non_fait": "À qualifier",
            "deja_servi": "Déjà servi",
            "locataire": "Locataire",
            "dnc": "DNC",
            "hors_cible": "Hors cible",
            "b2b_valide": "B2B validé",
        }
        display_order = (
            "qualifie",
            "rdv",
            "a_rappeler",
            "pas_interesse",
            "messagerie",
            "faux_num",
            "non_fait",
            "deja_servi",
            "locataire",
            "dnc",
            "hors_cible",
            "b2b_valide",
        )
        return [
            {
                "key": key,
                "label": short_labels.get(key, selection.get(key, key)),
            }
            for key in display_order
            if key in selection
        ]

    @api.model
    def _empty_campaign_status_counts(self):
        return {col["key"]: 0 for col in self._campaign_stats_status_columns()}

    @api.model
    def _finalize_campaign_stats_entry(self, entry, state_labels):
        statuses = entry.get("statuses") or {}
        entry["qualified"] = (
            statuses.get("qualifie", 0)
            + statuses.get("b2b_valide", 0)
            + statuses.get("rdv", 0)
        )
        entry["rdv"] = statuses.get("rdv", 0)
        entry["pending"] = statuses.get("non_fait", 0)
        entry["rappels"] = statuses.get("a_rappeler", 0)
        entry["state_label"] = state_labels.get(
            entry.get("state"), entry.get("state") or "—"
        )
        return entry

    @api.model
    def _new_campaign_stats_entry(
        self, camp_id, name, odoo_campaign_id=False, state=""
    ):
        return {
            "vicidial_id": camp_id,
            "name": name,
            "odoo_campaign_id": odoo_campaign_id,
            "state": state,
            "total": 0,
            "qualified": 0,
            "rdv": 0,
            "pending": 0,
            "rappels": 0,
            "statuses": self._empty_campaign_status_counts(),
        }

    @api.model
    def get_campaign_qualification_stats(
        self,
        date_from=None,
        date_to=None,
        user_id=None,
        campaign_vicidial_id=None,
        campaign_state=None,
    ):
        """Stats qualifications par campagne VICIdial (comptage par statut)."""
        domain = [("source_vicidial", "=", True)]
        if date_from:
            domain.append(("write_date", ">=", date_from))
        if date_to:
            domain.append(("write_date", "<=", date_to + " 23:59:59"))
        camp_vicidial_ids = self._dashboard_campaign_vicidial_ids(
            campaign_vicidial_id, campaign_state
        )
        if camp_vicidial_ids is not None:
            domain.append(("campagne_vicidial", "in", camp_vicidial_ids))
        if user_id:
            domain.append(("user_id", "=", user_id))

        Campaign = self.env["doorway.campaign"].sudo()
        state_labels = dict(Campaign._fields["state"].selection)
        vicidial_names = {
            c.vicidial_campaign_id: c.name
            for c in Campaign.search([("vicidial_campaign_id", "!=", False)])
        }
        stats = {}

        grouped = self.sudo().read_group(
            domain,
            ["qualification_statut"],
            ["campagne_vicidial", "qualification_statut"],
            lazy=False,
        )
        for row in grouped:
            camp_id = row.get("campagne_vicidial") or "—"
            qual = row.get("qualification_statut") or "non_fait"
            count = row.get("__count", 0) or 0
            if camp_id not in stats:
                odoo_camp = Campaign.search(
                    [("vicidial_campaign_id", "=", camp_id)], limit=1
                )
                stats[camp_id] = self._new_campaign_stats_entry(
                    camp_id,
                    vicidial_names.get(camp_id, camp_id),
                    odoo_camp.id if odoo_camp else False,
                    odoo_camp.state if odoo_camp else "",
                )
            entry = stats[camp_id]
            entry["total"] += count
            if qual in entry["statuses"]:
                entry["statuses"][qual] = count

        active_domain = [("state", "in", ("ready", "active"))]
        if campaign_state and campaign_state not in ("all", ""):
            active_domain = [("state", "=", campaign_state)]
        if campaign_vicidial_id and campaign_vicidial_id not in ("all", ""):
            active_domain.append(("vicidial_campaign_id", "=", campaign_vicidial_id))
        for camp in Campaign.search(active_domain):
            camp_id = camp.vicidial_campaign_id
            if camp_id and camp_id not in stats:
                stats[camp_id] = self._new_campaign_stats_entry(
                    camp_id, camp.name, camp.id, camp.state
                )

        rows = [
            self._finalize_campaign_stats_entry(entry, state_labels)
            for entry in stats.values()
        ]
        return sorted(rows, key=lambda x: (-x["total"], x["name"]))

    @api.model
    def get_qualification_hub_data(
        self,
        date_from=None,
        date_to=None,
        campaign_vicidial_id=None,
        campaign_state=None,
    ):
        """Hub Qualification CRM : dashboard, file et supervision."""
        user = self.env.user
        is_supervisor = user.has_group(
            "doorway_vicidial_campaigns.group_vicidial_supervisor"
        )
        today = fields.Date.today()
        if not date_from:
            date_from = fields.Date.to_string(today - timedelta(days=7))
        if not date_to:
            date_to = fields.Date.to_string(today)

        camp_vicidial_ids = self._dashboard_campaign_vicidial_ids(
            campaign_vicidial_id, campaign_state
        )
        queue_domain = [("source_vicidial", "=", True), ("user_id", "=", user.id)]
        if camp_vicidial_ids is not None:
            queue_domain.append(("campagne_vicidial", "in", camp_vicidial_ids))
        queue_leads = self.search(
            queue_domain, order="write_date desc", limit=15
        )
        queue_pending = self.search_count(
            queue_domain + [("qualification_statut", "=", "non_fait")]
        )
        qual_labels = dict(self._fields["qualification_statut"].selection)

        dashboard_user_id = None if is_supervisor else user.id
        dashboard = self.get_calls_coaching_dashboard(
            date_from=date_from,
            date_to=date_to,
            qualifications=["all"],
            user_id=dashboard_user_id,
            campaign_vicidial_id=campaign_vicidial_id,
            campaign_state=campaign_state,
        )
        kpi_cards = [
            {"key": "total", "label": "Total appels", "value": dashboard["kpis"].get("total", 0)},
            {"key": "qualifie", "label": "Qualifiés", "value": dashboard["kpis"].get("qualifie", 0)},
            {"key": "a_rappeler", "label": "Rappels", "value": dashboard["kpis"].get("a_rappeler", 0)},
            {"key": "rdv", "label": "RDV", "value": dashboard["kpis"].get("rdv", 0)},
            {"key": "pas_interesse", "label": "Pas intéressé", "value": dashboard["kpis"].get("pas_interesse", 0)},
            {"key": "messagerie", "label": "Répondeur", "value": dashboard["kpis"].get("messagerie", 0)},
            {"key": "faux_num", "label": "Mauvais numéro", "value": dashboard["kpis"].get("faux_num", 0)},
        ]

        supervision = None
        if is_supervisor:
            supervision = self.env[
                "doorway.vicidial.agent.session"
            ].get_supervisor_dashboard_data(date_from=date_from, date_to=date_to)

        Sync = self.env["doorway.vicidial.call.sync"].sudo()
        live_sync = Sync.search(
            [
                ("user_id", "=", user.id),
                ("statut_vicidial", "=", "INCALL"),
                ("date_fin", "=", False),
            ],
            limit=1,
            order="date_debut desc",
        )
        live_call = None
        if live_sync:
            live_call = {
                "sync_id": live_sync.id,
                "lead_id": live_sync.lead_id.id if live_sync.lead_id else False,
                "lead_name": live_sync.lead_name
                or (live_sync.lead_id.name if live_sync.lead_id else ""),
                "phone": live_sync.phone or "",
                "campagne": live_sync.campagne_vicidial or "",
                "since": fields.Datetime.to_string(live_sync.date_debut),
            }

        campaigns = self.get_campaign_qualification_stats(
            date_from=date_from,
            date_to=date_to,
            user_id=dashboard_user_id,
            campaign_vicidial_id=campaign_vicidial_id,
            campaign_state=campaign_state,
        )
        _, state_labels = self._dashboard_campaign_lookup()

        return {
            "is_supervisor": is_supervisor,
            "date_from": date_from,
            "date_to": date_to,
            "refreshed_at": fields.Datetime.to_string(fields.Datetime.now()),
            "live_call": live_call,
            "campaigns": campaigns,
            "status_columns": self._campaign_stats_status_columns(),
            "campaign_options": self.get_dashboard_campaign_options(),
            "campaign_states": [
                {"id": key, "label": label}
                for key, label in state_labels.items()
            ],
            "queue": {
                "total": self.search_count(queue_domain),
                "pending": queue_pending,
                "leads": [
                    {
                        "id": lead.id,
                        "name": lead.name,
                        "phone": lead.phone or "",
                        "city": lead.city or "",
                        "qualification_statut": lead.qualification_statut,
                        "qualification_label": qual_labels.get(
                            lead.qualification_statut, lead.qualification_statut
                        ),
                        "score": lead.score_qualification,
                        "campagne": lead.campagne_vicidial or "",
                    }
                    for lead in queue_leads
                ],
            },
            "dashboard": {
                "kpis": dashboard["kpis"],
                "kpi_cards": kpi_cards,
                "rows": (dashboard.get("rows") or [])[:20],
            },
            "supervision": supervision,
        }

    def _sync_vicidial_qualification_done(self):
        Sync = self.env["doorway.vicidial.call.sync"].sudo()
        for lead in self:
            sync = Sync.search(
                [
                    ("lead_id", "=", lead.id),
                    ("statut_vicidial", "=", "INCALL"),
                ],
                limit=1,
            )
            if sync:
                sync.qualification_faite = True

    def action_marquer_qualifie(self):
        for lead in self:
            lead.write(
                {
                    "qualification_statut": "qualifie",
                    "type": "opportunity",
                }
            )
            prochaine = self.env["crm.stage"].search(
                [
                    ("team_id", "=", lead.team_id.id),
                    ("sequence", ">", lead.stage_id.sequence),
                ],
                order="sequence asc",
                limit=1,
            )
            if prochaine:
                lead.stage_id = prochaine.id
            lead._sync_vicidial_qualification_done()
            lead._record_session_qualification()
            if lead.type_projet == "b2b_partenaire":
                lead._notifier_karine_b2b()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Lead qualifié"),
                "message": _("%s — Score %s/100")
                % (self[:1].name, self[:1].score_qualification),
                "type": "success",
            },
        }

    def _record_session_qualification(self):
        Session = self.env["doorway.vicidial.agent.session"]
        session = Session.get_active_session(self.env.user)
        if session:
            session.record_call_event(qualification_faite=True)

    def _rappel_assignee_id(self):
        """France B2C : rappels assignés à Zakaria (pipeline Rénovation)."""
        self.ensure_one()
        if (self.campagne_vicidial or "")[:8] == "DW_FRB2C":
            zakaria = self.env["res.users"].sudo().search(
                [("login", "=", "zakaria@agencedoorway.com")], limit=1
            )
            if zakaria:
                return zakaria.id
        return self.user_id.id or self.env.uid

    def action_marquer_rappel(self):
        model = self.env["ir.model"]._get("crm.lead")
        for lead in self:
            rappel_dt = lead.rappel_datetime or (
                fields.Datetime.now() + timedelta(days=1)
            )
            if isinstance(rappel_dt, str):
                rappel_dt = fields.Datetime.from_string(rappel_dt)
            rappel_date = rappel_dt.date()
            assignee = lead._rappel_assignee_id()
            lead.write(
                {
                    "qualification_statut": "a_rappeler",
                    "user_id": assignee,
                }
            )
            lead._sync_coaching_qualification("a_rappeler")
            self.env["mail.activity"].sudo().create(
                {
                    "res_model_id": model.id,
                    "res_id": lead.id,
                    "user_id": assignee,
                    "summary": _("Rappeler ce contact"),
                    "date_deadline": rappel_date,
                }
            )
            lead._create_rappel_calendar_event(rappel_dt)
            session = self.env["doorway.vicidial.agent.session"].get_active_session(
                self.env.user
            )
            if session:
                session.record_call_event(is_rappel=True)
        return True

    def _create_rappel_calendar_event(self, start_dt):
        self.ensure_one()
        if "calendar.event" not in self.env:
            return
        if isinstance(start_dt, str):
            start_dt = fields.Datetime.from_string(start_dt)
        end_dt = start_dt + timedelta(minutes=15)
        self.env["calendar.event"].sudo().create(
            {
                "name": _("Rappel Appels — %s") % self.name,
                "start": start_dt,
                "stop": end_dt,
                "user_id": self.user_id.id or self.env.uid,
                "partner_ids": [(6, 0, [self.env.user.partner_id.id])],
                "description": _("Tél: %s\nNotes: %s")
                % (self.phone or "—", self.notes_qualification or "—"),
            }
        )

    def register_renofacile_consent(
        self, consent_renov, consent_artisans, preuve=False, source="marenofacile"
    ):
        """Enregistre le consentement explicite de recontact RénoFacile."""
        for lead in self:
            vals = {
                "consentement_recontact_renov": bool(consent_renov),
                "consentement_recontact_artisans": bool(consent_artisans),
                "consentement_recontact_date": fields.Datetime.now(),
                "consentement_recontact_source": source or "marenofacile",
            }
            if preuve:
                vals["consentement_recontact_preuve"] = preuve
            lead.write(vals)
            lead.message_post(
                body=_(
                    "<b>Consentement rappel RénoFacile</b><br/>"
                    "Projet rénovation : %(renov)s<br/>"
                    "Artisans partenaires : %(artisans)s<br/>"
                    "Source : %(source)s"
                    "%(preuve)s"
                )
                % {
                    "renov": _("Oui") if consent_renov else _("Non"),
                    "artisans": _("Oui") if consent_artisans else _("Non"),
                    "source": source or "marenofacile",
                    "preuve": (
                        "<br/>Preuve : %s" % preuve if preuve else ""
                    ),
                },
                message_type="comment",
                subtype_xmlid="mail.mt_comment",
            )
        return True

    def action_marquer_hors_cible(self):
        self.write({"qualification_statut": "hors_cible", "active": False})
        return True

    def action_marquer_b2b_karine(self):
        for lead in self:
            lead.write({"qualification_statut": "b2b_valide", "type": "opportunity"})
            lead._sync_vicidial_qualification_done()
            lead._notifier_karine_b2b()
        return True

    def action_doorway_phone_call(self):
        """Route les agents vers le poste WebRTC VICIdial (composition manuelle)."""
        self.ensure_one()
        phone = (self.phone or "").strip()
        if not phone and self.partner_id:
            partner = self.partner_id
            phone = (partner.mobile or partner.phone or "").strip()
        if not phone:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Téléphone"),
                    "message": _("Aucun numéro renseigné sur cette opportunité."),
                    "type": "warning",
                    "sticky": False,
                },
            }
        return {
            "type": "ir.actions.client",
            "tag": "vicidial_workstation_action",
            "params": {
                "doorway_vicidial_dial_phone": phone,
                "doorway_vicidial_lead_id": self.id,
            },
        }

    def _notifier_karine_b2b(self):
        self.ensure_one()
        karine = self.env["res.users"].sudo().search(
            [("login", "ilike", "karine@agencedoorway.com")], limit=1
        )
        if not karine:
            return
        type_label = dict(self._fields["type_partenaire"].selection).get(
            self.type_partenaire, ""
        )
        self.message_post(
            partner_ids=[karine.partner_id.id],
            body=_(
                "<b>Nouveau partenaire B2B qualifié (Appels)</b><br/>"
                "Contact : %(name)s<br/>"
                "Type : %(type)s<br/>"
                "Zones : %(zones)s<br/>"
                "Score : %(score)s/100<br/>"
                "Notes : %(notes)s"
            )
            % {
                "name": self.name,
                "type": type_label or "—",
                "zones": self.zones_intervention or "—",
                "score": self.score_qualification,
                "notes": self.notes_qualification or "—",
            },
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
        )

    WORKSTATION_QUALIFICATION_BUTTONS = (
        ("qualifie", "Qualifié chaud", "success"),
        ("rdv", "RDV / Démo", "primary"),
        ("a_rappeler", "Rappel", "warning"),
        ("repondu", "Répondu", "teal"),
        ("pas_reponse", "Pas de réponse", "muted"),
        ("messagerie", "Messagerie", "muted"),
        ("pas_interesse", "Refus", "muted"),
        ("faux_num", "Mauvais numéro", "danger"),
        ("dnc", "DNC", "danger"),
    )

    WORKSTATION_CALL_OUTCOME_ONLY = frozenset({"repondu", "pas_reponse"})

    @api.model
    def get_workstation_qualification_options(self):
        """Boutons de qualification rapide — panneau contact poste d'appels."""
        selection = dict(self._fields["qualification_statut"].selection)
        return [
            {
                "code": code,
                "label": label,
                "tone": tone,
                "crm_label": selection.get(code, label),
            }
            for code, label, tone in self.WORKSTATION_QUALIFICATION_BUTTONS
        ]

    def _qualification_label(self, statut=None):
        self.ensure_one()
        key = statut or self.qualification_statut or "non_fait"
        return dict(self._fields["qualification_statut"].selection).get(key, key)

    def apply_workstation_qualification(self, statut, note=None):
        """Qualification depuis le poste d'appels (CRM + sync VICIdial)."""
        self.ensure_one()
        statut = (statut or "").strip()
        valid = {code for code, _label, _tone in self.WORKSTATION_QUALIFICATION_BUTTONS}
        if statut not in valid:
            return False
        body = (note or "").strip()
        if body:
            from odoo.tools import plaintext2html

            label_map = dict(
                (code, label) for code, label, _tone in self.WORKSTATION_QUALIFICATION_BUTTONS
            )
            self.message_post(
                body=plaintext2html(body),
                subject=_("Note d'appel — %s") % label_map.get(statut, statut),
            )
        if statut in self.WORKSTATION_CALL_OUTCOME_ONLY:
            return True
        handlers = {
            "qualifie": self.action_marquer_qualifie,
            "rdv": self.action_qualif_rdv,
            "a_rappeler": self.action_marquer_rappel,
            "pas_interesse": self.action_qualif_pas_interesse,
            "messagerie": self.action_qualif_messagerie,
            "dnc": self.action_qualif_dnc,
            "faux_num": lambda: self._action_set_qualification(
                "faux_num", {"active": False}
            ),
        }
        handler = handlers.get(statut)
        if handler:
            handler()
        return True
