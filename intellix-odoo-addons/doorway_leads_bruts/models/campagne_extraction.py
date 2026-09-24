# -*- coding: utf-8 -*-
import json
import logging
import re
import threading

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from odoo.addons.doorway_leads_bruts.services.scraper_registry import scrape_source

_logger = logging.getLogger(__name__)


class DoorwayCampagneExtraction(models.Model):
    _name = "doorway.campagne.extraction"
    _description = "Campagne d'extraction de leads"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "create_date desc"

    name = fields.Char(required=True, tracking=True)
    mot_cle = fields.Char(string="Mot-clé / Secteur", required=True, tracking=True)
    zone_geographique = fields.Selection(
        [
            ("maroc", "🇲🇦 Maroc"),
            ("france", "🇫🇷 France"),
            ("belgique", "🇧🇪 Belgique"),
            ("espagne", "🇪🇸 Espagne"),
            ("suisse", "🇨🇭 Suisse"),
            ("canada", "🇨🇦 Canada"),
            ("usa", "🇺🇸 États-Unis"),
            ("tunisie", "🇹🇳 Tunisie"),
            ("autre", "🌍 Autre pays"),
        ],
        required=True,
        default="france",
    )
    ville_region = fields.Char(string="Ville / Région", required=True)
    rayon_km = fields.Integer(string="Rayon (km)", default=10)
    volume_possible = fields.Integer(
        string="Volume possible",
        readonly=True,
        help="Maximum de leads estimé selon les sources sélectionnées.",
    )
    volume_cible = fields.Integer(
        string="Quantité à extraire",
        default=200,
        help="Nombre de leads à extraire (plafonné au volume possible).",
    )
    sources_selectionnees = fields.Many2many(
        "doorway.source.registry",
        "campagne_source_rel",
        "campagne_id",
        "source_id",
        string="Sources",
    )
    state = fields.Selection(
        [
            ("draft", "Brouillon"),
            ("running", "En cours"),
            ("done", "Terminée"),
            ("error", "Erreur"),
            ("cancelled", "Annulée"),
        ],
        default="draft",
        tracking=True,
    )
    progress_pct = fields.Float(string="Progression %", default=0.0)
    leads_count = fields.Integer(
        string="Leads extraits",
        compute="_compute_leads_count",
        store=True,
    )
    result_summary = fields.Char(
        string="Résultat",
        compute="_compute_result_summary",
        store=True,
    )
    leads_skipped_dup = fields.Integer(
        string="Doublons ignorés",
        default=0,
        help="Leads déjà présents dans une extraction passée (téléphone, email ou nom).",
    )
    leads_scraped_raw = fields.Integer(
        string="Résultats bruts scrapés",
        default=0,
    )
    leads_bruts_ids = fields.One2many("doorway.leads.bruts", "campagne_id")
    cout_credits_estime = fields.Float(digits=(16, 4))
    cout_credits_reel = fields.Float(digits=(16, 4))
    prix_unitaire_affiche = fields.Float(digits=(16, 4))
    marge_pct = fields.Float(string="Marge (%)", default=40.0)
    cout_reel_interne = fields.Float(
        string="Coût interne",
        digits=(16, 4),
        help="Coût réel interne (visible uniquement aux admins commerciaux dans les vues).",
    )
    cout_detail_json = fields.Text(string="Détail coût JSON")
    leads_estime_min = fields.Integer()
    leads_estime_max = fields.Integer()
    duree_estime_min = fields.Integer(string="Durée min (min)")
    duree_estime_max = fields.Integer(string="Durée max (min)")
    error_message = fields.Text()
    date_start = fields.Datetime()
    date_end = fields.Datetime()
    user_id = fields.Many2one("res.users", default=lambda self: self.env.user)

    @api.depends("leads_bruts_ids")
    def _compute_leads_count(self):
        for rec in self:
            rec.leads_count = len(rec.leads_bruts_ids)

    @api.depends(
        "leads_count",
        "volume_cible",
        "leads_skipped_dup",
        "leads_scraped_raw",
        "state",
    )
    def _compute_result_summary(self):
        for rec in self:
            if rec.state == "running":
                rec.result_summary = _("%s / %s leads") % (
                    rec.leads_count,
                    rec.volume_cible or "—",
                )
            elif rec.state == "draft":
                rec.result_summary = _("Objectif : %s leads") % (
                    rec.volume_cible or "—",
                )
            elif rec.state in ("done", "error", "cancelled"):
                parts = [_("%s lead(s) extraits") % rec.leads_count]
                if rec.volume_cible:
                    parts.append(_("%s demandés") % rec.volume_cible)
                if rec.leads_skipped_dup:
                    parts.append(_("%s doublons") % rec.leads_skipped_dup)
                if rec.leads_scraped_raw:
                    parts.append(_("%s bruts scrapés") % rec.leads_scraped_raw)
                rec.result_summary = " · ".join(parts)
            else:
                rec.result_summary = str(rec.leads_count)

    PAST_STATES = ("done", "error", "cancelled")
    ACTIVE_STATES = ("draft", "running")

    @api.model
    def _normalize_phone_key(self, phone):
        return re.sub(r"\D", "", phone or "")

    @api.model
    def _lead_dedup_key(self, data):
        """Identifiant unique : téléphone normalisé > email > nom."""
        if hasattr(data, "get"):
            name = (data.get("name") or "").strip()
            phone = data.get("phone")
            email = data.get("email")
        else:
            name = (getattr(data, "name", None) or "").strip()
            phone = getattr(data, "phone", None)
            email = getattr(data, "email", None)
        phone_key = self._normalize_phone_key(phone)
        email_key = (email or "").strip().lower()
        name_key = name.lower()
        return phone_key or email_key or name_key or False

    @api.model
    def _get_global_dedup_keys(self):
        self.env.cr.execute(
            """
            SELECT dedup_key
            FROM doorway_leads_bruts
            WHERE dedup_key IS NOT NULL AND dedup_key != ''
            """
        )
        return {row[0] for row in self.env.cr.fetchall()}

    @api.model
    def count_similar_past_extractions(self, mot_cle, ville_region, zone):
        mot = (mot_cle or "").strip()
        ville = (ville_region or "").strip()
        if not mot or not ville:
            return 0
        return self.search_count([
            ("state", "in", self.PAST_STATES),
            ("mot_cle", "=ilike", mot),
            ("ville_region", "=ilike", ville),
            ("zone_geographique", "=", zone),
        ])

    BLACKLIST_KEYWORDS = [
        "recrutement", "emploi", "candidat", "cv", "formation", "école",
        "université", "stagiaire", "restaurant", "hotel", "pharmacie",
        "clinique", "dentiste", "notaire", "avocat",
    ]

    @api.model
    def _nettoyer_deduplique(self, raw_leads, existing_keys=None):
        """Déduplication intra-lot + historique global."""
        existing = set(existing_keys or [])
        seen = set()
        clean = []
        stats = {
            "skipped_dup_global": 0,
            "skipped_dup_batch": 0,
            "skipped_invalid": 0,
        }
        for lead in raw_leads:
            if not lead or not lead.get("name"):
                stats["skipped_invalid"] += 1
                continue
            name = (lead.get("name") or "").strip()
            if len(name) < 3:
                stats["skipped_invalid"] += 1
                continue
            if any(bw in name.lower() for bw in self.BLACKLIST_KEYWORDS):
                stats["skipped_invalid"] += 1
                continue
            dedup_key = self._lead_dedup_key(lead)
            if not dedup_key:
                stats["skipped_invalid"] += 1
                continue
            if dedup_key in existing:
                stats["skipped_dup_global"] += 1
                continue
            if dedup_key in seen:
                stats["skipped_dup_batch"] += 1
                continue
            seen.add(dedup_key)
            lead["dedup_key"] = dedup_key
            clean.append(lead)
        return {"leads": clean, "stats": stats}

    def _scrape_all_sources(self, attempt=0):
        """Scrape toutes les sources — pages augmentées à chaque tentative."""
        self.ensure_one()
        all_raw = []
        sources = self.sources_selectionnees
        per_source = max(1, self.volume_cible // max(len(sources), 1))
        base_pages = max(3, min(15, per_source // 5))
        max_pages = min(25, base_pages + attempt * 5)

        for idx, source in enumerate(sources):
            try:
                batch = scrape_source(
                    source.code,
                    self.mot_cle,
                    self.ville_region,
                    rayon_km=self.rayon_km,
                    max_pages=max_pages,
                    env=self.with_context(
                        zone_geographique=self.zone_geographique
                    ).env,
                )
                for item in batch:
                    item["source_id"] = source.id
                all_raw.extend(batch)
            except Exception as exc:
                _logger.warning("Source %s failed: %s", source.code, exc)

            progress = round(
                (idx + 1) / max(len(sources), 1) * (60 + attempt * 10),
                1,
            )
            self.write({"progress_pct": min(progress, 85.0)})
        return all_raw

    @api.model
    def compute_volume_possible(self, sources):
        """Somme des capacités max de chaque source sélectionnée."""
        return sum(source.estimate_leads_max() for source in sources)

    @api.model
    def calculer_cout_estime(self, zone, sources, volume, marge_pct=None):
        """Calcule le coût détaillé pour le wizard (étape 3)."""
        config = self.env["doorway.credit.config"].get_config()
        marge = marge_pct if marge_pct is not None else config.marge_defaut_pct
        lines = []
        total = 0.0
        leads_min = 0
        leads_max = 0
        per_source_vol = max(1, volume // max(len(sources), 1))

        for source in sources:
            src_marge = config.marge_premium_pct if source.premium else marge
            cost = source.estimate_cost(per_source_vol)
            lmin, lmax = source.estimate_leads_range(per_source_vol)
            leads_min += lmin
            leads_max += lmax
            pages = max(1, int(per_source_vol / max(source.nb_leads_moy or 1, 1) * 10))
            lines.append({
                "source_id": source.id,
                "source_name": source.name,
                "source_code": source.code,
                "pages": pages,
                "fiches": per_source_vol,
                "cost_pages": round(pages * source.credit_par_page, 4),
                "cost_fiches": round(per_source_vol * source.credit_par_fiche, 4),
                "cost_total": cost,
                "marge_pct": src_marge,
                "leads_min": lmin,
                "leads_max": lmax,
            })
            total += cost

        nettoyage = round(volume * config.credit_nettoyage_ia, 4)
        import_odoo = round(volume * config.credit_import_odoo, 4)
        lines.append({
            "source_name": "Nettoyage IA (Claude)",
            "cost_total": nettoyage,
            "fiches": volume,
        })
        lines.append({
            "source_name": "Import Odoo",
            "cost_total": import_odoo,
            "fiches": volume,
        })
        total += nettoyage + import_odoo

        cout_interne = total * config.prix_credit_revient
        prix_affiche = round(cout_interne * (1 + marge / 100.0), 4)
        duree_min = max(3, int(volume / 25))
        duree_max = max(5, int(volume / 15))

        balance_credits = config.get_user_balance_credits()
        balance_money = config.get_user_balance_money()

        return {
            "lines": lines,
            "volume_possible": self.compute_volume_possible(sources),
            "total_credits": round(total, 4),
            "cout_reel_interne": round(cout_interne, 4),
            "prix_unitaire_affiche": prix_affiche,
            "marge_pct": marge,
            "leads_estime_min": leads_min,
            "leads_estime_max": leads_max,
            "duree_estime_min": duree_min,
            "duree_estime_max": duree_max,
            "balance_credits": balance_credits,
            "balance_money": balance_money,
            "balance_after": round(balance_credits - total, 4),
            "solde_suffisant": balance_credits >= total,
            "mode_commercial": config.mode_commercial,
            "devise": config.devise,
            "prix_ht": config.credits_to_display_price(total, marge),
            "prix_ttc": round(
                config.credits_to_display_price(total, marge) * (1 + config.tva_pct / 100),
                4,
            ),
        }

    def action_calculer_cout(self):
        for rec in self:
            if not rec.sources_selectionnees:
                raise UserError(_("Sélectionnez au moins une source."))
            result = rec.calculer_cout_estime(
                rec.zone_geographique,
                rec.sources_selectionnees,
                rec.volume_cible,
                rec.marge_pct,
            )
            rec.write({
                "volume_possible": result["volume_possible"],
                "cout_credits_estime": result["total_credits"],
                "prix_unitaire_affiche": result["prix_unitaire_affiche"],
                "leads_estime_min": result["leads_estime_min"],
                "leads_estime_max": result["leads_estime_max"],
                "duree_estime_min": result["duree_estime_min"],
                "duree_estime_max": result["duree_estime_max"],
                "cout_detail_json": json.dumps(result, ensure_ascii=False),
            })
            rec.sudo().write({
                "cout_reel_interne": result["cout_reel_interne"],
            })

    def _check_solde(self):
        self.ensure_one()
        config = self.env["doorway.credit.config"].get_config()
        required_money = self.cout_credits_estime * config.prix_credit_vente
        tenant = self.env["doorway.tenant"].get_tenant_for_company()
        if tenant and tenant.credit_balance < required_money:
            raise UserError(
                _("Solde insuffisant : %.2f requis, %.2f disponible.")
                % (required_money, tenant.credit_balance)
            )

    def _debit_credits(self, amount_credits, description):
        config = self.env["doorway.credit.config"].get_config()
        amount_money = round(amount_credits * config.prix_credit_vente, 2)
        tenant = self.env["doorway.tenant"].get_tenant_for_company()
        if not tenant or not tenant.credit_account_id:
            return
        if tenant.credit_account_id.balance < amount_money:
            raise UserError(_("Solde insuffisant pour débiter l'extraction."))
        tenant.credit_account_id.debit(
            amount_money,
            "n8n_workflow",
            description,
        )

    def action_lancer_extraction(self):
        for rec in self:
            if rec.state not in ("draft", "error"):
                raise UserError(_("Cette campagne ne peut pas être relancée."))
            if not rec.sources_selectionnees:
                raise UserError(_("Aucune source sélectionnée."))
            rec.action_calculer_cout()
            rec._check_solde()
            rec.write({
                "state": "running",
                "progress_pct": 0.0,
                "date_start": fields.Datetime.now(),
                "error_message": False,
            })
            rec._debit_credits(
                rec.cout_credits_estime,
                "Extraction Extracteur — %s" % rec.name,
            )
            dbname = self.env.cr.dbname
            uid = self.env.uid
            campagne_id = rec.id
            threading.Thread(
                target=self._run_extraction_thread,
                args=(dbname, uid, campagne_id),
                daemon=True,
            ).start()
        return True

    @api.model
    def _run_extraction_thread(self, dbname, uid, campagne_id):
        import odoo
        registry = odoo.registry(dbname)
        with registry.cursor() as cr:
            env = api.Environment(cr, uid, {})
            campagne = env["doorway.campagne.extraction"].browse(campagne_id)
            try:
                campagne._execute_extraction()
                cr.commit()
            except Exception as exc:
                _logger.exception("Extraction campagne %s", campagne_id)
                campagne.write({
                    "state": "error",
                    "error_message": str(exc),
                    "date_end": fields.Datetime.now(),
                })
                cr.commit()

    def _execute_extraction(self):
        self.ensure_one()
        Leads = self.env["doorway.leads.bruts"]
        existing_keys = self._get_global_dedup_keys()
        target = self.volume_cible
        new_leads = []
        total_raw = 0
        total_skipped_dup = 0
        max_attempts = 3

        for attempt in range(max_attempts):
            if len(new_leads) >= target:
                break
            batch_raw = self._scrape_all_sources(attempt=attempt)
            total_raw += len(batch_raw)
            result = self._nettoyer_deduplique(
                batch_raw,
                existing_keys=existing_keys,
            )
            stats = result["stats"]
            total_skipped_dup += (
                stats["skipped_dup_global"] + stats["skipped_dup_batch"]
            )
            for lead_data in result["leads"]:
                key = lead_data.get("dedup_key") or self._lead_dedup_key(lead_data)
                if not key or key in existing_keys:
                    continue
                new_leads.append(lead_data)
                existing_keys.add(key)
                if len(new_leads) >= target:
                    break

        created = 0
        for lead_data in new_leads[:target]:
            Leads.create({
                "name": lead_data.get("name"),
                "phone": lead_data.get("phone"),
                "email": lead_data.get("email"),
                "website": lead_data.get("website"),
                "address": lead_data.get("address"),
                "city": lead_data.get("city"),
                "source_id": lead_data.get("source_id"),
                "source_key": lead_data.get("source_key"),
                "source_url": lead_data.get("source_url"),
                "dedup_key": lead_data.get("dedup_key"),
                "campagne_id": self.id,
                "state": "brut",
            })
            created += 1
            if created % 20 == 0:
                self.write({
                    "progress_pct": 85 + created / max(target, 1) * 15,
                })
                self.env.cr.commit()

        self.write({
            "state": "done",
            "leads_skipped_dup": total_skipped_dup,
            "leads_scraped_raw": total_raw,
            "progress_pct": 100.0,
            "cout_credits_reel": self.cout_credits_estime,
            "date_end": fields.Datetime.now(),
        })
        msg = _("Extraction terminée : %(new)s nouveau(x) lead(s).") % {"new": created}
        if total_skipped_dup:
            msg += " " + _(
                "%(skipped)s doublon(s) ignoré(s) (déjà extraits auparavant)."
            ) % {"skipped": total_skipped_dup}
        if created < target:
            msg += " " + _(
                "Objectif %(target)s non atteint — élargissez les sources ou la zone."
            ) % {"target": target}
        self.message_post(body=msg, message_type="notification")
        config = self.env["doorway.credit.config"].get_config()
        if config.auto_import_crm_doorway and self.leads_bruts_ids:
            importable = self.leads_bruts_ids.filtered(
                lambda l: not l.crm_lead_id
                and ((l.phone or "").strip() or (l.email or "").strip())
            )
            if importable:
                importable.action_import_crm()
                self.message_post(
                    body=_(
                        "%s lead(s) envoyé(s) au pipeline Marketing Doorway (Zakaria)."
                    )
                    % len(importable),
                    message_type="notification",
                )

    @api.model
    def get_progress(self, campagne_id):
        camp = self.browse(campagne_id)
        if not camp.exists():
            return {}
        return {
            "id": camp.id,
            "state": camp.state,
            "progress_pct": camp.progress_pct,
            "leads_count": camp.leads_count,
            "error_message": camp.error_message or "",
        }

    def action_export_csv(self):
        import csv
        import io
        import base64
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Nom", "Téléphone", "Email", "Site", "Adresse", "Ville", "Source"])
        for lead in self.leads_bruts_ids:
            writer.writerow([
                lead.name, lead.phone, lead.email, lead.website,
                lead.address, lead.city, lead.source_id.name or "",
            ])
        attachment = self.env["ir.attachment"].create({
            "name": "leads_%s.csv" % self.id,
            "datas": base64.b64encode(output.getvalue().encode("utf-8")),
            "mimetype": "text/csv",
        })
        return {
            "type": "ir.actions.act_url",
            "url": "/web/content/%s?download=true" % attachment.id,
            "target": "self",
        }

    def action_import_all_crm(self):
        self.leads_bruts_ids.filtered(lambda l: l.state != "importe").action_import_crm()
        return True

    @api.model
    def import_from_crm_doorway(self, limit=500):
        """Crée une campagne d'import depuis les opportunités CRM Doorway existantes."""
        LeadsBruts = self.env["doorway.leads.bruts"].sudo()
        CrmLead = self.env["crm.lead"].sudo()
        if LeadsBruts.search_count([]) and not self.env.context.get("force_crm_import"):
            return self.browse()

        source = self.env.ref(
            "doorway_leads_bruts.source_crm_doorway",
            raise_if_not_found=False,
        )
        if not source:
            source = self.env["doorway.source.registry"].sudo().search([], limit=1)

        campagne = self.sudo().create({
            "name": "Import CRM Doorway",
            "mot_cle": "Import CRM",
            "zone_geographique": "france",
            "ville_region": "Toutes régions",
            "volume_cible": limit,
            "state": "running",
            "date_start": fields.Datetime.now(),
        })
        if source:
            campagne.sources_selectionnees = [(6, 0, [source.id])]

        domain = [
            "|",
            ("phone", "!=", False),
            ("email_from", "!=", False),
        ]
        crm_leads = CrmLead.search(domain, order="create_date desc", limit=limit)
        created = 0
        skipped = 0
        for lead in crm_leads:
            phone = (lead.phone or "").strip() or (
                (lead.partner_id.phone or "").strip() if lead.partner_id else ""
            ) or False
            marketing_team = self.env.ref(
                "renovation_conciergerie.crm_team_marketing",
                raise_if_not_found=False,
            )
            zakaria = self.env["res.users"].sudo().search(
                [
                    ("login", "=", "zakaria@agencedoorway.com"),
                    ("active", "=", True),
                ],
                limit=1,
            )
            if marketing_team and lead.team_id == marketing_team and zakaria:
                if lead.user_id != zakaria:
                    lead.sudo().write({"user_id": zakaria.id})

            vals = {
                "name": lead.contact_name or lead.name or lead.partner_name or _("Sans nom"),
                "phone": phone,
                "email": lead.email_from,
                "website": lead.website,
                "city": lead.city,
                "address": lead.street,
                "campagne_id": campagne.id,
                "source_id": source.id if source else False,
                "source_key": "crm_doorway",
                "crm_lead_id": lead.id,
                "state": "importe",
                "notes": _("Importé depuis le CRM Doorway (opportunité #%s)") % lead.id,
            }
            key = self._lead_dedup_key(vals)
            if not key or LeadsBruts.search_count([("dedup_key", "=", key)]):
                skipped += 1
                continue
            vals["dedup_key"] = key
            LeadsBruts.create(vals)
            created += 1

        campagne.write({
            "state": "done",
            "date_end": fields.Datetime.now(),
            "progress_pct": 100.0,
            "leads_scraped_raw": len(crm_leads),
            "leads_skipped_dup": skipped,
        })
        campagne.message_post(
            body=_(
                "Import CRM terminé : %(created)s lead(s) enregistrés, "
                "%(skipped)s ignorés (doublons ou sans contact)."
            )
            % {"created": created, "skipped": skipped}
        )
        return campagne
