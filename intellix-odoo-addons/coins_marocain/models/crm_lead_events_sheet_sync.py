# -*- coding: utf-8 -*-
"""Sync Google Sheet Meta leads → pipeline CRM Événements (Zakaria)."""
from __future__ import annotations

import csv
import io
import logging
import re
from datetime import date, datetime

import requests

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)

SHEET_ID_DEFAULT = "1OfNUID-FO_kud70jeUZi002RFzqn1rsAzNSTR3tVhqw"
ZAKARIA_LOGIN = "zakaria@agencedoorway.com"

# Colonnes positionnelles Meta Lead Ads (feuille sans en-tête fiable)
COL_ID = 0
COL_CREATED = 1
COL_CAMPAIGN = 7
COL_FORM = 9
COL_PLATFORM = 11
COL_EVENT_TYPE = 12
COL_NB_PERSONNES = 13
COL_DATE_ENV = 14
COL_EMAIL = 15
COL_NAME = 16
COL_PHONE = 17
COL_INBOX = 18
COL_STATUS = 25

EVENT_TYPE_MAP = {
    "fiançailles-mariage": "mariage",
    "fiancailles-mariage": "mariage",
    "mariage": "mariage",
    "wedding": "mariage",
    "moment_festif_entre_amis/famille": "groupe_amis",
    "moment_festif_entre_amis_famille": "groupe_amis",
    "amis": "groupe_amis",
    "famille": "reunion_famille",
    "reunion_famille": "reunion_famille",
    "anniversaire": "anniversaire",
    "birthday": "anniversaire",
    "seminaire": "seminaire",
    "séminaire": "seminaire",
    "seminar": "seminaire",
}


