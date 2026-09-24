# -*- coding: utf-8 -*-
import re

from odoo import api, fields, models


class VicidialMyCoaching(models.Model):
    _inherit = "doorway.vicidial.agent.session"

    @api.model
    def _coaching_qualification_label(self, qual):
        selection = (
            self.env["pe.coaching.call"]._fields["qualification_appel"].selection
            if "pe.coaching.call" in self.env
            else []
        )
        return dict(selection).get(qual, qual or "—")

    @api.model
    def _session_type_label(self, session_type):
        if "pe.coaching.session" not in self.env:
            return session_type or "—"
        return dict(
            self.env["pe.coaching.session"]._fields["session_type"].selection
        ).get(session_type, session_type or "—")

    @api.model
    def _score_to_100(self, score_25):
        return round((score_25 or 0) * 4)

    @api.model
    def _lead_subtitle(self, lead):
        if not lead:
            return ""
        parts = []
        if lead.type_projet:
            parts.append(
                dict(lead._fields["type_projet"].selection).get(
                    lead.type_projet, lead.type_projet
                )
            )
        if lead.city:
            parts.append(lead.city)
        return " · ".join(parts)

    @api.model
    def _parse_transcript_lines(self, transcript, agent_name="Agent"):
        if not transcript:
            return []
        lines = []
        for raw in transcript.strip().split("\n"):
            line = raw.strip()
            if not line:
                continue
            speaker = "agent"
            text = line
            match = re.match(
                r"^(?:(?:agent|employé|karine|conseiller)\s*:|"
                r"(?:prospect|client|madame|monsieur)\s*:)\s*(.*)$",
                line,
                flags=re.IGNORECASE,
            )
            if match:
                prefix = line.split(":", 1)[0].lower()
                text = line.split(":", 1)[1].strip()
                if any(
                    w in prefix
                    for w in ("prospect", "client", "madame", "monsieur")
                ):
                    speaker = "prospect"
            elif line.lower().startswith(("prospect:", "client:")):
                speaker = "prospect"
                text = line.split(":", 1)[1].strip()
            elif line.lower().startswith(("agent:", "employé:")):
                speaker = "agent"
                text = line.split(":", 1)[1].strip()
            label = "Prospect" if speaker == "prospect" else agent_name.split()[0]
            lines.append({"speaker": speaker, "label": label, "text": text})
        if not lines and transcript:
            lines.append(
                {
                    "speaker": "agent",
                    "label": agent_name.split()[0],
                    "text": transcript[:800],
                }
            )
        return lines[:12]

    @api.model
    def _parse_key_moments(self, call):
        moments = []
        if call.points_ameliorer:
            for idx, chunk in enumerate(call.points_ameliorer.split("\n")):
                text = chunk.strip(" •-\t")
                if not text:
                    continue
                moments.append(
                    {
                        "icon": "⚠️",
                        "time": "",
                        "text": text[:220],
                        "kind": "warning",
                    }
                )
                if len(moments) >= 3:
                    break
        if call.points_positifs:
            for chunk in call.points_positifs.split("\n"):
                text = chunk.strip(" •-\t")
                if not text:
                    continue
                moments.append(
                    {
                        "icon": "✅",
                        "time": "",
                        "text": text[:220],
                        "kind": "positive",
                    }
                )
                if len(moments) >= 4:
                    break
        if not moments and call.conseil_claude:
            moments.append(
                {
                    "icon": "💡",
                    "time": "",
                    "text": call.conseil_claude[:220],
                    "kind": "tip",
                }
            )
        return moments[:4]

    @api.model
    def _insights_count(self, call):
        count = 0
        if call.points_positifs:
            count += 1
        if call.points_ameliorer:
            count += 1
        if call.conseil_claude:
            count += 1
        return count

    @api.model
    def _compute_criteria_averages(self, calls):
        specs = [
            ("Accroche & introduction", "score_accroche", "#10b981"),
            ("Qualification du besoin", "score_qualification", "#6366f1"),
            ("Gestion des objections", "score_gestion_objections", "#f59e0b"),
            ("Closing & prochaine étape", "score_closing", "#f59e0b"),
        ]
        result = []
        for name, field, color in specs:
            vals = [getattr(c, field) for c in calls if getattr(c, field)]
            avg = round(sum(vals) / len(vals) * 4) if vals else 0
            result.append({"name": name, "score": avg, "color": color})
        if result:
            listen = round(
                (result[0]["score"] + result[1]["score"]) / 2
            )
            script = round(sum(r["score"] for r in result) / len(result))
            result.append(
                {
                    "name": "Écoute active",
                    "score": listen,
                    "color": "#10b981",
                }
            )
            result.append(
                {
                    "name": "Respect du script",
                    "score": script,
                    "color": "#8b5cf6",
                }
            )
        return result

    @api.model
    def _qualification_rate(self, calls):
        if not calls:
            return 0
        qualified_statuses = {"qualifie", "rdv", "b2b_valide"}
        qualified = sum(
            1 for c in calls if c.qualification_appel in qualified_statuses
        )
        return round(qualified / len(calls) * 100)

    @api.model
    def _build_weekly_insights(self, calls, sessions_data):
        strength = improve = tip = ""
        for call in calls:
            if call.points_positifs and not strength:
                strength = call.points_positifs.strip().split("\n")[0][:240]
            if call.points_ameliorer and not improve:
                improve = call.points_ameliorer.strip().split("\n")[0][:240]
            if call.conseil_claude and not tip:
                tip = call.conseil_claude.strip()[:240]
        if sessions_data and not strength:
            strength = (sessions_data[0].get("final_message") or "")[:240]
        if not strength:
            strength = (
                "Ton écoute et ta présentation sont analysées sur chaque appel "
                "enregistré — continue à consulter tes retours IA."
            )
        if not improve:
            improve = (
                "Identifie les objections récurrentes dans tes appels à réviser "
                "et entraîne-toi sur les reformulations proposées par Claude."
            )
        if not tip:
            tip = (
                "Vise des appels entre 3 et 5 minutes pour maximiser le taux "
                "de qualification sur tes campagnes actives."
            )
        return {"strength": strength, "improve": improve, "tip": tip}

    @api.model
    def _gamification_payload(self, profile, avg_score):
        if not profile:
            return {
                "level_label": "—",
                "level_num": 0,
                "score_elite": avg_score,
                "objectives": [],
            }
        objectives_data = []
        Objective = self.env.get("pe.objective")
        if Objective:
            objectives = Objective.search(
                [
                    ("profile_id", "=", profile.id),
                    ("status", "=", "active"),
                    ("contract_id", "=", False),
                ],
                order="date_deadline desc, id desc",
                limit=4,
            )
            icons = {
                "appels": "📞",
                "ia_calls": "📞",
                "ia_quality": "⭐",
                "crm_conversion": "🏆",
                "demos": "🎯",
            }
            for obj in objectives:
                current = round(obj.current_value or 0)
                target = round(obj.target_value or 0)
                pct = round(obj.achievement_rate or 0)
                badge = ""
                if pct >= 100:
                    badge = "Obtenu !"
                elif pct >= 80:
                    badge = "Bientôt !"
                elif target and current < target:
                    badge = "−%s" % max(target - current, 0)
                objectives_data.append(
                    {
                        "id": obj.id,
                        "name": obj.name,
                        "icon": icons.get(obj.objective_type, "🏆"),
                        "current": current,
                        "target": target,
                        "pct": pct,
                        "badge_label": badge,
                        "badge_style": (
                            "earned"
                            if pct >= 100
                            else ("soon" if pct >= 80 else "pending")
                        ),
                    }
                )
        level_num = profile.pe_points_total // 250 + 1 if profile else 1
        return {
            "level_label": profile.pe_level_name or ("Niveau %s" % level_num),
            "level_num": min(level_num, 10),
            "score_elite": round(profile.score_global or avg_score),
            "objectives": objectives_data,
        }

    @api.model
    def _serialize_call(self, call, employee_name):
        qual = call.qualification_appel or (
            call.lead_id.qualification_statut if call.lead_id else "non_fait"
        )
        insights = self._insights_count(call)
        needs_review = (
            not call.lu_par_employe
            or (call.score_global and call.score_global < 60)
            or bool(call.points_ameliorer)
        )
        return {
            "id": call.id,
            "date_appel": fields.Datetime.to_string(call.date_appel),
            "lead_id": call.lead_id.id if call.lead_id else False,
            "lead_name": call.lead_id.name if call.lead_id else "Prospect",
            "lead_subtitle": self._lead_subtitle(call.lead_id),
            "phone": call.numero_appele
            or (call.lead_id.phone if call.lead_id else ""),
            "duree": call.duree_affichee,
            "qualification": qual,
            "qualification_label": self._coaching_qualification_label(qual),
            "score_global": call.score_global or 0,
            "score_accroche": call.score_accroche or 0,
            "score_qualification": call.score_qualification or 0,
            "score_gestion_objections": call.score_gestion_objections or 0,
            "score_closing": call.score_closing or 0,
            "audio_url": call.audio_url or "",
            "analyse_done": call.analyse_done,
            "lu_par_employe": call.lu_par_employe,
            "points_positifs": call.points_positifs or "",
            "points_ameliorer": call.points_ameliorer or "",
            "conseil_claude": call.conseil_claude or "",
            "note_manager": call.note_manager or "",
            "transcript_excerpt": (call.transcript or "")[:500],
            "transcript_lines": self._parse_transcript_lines(
                call.transcript, employee_name
            ),
            "key_moments": self._parse_key_moments(call),
            "insights_count": insights,
            "needs_review": needs_review,
        }

    @api.model
    def get_my_coaching_data(self, date_from=None, date_to=None):
        """Coaching personnel de l'agent connecté (appels + sessions RH)."""
        user = self.env.user
        employee = self.env["doorway.vicidial.call.sync"]._resolve_employee_for_user(
            user
        )
        empty_kpis = {
            "total": 0,
            "avg_score": 0,
            "unread": 0,
            "analysed": 0,
            "qualification_rate": 0,
        }
        if not employee:
            return {
                "employee_name": user.name,
                "error": "no_employee",
                "calls": [],
                "sessions": [],
                "plans": [],
                "kpis": empty_kpis,
                "criteria_averages": [],
                "insights": self._build_weekly_insights([], []),
                "gamification": self._gamification_payload(None, 0),
            }

        kpis = dict(empty_kpis)
        calls_data = []
        call_records = self.env["pe.coaching.call"]
        Coaching = self.env.get("pe.coaching.call")
        if Coaching:
            domain = [
                ("employee_id", "=", employee.id),
                ("visible_employe", "=", True),
            ]
            if date_from:
                domain.append(("date_appel", ">=", date_from))
            if date_to:
                domain.append(("date_appel", "<=", date_to + " 23:59:59"))
            call_records = Coaching.search(domain, order="date_appel desc", limit=100)
            scores = []
            for call in call_records:
                if not call.lu_par_employe:
                    kpis["unread"] += 1
                if call.analyse_done:
                    kpis["analysed"] += 1
                if call.score_global:
                    scores.append(call.score_global)
                calls_data.append(
                    self._serialize_call(call, employee.name)
                )
            kpis["total"] = len(call_records)
            kpis["avg_score"] = (
                round(sum(scores) / len(scores)) if scores else 0
            )
            kpis["qualification_rate"] = self._qualification_rate(call_records)

        sessions_data = []
        plans_data = []
        Profile = self.env.get("pe.employee.profile")
        profile = (
            Profile.search([("employee_id", "=", employee.id)], limit=1)
            if Profile
            else Profile
        )
        if profile:
            Session = self.env.get("pe.coaching.session")
            if Session:
                sessions = Session.search(
                    [
                        ("profile_id", "=", profile.id),
                        ("status", "in", ("delivered", "acknowledged")),
                    ],
                    order="delivered_at desc, create_date desc",
                    limit=15,
                )
                for session in sessions:
                    sessions_data.append(
                        {
                            "id": session.id,
                            "date": fields.Datetime.to_string(
                                session.delivered_at or session.create_date
                            ),
                            "session_type": session.session_type,
                            "session_type_label": self._session_type_label(
                                session.session_type
                            ),
                            "final_message": session.final_message
                            or session.claude_draft
                            or "",
                            "action_plan": session.claude_action_plan or "",
                            "status": session.status,
                        }
                    )
            Plan = self.env.get("pe.coaching.plan")
            if Plan:
                plans = Plan.search(
                    [
                        ("profile_id", "=", profile.id),
                        ("status", "in", ("active", "completed")),
                    ],
                    order="create_date desc",
                    limit=10,
                )
                for plan in plans:
                    plans_data.append(
                        {
                            "id": plan.id,
                            "name": plan.name,
                            "status": plan.status,
                            "objective": plan.claude_success_criteria or "",
                            "progress_pct": round(plan.completion_rate or 0),
                        }
                    )

        return {
            "employee_name": employee.name,
            "calls": calls_data,
            "sessions": sessions_data,
            "plans": plans_data,
            "kpis": kpis,
            "criteria_averages": self._compute_criteria_averages(call_records),
            "insights": self._build_weekly_insights(call_records, sessions_data),
            "gamification": self._gamification_payload(
                profile, kpis["avg_score"]
            ),
        }

    @api.model
    def get_coaching_summary(self):
        """Résumé léger pour le poste agent."""
        data = self.get_my_coaching_data(
            date_from=fields.Date.to_string(
                fields.Date.subtract(fields.Date.today(), days=30)
            )
        )
        last = data["calls"][0] if data.get("calls") else {}
        return {
            "unread": data["kpis"].get("unread", 0),
            "avg_score": data["kpis"].get("avg_score", 0),
            "total": data["kpis"].get("total", 0),
            "last_conseil": (last.get("conseil_claude") or "")[:180],
            "last_points": (last.get("points_ameliorer") or "")[:180],
        }

    @api.model
    def mark_coaching_call_read(self, call_id):
        Coaching = self.env.get("pe.coaching.call")
        if not Coaching:
            return {"status": "error"}
        call = Coaching.browse(int(call_id))
        if not call.exists():
            return {"status": "error"}
        employee = self.env[
            "doorway.vicidial.call.sync"
        ]._resolve_employee_for_user(self.env.user)
        if not employee or call.employee_id != employee:
            return {"status": "forbidden"}
        call.action_marquer_lu()
        return {"status": "ok"}
