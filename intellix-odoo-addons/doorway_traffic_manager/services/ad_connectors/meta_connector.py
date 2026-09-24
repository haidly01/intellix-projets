# -*- coding: utf-8 -*-
"""Connecteur Meta Ads — Graph API insights + création campagne."""
import logging

import requests

_logger = logging.getLogger(__name__)

GRAPH_VERSION = "v21.0"
GRAPH_BASE = "https://graph.facebook.com/%s" % GRAPH_VERSION


class MetaAdsConnector:
    def __init__(self, access_token, ad_account_id=None):
        self.access_token = (access_token or "").strip()
        self.ad_account_id = self._normalize_account_id(ad_account_id)

    @staticmethod
    def _normalize_account_id(account_id):
        raw = (account_id or "").strip()
        if not raw:
            return ""
        return raw if raw.startswith("act_") else "act_%s" % raw

    @staticmethod
    def is_placeholder_account(account_id, page_id):
        """Détecte act_{page_id} — placeholder invalide généré à l'import."""
        if not account_id or not page_id:
            return False
        return account_id.replace("act_", "").strip() == str(page_id).strip()

    def _request(self, method, path, params=None, data=None):
        query = dict(params or {})
        query["access_token"] = self.access_token
        url = "%s/%s" % (GRAPH_BASE, path.lstrip("/"))
        try:
            if method == "GET":
                resp = requests.get(url, params=query, timeout=45)
            else:
                payload = dict(data or {})
                payload["access_token"] = self.access_token
                resp = requests.post(url, data=payload, timeout=45)
            body = resp.json()
            if resp.status_code >= 400 or body.get("error"):
                err = body.get("error") or {}
                return {
                    "ok": False,
                    "message": err.get("message") or resp.text,
                    "data": body,
                }
            return {"ok": True, "data": body}
        except requests.RequestException as exc:
            _logger.warning("Meta Ads API: %s", exc)
            return {"ok": False, "message": str(exc), "data": {}}

    def validate_token(self):
        return self._request("GET", "me", {"fields": "id,name"})

    def list_ad_accounts(self, limit=50):
        return self._request(
            "GET",
            "me/adaccounts",
            {
                "fields": "id,name,account_id,account_status",
                "limit": limit,
            },
        )

    def find_ad_account_for_page(self, page_id):
        """Associe une page Facebook au compte publicitaire act_ via promote_pages."""
        page_id = str(page_id or "").strip()
        if not page_id:
            return {"ok": False, "message": "ID page Meta manquant."}

        accounts_res = self.list_ad_accounts()
        if not accounts_res["ok"]:
            return accounts_res

        accounts = (accounts_res.get("data") or {}).get("data") or []
        if not accounts:
            return {
                "ok": False,
                "message": (
                    "Aucun compte publicitaire Meta accessible avec ce token. "
                    "Vérifiez les permissions ads_management / business_management."
                ),
            }

        for acct in accounts:
            act_id = acct.get("id") or ""
            if not act_id:
                continue
            pages_res = self._request(
                "GET",
                "%s/promote_pages" % act_id,
                {"fields": "id,name", "limit": 100},
            )
            if not pages_res["ok"]:
                continue
            for page in (pages_res.get("data") or {}).get("data") or []:
                if str(page.get("id")) == page_id:
                    return {
                        "ok": True,
                        "data": act_id,
                        "account_name": acct.get("name"),
                        "page_name": page.get("name"),
                    }

        if len(accounts) == 1:
            acct = accounts[0]
            return {
                "ok": True,
                "data": acct.get("id"),
                "account_name": acct.get("name"),
                "warning": "fallback_single_ad_account",
            }

        names = ", ".join(
            (a.get("name") or a.get("id") or "") for a in accounts[:5]
        )
        return {
            "ok": False,
            "message": (
                "Impossible d'associer la page %s à un compte Ads. "
                "Comptes accessibles : %s. Renseignez meta_account_id manuellement "
                "(format act_XXXXX)."
            )
            % (page_id, names),
        }

    def list_campaigns(self, limit=50):
        if not self.ad_account_id:
            return {"ok": False, "message": "Meta Ads Account ID manquant."}
        return self._request(
            "GET",
            "%s/campaigns" % self.ad_account_id,
            {
                "fields": "id,name,status,objective,daily_budget,lifetime_budget",
                "limit": limit,
            },
        )

    def fetch_campaign_insights(self, external_campaign_id, date_preset="last_7d"):
        if not external_campaign_id:
            return {"ok": False, "message": "ID campagne Meta manquant."}
        return self._request(
            "GET",
            "%s/insights" % external_campaign_id,
            {
                "fields": (
                    "impressions,clicks,ctr,spend,actions,"
                    "cost_per_action_type,purchase_roas"
                ),
                "date_preset": date_preset,
            },
        )

    @staticmethod
    def parse_insights_row(row):
        if not row:
            return {
                "impressions": 0,
                "clicks": 0,
                "ctr": 0.0,
                "spend": 0.0,
                "conversions": 0,
                "cpa": 0.0,
                "roas": 0.0,
            }
        spend = float(row.get("spend") or 0)
        clicks = int(row.get("clicks") or 0)
        impressions = int(row.get("impressions") or 0)
        ctr = float(row.get("ctr") or 0)
        conversions = 0
        for action in row.get("actions") or []:
            if action.get("action_type") in (
                "lead",
                "offsite_conversion.fb_pixel_lead",
                "onsite_conversion.lead_grouped",
                "offsite_complete_registration_add_meta_leads",
                "offsite_search_add_meta_leads",
            ):
                conversions += int(action.get("value") or 0)
        cpa = spend / conversions if conversions else 0.0
        roas_list = row.get("purchase_roas") or []
        roas = float(roas_list[0].get("value") or 0) if roas_list else 0.0
        return {
            "impressions": impressions,
            "clicks": clicks,
            "ctr": ctr,
            "spend": spend,
            "conversions": conversions,
            "cpa": round(cpa, 2),
            "roas": round(roas, 2),
        }

    def parse_insights(self, insight_data):
        rows = (insight_data or {}).get("data") or []
        return self.parse_insights_row(rows[0] if rows else {})

    @staticmethod
    def merge_metrics(metrics_list):
        total = {
            "impressions": 0,
            "clicks": 0,
            "spend": 0.0,
            "conversions": 0,
            "roas": 0.0,
        }
        for m in metrics_list:
            total["impressions"] += m.get("impressions") or 0
            total["clicks"] += m.get("clicks") or 0
            total["spend"] += m.get("spend") or 0
            total["conversions"] += m.get("conversions") or 0
        total["ctr"] = (
            round(100.0 * total["clicks"] / total["impressions"], 2)
            if total["impressions"]
            else 0.0
        )
        total["cpa"] = (
            round(total["spend"] / total["conversions"], 2)
            if total["conversions"]
            else 0.0
        )
        total["spend"] = round(total["spend"], 2)
        return total

    def create_campaign(self, name, objective="OUTCOME_LEADS", daily_budget_cents=5000):
        if not self.ad_account_id:
            return {"ok": False, "message": "Meta Ads Account ID manquant."}
        return self._request(
            "POST",
            "%s/campaigns" % self.ad_account_id,
            data={
                "name": name,
                "objective": objective,
                "status": "PAUSED",
                "special_ad_categories": "[]",
                "daily_budget": str(daily_budget_cents),
            },
        )
