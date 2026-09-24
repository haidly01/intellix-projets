# -*- coding: utf-8 -*-
import datetime
import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

VICIDIAL_STATUS_MAP = {
    "INCALL": "en_appel",
    "RINGING": "en_appel",
    "PAUSED": "en_pause",
    "READY": "actif",
    "CLOSER": "en_appel",
}


class PePresenceLog(models.Model):
    _name = "pe.presence.log"
    _description = "Log présence réelle par employé"
    _order = "timestamp desc"

    employee_id = fields.Many2one("hr.employee", required=True, index=True)
    timestamp = fields.Datetime(
        default=fields.Datetime.now, required=True, index=True
    )
    statut = fields.Selection(
        [
            ("actif", "Actif"),
            ("en_appel", "En appel (VICIdial)"),
            ("en_pause", "En pause (VICIdial PAUSED)"),
            ("inactif", "Inactif (session ouverte, pas d'activité)"),
            ("deconnecte", "Déconnecté"),
        ],
        required=True,
    )
    source = fields.Selection(
        [
            ("vicidial", "VICIdial"),
            ("odoo", "Odoo session"),
            ("cron", "Cron auto-détection"),
        ]
    )
    vicidial_agent_id = fields.Char(string="Agent ID VICIdial")
    note = fields.Char()


class PePresenceSummary(models.Model):
    _name = "pe.presence.summary"
    _description = "Résumé présence journalier"
    _order = "date desc"

    employee_id = fields.Many2one("hr.employee", required=True, index=True)
    date = fields.Date(required=True, index=True)
    heure_debut = fields.Datetime()
    heure_fin = fields.Datetime()
    heures_reelles = fields.Float(string="Heures réelles travaillées")
    heures_pause = fields.Float(string="Heures en pause")
    heures_inactif = fields.Float(string="Heures inactif (session idle)")
    nb_appels_vicidial = fields.Integer(string="Appels VICIdial")
    nb_leads_generes = fields.Integer(string="Leads générés")
    statut_jour = fields.Selection(
        [
            ("present", "Présent"),
            ("partiel", "Partiel"),
            ("absent", "Absent"),
            ("conge", "Congé"),
        ]
    )

    _employee_date_unique = models.Constraint(
        "unique(employee_id, date)",
        "Un seul résumé par employé par jour.",
    )

    @api.model
    def generer_resumes_hier(self):
        yesterday = fields.Date.today() - datetime.timedelta(days=1)
        svc = self.env["pe.presence.service"]
        employees = self.env["hr.employee"].search([("active", "=", True)])
        for emp in employees:
            on_leave = self.env["hr.leave"].search_count(
                [
                    ("employee_id", "=", emp.id),
                    ("state", "=", "validate"),
                    ("date_from", "<=", yesterday),
                    ("date_to", ">=", yesterday),
                ]
            )
            if on_leave:
                self._upsert_summary(
                    emp.id,
                    yesterday,
                    {"statut_jour": "conge", "heures_reelles": 0.0},
                )
                continue
            hours = svc.calculer_heures_reelles_jour(emp.id, yesterday)
            statut = "absent"
            if hours["heures_reelles"] >= 6:
                statut = "present"
            elif hours["heures_reelles"] >= 2:
                statut = "partiel"
            debut_jour = datetime.datetime.combine(yesterday, datetime.time.min)
            fin_jour = datetime.datetime.combine(yesterday, datetime.time(23, 59, 59))
            user = emp.user_id
            nb_appels = 0
            nb_leads = 0
            if user:
                Sync = self.env.get("doorway.vicidial.call.sync")
                if Sync:
                    nb_appels = Sync.sudo().search_count(
                        [
                            ("user_id", "=", user.id),
                            ("date_debut", ">=", debut_jour),
                            ("date_debut", "<=", fin_jour),
                        ]
                    )
                Session = self.env.get("doorway.vicidial.agent.session")
                if Session:
                    nb_leads = sum(
                        Session.sudo()
                        .search(
                            [
                                ("user_id", "=", user.id),
                                ("date_start", ">=", debut_jour),
                                ("date_start", "<=", fin_jour),
                            ]
                        )
                        .mapped("nb_qualifies")
                    )
            self._upsert_summary(
                emp.id,
                yesterday,
                {
                    "heures_reelles": hours["heures_reelles"],
                    "heures_pause": hours["heures_pause"],
                    "heures_inactif": hours["heures_inactif"],
                    "nb_appels_vicidial": nb_appels,
                    "nb_leads_generes": nb_leads,
                    "statut_jour": statut,
                },
            )

    def _upsert_summary(self, employee_id, date, vals):
        rec = self.search(
            [("employee_id", "=", employee_id), ("date", "=", date)], limit=1
        )
        if rec:
            rec.write(vals)
        else:
            vals.update({"employee_id": employee_id, "date": date})
            self.create(vals)


