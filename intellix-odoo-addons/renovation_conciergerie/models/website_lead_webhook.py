import secrets

from odoo import _, api, models


class RenovationWebsiteLeadWebhook(models.AbstractModel):
    _name = "renovation.website.lead.webhook"
    _description = "Webhooks publics — leads site web par pipeline"

    PIPELINE_CONFIG = {
        "renovation": {
            # Leads Gestion (Digital Doorway) — plus l'ancien Réno 92.
            "team_xmlid": "reno_immobilier.crm_team_reno_immobilier",
            "token_key": "renovation_conciergerie.website_lead_webhook_token",
            "name_prefix": "Site web",
        },
        "immobilier": {
            "team_xmlid": "reno_immobilier.crm_team_reno_immobilier",
            "token_key": "renovation_conciergerie.website_lead_webhook_token",
            "name_prefix": "Site web",
        },
        "marketing": {
            "team_xmlid": "renovation_conciergerie.crm_team_marketing",
            "token_key": "renovation_conciergerie.marketing_website_lead_webhook_token",
            "name_prefix": "Site web Marketing",
        },
    }

    # Domaine → source UTM lisible (kanban Leads Gestion).
    SITE_SOURCE_LABELS = {
        "maisonrecherchee.com": "Maison Recherchée",
        "soumissiontoitures.com": "Soumission Toiture",
        "soumissiontoiture.com": "Soumission Toiture",
        "reseaucuisineqc.com": "Cuisine",
        "isolationqc.com": "Isolation QC",
        "soumissionentrepreneurs.com": "Soumission Entrepreneurs",
        "portesetfenetresqc.com": "Portes et Fenêtres QC",
        "icithermopompe.com": "ICI Thermopompe",
        "haidlyreno.com": "Haidly Reno",
        "agencedoorway.com": "Agence Doorway",
        "marenofacile.fr": "Ma Reno Facile",
        "intellixcrm.com": "IntelliX CRM",
        "intellix.ai": "IntelliX CRM",
    }
    DOORWAY_SITES = {"agencedoorway.com"}
    MARKETING_SITES = {
        "agencedoorway.com",
        "intellixcrm.com",
        "intellix.ai",
    }
    # Kanban « Rénovation » (équipe 92) — pas Leads Gestion 116.
    MARENO_SITES = {"marenofacile.fr"}
    BLOCKED_SITES = {
        "drivenb2b.com",
        "driven.ca",
        "coinsquebec.com",
        "coinsmarocain.com",
    }

    @api.model
    def _ensure_website_lead_webhook_token(self):
        """Token webhook site web — pipeline Rénovation."""
        self._ensure_token("renovation_conciergerie.website_lead_webhook_token")

    @api.model
    def _ensure_marketing_website_lead_webhook_token(self):
        """Token webhook site web — pipeline Marketing."""
        self._ensure_token("renovation_conciergerie.marketing_website_lead_webhook_token")

    @api.model
    def _ensure_token(self, key):
        icp = self.env["ir.config_parameter"].sudo()
        if not icp.get_param(key):
            icp.set_param(key, secrets.token_urlsafe(32))

    @api.model
    def _check_token(self, pipeline_key, data):
        config = self.PIPELINE_CONFIG.get(pipeline_key)
        if not config:
            return False
        expected = (
            self.env["ir.config_parameter"].sudo().get_param(config["token_key"])
        )
        if not expected:
            return True
        provided = (
            data.get("token")
            or data.get("webhook_token")
        )
        return provided == expected

    @api.model
    def _parse_bool(self, value):
        if isinstance(value, bool):
            return value
        if value is None:
            return False
        return str(value).strip().lower() in ("1", "true", "yes", "oui", "on")

    @api.model
    def _marketing_vals_from_payload(self, data):
        """Champs spécifiques pipeline Marketing."""
        vals = {}
        company_type = (
            data.get("marketing_company_type")
            or data.get("company_type")
            or ""
        ).strip()
        if company_type:
            vals["marketing_company_type"] = company_type
        budget = data.get("marketing_monthly_budget") or data.get("monthly_budget")
        if budget not in (None, ""):
            try:
                vals["marketing_monthly_budget"] = float(budget)
            except (TypeError, ValueError):
                pass
        if "marketing_already_has_agency" in data or "has_agency" in data:
            vals["marketing_already_has_agency"] = self._parse_bool(
                data.get("marketing_already_has_agency", data.get("has_agency"))
            )
        need_map = {
            "marketing_need_social": ("marketing_need_social", "need_social"),
            "marketing_need_ai_agent": ("marketing_need_ai_agent", "need_ai_agent"),
            "marketing_need_crm": ("marketing_need_crm", "need_crm"),
            "marketing_need_seo": ("marketing_need_seo", "need_seo"),
            "marketing_need_website": ("marketing_need_website", "need_website"),
            "marketing_need_lead_gen": ("marketing_need_lead_gen", "need_lead_gen"),
        }
        for field, (key1, key2) in need_map.items():
            if key1 in data or key2 in data:
                vals[field] = self._parse_bool(data.get(key1, data.get(key2)))
        return vals


    @api.model
    def _notify_portfolio_lead_email(self, lead, data, pipeline_key):
        """Notification unique vers info@soumissionentrepreneurs.com."""
        import logging
        _logger = logging.getLogger(__name__)
        to_addr = (
            self.env["ir.config_parameter"].sudo().get_param(
                "renovation_conciergerie.portfolio_lead_notify_email"
            )
            or "info@soumissionentrepreneurs.com"
        )
        site = (
            data.get("site_source")
            or data.get("site")
            or data.get("source_site")
            or ""
        ).strip()
        subject = f"[Lead web] {site or pipeline_key} — {lead.contact_name or lead.name}"
        body = (
            f"<p><b>Nouveau lead site web</b></p>"
            f"<ul>"
            f"<li><b>Pipeline:</b> {pipeline_key}</li>"
            f"<li><b>Site:</b> {site or '-'}</li>"
            f"<li><b>Nom:</b> {lead.contact_name or '-'}</li>"
            f"<li><b>Email:</b> {lead.email_from or '-'}</li>"
            f"<li><b>Téléphone:</b> {lead.phone or '-'}</li>"
            f"<li><b>Ville:</b> {lead.city or '-'}</li>"
            f"<li><b>Lead Odoo:</b> #{lead.id} — {lead.name}</li>"
            f"</ul>"
            f"<p><b>Description</b></p>"
            f"<pre>{(lead.description or data.get('message') or data.get('description') or '-')}</pre>"
        )
        email_from = "info@soumissionentrepreneurs.com"
        mail_server = self.env["ir.mail_server"].sudo().browse(2)  # Brevo SMTP
        if not mail_server.exists() or not mail_server.active:
            mail_server = self.env["ir.mail_server"].sudo().search([("active", "=", True)], limit=1)
        vals = {
            "subject": subject,
            "body_html": body,
            "email_to": to_addr,
            "email_from": email_from,
            "auto_delete": False,
        }
        if mail_server:
            vals["mail_server_id"] = mail_server.id
        try:
            # File only — cron mail envoie. send() synchrone timeout le webhook n8n.
            self.env["mail.mail"].sudo().create(vals)
            return True
        except Exception:
            _logger.exception("portfolio lead email notify failed")
            return False

    @api.model
    def _ensure_utm_source(self, name):
        """Crée ou retrouve une source UTM (visible kanban + filtres)."""
        label = (name or "").strip()
        if not label:
            return self.env["utm.source"]
        Source = self.env["utm.source"].sudo()
        source = Source.search([("name", "=ilike", label)], limit=1)
        if source:
            return source
        return Source.create({"name": label})

    @api.model
    def _ensure_utm_medium(self, name):
        """Crée ou retrouve un medium UTM. Ne renomme jamais un existant."""
        label = (name or "").strip()
        if not label:
            return self.env["utm.medium"]
        Medium = self.env["utm.medium"].sudo()
        medium = Medium.search([("name", "=ilike", label)], limit=1)
        if medium:
            return medium
        return Medium.create({"name": label})

    @api.model
    def _ensure_utm_campaign(self, name):
        """Crée ou retrouve une campagne UTM. Ne renomme jamais une existante."""
        label = (name or "").strip()
        if not label:
            return self.env["utm.campaign"]
        Campaign = self.env["utm.campaign"].sudo()
        campaign = Campaign.search([("name", "=ilike", label)], limit=1)
        if campaign:
            return campaign
        return Campaign.create({"name": label})

    @api.model
    def _ensure_landing_page_field(self):
        """Champ texte libre page d'entrée — créé une fois, jamais écrasé ailleurs."""
        Lead = self.env["crm.lead"]
        if "x_landing_page_url" in Lead._fields:
            return "x_landing_page_url"
        Model = self.env["ir.model"].sudo().search([("model", "=", "crm.lead")], limit=1)
        if not Model:
            return False
        self.env["ir.model.fields"].sudo().create({
            "name": "x_landing_page_url",
            "field_description": "Page d'entrée",
            "model_id": Model.id,
            "ttype": "char",
            "size": 2048,
            "state": "manual",
        })
        Lead._invalidate_cache()
        return "x_landing_page_url"

    @api.model
    def _apply_website_attribution(self, vals, data):
        """UTM / referrer / landing first-touch → champs natifs. N'écrase pas
        une source site déjà posée sauf si une attribution visiteur est présente.
        """
        utm_source = (data.get("utm_source") or "").strip()
        utm_medium = (data.get("utm_medium") or "").strip()
        utm_campaign = (data.get("utm_campaign") or "").strip()
        utm_term = (data.get("utm_term") or "").strip()
        landing = (data.get("landing_page_url") or "").strip()
        ref_domain = (data.get("referrer_domain") or "").strip()
        gclid = (data.get("gclid") or "").strip()
        fbclid = (data.get("fbclid") or "").strip()

        if utm_source:
            source = self._ensure_utm_source(utm_source)
            if source:
                vals["source_id"] = source.id
        if utm_medium:
            medium = self._ensure_utm_medium(utm_medium)
            if medium:
                vals["medium_id"] = medium.id
        if utm_campaign:
            campaign = self._ensure_utm_campaign(utm_campaign)
            if campaign:
                vals["campaign_id"] = campaign.id
        if utm_term and not vals.get("referred"):
            vals["referred"] = utm_term[:255]

        field_name = self._ensure_landing_page_field()
        if landing and field_name:
            vals[field_name] = landing[:2048]

        extra = []
        if landing:
            extra.append("Page d'entrée: %s" % landing)
        if ref_domain:
            extra.append("Référent: %s" % ref_domain)
        if utm_term:
            extra.append("Mot-clé: %s" % utm_term)
        if gclid:
            extra.append("gclid: %s" % gclid)
        if fbclid:
            extra.append("fbclid: %s" % fbclid)
        if extra:
            desc = vals.get("description") or ""
            vals["description"] = (desc + "\n\n" + "\n".join(extra)).strip()
        return vals

    @api.model
    def _schedule_website_lead_activity(self, lead, source_label):
        """To-do visible sur l'opportunité, avec le nom du site source."""
        if not lead:
            return
        label = (source_label or "site web").strip()
        summary = f"Nouveau lead web — {label}"
        user = lead.user_id
        try:
            lead.activity_schedule(
                "mail.mail_activity_data_todo",
                summary=summary,
                note=f"Opportunité créée depuis {label}. Relancer le contact.",
                user_id=user.id if user else False,
            )
        except Exception:
            Activity = self.env["mail.activity"].sudo()
            act_type = self.env.ref("mail.mail_activity_data_todo", raise_if_not_found=False)
            Activity.create({
                "res_model_id": self.env["ir.model"]._get_id("crm.lead"),
                "res_id": lead.id,
                "activity_type_id": act_type.id if act_type else False,
                "summary": summary,
                "note": f"Opportunité créée depuis {label}. Relancer le contact.",
                "user_id": user.id if user else self.env.user.id,
            })

    @api.model
    def create_lead_from_website_payload(self, pipeline_key, data):
        config = self.PIPELINE_CONFIG.get(pipeline_key)
        if not config:
            return {"status": "error", "message": _("Pipeline inconnu.")}, 400

        team = self.env.ref(config["team_xmlid"], raise_if_not_found=False)
        if not team:
            return {
                "status": "error",
                "message": _("Équipe CRM introuvable pour ce pipeline."),
            }, 500

        contact_name = (
            data.get("contact_name")
            or data.get("name_contact")
            or data.get("nom")
            or data.get("full_name")
            or data.get("name")
            or ""
        ).strip()
        email = (
            data.get("email")
            or data.get("email_from")
            or data.get("courriel")
            or ""
        ).strip()
        phone = (
            data.get("phone")
            or data.get("mobile")
            or data.get("tel")
            or data.get("telephone")
            or ""
        ).strip()
        partner_name = (
            data.get("partner_name") or data.get("company") or data.get("company_name") or ""
        ).strip()
        title = (data.get("title") or data.get("subject") or "").strip()
        message = (
            data.get("message")
            or data.get("description")
            or data.get("notes")
            or data.get("comment")
            or ""
        ).strip()
        source_url = (data.get("source_url") or data.get("website") or data.get("url") or "").strip()
        site_source = (
            data.get("site_source")
            or data.get("site")
            or data.get("source_site")
            or ""
        ).strip()

        site_l = site_source.lower().replace("www.", "").split("/")[0].strip()
        if not site_l and source_url.startswith("http"):
            site_l = source_url.split("/")[2].lower().replace("www.", "").strip()

        if site_l in self.BLOCKED_SITES:
            return {
                "status": "error",
                "message": _("Ce site n'utilise pas le pipeline Réno Immobilier."),
            }, 400

        # Doorway + IntelliX → Marketing 96. Ma Reno Facile → Rénovation 92.
        # Sites réno QC + Haidly → Leads Gestion 116.
        if (
            site_l in self.MARKETING_SITES
            or site_l in self.DOORWAY_SITES
            or pipeline_key == "marketing"
            or str(data.get("pipeline") or "").strip().lower() == "marketing"
        ):
            pipeline_key = "marketing"
            config = self.PIPELINE_CONFIG.get(pipeline_key)
            team = self.env.ref(config["team_xmlid"], raise_if_not_found=False)
            if not team:
                return {
                    "status": "error",
                    "message": _("Équipe CRM introuvable pour ce pipeline."),
                }, 500
        elif site_l in self.MARENO_SITES:
            pipeline_key = "renovation"
            config = dict(self.PIPELINE_CONFIG.get("renovation") or {})
            team = self.env.ref(
                "renovation_conciergerie.crm_team_renovation",
                raise_if_not_found=False,
            )
            if not team:
                return {
                    "status": "error",
                    "message": _("Équipe CRM introuvable pour ce pipeline."),
                }, 500
        else:
            reno_team = self.env.ref(
                "reno_immobilier.crm_team_reno_immobilier", raise_if_not_found=False
            )
            if reno_team:
                team = reno_team
                pipeline_key = "renovation"
                config = self.PIPELINE_CONFIG.get("renovation")

        prefix = config["name_prefix"]

        lead_name = (data.get("name") or title or "").strip()
        if not lead_name:
            if contact_name:
                lead_name = f"{prefix} — {contact_name}"
            elif email:
                lead_name = f"{prefix} — {email}"
            elif phone:
                lead_name = f"{prefix} — {phone}"
            else:
                lead_name = prefix

        if not email and not phone:
            return {
                "status": "error",
                "message": _("Au moins un email ou un téléphone est requis."),
            }, 400

        description_parts = []
        if message:
            description_parts.append(message)
        if site_source:
            description_parts.append(f"Site source: {site_source}")
        if source_url:
            description_parts.append(f"Source: {source_url}")
        if title and title not in lead_name:
            description_parts.append(f"Sujet: {title}")

        assignee = team._get_default_assignee()
        vals = {
            "name": lead_name,
            "type": "opportunity",
            "team_id": team.id,
            "lead_provenance": "website",
            "contact_name": contact_name or False,
            "partner_name": partner_name or False,
            "email_from": email or False,
            "phone": phone or False,
            "description": "\n\n".join(description_parts) if description_parts else False,
            "street": (data.get("street") or data.get("address") or "").strip() or False,
            "city": (data.get("city") or data.get("ville") or data.get("localisation") or "").strip() or False,
            "zip": (data.get("zip") or data.get("postal_code") or "").strip() or False,
        }
        source_label = (
            data.get("source_label")
            or self.SITE_SOURCE_LABELS.get(site_l)
            or site_source
            or site_l
            or (source_url.split("/")[2] if source_url.startswith("http") else "")
        )
        if source_label:
            source_label = str(source_label).strip()
            if source_label.lower().replace("www.", "") in self.SITE_SOURCE_LABELS:
                source_label = self.SITE_SOURCE_LABELS[
                    source_label.lower().replace("www.", "")
                ]
            source = self._ensure_utm_source(source_label)
            if source:
                vals["source_id"] = source.id
        self._apply_website_attribution(vals, data)
        if assignee:
            vals["user_id"] = assignee.id
        company = team.company_id
        if not company:
            company = self.env["res.company"].sudo().search(
                [("name", "ilike", "Digital Doorway")], limit=1
            )
        if not company and assignee:
            company = assignee.company_id
        if company:
            vals["company_id"] = company.id

        if pipeline_key == "marketing":
            vals.update(self._marketing_vals_from_payload(data))
        elif pipeline_key == "renovation":
            service_names = data.get("services") or data.get("service_category")
            if service_names:
                if isinstance(service_names, str):
                    names = [s.strip() for s in service_names.split(",") if s.strip()]
                elif isinstance(service_names, (list, tuple)):
                    names = [str(s).strip() for s in service_names if str(s).strip()]
                else:
                    names = []
                if names:
                    categories = self.env["renovation.service.category"].sudo().search(
                        [("name", "in", names)]
                    )
                    if categories:
                        vals["service_category_ids"] = [(6, 0, categories.ids)]

        lead = self.env["crm.lead"].sudo().create(vals)
        self._notify_portfolio_lead_email(lead, data, pipeline_key)
        self._schedule_website_lead_activity(lead, source_label or site_source or pipeline_key)
        stage = lead.stage_id
        return {
            "status": "success",
            "lead_id": lead.id,
            "team_id": lead.team_id.id,
            "team_name": lead.team_id.name,
            "stage_id": stage.id if stage else False,
            "stage_name": stage.name if stage else False,
            "lead_provenance": lead.lead_provenance,
        }, 200
