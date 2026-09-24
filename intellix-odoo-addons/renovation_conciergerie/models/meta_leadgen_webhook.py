# -*- coding: utf-8 -*-
import logging
import secrets
import unicodedata

import requests

from odoo import _, api, models

_logger = logging.getLogger(__name__)

GRAPH_VERSION = "v21.0"

IMMO_STRUCTURED_KEYS = (
    "property_type",
    "selling_timeline",
    "estimated_value",
    "is_owner",
    "other_agents",
)


class RenovationMetaLeadgenWebhook(models.AbstractModel):
    _name = "renovation.meta.leadgen.webhook"
    _description = "Webhook Meta Leadgen standard (GET verify + POST leadgen)"

    @api.model
    def _ensure_verify_token(self):
        icp = self.env["ir.config_parameter"].sudo()
        key = "renovation_conciergerie.meta_leadgen_webhook_verify_token"
        if not icp.get_param(key):
            icp.set_param(key, secrets.token_urlsafe(32))

    @api.model
    def _get_verify_token(self):
        self._ensure_verify_token()
        return (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("renovation_conciergerie.meta_leadgen_webhook_verify_token")
        )

    @api.model
    def regenerate_verify_token(self):
        token = secrets.token_urlsafe(32)
        self.env["ir.config_parameter"].sudo().set_param(
            "renovation_conciergerie.meta_leadgen_webhook_verify_token",
            token,
        )
        return token

    @api.model
    def _iter_graph_tokens(self, page_id=None):
        """Tous les tokens Graph possibles, page d'abord (évite l'erreur #190)."""
        page_id = (
            str(page_id or "").strip()
            or self.env["ir.config_parameter"]
            .sudo()
            .get_param("renovation_conciergerie.meta_immo_facebook_page_id")
            or "964640820063787"
        )
        seen = set()
        Account = self.env["doorway.social.account"].sudo()
        recs = Account.search(
            [
                ("platform", "=", "facebook"),
                ("access_token", "!=", False),
                "|",
                ("external_account_id", "=", page_id),
                ("name", "ilike", "Maison Recherch"),
            ]
        )
        for rec in recs:
            token = (rec.access_token or "").strip()
            if token and token not in seen:
                seen.add(token)
                yield token
        icp = self.env["ir.config_parameter"].sudo()
        for key in (
            "renovation_conciergerie.meta_immo_page_access_token",
            "doorway_social_ia.meta_system_user_token",
        ):
            token = (icp.get_param(key) or "").strip()
            if token and token not in seen:
                seen.add(token)
                yield token
        config = self.env["doorway.veille.config"].sudo().search([], limit=1)
        token = (config.meta_access_token or "").strip() if config else ""
        if token and token not in seen:
            yield token

    @api.model
    def _get_graph_token(self, page_id=None):
        """Token Page requis pour /{page}/leadgen_forms et /{leadgen_id}.

        Le system user Social IA (#190) n'est pas un Page Access Token :
        le cron listait 0 formulaire et le webhook n'enrichissait pas le lead.
        """
        for token in self._iter_graph_tokens(page_id=page_id):
            return token
        return ""

    @staticmethod
    def _pick(obj, *keys):
        for key in keys:
            if not isinstance(obj, dict):
                continue
            value = obj.get(key)
            if value is not None and str(value).strip():
                return str(value).strip()
        return ""

    @staticmethod
    def _norm_meta_name(name):
        text = unicodedata.normalize("NFD", (name or "").lower())
        text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
        return text.replace(" ", "_")

    @api.model
    def _map_field_data(self, rows, target):
        for row in rows or []:
            name = (row.get("name") or "").lower()
            norm = self._norm_meta_name(row.get("name") or "")
            values = row.get("values") or []
            value = (values[0] if values else "") or ""
            if not value:
                continue
            if name in ("full_name", "nom_complet") or norm in (
                "full_name",
                "nom_complet",
            ):
                parts = value.split()
                target.setdefault("first_name", parts[0] if parts else "")
                if len(parts) > 1:
                    target.setdefault("last_name", " ".join(parts[1:]))
                target.setdefault("full_name", value)
            elif "first" in name or name in ("prénom", "prenom"):
                target.setdefault("first_name", value)
            elif "last" in name or name in ("nom", "name"):
                target.setdefault("last_name", value)
            elif any(part in name for part in ("phone", "téléphone", "tel", "mobile")):
                target.setdefault("phone", value)
            elif "email" in name or "courriel" in name:
                target.setdefault("email", value)
            elif "city" in name or "ville" in name:
                target.setdefault("city", value)
            elif any(part in name for part in ("address", "adresse", "street")):
                target.setdefault("full_address", value)
            elif "chauffage" in name or "heating" in name:
                target.setdefault("chauffage_actuel", value)
            elif "budget" in name:
                target.setdefault("budget_range", value)
            elif "project" in name or "projet" in name:
                target.setdefault("project_type", value)
            elif any(
                part in norm
                for part in (
                    "type_de_propriete",
                    "type_de_maison",
                    "property_type",
                    "type_maison",
                )
            ):
                target.setdefault("property_type", value)
            elif any(
                part in norm
                for part in (
                    "combien_de_temps",
                    "delai_de_vente",
                    "selling_timeline",
                    "envisagez-vous_de_vendre",
                    "envisagez_vous_de_vendre",
                )
            ) or ("vendre" in norm and "temps" in norm):
                target.setdefault("selling_timeline", value)
            elif (
                any(part in norm for part in ("proprietaire", "is_owner"))
                and "type_de_" not in norm
            ):
                target.setdefault("is_owner", value)
            elif any(
                part in norm
                for part in (
                    "valeur_estim",
                    "estimated_value",
                    "valeur_de_votre",
                    "valeur_estimee",
                )
            ):
                target.setdefault("estimated_value", value)
            elif any(
                part in norm
                for part in ("courtier", "other_agent", "autres_courtier")
            ):
                target.setdefault("other_agents", value)

    @api.model
    def _parse_leadgen_payload(self, body, change_value=None):
        body = body or {}
        payload = {}
        page_id = self._pick(body, "page_id", "facebook_page_id")
        form_id = self._pick(body, "form_id", "leadgen_form_id")
        leadgen_id = self._pick(body, "leadgen_id", "meta_lead_id", "id")
        field_data = {}

        if change_value:
            page_id = page_id or str(change_value.get("page_id") or "")
            form_id = form_id or str(change_value.get("form_id") or "")
            leadgen_id = leadgen_id or str(change_value.get("leadgen_id") or "")

        for entry in body.get("entry") or []:
            page_id = page_id or str(entry.get("id") or "")
            for change in entry.get("changes") or []:
                if change.get("field") != "leadgen":
                    continue
                value = change.get("value") or {}
                page_id = page_id or str(value.get("page_id") or "")
                form_id = form_id or str(value.get("form_id") or "")
                leadgen_id = leadgen_id or str(value.get("leadgen_id") or "")

        data = body.get("data")
        if isinstance(data, dict):
            full_name = self._pick(data, "full_name", "nom_complet")
            parts = full_name.split() if full_name else []
            field_data["first_name"] = (
                self._pick(data, "first_name", "prénom", "prenom") or (parts[0] if parts else "")
            )
            field_data["last_name"] = (
                self._pick(data, "last_name", "nom") or (" ".join(parts[1:]) if len(parts) > 1 else "")
            )
            field_data["phone"] = self._pick(data, "phone_number", "phone", "mobile", "tel")
            field_data["email"] = self._pick(data, "email", "courriel")
            field_data["full_address"] = self._pick(
                data, "street_address", "address", "full_address", "adresse"
            )
            field_data["city"] = self._pick(data, "city", "ville")
            form_id = form_id or self._pick(body.get("form") or {}, "id") or self._pick(data, "form_id")
            page_id = page_id or self._pick(body.get("page") or {}, "id") or self._pick(data, "page_id")
            leadgen_id = leadgen_id or str(body.get("id") or "")

        raw_rows = body.get("field_data")
        self._map_field_data(raw_rows, field_data)
        if raw_rows:
            payload["_raw_field_data"] = raw_rows
        payload.update(field_data)
        payload.update(
            {
                "page_id": page_id,
                "facebook_page_id": page_id,
                "form_id": form_id,
                "leadgen_form_id": form_id,
                "meta_lead_id": leadgen_id,
                "leadgen_id": leadgen_id,
            }
        )
        return payload

    @api.model
    def _fetch_lead_from_graph(self, leadgen_id, page_id=None):
        if not leadgen_id:
            return {}
        last_error = None
        for token in self._iter_graph_tokens(page_id=page_id):
            try:
                response = requests.get(
                    "https://graph.facebook.com/%s/%s" % (GRAPH_VERSION, leadgen_id),
                    params={
                        "access_token": token,
                        "fields": "field_data,created_time,id,form_id",
                    },
                    timeout=25,
                )
                data = response.json()
                if response.status_code >= 400 or data.get("error"):
                    last_error = data.get("error")
                    continue
                return data
            except requests.RequestException as exc:
                last_error = str(exc)
                continue
        if last_error:
            _logger.warning(
                "Meta Graph lead fetch failed for %s: %s",
                leadgen_id,
                last_error,
            )
        return {}

    @api.model
    def _enrich_from_graph(self, payload):
        leadgen_id = payload.get("leadgen_id") or ""
        if not leadgen_id:
            return payload
        has_contact = payload.get("phone") or payload.get("email")
        has_immo = any(payload.get(key) for key in IMMO_STRUCTURED_KEYS)
        if has_contact and has_immo and payload.get("_raw_field_data"):
            return payload
        graph_data = self._fetch_lead_from_graph(
            leadgen_id, page_id=payload.get("page_id")
        )
        if not graph_data:
            return payload
        field_data = {}
        self._map_field_data(graph_data.get("field_data"), field_data)
        for key, value in field_data.items():
            if value and not payload.get(key):
                payload[key] = value
        if graph_data.get("field_data") and not payload.get("_raw_field_data"):
            payload["_raw_field_data"] = graph_data.get("field_data")
        if not payload.get("form_id") and graph_data.get("form_id"):
            payload["form_id"] = str(graph_data["form_id"])
            payload["leadgen_form_id"] = str(graph_data["form_id"])
        return payload

    @api.model
    def _dispatch_lead(self, payload, route):
        pipeline = route.get("pipeline") or ""
        if route.get("skip_orchestrator") and not route.get("direct_odoo_create"):
            return {
                "status": "skipped",
                "pipeline": pipeline,
                "message": route.get("message") or _("Lead ignoré (routing)."),
            }, 200

        if pipeline == "marketing" or route.get("direct_odoo_create"):
            return (
                self.env["renovation.meta.marketing.webhook"]
                .sudo()
                .create_lead_from_meta_payload(payload)
            )

        if pipeline == "immo":
            return (
                self.env["renovation.meta.immo.webhook"]
                .sudo()
                .create_lead_from_meta(payload)
            )

        if pipeline == "energie":
            return (
                self.env["renovation.energie.webhook"]
                .sudo()
                .create_lead_from_webhook(payload)
            )

        if pipeline == "haidly":
            return (
                self.env["renovation.haidly.webhook"]
                .sudo()
                .create_lead_from_webhook(payload)
            )

        return {
            "status": "skipped",
            "pipeline": pipeline,
            "message": _("Pipeline non géré: %s") % pipeline,
        }, 200

    @api.model
    def _looks_like_immo_lead(self, payload):
        """True si le formulaire ressemble à Maison Recherchée (même form_id inconnu)."""
        payload = payload or {}
        if any(payload.get(key) for key in IMMO_STRUCTURED_KEYS):
            return True
        page_id = str(payload.get("page_id") or "").strip()
        default_page = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("renovation_conciergerie.meta_immo_facebook_page_id")
            or "964640820063787"
        )
        if page_id and page_id == str(default_page):
            return True
        blob = " ".join(
            str(payload.get(key) or "")
            for key in ("form_name", "campaign_name", "ad_name", "name")
        ).lower()
        return any(
            needle in blob
            for needle in (
                "maison recherchee",
                "maisonrecherch",
                "eval marchande",
                "évaluation marchande",
            )
        )

    @api.model
    def process_leadgen_event(self, body, change_value=None):
        payload = self._parse_leadgen_payload(body, change_value=change_value)
        payload = self._enrich_from_graph(payload)
        if payload.get("page_id") and payload.get("form_id"):
            self.env["renovation.meta.leads.routing"].sudo().link_meta_form(
                payload.get("page_id"),
                payload.get("form_id"),
                payload.get("form_name") or "",
            )
        route = self.env["renovation.meta.leads.routing"].sudo().resolve_route(payload)
        if route.get("status") == "unknown" and route.get("skip_orchestrator"):
            # Nouveau formulaire / pub Meta : page ou form_id pas encore dans
            # le mapping figé. Si le payload est une éval. marchande, on crée
            # quand même (sinon le lead n'entre jamais dans Odoo).
            if self._looks_like_immo_lead(payload):
                _logger.warning(
                    "Meta leadgen unmapped page_id=%s form_id=%s → fallback immo",
                    payload.get("page_id"),
                    payload.get("form_id"),
                )
                route = dict(
                    route,
                    status="ok",
                    pipeline="immo",
                    skip_orchestrator=False,
                    message="fallback immo (formulaire non mappé)",
                )
            else:
                _logger.info(
                    "Meta leadgen ignored (unmapped page_id=%s form_id=%s)",
                    payload.get("page_id"),
                    payload.get("form_id"),
                )
                return {
                    "status": "ignored",
                    "page_id": payload.get("page_id"),
                    "form_id": payload.get("form_id"),
                    "message": route.get("message"),
                }, 200
        result, status = self._dispatch_lead(payload, route)
        if isinstance(result, dict):
            result.setdefault("pipeline", route.get("pipeline"))
            result.setdefault("page_id", payload.get("page_id"))
            result.setdefault("form_id", payload.get("form_id"))
        return result, status

    @api.model
    def _graph_get_first_ok(self, path, params, page_id=None):
        """GET Graph en essayant chaque token jusqu'à un 200 sans error."""
        last_error = None
        for token in self._iter_graph_tokens(page_id=page_id):
            query = dict(params or {}, access_token=token)
            try:
                response = requests.get(
                    "https://graph.facebook.com/%s/%s" % (GRAPH_VERSION, path),
                    params=query,
                    timeout=25,
                )
                data = response.json() or {}
            except requests.RequestException as exc:
                last_error = str(exc)
                continue
            if response.status_code >= 400 or data.get("error"):
                last_error = data.get("error")
                continue
            return data, token
        if last_error:
            _logger.warning("Meta Graph GET %s failed: %s", path, last_error)
        return {}, None

    @staticmethod
    def _meta_created_after(created_time, since_iso):
        if not created_time:
            return True
        return str(created_time) >= str(since_iso)

    @api.model
    def _iter_form_leads(self, form_id, token, since_iso):
        """Paginate /{form_id}/leads. N'ignore pas les formulaires ARCHIVED."""
        params = {
            "access_token": token,
            "fields": "id,created_time,field_data,form_id",
            "limit": 100,
        }
        url = "https://graph.facebook.com/%s/%s/leads" % (GRAPH_VERSION, form_id)
        while url:
            try:
                response = requests.get(url, params=params, timeout=25)
                payload = response.json() or {}
            except requests.RequestException as exc:
                _logger.warning("Meta Graph leads page failed form=%s: %s", form_id, exc)
                return
            params = None
            if payload.get("error"):
                _logger.warning(
                    "Meta Graph leads failed form=%s: %s",
                    form_id,
                    payload.get("error"),
                )
                return
            for row in payload.get("data") or []:
                created_time = row.get("created_time") or ""
                if created_time and not self._meta_created_after(created_time, since_iso):
                    continue
                yield row
            url = (payload.get("paging") or {}).get("next") or ""

    @api.model
    def import_missing_maison_recherchee(self, days=14):
        """Rattrapage : tous les Instant Forms MR depuis `days` jours.

        Fenêtre volontairement plus large que 36 h : si le webhook Meta
        ou n8n rate, un lead de 2 jours ne doit plus être ignoré à vie.
        """
        import datetime as dt

        page_id = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("renovation_conciergerie.meta_immo_facebook_page_id")
            or "964640820063787"
        )
        if not page_id:
            return {"created": 0, "skipped": 0, "errors": ["no_page_id"]}
        forms_data, token = self._graph_get_first_ok(
            "%s/leadgen_forms" % page_id,
            {"fields": "id,name,status", "limit": 100},
            page_id=page_id,
        )
        if not token:
            return {
                "created": 0,
                "skipped": 0,
                "errors": ["graph_forms_unavailable"],
            }
        self.env.cr.execute(
            "SELECT immo_meta_lead_id FROM crm_lead "
            "WHERE immo_meta_lead_id IS NOT NULL AND immo_meta_lead_id != ''"
        )
        existing = {row[0] for row in self.env.cr.fetchall()}
        since = (
            dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=int(days or 14))
        ).strftime("%Y-%m-%dT%H:%M:%S+0000")
        created = 0
        skipped = 0
        errors = []
        routing = self.env["renovation.meta.leads.routing"].sudo()
        forms = list(forms_data.get("data") or [])
        for form in forms:
            routing.link_meta_form(page_id, form.get("id"), form.get("name") or "")
        for form in forms:
            status = (form.get("status") or "").upper()
            if status == "DELETED":
                continue
            fid = form.get("id")
            for row in self._iter_form_leads(fid, token, since):
                lid = str(row.get("id") or "")
                if not lid:
                    continue
                if lid in existing:
                    skipped += 1
                    continue
                try:
                    with self.env.cr.savepoint():
                        result, status_code = self.process_leadgen_event(
                            {
                                "page_id": page_id,
                                "form_id": str(row.get("form_id") or fid),
                                "leadgen_id": lid,
                                "field_data": row.get("field_data") or [],
                            }
                        )
                except Exception as exc:
                    msg = str(exc)
                    errors.append("%s: %s" % (lid, msg))
                    _logger.warning(
                        "MR Meta import exception leadgen=%s: %s", lid, msg
                    )
                    continue
                if isinstance(result, dict) and result.get("lead_id"):
                    if result.get("status") == "exists":
                        skipped += 1
                    else:
                        created += 1
                    existing.add(lid)
                    _logger.info(
                        "MR Meta import %s lead %s from %s",
                        result.get("status"),
                        result.get("lead_id"),
                        lid,
                    )
                else:
                    msg = (result or {}).get("message") if isinstance(result, dict) else status_code
                    errors.append("%s: %s" % (lid, msg))
                    _logger.warning(
                        "MR Meta import failed leadgen=%s: %s", lid, msg
                    )
        return {"created": created, "skipped": skipped, "errors": errors, "since": since}

    @api.model
    def cron_backfill_maison_recherchee(self):
        """Filet 15 min : Instant Forms MR → colonne Nouveau si le webhook rate."""
        result = self.import_missing_maison_recherchee(days=14)
        return int(result.get("created") or 0)
