# -*- coding: utf-8 -*-
"""Sort les fiches qui n’ont rien à faire dans le pipeline Coins Marocain."""
import re

from odoo import api, models

_IMPORT_EMAIL = re.compile(r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}", re.I)
_MAIL_PROVIDERS = {
    "gmail",
    "hotmail",
    "outlook",
    "yahoo",
    "icloud",
    "live",
    "msn",
}

QC_CITIES = (
    "mont-tremblant",
    "tremblant",
    "saint-jérôme",
    "saint-jerome",
    "mirabel",
    "saint-donat",
    "val-david",
    "sainte-agathe",
    "laval",
    "morin-heights",
    "nominingue",
    "sainte-adèle",
    "sainte-adele",
    "labelle",
    "blainville",
    "saint-sauveur",
    "sainte-lucie",
    "boisbriand",
    "val-morin",
    "sainte-thérèse",
    "sainte-therese",
    "la conception",
    "saint-hippolyte",
    "rivière-rouge",
    "riviere-rouge",
    "rosemère",
    "rosemere",
    "montréal",
    "montreal",
    "longueuil",
    "gatineau",
    "sherbrooke",
    "trois-rivières",
    "granby",
    "terrebonne",
    "repentigny",
    "brossard",
)

SPAM_NEEDLES = (
    "whitespark",
    "modash.io",
    "apple business",
    "meta for policy",
    "no-reply@apple.com",
)


