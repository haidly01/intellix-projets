# -*- coding: utf-8 -*-
import json
import re
from datetime import datetime, timedelta

import pytz

from odoo import http, fields
from odoo.exceptions import AccessError
from odoo.http import request

from .shell import is_reno_partner
from ..models.partner_lead_mandate import STATUS_VALUES
from ..models.partner_lead_attempt import ATTEMPT_RESULTS


class IntellixPartnerPortal(http.Controller):

    def _get_commercial_partner(self):
        user = request.env.user
        if user._is_public():
            return request.env["res.partner"]
        partner = user.partner_id.commercial_partner_id or user.partner_id
        return partner

    def _crm_backend_home(self, calendar=False):
        user = request.env.user
        if user._is_internal() and (
            user.has_group("renovation_conciergerie.group_doorway_pipeline_assigned")
            or user.has_group("sales_team.group_sale_salesman")
        ):
            return "/odoo/calendar" if calendar else "/odoo/action-726"
        if user._is_internal():
            return "/odoo"
        return None

    def _can_access_partner_portal(self):
        user = request.env.user
        if user._is_public():
            return False
        if user.has_group("base.group_portal"):
            return True
        return is_reno_partner(user)

    def _check_portal_access(self):
        partner = self._get_commercial_partner()
        if not partner:
            return None
        if not self._can_access_partner_portal():
            raise AccessError("Accès réservé aux utilisateurs portail.")
        return partner

    def _get_mandate(self, lead_id):
        partner = self._check_portal_access()
        if not partner:
            return partner, request.env["intellix.partner.lead.mandate"]
        mandate = request.env["intellix.partner.lead.mandate"].browse(lead_id)
        if not mandate.exists() or mandate.partner_id.commercial_partner_id != partner:
            return partner, request.env["intellix.partner.lead.mandate"]
        return partner, mandate

    def _portal_values(self, page="leads"):
        partner = self._check_portal_access()
        if not partner:
            return {"partner": partner, "page": page}
        return {
            "partner": partner,
            "page": page,
            "bloc": partner.active_bloc_id,
            "partner_score": partner.partner_score,
            "accepted_count": partner.portal_accepted_count,
            "converted_count": partner.portal_converted_count,
        }

    _MONTHS_FR = [
        "janv.", "févr.", "mars", "avr.", "mai", "juin",
        "juil.", "août", "sept.", "oct.", "nov.", "déc.",
    ]

    def _fmt_when(self, dt):
        if not dt:
            return ""
        local = fields.Datetime.context_timestamp(request.env.user, dt)
        return "%d %s %d, %s" % (
            local.day, self._MONTHS_FR[local.month - 1], local.year, local.strftime("%H:%M"),
        )

    def _parse_local_datetime(self, date_str, time_str):
        """Convertit une date/heure locale (formulaire) en datetime naïf UTC pour stockage."""
        naive = datetime.strptime("%s %s" % (date_str, time_str), "%Y-%m-%d %H:%M")
        tz_name = request.env.user.tz or "UTC"
        try:
            tz = pytz.timezone(tz_name)
        except Exception:
            tz = pytz.UTC
        return tz.localize(naive).astimezone(pytz.UTC).replace(tzinfo=None)

    def _team_users(self, partner):
        # sudo() conservé : ACL res.users pour group_portal/group_user est perm_write=0 (voir
        # Phase 1b) ; perm_read=1 suffirait ici mais on reste cohérent avec portal_team. Filtre
        # partner_id/child_of ci-dessous = seule barrière.
        return request.env["res.users"].sudo().search(
            [("partner_id", "child_of", partner.id)], order="name"
        )

    def _initials(self, name):
        parts = [p for p in (name or "?").split() if p]
        if not parts:
            return "?"
        if len(parts) == 1:
            return parts[0][:2].upper()
        return (parts[0][0] + parts[1][0]).upper()

    def _serialize_team(self, users):
        return [
            {"id": u.id, "name": u.name, "initials": self._initials(u.name)}
            for u in users
        ]

    def _serialize_lead(self, m):
        return {
            "id": m.id,
            "name": m.name,
            "city": m.city or "",
            "service": m.project_type or "",
            "status": m.status,
            "assignedTo": m.assigned_user_id.id or None,
            "notes": m.notes or "",
            "attempts": [
                {
                    "id": a.id,
                    "when": self._fmt_when(a.attempt_date),
                    "result": a.result,
                    "note": a.note or "",
                    "by": a.user_id.id or None,
                }
                for a in m.attempt_ids.sorted("attempt_date")
            ],
        }

    def _serialize_activity(self, a):
        local = fields.Datetime.context_timestamp(request.env.user, a.scheduled_at) if a.scheduled_at else None
        return {
            "id": a.id,
            "leadId": a.mandate_id.id,
            "type": a.activity_type,
            "title": a.title,
            "date": local.strftime("%Y-%m-%d") if local else "",
            "time": local.strftime("%H:%M") if local else "",
            "assignedTo": a.user_id.id or None,
            "done": a.done,
        }

    def _mandate_for_user(self, mandate_id, partner):
        """Mandat borné à l'organisation de l'appelant. Ne filtre PAS par membre assigné :
        cette restriction est appliquée séparément par _can_touch_mandate (cf. commentaire
        sur le caractère cosmétique/UX du filtre membre, la barrière réelle étant l'org)."""
        Mandate = request.env["intellix.partner.lead.mandate"]
        mandate = Mandate.browse(mandate_id)
        if not mandate.exists() or mandate.partner_id.commercial_partner_id != partner:
            return Mandate
        return mandate

    def _can_touch_mandate(self, mandate):
        """Un gestionnaire agit sur tout lead de son organisation ; un membre uniquement sur
        ses leads assignés — cohérent avec la contrainte dashboard (agrégats jamais mélangés
        hors des leads assignés d'un membre)."""
        if request.env.user.is_portal_manager:
            return True
        return mandate.assigned_user_id.id == request.env.user.id

    @http.route(["/my/leads", "/my/leads/page/<int:page>"], type="http", auth="user", website=True)
    def portal_leads_dashboard(self, page=1, **kw):
        if not self._can_access_partner_portal():
            crm = self._crm_backend_home()
            if crm:
                return request.redirect(crm)
            return request.redirect("/web/login?redirect=/my/leads")
        partner = self._check_portal_access()
        if not partner:
            return request.redirect("/web/login?redirect=/my/leads")
        is_manager = request.env.user.is_portal_manager
        # Pas de sudo() : la ir.rule rule_mandate_portal_partner (portail + partenaire rénovation)
        # applique déjà le child_of ; le domaine ci-dessous reste une deuxième barrière explicite.
        Mandate = request.env["intellix.partner.lead.mandate"]
        all_mandates = Mandate.search([("partner_id", "child_of", partner.id)])
        # Filtre membre : cosmétique/UX (cf. consigne), appliqué ici côté serveur pour ne
        # jamais faire transiter les données des collègues dans la page d'un Membre.
        mine = all_mandates if is_manager else all_mandates.filtered(
            lambda m: m.assigned_user_id.id == request.env.user.id
        )
        team = self._team_users(partner)
        activities = mine.mapped("activity_ids")

        values = self._portal_values(page="leads")
        values.update(
            {
                "crm_data_json": json.dumps(
                    {
                        "leads": [self._serialize_lead(m) for m in mine],
                        "activities": [self._serialize_activity(a) for a in activities],
                        "team": self._serialize_team(team),
                    }
                ),
                "is_manager": is_manager,
                "current_user_id": request.env.user.id,
            }
        )
        return request.render("intellix_partner_portal.portal_leads_dashboard", values)

    @http.route("/my/leads/api/reassign", type="jsonrpc", auth="user", methods=["POST"])
    def portal_lead_api_reassign(self, mandate_id=None, user_id=None, **kw):
        partner = self._check_portal_access()
        if not partner or not request.env.user.is_portal_manager:
            return {"ok": False}
        mandate = self._mandate_for_user(mandate_id, partner)
        if not mandate:
            return {"ok": False}
        target = None
        if user_id:
            # Barrière : la cible doit appartenir à la même organisation — jamais un user_id
            # arbitraire venant de la requête sans vérification.
            candidate = request.env["res.users"].sudo().browse(int(user_id))
            if not candidate.exists() or candidate.partner_id.commercial_partner_id != partner:
                return {"ok": False}
            target = candidate
        mandate.write({"assigned_user_id": target.id if target else False})
        return {"ok": True}

    @http.route("/my/leads/api/notes", type="jsonrpc", auth="user", methods=["POST"])
    def portal_lead_api_notes(self, mandate_id=None, notes=None, **kw):
        partner = self._check_portal_access()
        if not partner:
            return {"ok": False}
        mandate = self._mandate_for_user(mandate_id, partner)
        if not mandate or not self._can_touch_mandate(mandate):
            return {"ok": False}
        mandate.write({"notes": notes or ""})
        return {"ok": True}

    @http.route("/my/leads/api/status", type="jsonrpc", auth="user", methods=["POST"])
    def portal_lead_api_status(self, mandate_id=None, status=None, **kw):
        partner = self._check_portal_access()
        if not partner:
            return {"ok": False}
        mandate = self._mandate_for_user(mandate_id, partner)
        if not mandate or not self._can_touch_mandate(mandate):
            return {"ok": False}
        if status not in dict(STATUS_VALUES):
            return {"ok": False}
        # Décision humaine explicite uniquement : ce endpoint n'est jamais appelé
        # automatiquement par le système, seulement par un clic utilisateur.
        mandate.write({"status": status})
        return {"ok": True, "status": mandate.status, "status_label": mandate.status_label}

    @http.route("/my/leads/api/activity/create", type="jsonrpc", auth="user", methods=["POST"])
    def portal_lead_api_activity_create(self, mandate_id=None, activity_type=None, title=None,
                                         date=None, time=None, user_id=None, **kw):
        partner = self._check_portal_access()
        if not partner:
            return {"ok": False}
        mandate = self._mandate_for_user(mandate_id, partner)
        if not mandate or not self._can_touch_mandate(mandate):
            return {"ok": False}
        if activity_type not in ("call", "task", "meeting") or not (title or "").strip():
            return {"ok": False}
        assigned = False
        if request.env.user.is_portal_manager:
            if user_id:
                candidate = request.env["res.users"].sudo().browse(int(user_id))
                if candidate.exists() and candidate.partner_id.commercial_partner_id == partner:
                    assigned = candidate.id
        else:
            assigned = request.env.user.id
        try:
            scheduled_utc = self._parse_local_datetime(date, time)
        except Exception:
            return {"ok": False}
        activity = request.env["intellix.partner.lead.activity"].create(
            {
                "mandate_id": mandate.id,
                "activity_type": activity_type,
                "title": title.strip(),
                "scheduled_at": scheduled_utc,
                "user_id": assigned or False,
            }
        )
        return {"ok": True, "activity": self._serialize_activity(activity)}

    @http.route("/my/leads/api/activity/toggle", type="jsonrpc", auth="user", methods=["POST"])
    def portal_lead_api_activity_toggle(self, activity_id=None, **kw):
        partner = self._check_portal_access()
        if not partner:
            return {"ok": False}
        activity = request.env["intellix.partner.lead.activity"].browse(int(activity_id))
        if not activity.exists() or activity.mandate_id.partner_id.commercial_partner_id != partner:
            return {"ok": False}
        if not self._can_touch_mandate(activity.mandate_id):
            return {"ok": False}
        activity.write({"done": not activity.done})
        return {"ok": True, "done": activity.done}

    @http.route("/my/leads/api/attempt/create", type="jsonrpc", auth="user", methods=["POST"])
    def portal_lead_api_attempt_create(self, mandate_id=None, date=None, time=None,
                                        result=None, note=None, **kw):
        partner = self._check_portal_access()
        if not partner:
            return {"ok": False}
        mandate = self._mandate_for_user(mandate_id, partner)
        if not mandate or not self._can_touch_mandate(mandate):
            return {"ok": False}
        if result not in dict(ATTEMPT_RESULTS):
            return {"ok": False}
        try:
            attempt_utc = self._parse_local_datetime(date, time)
        except Exception:
            return {"ok": False}
        attempt = request.env["intellix.partner.lead.attempt"].create(
            {
                "mandate_id": mandate.id,
                "attempt_date": attempt_utc,
                "result": result,
                "note": (note or "").strip(),
                "user_id": request.env.user.id,
                "channel": "phone",
            }
        )
        # Transitions autorisées uniquement (jamais vers "perdu" -- décision humaine requise
        # via /my/leads/api/status, jamais automatique ici) :
        if mandate.status == "nouveau":
            mandate.status = "relance"
        if result == "interested":
            mandate.status = "rdv"
        return {
            "ok": True,
            "attempt": self._serialize_lead(mandate)["attempts"][-1],
            "status": mandate.status,
            "status_label": mandate.status_label,
        }

    @http.route(
        "/my/profil",
        type="http",
        auth="user",
        website=True,
        methods=["GET", "POST"],
        csrf=True,
    )
    def portal_profile(self, **kw):
        partner = self._check_portal_access()
        if not partner:
            return request.redirect("/web/login?redirect=/my/profil")

        ServiceCategory = request.env["renovation.service.category"]
        all_services = ServiceCategory.search([], order="name")

        if request.httprequest.method == "POST" and not request.env.user.is_portal_manager:
            return request.redirect("/my/profil")

        if request.httprequest.method == "POST":
            coverage_mode = kw.get("coverage_mode", partner.coverage_mode)
            city_text = kw.get("city_text", "")
            postal_codes_text = kw.get("postal_codes_text", "")
            radius = float(kw.get("coverage_radius_km") or partner.coverage_radius_km or 40)
            capacity = int(kw.get("monthly_lead_capacity") or partner.monthly_lead_capacity or 15)
            pause_mode = bool(kw.get("partner_pause_mode"))
            service_ids = [int(x) for x in request.httprequest.form.getlist("service_ids") if x.isdigit()]

            vals = {
                "coverage_mode": coverage_mode,
                "monthly_lead_capacity": capacity,
                "partner_pause_mode": pause_mode,
                "service_category_ids": [(6, 0, service_ids)],
            }
            if coverage_mode == "city":
                vals["city_text"] = city_text
            elif coverage_mode == "postal":
                vals["postal_codes_text"] = postal_codes_text
            elif coverage_mode == "radius":
                vals["coverage_radius_km"] = radius
            elif coverage_mode == "province":
                # Keep mode; province label stored in city_text for demo simplicity if no dedicated field
                state_name = (kw.get("state_name") or "").strip()
                if state_name:
                    vals["city_text"] = state_name

            # sudo() conservé : ni base.group_portal ni base.group_user (donc ni
            # renovation_conciergerie.group_renovation_partner) n'ont perm_write=1 sur res.partner
            # dans ir.model.access.csv (core ou custom) — seul group_partner_manager l'a. Sans
            # sudo(), cette écriture lève une AccessError pour tous les partenaires. La ir.rule
            # élargie ne change rien à ça : elle filtre, elle n'accorde pas de droit CRUD.
            # Barrière : `partner` est toujours user.partner_id.commercial_partner_id, jamais un
            # id fourni par la requête — aucun id externe n'entre dans ce write().
            partner.sudo().write(vals)
            return request.redirect("/my/profil?saved=1")

        values = self._portal_values(page="profil")
        zone_cities = []
        if partner.city_text:
            zone_cities = [
                t.strip()
                for t in re.split(r"[,;\n]+", partner.city_text)
                if t.strip()
            ]
        values.update(
            {
                "all_services": all_services,
                "zone_cities": zone_cities,
                "capacity_percent": (
                    (partner.leads_used_this_month / partner.monthly_lead_capacity * 100)
                    if partner.monthly_lead_capacity
                    else 0
                ),
            }
        )
        return request.render("intellix_partner_portal.portal_profile", values)

    @http.route(
        "/my/profil/zone/add",
        type="jsonrpc",
        auth="user",
        methods=["POST"],
    )
    def portal_zone_add(self, city=None, **kw):
        partner = self._check_portal_access()
        if not partner or not city:
            return {"ok": False}
        if not request.env.user.is_portal_manager:
            return {"ok": False}
        cities = partner.city_text or ""
        tokens = [t.strip() for t in re.split(r"[,;\n]+", cities) if t.strip()]
        if city.strip() not in tokens:
            tokens.append(city.strip())
        # sudo() conservé : même raison que portal_profile — aucune ACL write sur res.partner
        # pour group_portal/group_user. Barrière : `partner` = commercial_partner_id de
        # l'utilisateur courant, jamais un id fourni par la requête.
        partner.sudo().write({"city_text": ", ".join(tokens), "coverage_mode": "city"})
        return {"ok": True, "cities": tokens}

    @http.route(
        "/my/profil/zone/remove",
        type="jsonrpc",
        auth="user",
        methods=["POST"],
    )
    def portal_zone_remove(self, city=None, **kw):
        partner = self._check_portal_access()
        if not partner or not city:
            return {"ok": False}
        if not request.env.user.is_portal_manager:
            return {"ok": False}
        tokens = [t.strip() for t in re.split(r"[,;\n]+", partner.city_text or "") if t.strip()]
        tokens = [t for t in tokens if t.lower() != city.strip().lower()]
        # sudo() conservé : même raison que portal_profile — aucune ACL write sur res.partner
        # pour group_portal/group_user. Barrière : `partner` = commercial_partner_id de
        # l'utilisateur courant, jamais un id fourni par la requête.
        partner.sudo().write({"city_text": ", ".join(tokens)})
        return {"ok": True, "cities": tokens}


    def _relative_fr(self, dt):
        if not dt:
            return ""
        if isinstance(dt, str):
            try:
                dt = fields.Datetime.to_datetime(dt)
            except (ValueError, TypeError):
                return ""
        now = fields.Datetime.now()
        if dt > now:
            delta = dt - now
            secs = int(delta.total_seconds())
            if secs < 3600:
                mins = max(1, secs // 60)
                return "Dans %s minute%s" % (mins, "s" if mins > 1 else "")
            if secs < 86400:
                hours = secs // 3600
                return "Dans %s heure%s" % (hours, "s" if hours > 1 else "")
            days = secs // 86400
            return "Dans %s jour%s" % (days, "s" if days > 1 else "")
        secs = int((now - dt).total_seconds())
        if secs < 60:
            return "À l'instant"
        if secs < 3600:
            mins = secs // 60
            return "Il y a %s minute%s" % (mins, "s" if mins > 1 else "")
        if secs < 86400:
            hours = secs // 3600
            return "Il y a %s heure%s" % (hours, "s" if hours > 1 else "")
        days = secs // 86400
        return "Il y a %s jour%s" % (days, "s" if days > 1 else "")

    def _local_date(self, dt):
        if not dt:
            return None
        return fields.Datetime.context_timestamp(request.env.user, dt).date()

    @http.route(["/my/dashboard", "/my/dashboard/"], type="http", auth="user", website=True, sitemap=False)
    def portal_dashboard(self, **kw):
        """Tableau de bord CRM leads — KPI, activités du jour, pipeline, analyse."""
        if not self._can_access_partner_portal():
            crm = self._crm_backend_home()
            if crm:
                return request.redirect(crm)
            return request.redirect("/web/login?redirect=/my/dashboard")
        partner = self._check_portal_access()
        if not partner:
            return request.redirect("/web/login?redirect=/my/dashboard")
        is_manager = request.env.user.is_portal_manager

        # Pas de sudo() : couvert par rule_mandate_portal_partner (portail + partenaire rénovation).
        Mandate = request.env["intellix.partner.lead.mandate"]
        all_mandates = Mandate.search([("partner_id", "child_of", partner.id)])
        # Filtre membre cosmétique/UX (cf. /my/leads) : jamais d'agrégat mélangeant les leads
        # d'un collègue dans la vue d'un Membre.
        mine = all_mandates if is_manager else all_mandates.filtered(
            lambda m: m.assigned_user_id.id == request.env.user.id
        )
        activities = mine.mapped("activity_ids")

        today = fields.Date.context_today(request.env.user)
        week_end = today + timedelta(days=7)

        due_today = activities.filtered(
            lambda a: not a.done and self._local_date(a.scheduled_at) == today
        ).sorted("scheduled_at")
        upcoming = activities.filtered(
            lambda a: not a.done and self._local_date(a.scheduled_at)
            and today < self._local_date(a.scheduled_at) <= week_end
        ).sorted("scheduled_at")
        rdv_week = activities.filtered(
            lambda a: a.activity_type == "meeting" and self._local_date(a.scheduled_at)
            and today <= self._local_date(a.scheduled_at) <= week_end
        )

        vendu_leads = mine.filtered(lambda m: m.status == "vendu")
        perdu_leads = mine.filtered(lambda m: m.status == "perdu")
        resolved = vendu_leads | perdu_leads
        # Taux de closing = vendus / (vendus + perdus) -- jamais vendus/total.
        close_rate = round(len(vendu_leads) / len(resolved) * 100) if resolved else None

        avg_win = (
            sum(len(m.attempt_ids) for m in vendu_leads) / len(vendu_leads)
            if vendu_leads else None
        )
        avg_loss = (
            sum(len(m.attempt_ids) for m in perdu_leads) / len(perdu_leads)
            if perdu_leads else None
        )

        status_colors = {"nouveau": "sky", "relance": "amber", "rdv": "violet", "vendu": "emerald", "perdu": "rose"}
        pipeline_rows = []
        max_count = max([len(mine.filtered(lambda m, k=k: m.status == k)) for k, _ in STATUS_VALUES] + [1])
        for key, label in STATUS_VALUES:
            count = len(mine.filtered(lambda m, k=key: m.status == k))
            pipeline_rows.append(
                {
                    "key": key,
                    "label": label,
                    "count": count,
                    "pct": round(count / max_count * 100),
                    "color_var": status_colors[key],
                }
            )

        team_stats = []
        if is_manager:
            for u in self._team_users(partner):
                u_leads = all_mandates.filtered(lambda m, uid=u.id: m.assigned_user_id.id == uid)
                u_active = u_leads.filtered(lambda m: m.status not in ("vendu", "perdu"))
                u_pending = u_active.filtered(lambda m: m.status in ("nouveau", "relance"))
                u_resolved = u_leads.filtered(lambda m: m.status in ("vendu", "perdu"))
                u_vendu = u_leads.filtered(lambda m: m.status == "vendu")
                u_rate = round(len(u_vendu) / len(u_resolved) * 100) if u_resolved else None
                has_upcoming = bool(activities.filtered(lambda a, uid=u.id: not a.done and a.user_id.id == uid))
                team_stats.append(
                    {
                        "user": u,
                        "initials": self._initials(u.name),
                        "active": len(u_active),
                        "pending": len(u_pending),
                        "total": len(u_leads),
                        "resolved": len(u_resolved),
                        "rate": u_rate,
                        "has_upcoming": has_upcoming,
                    }
                )

        # ---- Analyse du traitement des leads : recommandations (règles simples) ----
        recos = []
        at_risk = mine.filtered(
            lambda m: m.status == "relance"
            and len(m.attempt_ids) >= 3
            and not m.activity_ids.filtered(
                lambda a: not a.done and self._local_date(a.scheduled_at) and self._local_date(a.scheduled_at) >= today
            )
        )
        if at_risk:
            recos.append(
                {
                    "type": "warn",
                    "names": ", ".join(at_risk.mapped("name")),
                    "text": " — 3 tentatives sans réponse et aucune relance planifiée. "
                    "Marque le dossier Perdu ou planifie un dernier contact par un autre canal (texto, courriel).",
                }
            )
        untouched = mine.filtered(lambda m: m.status == "nouveau" and not m.attempt_ids)
        if untouched:
            recos.append(
                {
                    "type": "warn",
                    "names": ", ".join(untouched.mapped("name")),
                    "text": " n'ont encore reçu aucun appel — plus le premier contact tarde, "
                    "plus les chances de closing baissent.",
                }
            )
        if avg_win and avg_loss:
            recos.append(
                {
                    "type": "info",
                    "names": "",
                    "text": "Les dossiers vendus ferment en moyenne après %.1f appel(s), contre %.1f "
                    "pour les dossiers perdus — au-delà de 3 tentatives sans réponse, un nouveau canal "
                    "convertit souvent mieux qu'un 4e appel." % (avg_win, avg_loss),
                }
            )
        if is_manager:
            rated = [t for t in team_stats if t["rate"] is not None]
            if rated:
                worst = min(rated, key=lambda t: t["rate"])
                if worst["rate"] < 50:
                    recos.append(
                        {
                            "type": "bad",
                            "names": worst["user"].name,
                            "text": " — %s%% de closing sur les dossiers clos (%s). Ça vaut la peine de "
                            "revoir l'approche de relance ensemble." % (worst["rate"], worst["resolved"]),
                        }
                    )
            no_activity = [t for t in team_stats if t["total"] > 0 and not t["has_upcoming"]]
            if no_activity:
                names = ", ".join(t["user"].name for t in no_activity)
                verb = "ont" if len(no_activity) > 1 else "a"
                recos.append(
                    {
                        "type": "warn",
                        "names": names,
                        "text": " n'%s aucune activité à venir planifiée — risque de perdre le fil "
                        "sur ses leads en cours." % verb,
                    }
                )
        if not recos:
            recos.append({"type": "ok", "names": "", "text": "Rien à signaler pour l'instant — le traitement des leads suit un bon rythme."})

        # ---- Activité récente : dernières tentatives, tous leads visibles, antéchronologique ----
        feed_entries = []
        for m in mine:
            for a in m.attempt_ids:
                feed_entries.append(
                    {
                        "lead_name": m.name,
                        "result_label": dict(ATTEMPT_RESULTS).get(a.result, a.result),
                        "when": self._fmt_when(a.attempt_date),
                        "by": a.user_id.name if a.user_id else "—",
                        "sort": a.attempt_date or fields.Datetime.now(),
                    }
                )
        feed_entries.sort(key=lambda f: f["sort"])
        recent_feed = list(reversed(feed_entries))[:6]

        values = self._portal_values(page="dashboard")
        values.update(
            {
                "is_manager": is_manager,
                "kpi_leads_count": len(mine),
                "kpi_today_count": len(due_today),
                "kpi_rdv_week_count": len(rdv_week),
                "kpi_close_rate": close_rate,
                "kpi_vendu_count": len(vendu_leads),
                "kpi_resolved_count": len(resolved),
                "due_today": due_today,
                "upcoming": upcoming,
                "pipeline_rows": pipeline_rows,
                "team_stats": team_stats,
                "avg_win": avg_win,
                "avg_loss": avg_loss,
                "recos": recos,
                "recent_feed": recent_feed,
                "activity_type_labels": {"call": "Appel", "task": "Tâche", "meeting": "RDV"},
            }
        )
        return request.render("intellix_partner_portal.portal_dashboard", values)

    @http.route(
        "/my/dashboard/activity/<int:activity_id>/toggle",
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
        csrf=True,
    )
    def portal_dashboard_activity_toggle(self, activity_id, **kw):
        partner = self._check_portal_access()
        if not partner:
            return request.redirect("/web/login?redirect=/my/dashboard")
        activity = request.env["intellix.partner.lead.activity"].browse(activity_id)
        if (
            activity.exists()
            and activity.mandate_id.partner_id.commercial_partner_id == partner
            and self._can_touch_mandate(activity.mandate_id)
        ):
            activity.write({"done": not activity.done})
        return request.redirect("/my/dashboard")

    @http.route(["/my/stats", "/my/stats/"], type="http", auth="user", website=True, sitemap=False)
    def portal_stats(self, **kw):
        partner = self._check_portal_access()
        if not partner:
            return request.redirect("/web/login?redirect=/my/stats")
        values = self._portal_values(page="stats")
        bloc = partner.active_bloc_id
        # bloc.size is the real field (not lead_count)
        bloc_size = int(bloc.size) if bloc else 10
        delivered = int(bloc.delivered_count) if bloc else int(partner.portal_accepted_count or 0)
        remaining = max(bloc_size - delivered, 0)
        values.update({
            "bloc_size": bloc_size,
            "delivered_count": delivered,
            "remaining_count": remaining,
            "bloc_percent": min(100, int(delivered / (bloc_size or 1) * 100)),
        })
        return request.render("intellix_partner_portal.portal_stats", values)

    @http.route(["/my/facturation", "/my/facturation/"], type="http", auth="user", website=True, sitemap=False)
    def portal_billing(self, **kw):
        partner = self._check_portal_access()
        if not partner:
            return request.redirect("/web/login?redirect=/my/facturation")
        if not request.env.user.is_portal_manager:
            return request.redirect("/my/dashboard")
        values = self._portal_values(page="facturation")
        # sudo() conservé : account.move est core Odoo, scopé par défaut à la comptabilité interne,
        # pas aux partenaires externes. Filtre partner_id/child_of ci-dessous = seule barrière.
        invoices = request.env["account.move"].sudo().search([
            ("partner_id", "child_of", partner.commercial_partner_id.id),
            ("move_type", "in", ["out_invoice", "out_refund"]),
            ("state", "!=", "cancel"),
        ], order="invoice_date desc", limit=50)
        values["invoices"] = invoices
        return request.render("intellix_partner_portal.portal_billing", values)

    @http.route(["/my/visites", "/my/visites/"], type="http", auth="user", website=True, sitemap=False)
    def portal_visits(self, **kw):
        """Visites = calendar.event du partenaire (lecture seule). Vide si aucun RDV lié."""
        if not self._can_access_partner_portal():
            crm = self._crm_backend_home(calendar=True)
            if crm:
                return request.redirect(crm)
            return request.redirect("/web/login?redirect=/my/visites")
        partner = self._check_portal_access()
        if not partner:
            return request.redirect("/web/login?redirect=/my/visites")
        values = self._portal_values(page="visites")
        # sudo() conservé : même raison que dans portal_dashboard (calendar.event core Odoo,
        # règles par défaut non adaptées aux partenaires externes). Filtre ci-dessous = seule barrière.
        Event = request.env["calendar.event"].sudo()
        visits = Event.search(
            [
                "|",
                ("partner_ids", "child_of", partner.id),
                ("user_id", "=", request.env.user.id),
            ],
            order="start desc",
            limit=50,
        )
        values["visits"] = visits
        return request.render("intellix_partner_portal.portal_visits", values)

    @http.route(["/my/devis-ventes", "/my/devis-ventes/"], type="http", auth="user", website=True, sitemap=False)
    def portal_sales(self, **kw):
        """Devis & ventes = sale.order liés au partenaire commercial (lecture seule)."""
        if not self._can_access_partner_portal():
            crm = self._crm_backend_home()
            if crm:
                return request.redirect(crm)
            return request.redirect("/web/login?redirect=/my/devis-ventes")
        partner = self._check_portal_access()
        if not partner:
            return request.redirect("/web/login?redirect=/my/devis-ventes")
        values = self._portal_values(page="devis")
        commercial = partner.commercial_partner_id or partner
        # sudo() conservé : même raison que portal_dashboard (sale.order core Odoo). Filtre
        # partner_id/child_of ci-dessous = seule barrière.
        orders = request.env["sale.order"].sudo().search(
            [("partner_id", "child_of", commercial.id)],
            order="date_order desc",
            limit=50,
        )
        values["orders"] = orders
        return request.render("intellix_partner_portal.portal_sales", values)

    @http.route(["/my/equipe", "/my/equipe/"], type="http", auth="user", website=True, sitemap=False)
    def portal_team(self, **kw):
        """Équipe = utilisateurs portail de l'organisation. Lecture ouverte à tous les
        membres ; invitation/retrait réservés aux gestionnaires (is_portal_manager)."""
        if not self._can_access_partner_portal():
            crm = self._crm_backend_home()
            if crm:
                return request.redirect(crm)
            return request.redirect("/web/login?redirect=/my/equipe")
        partner = self._check_portal_access()
        if not partner:
            return request.redirect("/web/login?redirect=/my/equipe")
        values = self._portal_values(page="equipe")
        # sudo() conservé : ACL res.users pour group_portal/group_user est perm_write=0
        # (vérifié dans base/security/ir.model.access.csv, seul group_erp_manager l'a) ;
        # perm_read=1 suffirait pour lister, mais on reste cohérent avec le reste du
        # contrôleur. Filtre partner_id/child_of ci-dessous = seule barrière.
        Users = request.env["res.users"].sudo()
        members = Users.search(
            [("partner_id", "child_of", partner.id)],
            order="is_portal_manager desc, name",
        )
        values.update({
            "members": members,
            "is_manager": request.env.user.is_portal_manager,
        })
        return request.render("intellix_partner_portal.portal_team", values)

    @http.route(
        "/my/equipe/inviter",
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
        csrf=True,
    )
    def portal_team_invite(self, **kw):
        partner = self._check_portal_access()
        if not partner or not request.env.user.is_portal_manager:
            return request.redirect("/my/equipe")
        name = (kw.get("name") or "").strip()
        email = (kw.get("email") or "").strip()
        if not name or not email:
            return request.redirect("/my/equipe?invite_error=missing")
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
            return request.redirect("/my/equipe?invite_error=invalid_email")
        # sudo() conservé : ACL res.users n'accorde perm_create qu'à group_erp_manager.
        # Barrière : parent_id/partner_id du nouveau membre est TOUJOURS `partner`
        # (commercial_partner_id de l'appelant, jamais un id fourni par la requête) —
        # le nouveau membre est borné à la même organisation que le gestionnaire qui invite.
        Users = request.env["res.users"].sudo()
        existing = Users.with_context(active_test=False).search([("login", "=", email)], limit=1)
        if existing:
            return request.redirect("/my/equipe?invite_error=exists")
        portal_group = request.env.ref("base.group_portal")
        # res.users est _inherits de res.partner (name/email délégués) : passer le
        # partner_id de la SOCIÉTÉ directement dans ce create() écraserait son nom/email
        # avec ceux du nouveau membre (vérifié empiriquement). On crée donc un contact
        # individuel dédié, enfant de la société, puis l'utilisateur pointe sur ce contact.
        new_partner = request.env["res.partner"].sudo().create({
            "name": name,
            "email": email,
            "parent_id": partner.id,
            "company_type": "person",
        })
        new_user = Users.create({
            "login": email,
            "partner_id": new_partner.id,
            "group_ids": [(6, 0, [portal_group.id])],
            "is_portal_manager": False,
        })
        try:
            new_user.with_context(create_user=1).action_reset_password()
        except Exception:
            # Échec d'envoi (serveur mail mal configuré, etc.) : on annule la création
            # plutôt que de laisser un compte fantôme sans mot de passe ni invitation,
            # et on redirige proprement au lieu de laisser remonter une page d'erreur 500.
            # res.users référence partner_id : on supprime l'utilisateur avant le contact
            # (même contrainte FK rencontrée en Phase 1a).
            new_user.unlink()
            new_partner.unlink()
            return request.redirect("/my/equipe?invite_error=mail_failed")
        return request.redirect("/my/equipe?invited=1")

    @http.route(
        "/my/equipe/<int:user_id>/retirer",
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
        csrf=True,
    )
    def portal_team_remove(self, user_id, **kw):
        partner = self._check_portal_access()
        if not partner or not request.env.user.is_portal_manager:
            return request.redirect("/my/equipe")
        # sudo() conservé : même raison que portal_team_invite (ACL write=0 pour ces
        # groupes). Barrière : target.partner_id.commercial_partner_id doit être `partner`
        # — jamais d'accès à un membre d'une autre organisation.
        Users = request.env["res.users"].sudo()
        target = Users.browse(user_id)
        if not target.exists() or target.partner_id.commercial_partner_id != partner:
            return request.redirect("/my/equipe")
        if target.id == request.env.user.id:
            return request.redirect("/my/equipe?remove_error=self")
        if target.is_portal_manager:
            remaining_managers = Users.search_count([
                ("partner_id", "child_of", partner.id),
                ("is_portal_manager", "=", True),
                ("id", "!=", target.id),
                ("active", "=", True),
            ])
            if remaining_managers == 0:
                return request.redirect("/my/equipe?remove_error=last_manager")
        # Jamais de unlink() : un res.users lié à des mandats/messages ne peut pas être
        # supprimé (contrainte Odoo déjà rencontrée), et on veut pouvoir réactiver.
        target.write({"active": False})
        return request.redirect("/my/equipe?removed=1")