class PePresenceService(models.AbstractModel):
    _name = "pe.presence.service"
    _description = "Service calcul présence People Engine"

    def _icp_int(self, key, default):
        return int(
            self.env["ir.config_parameter"]
            .sudo()
            .get_param(key, default)
            or default
        )

    def sync_all_presence(self):
        employees = self.env["hr.employee"].search([("active", "=", True)])
        for emp in employees:
            self._sync_employee(emp)

    def _sync_employee(self, employee):
        statut_vicidial = self._get_vicidial_status(employee)
        statut_odoo = self._get_odoo_session_status(employee)
        if statut_vicidial in ("en_appel", "en_pause"):
            statut_final = statut_vicidial
            source = "vicidial"
        elif statut_odoo == "actif":
            statut_final = "actif"
            source = "odoo"
        elif statut_odoo == "inactif":
            statut_final = "inactif"
            source = "odoo"
        else:
            statut_final = "deconnecte"
            source = "cron"

        dernier = self.env["pe.presence.log"].search(
            [("employee_id", "=", employee.id)],
            limit=1,
            order="timestamp desc",
        )
        if not dernier or dernier.statut != statut_final:
            profile = self.env["pe.employee.profile"].search(
                [("employee_id", "=", employee.id)], limit=1
            )
            self.env["pe.presence.log"].create(
                {
                    "employee_id": employee.id,
                    "statut": statut_final,
                    "source": source,
                    "vicidial_agent_id": profile.vicidial_agent_id
                    if profile
                    else False,
                }
            )

    def _get_vicidial_login(self, employee):
        profile = self.env["pe.employee.profile"].search(
            [("employee_id", "=", employee.id)], limit=1
        )
        vicidial_user = (
            (profile.vicidial_user or profile.vicidial_agent_id or "").strip()
            if profile
            else ""
        )
        if not vicidial_user and employee.user_id:
            agent = self.env.get("doorway.campaign.agent.user")
            if agent:
                rec = agent.sudo().search(
                    [("user_id", "=", employee.user_id.id), ("active", "=", True)],
                    limit=1,
                )
                vicidial_user = (rec.vicidial_user or "").strip() if rec else ""
        return vicidial_user or None

    def _get_vicidial_status(self, employee):
        vicidial_user = self._get_vicidial_login(employee)
        if not vicidial_user:
            return None
        try:
            from odoo.addons.doorway_vicidial_campaigns.services.vicidial_service import (
                VicidialService,
            )

            svc = VicidialService(self.env)
            if not svc.is_available():
                return None
            conn = svc._connect()
            try:
                cur = conn.cursor(dictionary=True)
                cur.execute(
                    """
                    SELECT status FROM vicidial_live_agents
                    WHERE user = %s
                      AND last_update_time > DATE_SUB(NOW(), INTERVAL 5 MINUTE)
                    LIMIT 1
                    """,
                    (vicidial_user,),
                )
                row = cur.fetchone()
                cur.close()
            finally:
                conn.close()
            if not row:
                return None
            return VICIDIAL_STATUS_MAP.get((row.get("status") or "").upper())
        except Exception as exc:  # noqa: BLE001
            _logger.warning(
                "VICIdial presence error for %s: %s", employee.name, exc
            )
            return None

    def _get_odoo_session_status(self, employee):
        user = employee.user_id
        if not user:
            return "deconnecte"
        Presence = self.env.get("mail.presence")
        if not Presence:
            return "deconnecte"
        presence = Presence.search([("user_id", "=", user.id)], limit=1)
        if not presence:
            return "deconnecte"
        seuil_inactif = self._icp_int("people_engine.seuil_inactif_minutes", 10) * 60
        seuil_deco = self._icp_int(
            "people_engine.seuil_deconnecte_minutes", 30
        ) * 60
        now = fields.Datetime.now()
        ref = presence.last_presence or presence.last_poll
        if not ref:
            return "deconnecte"
        delta = (now - ref).total_seconds()
        if delta < 300:
            return "actif"
        if delta < seuil_inactif:
            return "actif"
        if delta < seuil_deco:
            return "inactif"
        return "deconnecte"

    def calculer_heures_reelles_jour(self, employee_id, date):
        debut_jour = datetime.datetime.combine(date, datetime.time.min)
        fin_jour = datetime.datetime.combine(date, datetime.time(23, 59, 59))
        logs = self.env["pe.presence.log"].search(
            [
                ("employee_id", "=", employee_id),
                ("timestamp", ">=", debut_jour),
                ("timestamp", "<=", fin_jour),
            ],
            order="timestamp asc",
        )
        heures_reelles = heures_pause = heures_inactif = 0.0
        if len(logs) < 2:
            return {
                "heures_reelles": heures_reelles,
                "heures_pause": heures_pause,
                "heures_inactif": heures_inactif,
            }
        for i in range(len(logs) - 1):
            log_actuel = logs[i]
            log_suivant = logs[i + 1]
            duree_h = (
                log_suivant.timestamp - log_actuel.timestamp
            ).total_seconds() / 3600.0
            if log_actuel.statut in ("actif", "en_appel"):
                heures_reelles += duree_h
            elif log_actuel.statut == "en_pause":
                heures_pause += duree_h
            elif log_actuel.statut == "inactif":
                heures_inactif += duree_h
        return {
            "heures_reelles": round(heures_reelles, 2),
            "heures_pause": round(heures_pause, 2),
            "heures_inactif": round(heures_inactif, 2),
        }
