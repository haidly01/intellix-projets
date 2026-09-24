# -*- coding: utf-8 -*-
import json
import logging
from datetime import datetime, time
from zoneinfo import ZoneInfo

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class AgentTestCall(models.Model):
    _name = "doorway.agent.test.call"
    _description = "Appel test agent IA"
    _order = "create_date desc"

    agent_id = fields.Many2one(
        "doorway.agent.profile",
        string="Agent",
        required=True,
        ondelete="cascade",
        index=True,
    )
    call_mode = fields.Selection(
        [
            ("phone", "Appel téléphonique"),
            ("browser_mic", "Micro navigateur (WebRTC)"),
        ],
        string="Mode",
        required=True,
        default="phone",
    )
    phone_number = fields.Char(string="Numéro appelé")
    call_volet = fields.Selection(
        [
            ("reception", "Réception"),
            ("qualification", "Lead qualification"),
            ("cold_call", "Appel à froid"),
        ],
        string="Volet",
    )
    external_call_id = fields.Char(string="ID appel (provider)", index=True)
    state = fields.Selection(
        [
            ("pending", "En attente"),
            ("in_progress", "En cours"),
            ("done", "Terminé"),
            ("failed", "Échoué"),
        ],
        string="Statut",
        default="pending",
        index=True,
    )
    duration_seconds = fields.Integer(string="Durée (sec)")
    recording_url = fields.Char(string="URL enregistrement")
    transcript = fields.Text(string="Transcription complète")
    score_fluidite = fields.Float(string="Fluidité /20")
    score_pertinence = fields.Float(string="Pertinence /20")
    score_conversion = fields.Float(string="Conversion /20")
    score_tone = fields.Float(string="Ton /20")
    score_global = fields.Float(
        string="Score global /100",
        compute="_compute_global",
        store=True,
    )
    analyse_ia = fields.Text(string="Analyse Claude")
    forces = fields.Text(string="Points forts")
    faiblesses = fields.Text(string="Points faibles")
    recommandations = fields.Text(string="Recommandations")
    tested_by = fields.Many2one(
        "res.users",
        string="Testé par",
        default=lambda self: self.env.uid,
    )
    scenario_hint = fields.Text(string="Scénario test")
    test_send_email = fields.Boolean(string="Tester envoi e-mail")
    test_send_sms = fields.Boolean(string="Tester envoi SMS")
    test_availability_check = fields.Boolean(string="Tester disponibilité horaire")
    test_human_transfer = fields.Boolean(string="Tester transfert humain")
    expected_action_result = fields.Text(string="Résultat attendu")
    action_result_notes = fields.Text(string="Résultat obtenu / notes")
    user_rating = fields.Selection(
        [
            ("1", "1"),
            ("2", "2"),
            ("3", "3"),
            ("4", "4"),
            ("5", "5"),
        ],
        string="Note utilisateur",
    )
    user_feedback_comment = fields.Text(string="Commentaire utilisateur")
    feedback_ids = fields.One2many(
        "doorway.agent.feedback",
        "test_call_id",
        string="Retours",
    )

    def _is_energie_test_agent(self, agent=None):
        agent = agent or self.agent_id
        name = (agent.name or "").lower()
        return bool(
            agent.energie_agent_role
            or any(
                hint in name
                for hint in (
                    "thermo",
                    "énergie",
                    "energie",
                    "isolation",
                    "portes",
                    "fenêtres",
                    "fenetres",
                    "ici therm",
                )
            )
        )

    def _energie_lead_site_for_test(self, agent=None):
        agent = agent or self.agent_id
        name = (agent.name or "").lower()
        if "isolation" in name:
            return "isolationqc"
        if "porte" in name or "fenêtre" in name or "fenetre" in name:
            return "portesetfenetresqc"
        return "icithermopompe"

    def _elevenlabs_dynamic_variables(self):
        """Variables ConvAI pour tests Maison Recherchée / qualification."""
        self.ensure_one()
        agent = self.agent_id
        if agent.haidly_agent_role:
            return {
                "lead_name": "Jean Test Odoo",
                "project_type": "cuisine",
                "city": "Longueuil",
                "budget_range": "25_50k",
                "property_type": "maison",
                "lead_id_odoo": "TEST-%s" % (self.id or "wizard"),
            }
        if self._is_energie_test_agent(agent):
            return {
                "lead_name": "Jean Test",
                "lead_site": self._energie_lead_site_for_test(agent),
                "lead_city": "Québec",
                "current_heating": "mazout",
                "project_type": "thermopompe",
                "lead_id_odoo": "TEST-%s" % (self.id or "wizard"),
            }
        if agent.immo_agent_role == "j0_qualification" or self.call_volet == "qualification":
            return {
                "lead_name": "Jean Test Odoo",
                "property_address": "",
                "selling_timeline": "",
                "lead_id_odoo": "TEST-%s" % (self.id or "wizard"),
            }
        return {}

    def _linked_script_profile(self, agent=None):
        """Profil Odoo source du script si l'agent testé n'a pas de prompt."""
        agent = agent or self.agent_id
        return agent._linked_script_profile()

    def _resolve_web_test_script_profile(self, agent=None):
        """Profil portant le script effectif (agent testé ou profil lié J+0)."""
        agent = agent or self.agent_id
        own = (agent.system_prompt or "").strip()
        if own:
            return agent
        linked = self._linked_script_profile(agent)
        if linked != agent and (linked.system_prompt or "").strip():
            return linked
        return agent

    def _resolve_web_test_first_message(self):
        """Premier message ConvAI — extrait du script effectif (agent ou profil lié)."""
        self.ensure_one()
        return self._resolve_web_test_script_profile().get_web_test_first_message()

    def _resolve_web_test_script(self, elevenlabs_agent_id=None):
        """Script effectif + source pour le test web."""
        self.ensure_one()
        agent = self.agent_id
        parts = []
        source = "odoo_agent"
        script_profile = agent

        prompt = (agent.system_prompt or "").strip()
        if prompt:
            parts.append(agent._runtime_system_prompt())
        else:
            linked = self._linked_script_profile(agent)
            linked_prompt = (linked.system_prompt or "").strip()
            if linked_prompt and linked != agent:
                parts.append(linked._runtime_system_prompt())
                source = "odoo_linked"
                script_profile = linked
            elif elevenlabs_agent_id:
                from odoo.addons.doorway_agents_dashboard.services.elevenlabs_client import (
                    ElevenLabsClient,
                )

                bundle = ElevenLabsClient(self.env).fetch_agent_prompt_bundle(
                    elevenlabs_agent_id
                )
                el_prompt = (bundle.get("prompt") or "").strip()
                if el_prompt:
                    parts.append(el_prompt)
                    source = "elevenlabs_default"

        volet_code = agent._resolve_volet(self.call_volet or agent.default_volet)
        volet = agent.volet_ids.filtered(lambda v: v.code == volet_code)[:1]
        if not volet and script_profile != agent:
            volet = script_profile.volet_ids.filtered(lambda v: v.code == volet_code)[:1]
        skip_volet_hint = bool(
            script_profile.immo_agent_role == "j0_qualification"
            or script_profile.haidly_agent_role == "j0_qualification"
            or getattr(script_profile, "energie_agent_role", None) == "j0_qualification"
            or (
                (script_profile.system_prompt or "").strip()
                and "QUESTIONS (ordre" in (parts[0] if parts else "")
            )
        )
        if (
            volet
            and (volet.prompt_hint or "").strip()
            and not skip_volet_hint
        ):
            parts.append(
                _("Contexte volet (%(code)s): %(hint)s")
                % {"code": volet_code, "hint": volet.prompt_hint.strip()}
            )
        if (self.scenario_hint or "").strip():
            parts.append(
                _("Scénario de test: %(hint)s") % {"hint": self.scenario_hint.strip()}
            )

        full_prompt = "\n\n".join(parts).strip()
        first_message = script_profile.get_web_test_first_message()
        if not first_message and source == "elevenlabs_default" and elevenlabs_agent_id:
            from odoo.addons.doorway_agents_dashboard.services.elevenlabs_client import (
                ElevenLabsClient,
            )

            bundle = ElevenLabsClient(self.env).fetch_agent_prompt_bundle(
                elevenlabs_agent_id
            )
            first_message = (bundle.get("first_message") or "").strip()

        source_labels = {
            "odoo_agent": _("Prompt Odoo — %s") % agent.name,
            "odoo_linked": _("Script lié — %s (éditez le prompt sur %s pour personnaliser)")
            % (script_profile.name, agent.name),
            "elevenlabs_default": _("Script ElevenLabs par défaut (agent %s)")
            % (elevenlabs_agent_id or "?"),
        }
        return full_prompt, source, source_labels.get(source, source), script_profile

    def _get_effective_script_prompt(self, elevenlabs_agent_id=None):
        prompt, _source, _label, _profile = self._resolve_web_test_script(
            elevenlabs_agent_id=elevenlabs_agent_id
        )
        return prompt

    @api.model
    def web_test_copy_script_to_agent(self, test_call_id):
        """Copie le script lié (ex. Énergie Pro) sur l'agent testé."""
        test_call = self.browse(int(test_call_id)).exists()
        if not test_call:
            return {"ok": False, "error": _("Appel test introuvable.")}
        _prompt, _source, _label, linked = test_call._resolve_web_test_script()
        if linked == test_call.agent_id:
            return {
                "ok": False,
                "error": _("Cet agent a déjà son propre script."),
            }
        body = (linked.system_prompt or "").strip()
        if not body:
            return {"ok": False, "error": _("Script source vide.")}
        test_call.agent_id.write({"system_prompt": body})
        return {
            "ok": True,
            "message": _("Script copié depuis %s vers %s.")
            % (linked.name, test_call.agent_id.name),
        }

    @api.model
    def _ensure_call_window(self):
        """Bloque les appels hors plage Canada (America/Toronto)."""
        tz = ZoneInfo("America/Toronto")
        now_local = datetime.now(tz)
        start = time(9, 30)
        end = time(20, 30)
        if not (start <= now_local.time() <= end):
            raise UserError(
                _(
                    "Appels autorisés uniquement entre 09:30 et 20:30 "
                    "(fuseau America/Toronto). Heure locale actuelle: %s."
                )
                % now_local.strftime("%H:%M")
            )

    @api.constrains("call_mode", "phone_number")
    def _check_phone_for_call_mode(self):
        for rec in self:
            if rec.call_mode == "phone" and not (rec.phone_number or "").strip():
                raise ValidationError(
                    _("Le numéro de téléphone est requis pour un appel téléphonique.")
                )

    @api.depends("score_fluidite", "score_pertinence", "score_conversion", "score_tone")
    def _compute_global(self):
        for rec in self:
            rec.score_global = (
                rec.score_fluidite
                + rec.score_pertinence
                + rec.score_conversion
                + rec.score_tone
            )

    def action_launch_test_call(self):
        for rec in self:
            if rec.state not in ("pending", "failed"):
                continue
            rec._launch_provider_call()
        return True

    def _elevenlabs_web_test_candidates(self, agent):
        """IDs ElevenLabs à tenter pour le test web (agent n8n souvent obsolète)."""
        seen = set()
        candidates = []

        def _add(agent_id):
            agent_id = (agent_id or "").strip()
            if not agent_id or agent_id in seen:
                return
            if agent_id.startswith("ELEVENLABS_") or agent_id in (
                "energie_pro",
                "maison_recherchee",
            ):
                return
            seen.add(agent_id)
            candidates.append(agent_id)

        _add(agent.external_agent_id)
        icp = self.env["ir.config_parameter"].sudo()
        name = (agent.name or "").lower()
        pipeline = agent.pipeline or ""

        energie_hints = (
            agent.energie_agent_role
            or pipeline == "renovation"
            or any(
                hint in name
                for hint in (
                    "thermo",
                    "énergie",
                    "energie",
                    "isolation",
                    "ici therm",
                    "portes",
                    "fenêtres",
                    "fenetres",
                )
            )
        )
        if energie_hints:
            _add(icp.get_param("doorway_agents_dashboard.elevenlabs_agent_id_energie"))
            energie = self.env.ref(
                "doorway_agents_dashboard.agent_energie_pro",
                raise_if_not_found=False,
            )
            if energie:
                _add(energie.external_agent_id)

        immo_hints = (
            agent.immo_agent_role
            or pipeline == "immobilier"
            or any(hint in name for hint in ("sophie", "immo", "maison"))
        )
        if immo_hints:
            _add(icp.get_param("doorway_agents_dashboard.elevenlabs_agent_id_immo"))

        haidly_hints = (
            agent.haidly_agent_role
            or any(hint in name for hint in ("haidly", "soumission"))
        )
        if haidly_hints:
            _add(icp.get_param("doorway_agents_dashboard.elevenlabs_agent_id_haidly"))

        siblings = self.env["doorway.agent.profile"].search(
            [
                ("provider", "=", "elevenlabs"),
                ("pipeline", "=", pipeline),
                ("external_agent_id", "!=", False),
            ],
            limit=5,
        )
        for sibling in siblings:
            _add(sibling.external_agent_id)
        return candidates

    def _web_test_el_language(self, agent):
        return {
            "fr": "fr",
            "en": "en",
            "es": "es",
            "bilingual": "en",
        }.get(agent.language or "fr", "fr")

    def _web_test_elevenlabs_session(
        self,
        test_call,
        fallback=False,
        fallback_reason="",
        script_prompt=None,
        first_message=None,
    ):
        """Token / signed URL ElevenLabs pour test navigateur."""
        from odoo.addons.doorway_agents_dashboard.services.elevenlabs_client import (
            ElevenLabsClient,
        )

        client = ElevenLabsClient(self.env)
        dynamic_variables = test_call._elevenlabs_dynamic_variables()
        el_lang = self._web_test_el_language(test_call.agent_id)
        last_error = ""
        for agent_id in self._elevenlabs_web_test_candidates(test_call.agent_id):
            client.enable_web_test_overrides(agent_id)
            client.patch_web_test_turn_timeouts(agent_id)
            if script_prompt:
                client.force_web_test_agent_config(
                    agent_id,
                    script_prompt,
                    first_message=first_message,
                    language=el_lang,
                )
            token_data = client.get_conversation_token(
                agent_id,
                dynamic_variables=dynamic_variables,
            )
            if token_data.get("ok"):
                return {
                    "ok": True,
                    "stack": "elevenlabs_fallback" if fallback else "elevenlabs_direct",
                    "conversation_token": token_data.get("conversation_token") or "",
                    "signed_url": token_data.get("signed_url") or "",
                    "fallback_reason": fallback_reason or "",
                    "elevenlabs_agent_id": agent_id,
                }
            last_error = token_data.get("message") or last_error
        return {
            "ok": False,
            "message": last_error
            or _("Token conversation ElevenLabs indisponible."),
        }

    def _web_test_prepare_error(self, message):
        return {"ok": False, "error": message}

    def _web_test_metadata_payload(
        self,
        test_call,
        script_prompt,
        script_source,
        script_label,
        script_profile,
        first_message,
        stack=None,
        fallback_reason="",
    ):
        agent = test_call.agent_id
        return {
            "ok": True,
            "test_call_id": test_call.id,
            "agent_id": agent.id,
            "agent_name": agent.name,
            "provider": agent.provider,
            "stack": stack or agent.provider,
            "scenario_hint": test_call.scenario_hint or "",
            "call_volet": test_call.call_volet or "",
            "fallback_reason": fallback_reason or "",
            "dynamic_variables": test_call._elevenlabs_dynamic_variables(),
            "script_source": script_source,
            "script_label": script_label,
            "script_profile_name": script_profile.name,
            "script_preview": (script_prompt or "")[:1200],
            "script_has_improvements": "MISSION:" in (script_prompt or "")
            and "RÈGLE ADRESSE" in (script_prompt or ""),
            "script_is_linked": script_source == "odoo_linked",
            "first_message_preview": (first_message or "")[:200],
        }

    @api.model
    def web_test_preview(self, test_call_id):
        """Aperçu rapide sans appels ElevenLabs (ouverture écran test web)."""
        test_call = self.browse(int(test_call_id)).exists()
        if not test_call:
            return self._web_test_prepare_error(_("Appel test introuvable."))
        agent = test_call.agent_id
        if not (test_call._get_effective_script_prompt() or "").strip():
            return self._web_test_prepare_error(_("Prompt système vide sur cet agent."))
        script_prompt, script_source, script_label, script_profile = (
            test_call._resolve_web_test_script()
        )
        first_message = test_call._resolve_web_test_first_message()
        stack = (
            "elevenlabs_direct"
            if agent.provider == "elevenlabs"
            else agent.provider
        )
        payload = self._web_test_metadata_payload(
            test_call,
            script_prompt,
            script_source,
            script_label,
            script_profile,
            first_message,
            stack=stack,
        )
        payload["preview_only"] = True
        return payload

    @api.model
    def web_test_prepare(self, test_call_id):
        """Prépare un test web — stack n8n (prod) ou ElevenLabs direct / secours."""
        test_call = self.browse(int(test_call_id)).exists()
        if not test_call:
            return self._web_test_prepare_error(_("Appel test introuvable."))
        agent = test_call.agent_id
        effective_prompt = test_call._get_effective_script_prompt()
        if not (effective_prompt or "").strip():
            return self._web_test_prepare_error(_("Prompt système vide sur cet agent."))

        script_profile = test_call._resolve_web_test_script_profile()
        script_prompt, script_source, script_label, script_profile = (
            test_call._resolve_web_test_script()
        )
        first_message = test_call._resolve_web_test_first_message()
        el_lang = test_call._web_test_el_language(agent)

        if agent.provider != "elevenlabs":
            sync = script_profile.sync_prompt_to_elevenlabs()
            if not sync.get("ok"):
                _logger.warning(
                    "Sync prompt ElevenLabs avant test web (agent %s): %s",
                    agent.id,
                    sync.get("message"),
                )

        session = None
        n8n_error = ""
        if agent.provider in ("n8n", "retell"):
            from odoo.addons.doorway_agents_dashboard.services.n8n_client import (
                N8NClient,
            )

            session = N8NClient(self.env).start_web_test(test_call)
            if not session.get("ok"):
                n8n_error = session.get("message") or _(
                    "Webhook n8n start-web-test indisponible."
                )
                _logger.warning(
                    "Test web n8n indisponible (agent %s): %s",
                    agent.id,
                    n8n_error,
                )
                session = test_call._web_test_elevenlabs_session(
                    test_call,
                    fallback=True,
                    fallback_reason=n8n_error,
                    script_prompt=script_prompt,
                    first_message=first_message,
                )
        elif agent.provider == "elevenlabs":
            session = test_call._web_test_elevenlabs_session(
                test_call,
                script_prompt=script_prompt,
                first_message=first_message,
            )
        else:
            return self._web_test_prepare_error(
                _("Fournisseur non supporté pour le test web.")
            )

        if not session.get("ok"):
            parts = [session.get("message") or _("Session web indisponible.")]
            if n8n_error:
                parts.append(_("n8n : %s") % n8n_error)
            parts.append(
                _(
                    "Déployez le workflow n8n start-web-test ou vérifiez "
                    "que l'agent ElevenLabs existe (external_agent_id)."
                )
            )
            return self._web_test_prepare_error("\n".join(parts))

        if not (
            session.get("conversation_token")
            or session.get("signed_url")
            or session.get("websocket_url")
            or session.get("session_url")
        ):
            return self._web_test_prepare_error(
                _(
                    "Aucune session web utilisable (token, signed_url ou websocket). "
                    "Vérifiez le workflow n8n start-web-test."
                )
            )

        el_agent_id = session.get("elevenlabs_agent_id") or ""
        if el_agent_id:
            script_prompt, script_source, script_label, script_profile = (
                test_call._resolve_web_test_script(elevenlabs_agent_id=el_agent_id)
            )
            first_message = test_call._resolve_web_test_first_message()
        payload_token = session.get("conversation_token") or ""
        payload_signed = session.get("signed_url") or ""
        conversation_overrides = {}
        if el_agent_id and (script_prompt or first_message):
            from odoo.addons.doorway_agents_dashboard.services.elevenlabs_client import (
                ElevenLabsClient,
            )

            el_client = ElevenLabsClient(self.env)
            el_client.enable_web_test_overrides(el_agent_id)
            el_client.patch_web_test_turn_timeouts(el_agent_id)
            el_client.force_web_test_agent_config(
                el_agent_id,
                script_prompt,
                first_message=first_message,
                language=el_lang,
            )
            token_refresh = el_client.get_conversation_token(
                el_agent_id,
                dynamic_variables=test_call._elevenlabs_dynamic_variables(),
            )
            if token_refresh.get("ok"):
                payload_token = token_refresh.get("conversation_token") or ""
                payload_signed = token_refresh.get("signed_url") or ""
            else:
                payload_token = session.get("conversation_token") or ""
                payload_signed = session.get("signed_url") or ""
                _logger.warning(
                    "Refresh token web test (agent %s): %s",
                    el_agent_id,
                    token_refresh.get("message"),
                )
            agent_override = {"language": el_lang}
            if script_prompt:
                agent_override["prompt"] = {
                    "prompt": script_prompt,
                    "max_tokens": 500,
                    "temperature": 0.35,
                }
            if first_message:
                agent_override["firstMessage"] = first_message
            conversation_overrides = {"agent": agent_override}

        test_call.write(
            {
                "state": "in_progress",
                "external_call_id": session.get("external_call_id") or "",
            }
        )
        payload = self._web_test_metadata_payload(
            test_call,
            script_prompt,
            script_source,
            script_label,
            script_profile,
            first_message,
            stack=session.get("stack") or agent.provider,
            fallback_reason=session.get("fallback_reason") or "",
        )
        payload.update(
            {
                "preview_only": False,
                "conversation_token": payload_token,
                "signed_url": payload_signed,
                "websocket_url": session.get("websocket_url") or "",
                "session_url": session.get("session_url") or "",
                "elevenlabs_agent_id": el_agent_id,
                "conversation_overrides": conversation_overrides,
            }
        )
        return payload

    @api.model
    def web_test_finalize(self, test_call_id, transcript_lines=None, duration_seconds=0, external_conversation_id=""):
        """Finalise un test web : transcription, analyse IA, stats agent."""
        test_call = self.browse(int(test_call_id)).exists()
        if not test_call:
            raise UserError(_("Appel test introuvable."))
        lines = transcript_lines or []
        transcript = ""
        if isinstance(lines, list):
            parts = []
            for line in lines:
                if isinstance(line, dict):
                    role = line.get("role") or line.get("source") or "?"
                    text = line.get("text") or line.get("message") or ""
                    parts.append("%s: %s" % (role, text))
                else:
                    parts.append(str(line))
            transcript = "\n".join(parts).strip()
        if not transcript and external_conversation_id:
            agent = test_call.agent_id
            if agent.provider in ("n8n", "retell"):
                from odoo.addons.doorway_agents_dashboard.services.n8n_client import (
                    N8NClient,
                )

                call_data = N8NClient(self.env).fetch_call(external_conversation_id)
                transcript = N8NClient.extract_transcript(call_data)
            elif agent.provider == "elevenlabs":
                from odoo.addons.doorway_agents_dashboard.services.elevenlabs_client import (
                    ElevenLabsClient,
                )

                transcript = ElevenLabsClient(self.env).fetch_conversation_transcript(
                    external_conversation_id
                )
        vals = {
            "state": "done",
            "duration_seconds": int(duration_seconds or 0),
        }
        if transcript:
            vals["transcript"] = transcript
        if external_conversation_id:
            vals["external_call_id"] = external_conversation_id
        test_call.write(vals)
        if test_call.transcript and not test_call.analyse_ia:
            try:
                from odoo.addons.doorway_agents_dashboard.services.call_analyzer import (
                    CallAnalyzer,
                )

                result = CallAnalyzer(self.env).analyze_test_call(test_call)
                if result.get("ok"):
                    test_call.write(test_call._analysis_vals(result))
            except Exception as exc:  # noqa: BLE001
                _logger.warning("Auto-analyse web test %s: %s", test_call.id, exc)
        if test_call.agent_id:
            test_call.agent_id._update_test_stats(test_call.score_global or 0.0)
        return {
            "status": "ok",
            "test_call_id": test_call.id,
            "score_global": test_call.score_global or 0,
            "analyse_ia": test_call.analyse_ia or "",
            "forces": test_call.forces or "",
            "faiblesses": test_call.faiblesses or "",
            "recommandations": test_call.recommandations or "",
        }

    @api.model
    def web_test_run_ai_assist(self, test_call_id, feedback_id=None):
        """Assistance IA : amélioration agent à partir du test + retour utilisateur."""
        test_call = self.browse(int(test_call_id)).exists()
        if not test_call:
            raise UserError(_("Appel test introuvable."))
        Feedback = self.env["doorway.agent.feedback"]
        feedback = Feedback.browse(int(feedback_id)).exists() if feedback_id else False
        if not feedback:
            feedback = Feedback.search(
                [("test_call_id", "=", test_call.id)],
                order="create_date desc",
                limit=1,
            )
        if feedback:
            result = feedback._run_ai_assist()
        else:
            from odoo.addons.doorway_agents_dashboard.services.claude_service import (
                ClaudeService,
            )

            result = ClaudeService(self.env).analyze_with_user_feedback(
                transcript=test_call.transcript or "",
                user_comment=test_call.user_feedback_comment or test_call.scenario_hint or "",
                rating=int(test_call.user_rating or 3),
                issue_tags=[],
                current_prompt=test_call._get_effective_script_prompt(),
            )
            test_call.agent_id.write(
                {
                    "performance_weaknesses_json": json.dumps(
                        result.get("weaknesses") or [], ensure_ascii=False
                    ),
                    "performance_suggestions_json": json.dumps(
                        result.get("prompt_suggestions") or [], ensure_ascii=False
                    ),
                    "performance_analysis_at": fields.Datetime.now(),
                }
            )
        return {
            "status": "ok",
            "weaknesses": result.get("weaknesses") or [],
            "prompt_suggestions": result.get("prompt_suggestions") or [],
            "analysis": result.get("analysis") or "",
            "feedback_id": feedback.id if feedback else False,
        }

    def _launch_provider_call(self):
        self.ensure_one()
        if self.call_mode == "browser_mic":
            raise UserError(
                _("Utilisez l'action « Test web » pour lancer un appel navigateur.")
            )
        self._ensure_call_window()

        provider = self.agent_id.provider
        if provider == "elevenlabs":
            from odoo.addons.doorway_agents_dashboard.services.elevenlabs_client import (
                ElevenLabsClient,
            )

            result = ElevenLabsClient(self.env).start_test_call(self)
        elif provider in ("n8n", "retell"):
            agent = self.agent_id
            if agent.provider == "n8n" and agent.pipeline == "renovation":
                from odoo.addons.doorway_agents_dashboard.services.telephony_adapter_service import (
                    TelephonyAdapterService,
                )

                result = TelephonyAdapterService(self.env).initiate_outbound_call(
                    self.phone_number,
                    nombre=agent.name,
                    campaign=agent.external_agent_id,
                )
                result = {
                    "ok": result.get("ok"),
                    "state": "in_progress",
                    "external_call_id": "",
                    "message": result.get("raw", ""),
                }
            else:
                from odoo.addons.doorway_agents_dashboard.services.n8n_client import (
                    N8NClient,
                )

                result = N8NClient(self.env).start_test_call(self)
        else:
            raise UserError(_("Fournisseur non supporté."))

        if not result.get("ok"):
            self.write({"state": "failed"})
            raise UserError(result.get("message") or _("Échec appel test."))

        self.write(
            {
                "state": result.get("state") or "in_progress",
                "external_call_id": result.get("external_call_id"),
            }
        )

    def action_analyze(self):
        from odoo.addons.doorway_agents_dashboard.services.call_analyzer import (
            CallAnalyzer,
        )

        for rec in self:
            if not rec.transcript:
                raise UserError(_("Transcription vide — attendez la fin de l'appel."))
            result = CallAnalyzer(self.env).analyze_test_call(rec)
            if result.get("ok"):
                rec.write(rec._analysis_vals(result))
            else:
                raise UserError(result.get("message") or _("Analyse impossible."))
        return True

    @api.model
    def _analysis_vals(self, result):
        forces = result.get("forces") or ""
        if isinstance(forces, list):
            forces = "\n".join("- %s" % i for i in forces)
        faiblesses = result.get("faiblesses") or ""
        if isinstance(faiblesses, list):
            faiblesses = "\n".join("- %s" % i for i in faiblesses)
        recommandations = result.get("recommandations") or ""
        if isinstance(recommandations, list):
            recommandations = "\n".join("- %s" % i for i in recommandations)
        return {
            "analyse_ia": result.get("analyse_ia") or "",
            "forces": forces,
            "faiblesses": faiblesses,
            "recommandations": recommandations,
            "score_fluidite": result.get("score_fluidite") or 0.0,
            "score_pertinence": result.get("score_pertinence") or 0.0,
            "score_conversion": result.get("score_conversion") or 0.0,
            "score_tone": result.get("score_tone") or 0.0,
        }

    def finalize_from_webhook(self, transcript="", status="completed", duration=0):
        self.ensure_one()
        is_done = status in ("completed", "ended", "done")
        vals = {
            "state": "done" if is_done else "failed",
        }
        if transcript:
            vals["transcript"] = transcript
        if duration:
            vals["duration_seconds"] = duration
        self.write(vals)
        if self.state == "done" and self.transcript and not self.analyse_ia:
            try:
                from odoo.addons.doorway_agents_dashboard.services.call_analyzer import (
                    CallAnalyzer,
                )

                result = CallAnalyzer(self.env).analyze_test_call(self)
                if result.get("ok"):
                    self.write(self._analysis_vals(result))
            except Exception as exc:  # noqa: BLE001
                _logger.warning("Auto-analyse test call %s: %s", self.id, exc)
        if self.state == "done" and self.agent_id:
            self.agent_id._update_test_stats(self.score_global or 0.0)
        if self.state == "done":
            self._export_to_google_sheet()

    def _export_to_google_sheet(self):
        self.ensure_one()
        try:
            from odoo.addons.doorway_agents_dashboard.services.google_sheets_service import (
                GoogleSheetsService,
            )

            GoogleSheetsService(self.env).export_test_call(self)
        except Exception as exc:  # noqa: BLE001
            _logger.warning("Export Google Sheet test call %s: %s", self.id, exc)

    @api.model
    def web_test_go_live(self, test_call_id):
        """Sortie phase test : sync prompt, campagne VICIdial, démarrage."""
        test_call = self.browse(test_call_id).exists()
        if not test_call or not test_call.agent_id:
            raise UserError(_("Appel test introuvable."))
        agent = test_call.agent_id
        if not hasattr(agent, "action_go_live_from_web_test"):
            raise UserError(
                _(
                    "Module Campagnes VICIdial requis. "
                    "Installez doorway_vicidial_campaigns."
                )
            )
        return agent.action_go_live_from_web_test()

    @api.model
    def find_by_external_id(self, provider, external_call_id):
        if not external_call_id:
            return self.browse()
        return self.search(
            [
                ("external_call_id", "=", external_call_id),
                ("agent_id.provider", "=", provider),
            ],
            limit=1,
        )
