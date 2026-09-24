# -*- coding: utf-8 -*-

import json

import logging

import re



from odoo import _, api, models



_logger = logging.getLogger(__name__)



DEFAULT_PRESENTATION_PROMPT = """Tu es un coach d'onboarding pour agents call center Doorway / Intellix CRM.

Présente la plateforme à un agent qualificateur VICIdial en français (tutoiement), 200-300 mots.

Mentionne ses campagnes assignées et son pipeline CRM réel (Québec, France, B2B, etc.).

JSON : {"presentation": "html simple", "tips": ["...", "...", "..."]}"""





class DoorwayVicidialOnboardingService(models.AbstractModel):

    _name = "doorway.vicidial.onboarding.service"

    _description = "Onboarding agent call center + présentation Claude"



    @api.model

    def _parse_json_response(self, text):

        text = (text or "").strip()

        if text.startswith("```"):

            text = re.sub(r"^```(?:json)?\s*", "", text)

            text = re.sub(r"\s*```$", "", text)

        try:

            return json.loads(text)

        except json.JSONDecodeError:

            return {"presentation": text, "tips": []}



    @api.model

    def _agent_context(self):

        user = self.env.user

        agent = (

            self.env["doorway.campaign.agent.user"]

            .sudo()

            .search([("user_id", "=", user.id), ("active", "=", True)], limit=1)

        )

        Campaign = self.env["doorway.campaign"].sudo()

        assigned = Campaign.browse()

        if agent:

            assigned = Campaign.search([("human_agent_ids", "in", agent.id)])

        team = (

            agent.vicidial_crm_team_id.name

            if agent and agent.vicidial_crm_team_id

            else _("Appels — Qualification")

        )

        campaign_names = ", ".join(assigned.mapped("name")) if assigned else ""

        region_hint = _("tes marchés assignés")

        if assigned:

            pipelines = set(assigned.mapped("pipeline"))

            if pipelines == {"thermopompe"} or any(

                "rap" in (n or "").lower() for n in assigned.mapped("name")

            ):

                region_hint = _("Québec B2C")

            elif "driven" in pipelines:

                region_hint = _("B2B / Driven")

        if "Qualification France" in (team or ""):
            team = _("Appels — Qualification")
        if assigned and region_hint == _("Québec B2C"):
            team = _("Appels — Québec")
        elif assigned and region_hint == _("B2B / Driven"):
            team = _("Appels — B2B")

        return {

            "user": user,

            "agent": agent,

            "team": team,

            "campaigns": assigned,

            "campaign_names": campaign_names,

            "region_hint": region_hint,

            "vicidial_login": (agent.vicidial_user or "") if agent else "",

        }



    @api.model

    def _default_presentation_html(self):

        ctx = self._agent_context()

        name = ctx["user"].name.split()[0] if ctx["user"].name else _("toi")

        campaigns_html = ""

        if ctx["campaign_names"]:

            campaigns_html = (

                f'<p class="mb-2"><strong>Tes campagnes :</strong> '

                f'{ctx["campaign_names"]}</p>'

            )

        team_line = ctx["team"]

        return f"""

<div class="alert alert-light border mb-3">

    <p><strong>Bonjour {name} !</strong> Voici ton parcours qualificateur sur Intellix :</p>

    {campaigns_html}

    <p class="text-muted small mb-2">Équipe CRM : <strong>{team_line}</strong> · {ctx["region_hint"]}</p>

    <ul>

        <li><strong>Mon poste d'appels</strong> — tes campagnes VICIdial et la sync CRM</li>

        <li><strong>Qualification CRM</strong> — classe chaque lead (Qualifié, RDV, Rappel, Non qualifié)</li>

        <li><strong>Mon coaching Claude</strong> — scores et conseils après chaque appel</li>

        <li><strong>Mes rappels</strong> — ne rate aucune relance</li>

    </ul>

</div>

"""



    @api.model

    def get_claude_presentation_html(self):

        ctx = self._agent_context()

        fallback = self._default_presentation_html()

        svc = self.env.get("renovation.ai.service")

        if not svc or not svc._available():

            return fallback

        system = svc._get_prompt(

            "vicidial_qualifier_presentation", DEFAULT_PRESENTATION_PROMPT

        )

        user_msg = f"""Agent : {ctx['user'].name}

Login VICIdial : {ctx['vicidial_login'] or 'à configurer'}

Équipe / pipeline CRM : {ctx['team']}

Campagnes assignées : {ctx['campaign_names'] or 'à configurer'}

Marché : {ctx['region_hint']}

Rôle : qualificateur call center (appels sortants)

"""

        try:

            answer = svc._call(

                [{"role": "user", "content": user_msg}],

                system=system,

                max_tokens=900,

                purpose="vicidial_onboarding",

            )

        except Exception as exc:  # noqa: BLE001

            _logger.warning("VICIdial onboarding Claude: %s", exc)

            return fallback

        if not answer:

            return fallback

        data = self._parse_json_response(answer)

        presentation = data.get("presentation") or ""

        tips = data.get("tips") or []

        tips_html = ""

        if tips:

            items = "".join(f"<li>{tip}</li>" for tip in tips[:5])

            tips_html = f'<div class="mt-2"><strong>3 conseils pour démarrer :</strong><ul>{items}</ul></div>'

        return f"""

<div class="alert alert-success border-0 mb-3">

    <div class="small text-muted mb-1"><i class="fa fa-magic"/> Présentation personnalisée par Claude</div>

    {presentation}

    {tips_html}

</div>

"""


