# -*- coding: utf-8 -*-
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models

from .region_map import (
    ALL_QC_REGIONS,
    MATRIX_SERVICES,
    build_recruitment_callout,
    format_pct,
    lead_region,
    normalize_service_name,
    period_days_label,
    plural_leads,
    regions_from_texts,
    service_keys_from_names,
)


class RenoImmobilierDashboard(models.TransientModel):
    _name = "reno.immobilier.dashboard"
    _description = "Tableau de bord Réno Immobilier"

    name = fields.Char(default="Tableau de bord", readonly=True)
    date_from = fields.Date(string="Du", required=True)
    date_to = fields.Date(string="Au", required=True)
    pipeline_nouveau = fields.Integer(string="Nouveau", readonly=True)
    pipeline_attribue = fields.Integer(string="Attribué", readonly=True)
    pipeline_a_relancer = fields.Integer(string="À relancer", readonly=True)
    pipeline_en_contact = fields.Integer(string="En contact", readonly=True)
    pipeline_gagne = fields.Integer(string="Gagné", readonly=True)
    pipeline_perdu = fields.Integer(string="Perdu", readonly=True)
    pipeline_total = fields.Integer(string="Leads période", readonly=True)
    jumelage_auto_pct = fields.Float(string="Auto (%)", readonly=True)
    jumelage_manuel_pct = fields.Float(string="Manuel (%)", readonly=True)
    jumelage_aucun_pct = fields.Float(string="Aucun match (%)", readonly=True)
    jumelage_note = fields.Char(string="Jumelage", readonly=True)
    source_summary = fields.Text(string="Sources", readonly=True)
    package_summary = fields.Text(string="Forfaits", readonly=True)
    package_alert_count = fields.Integer(string="Forfaits ≤ 20 %", readonly=True)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        today = fields.Date.context_today(self)
        res.setdefault("date_from", today - relativedelta(days=29))
        res.setdefault("date_to", today)
        return res

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._reno_refresh_metrics()
        return records

    def _reno_team_ids(self):
        return self.env["crm.lead"]._reno_immo_team_ids()

    def _reno_period_bounds(self, date_from=None, date_to=None):
        day_from = date_from or self.date_from
        day_to = date_to or self.date_to
        start = fields.Datetime.to_datetime(day_from)
        end = fields.Datetime.to_datetime(day_to)
        if end:
            end = end.replace(hour=23, minute=59, second=59)
        return day_from, day_to, start, end

    def _reno_period_domain(self, date_from=None, date_to=None):
        _day_from, _day_to, start, end = self._reno_period_bounds(date_from, date_to)
        return [
            ("team_id", "in", self._reno_team_ids()),
            ("create_date", ">=", start),
            ("create_date", "<=", end),
        ]

    def _reno_period_leads(self, date_from=None, date_to=None):
        Lead = self.env["crm.lead"].sudo()
        return Lead.search(self._reno_period_domain(date_from, date_to)).filtered(
            lambda l: not l.reno_facile_paused
        )

    def _reno_refresh_metrics(self):
        for rec in self:
            payload = rec._reno_build_payload(rec.date_from, rec.date_to)
            rec.pipeline_nouveau = payload["kpis"]["nouveau"]
            rec.pipeline_attribue = payload["kpis"]["attribue"]
            rec.pipeline_a_relancer = payload["kpis"]["a_relancer"]
            rec.pipeline_en_contact = payload["kpis"]["en_contact"]
            rec.pipeline_gagne = payload["kpis"]["gagne"]
            rec.pipeline_perdu = payload["kpis"]["perdu"]
            rec.pipeline_total = payload["kpis"]["total"]
            rec.jumelage_auto_pct = payload["jumelage"]["auto_pct"]
            rec.jumelage_manuel_pct = payload["jumelage"]["manuel_pct"]
            rec.jumelage_aucun_pct = payload["jumelage"]["aucun_pct"]
            rec.jumelage_note = payload["jumelage"]["note"]
            rec.source_summary = payload["source_summary"]
            rec.package_summary = payload["package_summary"]
            rec.package_alert_count = payload["package_alert_count"]

    def _reno_kpi_counts(self, leads):
        counts = {
            "nouveau": 0,
            "attribue": 0,
            "a_relancer": 0,
            "en_contact": 0,
            "gagne": 0,
            "perdu": 0,
        }
        for lead in leads:
            status = lead.reno_gestion_status or "nouveau"
            if status in counts:
                counts[status] += 1
        counts["total"] = len(leads)
        counts["perdu_relancer"] = counts["perdu"] + counts["a_relancer"]
        return counts

    def _reno_jumelage(self, leads):
        auto = leads.filtered(lambda l: l.reno_assign_origin == "auto")
        manuel = leads.filtered(lambda l: l.reno_assign_origin == "manual")
        aucun = leads.filtered(
            lambda l: l.assignment_status == "no_match"
            or (not l.reno_assigned_partner_id and not getattr(l, "assigned_partner_id", False))
        )
        total = len(leads) or 1
        meaningful = bool(
            auto
            or manuel
            or leads.filtered(lambda l: l.assignment_status == "no_match")
        )
        n_auto, n_manuel, n_aucun = len(auto), len(manuel), len(aucun)
        if not meaningful:
            return {
                "auto": 0,
                "manuel": 0,
                "aucun": 0,
                "total": len(leads),
                "auto_pct": 0.0,
                "manuel_pct": 0.0,
                "aucun_pct": 0.0,
                "auto_pct_label": format_pct(0),
                "manuel_pct_label": format_pct(0),
                "aucun_pct_label": format_pct(0),
                "note": "En attente de données — mapping catégorie tout juste corrigé",
            }
        return {
            "auto": n_auto,
            "manuel": n_manuel,
            "aucun": n_aucun,
            "total": len(leads),
            "auto_pct": n_auto * 100.0 / total,
            "manuel_pct": n_manuel * 100.0 / total,
            "aucun_pct": n_aucun * 100.0 / total,
            "auto_pct_label": format_pct(n_auto * 100.0 / total),
            "manuel_pct_label": format_pct(n_manuel * 100.0 / total),
            "aucun_pct_label": format_pct(n_aucun * 100.0 / total),
            "note": "%s auto · %s manuel · %s sans match (sur %s)"
            % (n_auto, n_manuel, n_aucun, len(leads)),
        }

    def _reno_source_rows(self, leads):
        sources = {}
        for lead in leads:
            key = (lead.source_id.name or "Sans source").strip() or "Sans source"
            if key.lower() == "sans source":
                key = "Sans source"
            sources[key] = sources.get(key, 0) + 1
        ranked = sorted(sources.items(), key=lambda i: (-i[1], i[0].lower()))
        peak = ranked[0][1] if ranked else 1
        return [
            {
                "name": name,
                "count": count,
                "pct": (count * 100.0 / peak) if peak else 0,
            }
            for name, count in ranked
        ]

    def _reno_package_records(self, states=("active",)):
        Package = self.env["renovation.partner.package"].sudo()
        return Package.search([("state", "in", list(states))])

    def _reno_partner_cards(self, packages):
        cards = []
        alerts = 0
        lines = []
        for pkg in packages.sorted(
            key=lambda p: (
                0 if p.health_status == "a_renouveler" else 1 if p.health_status == "epuise" else 2,
                p.leads_remaining_pct if p.leads_remaining_pct is not False else 0,
                (p.partner_id.name or p.name or "").lower(),
            )
        ):
            pct = pkg.leads_remaining_pct if pkg.leads_remaining_pct is not False else 0
            weak = pkg.health_status in ("a_renouveler", "epuise") or pct <= 20
            if weak:
                alerts += 1
            status = "faible" if weak else "sain"
            status_label = "Faible" if weak else "Sain"
            partner = pkg.partner_id
            services = self._reno_package_service_labels(pkg)
            regions = self._reno_package_regions(pkg)
            if regions and len(regions) >= len(ALL_QC_REGIONS):
                region_label = "Multi-région"
            elif regions:
                region_label = ", ".join(regions[:2])
            else:
                region_label = (
                    (getattr(partner, "city_text", None) or "").strip()
                    or (partner.city or "").strip()
                    or ""
                )
            service_label = ", ".join(services[:3]) if services else "Général"
            place = " · ".join(bit for bit in (region_label, service_label) if bit)
            remaining = pkg.leads_remaining if pkg.leads_remaining is not False else 0
            total = pkg.leads_total or 0
            fill = pct if pct else (100.0 if total and remaining >= total else 0)
            cards.append(
                {
                    "id": pkg.id,
                    "name": partner.name or pkg.name or "Partenaire",
                    "place": place,
                    "status": status,
                    "status_label": status_label,
                    "remaining": remaining,
                    "total": total,
                    "fill": max(0, min(100, fill)),
                    "quota": "%s restants / %s" % (remaining, total),
                }
            )
            flag = " ⚠" if weak else ""
            lines.append(
                "%s — %s restants / %s (%s %%)%s"
                % (partner.name or pkg.name, remaining, total, int(pct), flag)
            )
        return cards, alerts, "\n".join(lines) or "Aucun forfait"

    def _reno_package_service_labels(self, package):
        names = []
        if "category_ids" in package._fields and package.category_ids:
            names.extend(package.category_ids.mapped("name"))
        partner = package.partner_id
        if partner and "service_category_ids" in partner._fields and partner.service_category_ids:
            names.extend(partner.service_category_ids.mapped("name"))
        seen = set()
        ordered = []
        for name in names:
            key = normalize_service_name(name)
            if name and key not in seen:
                seen.add(key)
                ordered.append(name)
        return ordered

    def _reno_package_service_keys(self, package):
        return service_keys_from_names(self._reno_package_service_labels(package))

    def _reno_is_qc_province(self, provinces):
        for state in provinces:
            code = (state.code or "").upper()
            name = (state.name or "").lower()
            if code == "QC" or "québec" in name or "quebec" in name:
                return True
        return False

    def _reno_package_regions(self, package):
        partner = package.partner_id
        mode = getattr(package, "coverage_mode", False) or getattr(
            partner, "coverage_mode", False
        )
        provinces = getattr(package, "province_ids", False) or getattr(
            partner, "province_ids", False
        )
        if not provinces:
            provinces = self.env["res.country.state"]
        if mode == "province" and self._reno_is_qc_province(provinces):
            return list(ALL_QC_REGIONS)
        texts = [
            getattr(package, "city_text", None) or "",
            getattr(partner, "city_text", None) or "",
            partner.city or "",
            partner.state_id.name if partner.state_id else "",
        ]
        regions = regions_from_texts(*texts)
        if not regions and mode == "province" and not provinces:
            # Province sans liste : on ne suppose pas tout le QC.
            return []
        return regions

    def _reno_lead_region(self, lead):
        extra = " ".join(
            bit
            for bit in (
                lead.zip or "",
                lead.state_id.name if lead.state_id else "",
                getattr(lead, "street2", None) or "",
            )
            if bit
        )
        return lead_region(lead.city, extra)

    def _reno_coverage_matrix(self, leads, packages, period_label):
        services = [
            {"key": key, "label": label}
            for key, label, _names in MATRIX_SERVICES
        ]
        coverage = {}
        health = {}
        for pkg in packages:
            regions = self._reno_package_regions(pkg)
            keys = self._reno_package_service_keys(pkg)
            if not regions or not keys:
                continue
            weak = pkg.health_status in ("a_renouveler", "epuise") or (
                (pkg.leads_remaining_pct if pkg.leads_remaining_pct is not False else 0) <= 20
            )
            partner_id = pkg.partner_id.id
            for region in regions:
                for key in keys:
                    cell = coverage.setdefault(region, {}).setdefault(key, set())
                    cell.add(partner_id)
                    health.setdefault(region, {}).setdefault(key, []).append(not weak)

        lead_counts = {}
        unmapped = 0
        for lead in leads:
            region = self._reno_lead_region(lead)
            if not region:
                unmapped += 1
                continue
            lead_counts[region] = lead_counts.get(region, 0) + 1

        row_names = set(lead_counts) | set(coverage)
        rows = []
        for name in sorted(
            row_names,
            key=lambda n: (-lead_counts.get(n, 0), ALL_QC_REGIONS.index(n) if n in ALL_QC_REGIONS else 99, n),
        ):
            cells = []
            for key, label, _names in MATRIX_SERVICES:
                partners = coverage.get(name, {}).get(key) or set()
                count = len(partners)
                if not count:
                    tone = "gap"
                    value = ""
                else:
                    goods = health.get(name, {}).get(key) or []
                    tone = "ok" if any(goods) else "warn"
                    value = str(count)
                cells.append(
                    {
                        "key": key,
                        "label": label,
                        "tone": tone,
                        "value": value,
                        "count": count,
                    }
                )
            rows.append(
                {
                    "name": name,
                    "leads": lead_counts.get(name, 0),
                    "leads_label": "%s · %s" % (plural_leads(lead_counts.get(name, 0)), period_label),
                    "cells": cells,
                }
            )
        callout = build_recruitment_callout(rows, services, period_label, unmapped)
        return {
            "services": services,
            "rows": rows,
            "callout": callout,
            "unmapped_leads": unmapped,
        }

    def _reno_build_payload(self, date_from, date_to):
        day_from, day_to, _start, _end = self._reno_period_bounds(date_from, date_to)
        leads = self._reno_period_leads(day_from, day_to)
        kpis = self._reno_kpi_counts(leads)
        jumelage = self._reno_jumelage(leads)
        sources = self._reno_source_rows(leads)
        all_packages = self._reno_package_records(("active", "draft", "expired"))
        active = all_packages.filtered(lambda p: p.state == "active")
        cards, alerts, package_summary = self._reno_partner_cards(active)
        period_label = period_days_label(day_from, day_to)
        matrix = self._reno_coverage_matrix(leads, active, period_label)
        source_summary = (
            "\n".join("%s — %s" % (row["name"], row["count"]) for row in sources)
            or "Aucun lead sur la période"
        )
        preview = 4
        hidden = max(0, len(cards) - preview)
        return {
            "date_from": fields.Date.to_string(day_from) if day_from else False,
            "date_to": fields.Date.to_string(day_to) if day_to else False,
            "period_label": period_label,
            "kpis": kpis,
            "jumelage": jumelage,
            "sources": sources,
            "source_summary": source_summary,
            "matrix": matrix,
            "partners": cards,
            "partners_preview": preview,
            "partners_hidden": hidden,
            "partners_subtitle": "%s partenaires · quota restant par forfait"
            % len(cards),
            "package_summary": package_summary,
            "package_alert_count": alerts,
        }

    @api.model
    def get_dashboard_payload(self, date_from=None, date_to=None):
        today = fields.Date.context_today(self)
        day_from = fields.Date.to_date(date_from) if date_from else today - relativedelta(days=29)
        day_to = fields.Date.to_date(date_to) if date_to else today
        return self._reno_build_payload(day_from, day_to)

    def action_refresh(self):
        self._reno_refresh_metrics()
        return {
            "type": "ir.actions.act_window",
            "name": "Tableau de bord",
            "res_model": "reno.immobilier.dashboard",
            "res_id": self.id,
            "view_mode": "form",
            "target": "current",
        }

    @api.model
    def action_open(self):
        return {
            "type": "ir.actions.client",
            "tag": "reno_immobilier_dashboard",
            "name": "Tableau de bord",
        }

    def action_open_leads(self):
        return self.env["ir.actions.act_window"]._for_xml_id(
            "reno_immobilier.action_reno_immobilier_leads"
        )
