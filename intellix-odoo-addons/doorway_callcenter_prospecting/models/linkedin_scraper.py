# -*- coding: utf-8 -*-
import logging
import os
import re
import subprocess
import unicodedata
from datetime import datetime

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

SCRAPER_SCRIPT = "/home/odoo/scrapers/linkedin_sales_nav_scraper.py"


class LinkedInScraper(models.Model):
    _name = "linkedin.scraper"
    _description = "Orchestration scraper LinkedIn Sales Navigator"

    name = fields.Char(default="LinkedIn SN Karine")
    last_status = fields.Char(readonly=True)
    last_run = fields.Datetime(readonly=True)

    @api.model
    def _icp_set(self, key, value):
        self.env["ir.config_parameter"].sudo().set_param(key, value)

    @api.model
    def _icp_get(self, key, default=""):
        return self.env["ir.config_parameter"].sudo().get_param(key, default)

    @api.model
    def launch_scrape_subprocess(self, trigger="manual", extra_args=None):
        status = self._icp_get("linkedin.scraper.status", "idle")
        if status == "running":
            _logger.info("LinkedIn scraper déjà en cours — skip lancement")
            return False

        if not os.path.isfile(SCRAPER_SCRIPT):
            self._icp_set("linkedin.scraper.status", "error: script introuvable")
            _logger.error("Script scraper absent: %s", SCRAPER_SCRIPT)
            return False

        cookies = self._icp_get("linkedin.karine.cookies", "")
        if not cookies or "li_at=" not in cookies:
            self._icp_set("linkedin.scraper.status", "error: cookies manquants")
            return False

        cmd = ["/usr/bin/python3", SCRAPER_SCRIPT, "--triggered-by", trigger]
        if extra_args:
            cmd.extend(extra_args)

        try:
            subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
                cwd=os.path.dirname(SCRAPER_SCRIPT),
            )
            self._icp_set("linkedin.scraper.status", "running")
            self._icp_set("linkedin.scraper.last_run", fields.Datetime.now().isoformat())
            _logger.info("LinkedIn scraper lancé: %s", " ".join(cmd))
            return True
        except OSError as exc:
            self._icp_set("linkedin.scraper.status", f"error: {exc}")
            _logger.exception("Échec lancement scraper LinkedIn")
            return False

    @api.model
    def _norm_ascii(self, text):
        text = unicodedata.normalize("NFKD", text or "")
        return "".join(c for c in text if not unicodedata.combining(c)).lower().strip()

    @api.model
    def _norm_key(self, name, company=""):
        n = self._norm_ascii(name)
        c = self._norm_ascii(company)
        n = re.sub(r"[^a-z0-9]+", " ", n).strip()
        c = re.sub(r"[^a-z0-9]+", " ", c).strip()
        return f"{c}|{n}" if c else n

    @api.model
    def _ensure_tag(self, name):
        Tag = self.env["crm.tag"].sudo()
        tag = Tag.search([("name", "=", name)], limit=1)
        if not tag:
            tag = Tag.create({"name": name})
        return tag.id

    @api.model
    def _existing_defi_keys(self):
        Lead = self.env["crm.lead"].sudo()
        tag = self.env["crm.tag"].sudo().search([("name", "=", "Défi Zakaria")], limit=1)
        domain = []
        if tag:
            domain.append(("tag_ids", "in", tag.id))
        keys = set()
        urls = set()
        for lead in Lead.search(domain):
            keys.add(self._norm_key(lead.contact_name or "", lead.partner_name or lead.name or ""))
            if lead.contact_name:
                keys.add(self._norm_key(lead.contact_name, ""))
            desc = lead.description or ""
            for m in re.finditer(r"https?://[^\s]+linkedin[^\s]+", desc):
                urls.add(m.group(0).rstrip("/"))
        return keys, urls

    @api.model
    def import_linkedin_leads(self, leads, allow_phase2=False):
        if not leads:
            return {"imported": 0, "skipped": 0, "csv_only": 0}

        mkt = self.env.ref(
            "renovation_conciergerie.crm_team_marketing", raise_if_not_found=False
        )
        zak = self.env["res.users"].sudo().search(
            [("login", "=", "zakaria@agencedoorway.com"), ("active", "=", True)],
            limit=1,
        )
        country = self.env["res.country"].sudo().search([("code", "=", "MA")], limit=1)
        stage = self.env["crm.stage"].sudo().search(
            [("name", "=", "Nouveau"), ("team_ids", "in", mkt.id)],
            limit=1,
        ) if mkt else self.env["crm.stage"]

        tag_li = self._ensure_tag("LinkedIn Sales Nav")
        tag_cc = self._ensure_tag("Prospect Call Center Maroc")
        tag_zak = self._ensure_tag("Défi Zakaria")
        tag_casa = self._ensure_tag("Casablanca")
        tag_marr = self._ensure_tag("Marrakech")

        existing_keys, existing_urls = self._existing_defi_keys()
        imported = skipped = csv_only = 0

        for row in leads:
            if not isinstance(row, dict):
                continue
            phase = int(row.get("phase") or 1)
            if phase >= 2 and not allow_phase2:
                csv_only += 1
                continue

            nom = (row.get("nom") or row.get("name") or "").strip()
            entreprise = (row.get("entreprise") or row.get("company") or "").strip()
            if not nom or len(nom) < 2:
                skipped += 1
                continue

            linkedin_url = (row.get("linkedin_url") or row.get("profile_url") or "").strip()
            key = self._norm_key(nom, entreprise)
            if key in existing_keys or (linkedin_url and linkedin_url.rstrip("/") in existing_urls):
                skipped += 1
                continue

            ville = (row.get("ville") or row.get("city") or "Casablanca").strip()
            city_tag = tag_marr if "marrakech" in ville.lower() else tag_casa
            titre = (row.get("titre") or row.get("title") or "").strip()
            phone = (row.get("telephone") or row.get("phone") or "").strip()

            desc_lines = [
                f"Phase {phase} — LinkedIn Sales Navigator (Karine)",
                f"Titre : {titre or '-'}",
                f"Entreprise : {entreprise or '-'}",
                f"URL : {linkedin_url or '-'}",
            ]
            if row.get("source"):
                desc_lines.append(f"Recherche : {row['source']}")

            vals = {
                "name": f"LinkedIn — {entreprise or nom} — {nom}",
                "type": "opportunity",
                "partner_name": entreprise or nom,
                "contact_name": nom,
                "function": titre or False,
                "phone": phone or False,
                "city": ville,
                "description": "\n".join(desc_lines),
                "lead_provenance": "nouveau",
                "tag_ids": [(6, 0, [tag_li, tag_cc, tag_zak, city_tag])],
            }
            if mkt:
                vals["team_id"] = mkt.id
            if zak:
                vals["user_id"] = zak.id
            if stage:
                vals["stage_id"] = stage.id
            if country:
                vals["country_id"] = country.id

            self.env["crm.lead"].sudo().create(vals)
            existing_keys.add(key)
            if linkedin_url:
                existing_urls.add(linkedin_url.rstrip("/"))
            imported += 1

        self._icp_set("linkedin.scraper.leads_found", str(imported))
        self._icp_set(
            "linkedin.scraper.status",
            f"done: {imported} importés, {skipped} ignorés, {csv_only} phase2 csv",
        )
        return {"imported": imported, "skipped": skipped, "csv_only": csv_only}
