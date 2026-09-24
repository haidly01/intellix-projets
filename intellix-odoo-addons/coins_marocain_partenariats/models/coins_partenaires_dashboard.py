# -*- coding: utf-8 -*-
"""Stats live pour la vue partenaires (ITEX / Driven / radio / influenceurs).

Pas de nouveau modèle métier : méthode utilitaire sur coins.entente.
Pas de cache — recalcul à chaque appel.
Tag ITEX absent en prod → partenaires = ententes actives (coins.entente).
"""
from datetime import timedelta

from odoo import api, fields, models


class CoinsEntenteDashboard(models.Model):
    _inherit = "coins.entente"

    @api.model
    def get_live_dashboard_stats(self, period_days=30):
        """Agrégats temps réel pour le dashboard partenaires.

        :param period_days: fenêtre CRM / Ventes (7, 30 ou 90). Défaut 30.
        """
        try:
            period_days = int(period_days or 30)
        except (TypeError, ValueError):
            period_days = 30
        if period_days not in (7, 30, 90):
            period_days = 30

        today = fields.Date.context_today(self)
        since = fields.Datetime.to_datetime(today) - timedelta(days=period_days - 1)
        # début de journée
        since = since.replace(hour=0, minute=0, second=0, microsecond=0)

        Category = self.env["res.partner.category"].sudo()
        itex_tag = Category.search([("name", "ilike", "ITEX")], limit=1)

        Entente = self.sudo()
        if itex_tag:
            Partner = self.env["res.partner"].sudo()
            members_active = Partner.search_count(
                [("active", "=", True), ("category_id", "in", [itex_tag.id])]
            )
            # Répartition : autres catégories des partenaires tagués ITEX
            partners = Partner.search(
                [("active", "=", True), ("category_id", "in", [itex_tag.id])]
            )
            cat_counts = {}
            for p in partners:
                for cat in p.category_id:
                    if cat.id == itex_tag.id:
                        continue
                    label = cat.name or "Autre"
                    cat_counts[label] = cat_counts.get(label, 0) + 1
            categories = [
                {"code": label, "label": label, "count": count}
                for label, count in sorted(cat_counts.items(), key=lambda x: -x[1])
            ]
            if not categories:
                categories = [{"code": "none", "label": "Sans autre catégorie", "count": 0}]
            members_source = "res.partner · tag ITEX"
        else:
            # Fallback prouvé en prod (août 2026) : pas de tag ITEX
            active_domain = [
                ("active", "=", True),
                ("statut_entente", "in", ("active", "a_renouveler")),
            ]
            members_active = Entente.search_count(active_domain)
            type_labels = dict(self._fields["type_partenaire"].selection)
            by_type = {code: 0 for code in type_labels}
            grouped = Entente.read_group(
                active_domain,
                ["type_partenaire"],
                ["type_partenaire"],
                lazy=False,
            )
            for row in grouped or []:
                code = row.get("type_partenaire")
                if code in by_type:
                    by_type[code] = int(
                        row.get("type_partenaire_count") or row.get("__count") or 0
                    )
            categories = [
                {
                    "code": code,
                    "label": type_labels.get(code) or code or "Non classé",
                    "count": by_type.get(code, 0),
                }
                for code in type_labels
            ]
            members_source = "coins.entente (active / à renouveler)"

        Lead = self.env["crm.lead"].sudo()
        Order = self.env["sale.order"].sudo()
        crm_count = Lead.search_count([("create_date", ">=", since)])
        sale_count = Order.search_count([("create_date", ">=", since)])

        members_renew = 0
        if itex_tag:
            members_renew = 0
        else:
            members_renew = Entente.search_count(
                [("active", "=", True), ("statut_entente", "=", "a_renouveler")]
            )

        max_cat = max((c.get("count") or 0) for c in categories) if categories else 0
        for c in categories:
            n = int(c.get("count") or 0)
            c["count"] = n
            c["pct"] = int(round(100.0 * n / max_cat)) if max_cat else 0

        lead_rows = Lead.search_read(
            [("create_date", ">=", since)],
            ["name", "city", "stage_id", "tag_ids", "contact_name"],
            order="create_date desc",
            limit=8,
        )
        Tag = self.env["crm.tag"].sudo()
        recent_leads = []
        for row in lead_rows:
            tag_names = ""
            if row.get("tag_ids"):
                tag_names = ", ".join(Tag.browse(row["tag_ids"]).mapped("name")[:3])
            stage = (row.get("stage_id") or [False, ""])[1] or "—"
            stage_l = (stage or "").lower()
            status_kind = "renew"
            if any(k in stage_l for k in ("nouveau", "pitch", "new")):
                status_kind = "nouveau"
            elif any(k in stage_l for k in ("gagn", "won", "qualif", "propos", "actif")):
                status_kind = "active"
            recent_leads.append(
                {
                    "name": row.get("name") or row.get("contact_name") or "—",
                    "services": tag_names or "—",
                    "city": row.get("city") or "—",
                    "status": stage,
                    "status_kind": status_kind,
                }
            )

        return {
            "period_days": period_days,
            "since": fields.Datetime.to_string(since),
            "as_of": fields.Datetime.to_string(fields.Datetime.now()),
            "members_active": int(members_active or 0),
            "members_renew": int(members_renew or 0),
            "members_source": members_source,
            "itex_tag_id": itex_tag.id if itex_tag else False,
            "categories": categories,
            "crm_opportunities": int(crm_count or 0),
            "sale_orders": int(sale_count or 0),
            "recent_leads": recent_leads,
        }