class CrmLead(models.Model):
    _inherit = "crm.lead"

    coins_sheet_row_key = fields.Char(
        string="Clé ligne Google Sheet",
        index=True,
        copy=False,
        help="Identifiant Meta lead (ex. l:123…) pour dédupiquer les imports Sheet.",
    )
    coins_sheet_source_url = fields.Char(
        string="URL fiche Meta / inbox",
        copy=False,
    )

    @api.model
    def _coins_events_sheet_csv_url(self):
        icp = self.env["ir.config_parameter"].sudo()
        sheet_id = (
            icp.get_param("coins_marocain.events_sheet_id") or SHEET_ID_DEFAULT
        ).strip()
        gid = (icp.get_param("coins_marocain.events_sheet_gid") or "0").strip()
        return (
            f"https://docs.google.com/spreadsheets/d/{sheet_id}/export"
            f"?format=csv&gid={gid}"
        )

    @api.model
    def _coins_events_zakaria_user(self):
        icp = self.env["ir.config_parameter"].sudo()
        login = (
            icp.get_param("coins_marocain.events_default_user_login") or ZAKARIA_LOGIN
        ).strip()
        return self.env["res.users"].sudo().search(
            [("login", "=", login), ("active", "=", True)], limit=1
        )

    @api.model
    def _coins_ensure_zakaria_on_events_team(self, team, user):
        if not team or not user:
            return
        # Odoo 19 : member_ids sur crm.team
        if "member_ids" in team._fields and user not in team.member_ids:
            team.sudo().write({"member_ids": [(4, user.id)]})
        if "user_id" in team._fields and not team.user_id:
            team.sudo().write({"user_id": user.id})

    @api.model
    def _coins_parse_nb_personnes(self, raw):
        text = (raw or "").strip()
        if not text:
            return 0
        nums = [int(x) for x in re.findall(r"\d+", text)]
        if not nums:
            return 0
        if len(nums) >= 2:
            return max(nums)
        return nums[0]

    @api.model
    def _coins_parse_date_envisagée(self, raw):
        text = (raw or "").strip()
        if not text:
            return False, True
        # De 09/08/2026 à 16/08/2026
        m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", text)
        if m:
            d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
            try:
                return date(y, mo, d), False
            except ValueError:
                return False, True
        # Le mois de September / septembre 2026
        months = {
            "january": 1,
            "janvier": 1,
            "february": 2,
            "février": 2,
            "fevrier": 2,
            "march": 3,
            "mars": 3,
            "april": 4,
            "avril": 4,
            "may": 5,
            "mai": 5,
            "june": 6,
            "juin": 6,
            "july": 7,
            "juillet": 7,
            "august": 8,
            "août": 8,
            "aout": 8,
            "september": 9,
            "septembre": 9,
            "october": 10,
            "octobre": 10,
            "november": 11,
            "novembre": 11,
            "december": 12,
            "décembre": 12,
            "decembre": 12,
        }
        low = text.lower()
        year_m = re.search(r"(20\d{2})", low)
        year = int(year_m.group(1)) if year_m else date.today().year
        for name, mo in months.items():
            if name in low:
                try:
                    return date(year, mo, 1), True
                except ValueError:
                    return False, True
        return False, True

    @api.model
    def _coins_map_event_type(self, raw):
        key = (raw or "").strip().lower().replace(" ", "_")
        return EVENT_TYPE_MAP.get(key) or EVENT_TYPE_MAP.get(
            key.replace("’", "'")
        ) or "autre"

    @api.model
    def _coins_fetch_events_sheet_rows(self):
        url = self._coins_events_sheet_csv_url()
        resp = requests.get(url, timeout=45, headers={"User-Agent": "CoinsMarocainOdoo/1.0"})
        resp.raise_for_status()
        text = resp.content.decode("utf-8-sig", errors="replace")
        return list(csv.reader(io.StringIO(text)))

    @api.model
    def _coins_row_to_lead_vals(self, row, team, stage, user):
        if not row or len(row) < 18:
            return None
        lead_key = (row[COL_ID] or "").strip()
        if not lead_key.startswith("l:"):
            return None
        email = (row[COL_EMAIL] if len(row) > COL_EMAIL else "").strip()
        name = (row[COL_NAME] if len(row) > COL_NAME else "").strip()
        phone = (row[COL_PHONE] if len(row) > COL_PHONE else "").strip()
        if not email and not phone and not name:
            return None

        event_raw = row[COL_EVENT_TYPE] if len(row) > COL_EVENT_TYPE else ""
        event_type = self._coins_map_event_type(event_raw)
        nb = self._coins_parse_nb_personnes(
            row[COL_NB_PERSONNES] if len(row) > COL_NB_PERSONNES else ""
        )
        date_env, flexible = self._coins_parse_date_envisagée(
            row[COL_DATE_ENV] if len(row) > COL_DATE_ENV else ""
        )
        campaign = row[COL_CAMPAIGN] if len(row) > COL_CAMPAIGN else ""
        form_name = row[COL_FORM] if len(row) > COL_FORM else ""
        platform = row[COL_PLATFORM] if len(row) > COL_PLATFORM else ""
        inbox = row[COL_INBOX] if len(row) > COL_INBOX else ""
        created = row[COL_CREATED] if len(row) > COL_CREATED else ""

        lead_name = name or email or phone or lead_key
        desc_lines = [
            f"Import Google Sheet Coins Événements ({lead_key})",
            f"Type formulaire : {event_raw}",
            f"Personnes : {row[COL_NB_PERSONNES] if len(row) > COL_NB_PERSONNES else ''}",
            f"Date envisagée : {row[COL_DATE_ENV] if len(row) > COL_DATE_ENV else ''}",
            f"Campagne : {campaign}",
            f"Formulaire : {form_name}",
            f"Plateforme : {platform}",
            f"Créé Meta : {created}",
        ]
        if inbox:
            desc_lines.append(f"Inbox : {inbox}")

        vals = {
            "name": f"[Événement] {lead_name}",
            "contact_name": name or False,
            "email_from": email or False,
            "phone": phone or False,
            "description": "\n".join(desc_lines),
            "type": "opportunity",
            "team_id": team.id,
            "stage_id": stage.id if stage else False,
            "user_id": user.id if user else False,
            "coins_sheet_row_key": lead_key,
            "coins_sheet_source_url": inbox or False,
            "coins_type_evenement": event_type,
            "coins_nombre_personnes": nb,
            "coins_date_souhaitee": date_env or False,
            "coins_date_flexible": flexible,
            "coins_moyen_recontact": "whatsapp" if phone else "email",
            "coins_provenance_invites": (
                "local"
                if (phone or "").replace(" ", "").startswith("+212")
                or (phone or "").startswith("06")
                or (phone or "").startswith("07")
                else "international"
            ),
        }
        return vals

    @api.model
    def action_sync_coins_events_google_sheet(self):
        """Importe / met à jour les leads Sheet → équipe Événements, user Zakaria."""
        team = self.env.ref(
            "coins_marocain.crm_team_evenements", raise_if_not_found=False
        )
        if not team:
            return {"ok": False, "error": "crm_team_evenements introuvable"}

        stage = self.env.ref(
            "coins_marocain.crm_stage_evenements_coins_marocain",
            raise_if_not_found=False,
        )
        user = self._coins_events_zakaria_user()
        self._coins_ensure_zakaria_on_events_team(team, user)

        try:
            rows = self._coins_fetch_events_sheet_rows()
        except Exception as exc:  # noqa: BLE001
            _logger.exception("coins events sheet fetch failed")
            return {"ok": False, "error": str(exc)}

        created = updated = skipped = 0
        Lead = self.sudo()
        for row in rows:
            vals = self._coins_row_to_lead_vals(row, team, stage, user)
            if not vals:
                skipped += 1
                continue
            key = vals["coins_sheet_row_key"]
            existing = Lead.search([("coins_sheet_row_key", "=", key)], limit=1)
            if existing:
                # Ne pas écraser un commercial déjà réassigné ; garder Zakaria si vide
                write_vals = {
                    k: v
                    for k, v in vals.items()
                    if k
                    not in (
                        "team_id",
                        "stage_id",
                        "type",
                        "user_id",
                    )
                }
                if not existing.user_id and user:
                    write_vals["user_id"] = user.id
                if existing.team_id != team:
                    write_vals["team_id"] = team.id
                existing.write(write_vals)
                updated += 1
            else:
                Lead.create(vals)
                created += 1

        result = {
            "ok": True,
            "created": created,
            "updated": updated,
            "skipped": skipped,
            "zakaria_user_id": user.id if user else False,
            "team_id": team.id,
            "sheet_url": self._coins_events_sheet_csv_url(),
        }
        _logger.info("coins events sheet sync: %s", result)
        return result

    @api.model
    def cron_sync_coins_events_google_sheet(self):
        return self.action_sync_coins_events_google_sheet()