class CrmLeadCoinsMarocainPurge(models.Model):
    _inherit = "crm.lead"

    def _cm_team(self):
        return self.env.ref(
            "coins_marocain_partenariats.crm_team_coins_marocain",
            raise_if_not_found=False,
        )

    def _cm_is_won(self):
        self.ensure_one()
        name = (self.stage_id.name or "").lower()
        return name in ("gagné", "gagne", "won") or bool(self.stage_id.is_won)

    def _cm_foreign_bucket(self):
        """Pourquoi cette fiche n’est pas un partenaire Coins Marocain."""
        self.ensure_one()
        name = (self.name or "").strip()
        low = name.lower()
        city = (self.city or "").lower()
        phone = self.phone or ""
        email = (self.email_from or "").lower()
        desc = (self.description or "").lower()
        if name.startswith("Import —") or name.startswith("Import -"):
            return "import_reno_qc"
        if "agence doorway" in low or "jean testeur" in low:
            return "meta_doorway"
        if "page agence doorway" in desc or "lead ads marketing" in desc:
            return "meta_doorway"
        if low.startswith("[outreach]") or "call center casablanca" in low:
            return "outreach_callcenter"
        if any(n in low or n in email for n in SPAM_NEEDLES):
            return "spam"
        if "+216" in phone:
            return "hors_maroc"
        if phone.startswith("+34") or phone.startswith("+346"):
            return "hors_maroc"
        if any(c in city or c in low for c in QC_CITIES):
            return "quebec_tourisme"
        digits = "".join(ch for ch in phone if ch.isdigit())
        if digits.startswith("1") and len(digits) >= 11 and "+212" not in phone:
            if "secteur:" in desc or "laurentides" in desc or "rive sud" in desc:
                return "import_reno_qc"
        return False

    @api.model
    def _cm_purge_foreign_leads(self):
        """Import reno → Réno Immobilier. Meta Doorway → Marketing. QC / spam → archive."""
        team_cm = self._cm_team()
        if not team_cm:
            return {}
        team_reno = self.env.ref(
            "reno_immobilier.crm_team_reno_immobilier", raise_if_not_found=False
        )
        team_mkt = self.env.ref(
            "renovation_conciergerie.crm_team_marketing", raise_if_not_found=False
        )
        stage_reno = self.env.ref(
            "reno_immobilier.crm_stage_nouveau", raise_if_not_found=False
        )
        stage_mkt = self.env["crm.stage"].sudo().search(
            [("name", "=", "Nouveau"), ("team_ids", "in", [team_mkt.id])]
            if team_mkt
            else [("id", "=", 0)],
            limit=1,
        )
        leads = (
            self.with_context(active_test=False)
            .sudo()
            .search([("team_id", "=", team_cm.id)])
        )
        ctx = {
            "tracking_disable": True,
            "mail_notrack": True,
            "doorway_skip_activity_sync": True,
            "mail_activity_meeting_update": True,
        }
        counts = {
            "import_reno_qc": 0,
            "meta_doorway": 0,
            "quebec_tourisme": 0,
            "outreach_callcenter": 0,
            "spam": 0,
            "hors_maroc": 0,
            "kept": 0,
        }
        for lead in leads:
            if lead._cm_is_won():
                counts["kept"] += 1
                continue
            bucket = lead._cm_foreign_bucket()
            if not bucket:
                counts["kept"] += 1
                continue
            rec = lead.with_context(**ctx)
            if bucket == "import_reno_qc":
                rec._cm_promote_import_to_partner()
            elif bucket == "meta_doorway" and team_mkt:
                vals = {"team_id": team_mkt.id}
                if stage_mkt:
                    vals["stage_id"] = stage_mkt.id
                rec.write(vals)
            else:
                rec.write({"active": False})
            counts[bucket] = counts.get(bucket, 0) + 1
        return counts

    @api.model_create_multi
    def create(self, vals_list):
        leads = super().create(vals_list)
        team_cm = self._cm_team()
        if not team_cm:
            return leads
        team_reno = self.env.ref(
            "reno_immobilier.crm_team_reno_immobilier", raise_if_not_found=False
        )
        team_mkt = self.env.ref(
            "renovation_conciergerie.crm_team_marketing", raise_if_not_found=False
        )
        stage_reno = self.env.ref(
            "reno_immobilier.crm_stage_nouveau", raise_if_not_found=False
        )
        for lead in leads:
            bucket = lead._cm_foreign_bucket()
            if bucket == "import_reno_qc":
                lead.sudo()._cm_promote_import_to_partner()
                continue
            if lead.team_id.id != team_cm.id:
                continue
            if bucket == "meta_doorway" and team_mkt:
                lead.sudo().write({"team_id": team_mkt.id})
        return leads

    def _cm_promote_import_to_partner(self):
        """Import entrepreneurs QC → fiche Partenaires B2B, pas Leads Gestion."""
        Partner = self.env["res.partner"].sudo()
        cat = self.env["res.partner.category"].sudo().search(
            [("name", "=", "Partenaire Réno Immo")], limit=1
        )
        ctx = {
            "tracking_disable": True,
            "mail_notrack": True,
            "mail_create_nolog": True,
        }
        for lead in self:
            raw = (lead.name or "").strip()
            title = re.sub(r"^Import\s*[—\-–]\s*", "", raw, flags=re.I).strip() or raw
            email = (lead.email_from or "").strip()
            found = _IMPORT_EMAIL.findall(title) or _IMPORT_EMAIL.findall(email)
            if found:
                email = found[0]
            if email and email.split("@")[-1].split(".")[0].lower() in _MAIL_PROVIDERS:
                local = email.split("@")[0]
                if _IMPORT_EMAIL.fullmatch(title) or title.lower() in _MAIL_PROVIDERS:
                    title = re.sub(r"[._\-]+", " ", local).strip().title()
            elif _IMPORT_EMAIL.fullmatch(title):
                domain = title.split("@")[-1].split(".")[0]
                title = domain.replace("-", " ").title()
            partner = Partner.browse()
            if email:
                partner = Partner.with_context(active_test=False).search(
                    [("email", "=ilike", email)], limit=1
                )
            vals = {
                "name": (title or email or "Partenaire import")[:128],
                "is_company": True,
                "supplier_rank": 1,
                "comment": "Import B2B depuis lead #%s. Pas un lead B2C Leads Gestion.\n%s"
                % (lead.id, (lead.description or "")[:1500]),
            }
            if email:
                vals["email"] = email
            if lead.phone:
                vals["phone"] = lead.phone
            if lead.city:
                vals["city"] = lead.city
            if cat:
                vals["category_id"] = [(4, cat.id)]
            if partner:
                upd = {
                    k: vals[k]
                    for k in ("supplier_rank", "comment", "category_id")
                    if k in vals
                }
                if not partner.email and email:
                    upd["email"] = email
                partner.with_context(**ctx).write(upd)
            else:
                Partner.with_context(**ctx).create(vals)
            lead.with_context(**ctx).write({"active": False})
