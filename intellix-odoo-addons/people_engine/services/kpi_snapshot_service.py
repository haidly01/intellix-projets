# -*- coding: utf-8 -*-
import datetime
import logging

from odoo import api, fields, models

from odoo.addons.people_engine.services.disciplinary_config import SEUILS_KPI

_logger = logging.getLogger(__name__)

STAGE_DONE_NAMES = ("done", "terminé", "termine", "publié", "publie", "closed")


class PeKpiSnapshotService(models.AbstractModel):
    _name = "pe.kpi.snapshot.service"
    _description = "Calcul snapshots KPI commercial / marketing"

    @api.model
    def _iso_week_bounds(self, ref_date=None):
        ref = ref_date or fields.Date.today()
        lundi = ref - datetime.timedelta(days=ref.weekday())
        vendredi = lundi + datetime.timedelta(days=4)
        iso = ref.isocalendar()
        return lundi, vendredi, iso[1], iso[0]

    @api.model
    def resolve_departement(self, employee):
        """Détermine commercial / marketing / call_center depuis département ou profil."""
        profile = self.env["pe.employee.profile"].sudo().search(
            [("employee_id", "=", employee.id)], limit=1
        )
        labels = []
        if profile and profile.department_pe_id:
            labels.append(profile.department_pe_id.name or "")
            labels.append(profile.department_pe_id.code or "")
        if employee.department_id:
            labels.append(employee.department_id.name or "")
        text = " ".join(labels).lower()
        if "marketing" in text:
            return "marketing"
        if any(k in text for k in ("commercial", "vente", "closing", "sales")):
            return "commercial"
        if any(k in text for k in ("call", "cc", "centre")):
            return "call_center"
        if profile and profile.vicidial_user:
            return "call_center"
        return False

    @api.model
    def calculer_kpi_commercial(self, employee, date_debut, date_fin):
        if not employee.user_id:
            return {}
        uid = employee.user_id.id
        Lead = self.env["crm.lead"].sudo()
        dt_start = datetime.datetime.combine(date_debut, datetime.time.min)
        dt_end = datetime.datetime.combine(date_fin, datetime.time.max)

        leads_crees = Lead.search_count(
            [
                ("user_id", "=", uid),
                ("create_date", ">=", dt_start),
                ("create_date", "<=", dt_end),
            ]
        )
        leads_qualifies = Lead.search_count(
            [
                ("user_id", "=", uid),
                ("probability", ">", 0),
                ("type", "=", "opportunity"),
                ("write_date", ">=", dt_start),
                ("write_date", "<=", dt_end),
            ]
        )
        opportunites = Lead.search_count(
            [
                ("user_id", "=", uid),
                ("type", "=", "opportunity"),
                ("probability", "not in", [0, 100]),
                ("active", "=", True),
            ]
        )
        won_domain = [
            ("user_id", "=", uid),
            ("probability", "=", 100),
            ("active", "=", True),
        ]
        if "date_closed" in Lead._fields:
            won_domain.extend(
                [
                    ("date_closed", ">=", date_debut),
                    ("date_closed", "<=", date_fin),
                ]
            )
        else:
            won_domain.extend(
                [
                    ("write_date", ">=", dt_start),
                    ("write_date", "<=", dt_end),
                ]
            )
        deals = Lead.search(won_domain)
        deals_gagnes = len(deals)
        ca_genere = sum(deals.mapped("expected_revenue"))
        taux = (deals_gagnes / leads_crees * 100.0) if leads_crees else 0.0

        Activity = self.env["mail.activity"].sudo()
        rdv = relances = 0
        if Activity:
            activities = Activity.search(
                [
                    ("user_id", "=", uid),
                    ("date_deadline", ">=", date_debut),
                    ("date_deadline", "<=", date_fin),
                ]
            )
            for act in activities:
                cat = ""
                if act.activity_type_id and hasattr(act.activity_type_id, "category"):
                    cat = act.activity_type_id.category or ""
                name = (act.activity_type_id.name or "").lower()
                if cat == "meeting" or "rdv" in name or "meeting" in name:
                    rdv += 1
                elif cat in ("phonecall", "email") or any(
                    k in name for k in ("call", "email", "relance")
                ):
                    relances += 1

        pipeline = Lead.search(
            [
                ("user_id", "=", uid),
                ("probability", "not in", [0, 100]),
                ("active", "=", True),
            ]
        )
        return {
            "leads_crees": leads_crees,
            "leads_qualifies": leads_qualifies,
            "opportunites": opportunites,
            "deals_gagnes": deals_gagnes,
            "ca_genere": ca_genere,
            "taux_conversion_pc": round(taux, 2),
            "rdv_pris": rdv,
            "relances_effectuees": relances,
            "pipeline_valeur": sum(pipeline.mapped("expected_revenue")),
        }

    @api.model
    def calculer_kpi_marketing(self, employee, date_debut, date_fin):
        if not employee.user_id:
            return {}
        uid = employee.user_id.id
        dt_start = datetime.datetime.combine(date_debut, datetime.time.min)
        dt_end = datetime.datetime.combine(date_fin, datetime.time.max)

        Task = self.env["project.task"].sudo()
        taches_assignees = Task.search_count(
            [
                ("user_ids", "in", [uid]),
                ("create_date", ">=", dt_start),
                ("create_date", "<=", dt_end),
            ]
        )
        done_tasks = Task.search(
            [
                ("user_ids", "in", [uid]),
                ("write_date", ">=", dt_start),
                ("write_date", "<=", dt_end),
            ]
        )
        taches_completees = sum(
            1
            for t in done_tasks
            if (t.stage_id.name or "").lower() in STAGE_DONE_NAMES
            or getattr(t, "state", "") in ("1_done", "done")
        )
        taux = (
            (taches_completees / taches_assignees * 100.0) if taches_assignees else 0.0
        )

        heures = 0.0
        AnalyticLine = self.env["account.analytic.line"].sudo()
        if "employee_id" in AnalyticLine._fields:
            logs = AnalyticLine.search(
                [
                    ("employee_id", "=", employee.id),
                    ("date", ">=", date_debut),
                    ("date", "<=", date_fin),
                ]
            )
            heures = sum(logs.mapped("unit_amount"))

        Lead = self.env["crm.lead"].sudo()
        leads_marketing = Lead.search_count(
            [
                ("create_date", ">=", dt_start),
                ("create_date", "<=", dt_end),
                "|",
                ("source_id.name", "ilike", "marketing"),
                ("medium_id.name", "ilike", "marketing"),
            ]
        )

        publications = 0
        SocialPost = self.env.get("doorway.social.post")
        if SocialPost and "user_id" in SocialPost._fields:
            publications = SocialPost.search_count(
                [
                    ("user_id", "=", uid),
                    ("create_date", ">=", dt_start),
                    ("create_date", "<=", dt_end),
                ]
            )

        campagnes = 0
        Campaign = self.env.get("pe.cc.campaign")
        if Campaign:
            campagnes = Campaign.search_count([("active", "=", True)])

        return {
            "taches_assignees": taches_assignees,
            "taches_completees": taches_completees,
            "taux_completion_pc": round(taux, 2),
            "publications_faites": publications,
            "leads_generes_marketing": leads_marketing,
            "heures_loguees": round(heures, 2),
            "campagnes_actives": campagnes,
        }

    @api.model
    def evaluer_statut_kpi(self, kpis, departement):
        """Retourne ok | attention | critique selon SEUILS_KPI."""
        seuils = SEUILS_KPI.get(departement, {})
        scores = []
        critiques = []

        if departement == "commercial":
            leads = kpis.get("leads_crees", 0)
            conv = kpis.get("taux_conversion_pc", 0)
            rdv = kpis.get("rdv_pris", 0)
            s_leads = seuils.get("leads_par_semaine", {})
            s_conv = seuils.get("taux_conversion", {})
            rdv_min = seuils.get("rdv_minimum", 2)
            scores = [
                leads >= s_leads.get("minimum", 0),
                conv >= s_conv.get("minimum", 0),
                rdv >= rdv_min,
            ]
            critiques = [
                leads < s_leads.get("critique", 0),
                conv < s_conv.get("critique", 0),
            ]
        elif departement == "marketing":
            taux = kpis.get("taux_completion_pc", 0)
            heures = kpis.get("heures_loguees", 0)
            s_taches = seuils.get("taches_completees_semaine", {})
            scores = [
                taux >= s_taches.get("minimum", 0),
                heures >= seuils.get("heures_minimum", 35),
            ]
            critiques = [
                taux < s_taches.get("critique", 0),
                heures < seuils.get("heures_critique", 20),
            ]
        else:
            return "ok"

        if any(critiques):
            return "critique"
        if not all(scores):
            return "attention"
        return "ok"

    @api.model
    def _process_alerts_and_incidents(self, snapshot):
        disc = self.env["pe.disciplinary.service"].sudo()
        employee = snapshot.employee_id
        if snapshot.statut_global == "attention" and not snapshot.alerte_envoyee:
            disc._create_alert_if_new(
                employee.id,
                "kpi_sous_seuil",
                "KPI sous seuil — %s" % employee.name,
                "KPIs semaine %s/%s sous le minimum — coaching recommandé."
                % (snapshot.semaine, snapshot.annee),
                niveau="warning",
            )
            snapshot.alerte_envoyee = True
        elif snapshot.statut_global == "critique" and not snapshot.alerte_envoyee:
            disc._create_alert_if_new(
                employee.id,
                "kpi_sous_seuil",
                "KPI critique — %s" % employee.name,
                "KPIs semaine %s/%s critiques — procédure disciplinaire à envisager."
                % (snapshot.semaine, snapshot.annee),
                niveau="critique",
            )
            snapshot.alerte_envoyee = True

        if snapshot.statut_global in ("attention", "critique"):
            prev_week = snapshot.semaine - 1
            prev_year = snapshot.annee
            if prev_week < 1:
                prev_week = 52
                prev_year -= 1
            prev = self.env["pe.kpi.snapshot"].sudo().search(
                [
                    ("employee_id", "=", employee.id),
                    ("semaine", "=", prev_week),
                    ("annee", "=", prev_year),
                    ("departement", "=", snapshot.departement),
                    ("statut_global", "in", ("attention", "critique")),
                ],
                limit=1,
            )
            if prev and not snapshot.incident_cree:
                incident = disc._create_incident_if_new(
                    employee.id,
                    "kpi_sous_seuil",
                    "Performance insuffisante — 2 semaines consécutives sous seuil "
                    "(S%s/%s et S%s/%s)."
                    % (prev.semaine, prev.annee, snapshot.semaine, snapshot.annee),
                    gravite="modere",
                )
                if incident:
                    snapshot.write(
                        {"incident_cree": True, "incident_id": incident.id}
                    )

    @api.model
    def cron_kpi_hebdomadaire(self):
        """Cron vendredi 17h — snapshots + alertes."""
        today = fields.Date.today()
        if today.weekday() != 4:
            return True
        lundi, vendredi, semaine, annee = self._iso_week_bounds(today)
        Snapshot = self.env["pe.kpi.snapshot"].sudo()
        created = 0
        for employee in self.env["hr.employee"].sudo().search([("active", "=", True)]):
            dept = self.resolve_departement(employee)
            if dept not in ("commercial", "marketing"):
                continue
            existing = Snapshot.search(
                [
                    ("employee_id", "=", employee.id),
                    ("semaine", "=", semaine),
                    ("annee", "=", annee),
                    ("departement", "=", dept),
                ],
                limit=1,
            )
            if existing:
                snapshot = existing
            else:
                if dept == "commercial":
                    kpis = self.calculer_kpi_commercial(employee, lundi, vendredi)
                else:
                    kpis = self.calculer_kpi_marketing(employee, lundi, vendredi)
                statut = self.evaluer_statut_kpi(kpis, dept)
                snapshot = Snapshot.create(
                    {
                        "employee_id": employee.id,
                        "departement": dept,
                        "semaine": semaine,
                        "annee": annee,
                        "periode_debut": lundi,
                        "periode_fin": vendredi,
                        "statut_global": statut,
                        **kpis,
                    }
                )
                created += 1
            self._process_alerts_and_incidents(snapshot)
        _logger.info("PE KPI hebdo : %s snapshots traités", created)
        return True
