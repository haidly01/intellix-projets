# -*- coding: utf-8 -*-
"""Provisionnement d'un utilisateur Demo Call Center (modèle Abdallah)."""
import logging
import secrets
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from odoo import _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

PILOT_LOGIN = "Echcherkia65@gmail.com"
PILOT_NAME = "Abdallah Echcherki"
PILOT_COMPANY = "Demo CC — Abdallah Echcherki"
DEMO_CREDIT_EUR = 48.0
DEMO_FLAT_RATE = 0.22
VICIDIAL_CAMPAIGN = "ABD_DEMO"
DEMO_TRUNK_NAME = "TrustSIP"
DEMO_LIST_NAME = "ABD_DEMO"
VICIDIAL_TEMPLATE = "DW_ESREN"
SOFIA_EXTERNAL_ID = "sofia-es-avatrade-2026"


class DemoCallCenterProvisioning:
    def __init__(self, env):
        self.env = env

    def _demo_group(self):
        return self.env.ref("doorway_demo_call_center.group_demo_call_center")

    def _qualifier_group(self):
        return self.env.ref("doorway_vicidial_campaigns.group_vicidial_qualifier")

    def provision_demo_user(
        self,
        name,
        login,
        company_name=None,
        credit_eur=DEMO_CREDIT_EUR,
        flat_rate_eur=DEMO_FLAT_RATE,
        password=None,
        vicidial_campaign_id=VICIDIAL_CAMPAIGN,
        sofia_external_id=SOFIA_EXTERNAL_ID,
    ):
        """Crée société, tenant, utilisateur, agent Sofia, campagne et accès VICIdial."""
        login = (login or "").strip().lower()
        company_name = company_name or ("Demo CC — %s" % name)
        password = password or secrets.token_urlsafe(10)
        demo_group = self._demo_group()

        company = self.env["res.company"].sudo().search(
            [("name", "=", company_name)], limit=1
        )
        if not company:
            company = self.env["res.company"].sudo().create({"name": company_name})
        tenant = self._ensure_demo_tenant(company, login, credit_eur, flat_rate_eur)

        user = self.env["res.users"].sudo().search([("login", "=", login)], limit=1)
        group_ids = [
            self.env.ref("base.group_user").id,
            demo_group.id,
            self._qualifier_group().id,
        ]
        tester = self.env.ref(
            "doorway_agents_dashboard.group_doorway_agent_tester",
            raise_if_not_found=False,
        )
        if tester:
            group_ids.append(tester.id)
        user_vals = {
            "name": name,
            "login": login,
            "email": login,
            "company_id": company.id,
            "company_ids": [(6, 0, [company.id])],
            "group_ids": [(6, 0, group_ids)],
            "password": password,
        }
        if user:
            user.write(
                {
                    "name": name,
                    "company_id": company.id,
                    "company_ids": [(6, 0, [company.id])],
                    "groups_id": [(4, demo_group.id)],
                    "password": password,
                }
            )
        else:
            user = self.env["res.users"].sudo().create(user_vals)

        agent_profile = self._clone_sofia_agent(company, sofia_external_id, name)
        user.write({"doorway_agent_profile_id": agent_profile.id})

        sip_trunk = self._ensure_demo_sip_trunk(company)
        self._setup_demo_vicidial(
            vicidial_campaign_id,
            DEMO_TRUNK_NAME,
            DEMO_LIST_NAME,
            "Demo Espagne — %s" % name.split()[0],
        )

        campaign = self._ensure_demo_campaign(
            company, agent_profile, vicidial_campaign_id, name, sip_trunk
        )
        vicidial_user = self._ensure_vicidial_agent(user, name, vicidial_campaign_id)
        if vicidial_user:
            campaign.write({"human_agent_ids": [(4, vicidial_user.id)]})

        _logger.info(
            "Demo CC provisionné : %s (%s) — société %s — campagne %s — solde %.2f €",
            name,
            login,
            company_name,
            campaign.name,
            tenant.credit_balance,
        )
        result = {
            "user_id": user.id,
            "company_id": company.id,
            "tenant_id": tenant.id,
            "campaign_id": campaign.id,
            "agent_profile_id": agent_profile.id,
            "vicidial_user": vicidial_user.vicidial_user if vicidial_user else "",
            "credit_balance": tenant.credit_balance,
            "login": login,
            "password": password,
            "api_key": tenant.api_key,
        }
        try:
            self.send_access_invitation(user, password, campaign=campaign, tenant=tenant)
            result["invitation_sent"] = True
        except Exception as exc:  # noqa: BLE001
            _logger.warning("Invitation demo non envoyée à %s : %s", login, exc)
            result["invitation_sent"] = False
            result["invitation_error"] = str(exc)
        return result

    def _brevo_mail_server(self):
        return (
            self.env["ir.mail_server"]
            .sudo()
            .search(
                [
                    ("smtp_host", "ilike", "brevo"),
                    ("active", "=", True),
                ],
                limit=1,
            )
        )

    def send_access_invitation(self, user, password, campaign=None, tenant=None):
        """Envoie l'e-mail d'accès Intellix (Brevo — Hostinger SMTP souvent bloqué)."""
        user = user.sudo()
        login = (user.login or user.email or "").strip()
        if not login:
            raise UserError(_("Adresse e-mail utilisateur manquante."))
        tenant = tenant or self.env["doorway.tenant"].sudo().search(
            [("company_id", "=", user.company_id.id)], limit=1
        )
        campaign = campaign or self.env["doorway.campaign"].sudo().search(
            [("company_id", "=", user.company_id.id)], limit=1
        )
        contacts = 0
        if campaign:
            contacts = self.env["doorway.campaign.contact"].sudo().search_count(
                [("campaign_id", "=", campaign.id)]
            )
        credit = tenant.credit_balance if tenant else 0.0
        base_url = (
            self.env["ir.config_parameter"].sudo().get_param("web.base.url")
            or "https://intellixcrm.com"
        ).rstrip("/")

        brevo = self._brevo_mail_server()
        if not brevo or not brevo.smtp_pass:
            raise UserError(_("Serveur SMTP Brevo non configuré."))

        html = _(
            "<p>Bonjour %(name)s,</p>"
            "<p>Bienvenue sur <strong>Intellix CRM</strong>. "
            "Votre environnement demo <strong>Call Center Espagne</strong> est actif.</p>"
            "<table cellpadding='0' cellspacing='0' style='border-collapse:collapse;margin:18px 0;'>"
            "<tr><td style='padding:8px 12px;background:#f4f6f8;'><strong>Lien</strong></td>"
            "<td style='padding:8px 12px;'><a href='%(url)s/web/login'>%(url)s/web/login</a></td></tr>"
            "<tr><td style='padding:8px 12px;background:#f4f6f8;'><strong>Identifiant</strong></td>"
            "<td style='padding:8px 12px;'>%(login)s</td></tr>"
            "<tr><td style='padding:8px 12px;background:#f4f6f8;'><strong>Mot de passe temporaire</strong></td>"
            "<td style='padding:8px 12px;font-family:monospace;'>%(password)s</td></tr>"
            "<tr><td style='padding:8px 12px;background:#f4f6f8;'><strong>Campagne</strong></td>"
            "<td style='padding:8px 12px;'>%(campaign)s (%(contacts)s contacts)</td></tr>"
            "<tr><td style='padding:8px 12px;background:#f4f6f8;'><strong>Crédit demo</strong></td>"
            "<td style='padding:8px 12px;'>%(credit).2f €</td></tr>"
            "</table>"
            "<p>À la première connexion, changez votre mot de passe si demandé.</p>"
            "<p>Support : <a href='mailto:info@agencedoorway.com'>info@agencedoorway.com</a></p>"
            "<p>— L'équipe Doorway / Intellix</p>"
        ) % {
            "name": user.name,
            "url": base_url,
            "login": login,
            "password": password,
            "campaign": campaign.name if campaign else "—",
            "contacts": contacts,
            "credit": credit,
        }
        plain = _(
            "Accès Intellix CRM\nURL: %(url)s/web/login\nIdentifiant: %(login)s\n"
            "Mot de passe: %(password)s\nCampagne: %(campaign)s (%(contacts)s contacts)\n"
            "Crédit: %(credit).2f €"
        ) % {
            "url": base_url,
            "login": login,
            "password": password,
            "campaign": campaign.name if campaign else "—",
            "contacts": contacts,
            "credit": credit,
        }

        msg = MIMEMultipart("alternative")
        msg["Subject"] = _("Votre accès Intellix CRM — Demo Call Center Espagne")
        msg["From"] = "Intellix CRM <info@agencedoorway.com>"
        msg["To"] = login
        msg.attach(MIMEText(plain, "plain", "utf-8"))
        msg.attach(MIMEText(html, "html", "utf-8"))

        with smtplib.SMTP(brevo.smtp_host, 587, timeout=30) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            smtp.login(brevo.smtp_user, brevo.smtp_pass)
            smtp.send_message(msg)

        user.partner_id.message_post(
            body=_(
                "Invitation Intellix envoyée à <strong>%(email)s</strong> "
                "(Brevo). Campagne : %(campaign)s."
            )
            % {
                "email": login,
                "campaign": campaign.name if campaign else "—",
            },
            message_type="comment",
            subtype_xmlid="mail.mt_note",
        )
        return True

    def _ensure_demo_tenant(self, company, email, credit_eur, flat_rate_eur):
        Tenant = self.env["doorway.tenant"].sudo()
        tenant = Tenant.search([("company_id", "=", company.id)], limit=1)
        vals = {
            "name": company.name,
            "company_id": company.id,
            "email_admin": email,
            "status": "active",
            "demo_call_center": True,
            "demo_flat_rate_eur": flat_rate_eur,
            "daily_credit_limit": 500.0,
        }
        if tenant:
            tenant.write(vals)
        else:
            tenant = Tenant.create(vals)
        account = tenant.credit_account_id
        if not account:
            account = self.env["doorway.credit.account"].sudo().create(
                {"tenant_id": tenant.id}
            )
            tenant.credit_account_id = account.id
        if account.balance < credit_eur:
            topup = credit_eur - account.balance
            account.credit(topup, transaction_type="purchase")
            tx = account.transaction_ids[:1]
            if tx:
                tx.write(
                    {
                        "description": _("Crédit demo initial — %.2f €") % credit_eur,
                    }
                )
        return tenant

    def _clone_sofia_agent(self, company, template_external_id, owner_name):
        Agent = self.env["doorway.agent.profile"].sudo()
        template = Agent.search(
            [("external_agent_id", "=", template_external_id)], limit=1
        )
        demo_external = "sofia-es-demo-%s" % owner_name.split()[0].lower()[:12]
        existing = Agent.search(
            [
                ("company_id", "=", company.id),
                ("external_agent_id", "=", demo_external),
            ],
            limit=1,
        )
        if existing:
            return existing
        if not template:
            return Agent.create(
                {
                    "name": "Sofía · España (Demo)",
                    "provider": "n8n",
                    "external_agent_id": demo_external,
                    "pipeline": "renovation",
                    "agent_type": "outbound",
                    "language": "es",
                    "status": "active",
                    "company_id": company.id,
                }
            )
        clone_vals = {
            "name": "Sofía · España (Demo %s)" % owner_name.split()[0],
            "company_id": company.id,
            "external_agent_id": demo_external,
            "status": "active",
        }
        clone = template.copy(default=clone_vals)
        return clone

    def _ensure_demo_sip_trunk(self, company):
        Trunk = self.env["doorway.sip.trunk"].sudo()
        trunk = Trunk.search([("company_id", "=", company.id)], limit=1)
        template = Trunk.search(
            [("name", "=", "TrustSIP — Espagne"), ("company_id", "=", False)],
            limit=1,
        )
        vals = {
            "name": DEMO_TRUNK_NAME,
            "company_id": company.id,
            "provider": "custom",
            "active": True,
        }
        if template:
            vals.update(
                {
                    "termination_uri": template.termination_uri,
                    "sip_username": template.sip_username,
                    "sip_password": template.sip_password,
                    "sip_port": template.sip_port,
                    "notes": template.notes,
                }
            )
        if trunk:
            trunk.write(vals)
        else:
            trunk = Trunk.create(vals)
        return trunk

    def _setup_demo_vicidial(self, campaign_id, trunk_cid, list_name, campaign_label):
        from odoo.addons.doorway_vicidial_campaigns.services.vicidial_service import (
            VicidialService,
        )

        svc = VicidialService(self.env)
        if not svc.is_available():
            _logger.warning("MySQL VICIdial indisponible — campagne demo ignorée")
            return False
        cid = (campaign_id or "")[:20]
        conn = svc._connect()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT campaign_id FROM vicidial_campaigns WHERE campaign_id = %s",
                (cid,),
            )
            if not cur.fetchone():
                cur.execute(
                    """
                    INSERT INTO vicidial_campaigns (
                        campaign_id, campaign_name, active, dial_method,
                        auto_dial_level, hopper_level, dial_prefix, campaign_cid,
                        local_call_time, dial_timeout, campaign_description
                    )
                    SELECT %s, %s, 'N', dial_method, auto_dial_level, hopper_level,
                           dial_prefix, %s, local_call_time, dial_timeout, %s
                    FROM vicidial_campaigns WHERE campaign_id = %s LIMIT 1
                    """,
                    (cid, campaign_label[:40], trunk_cid[:20], campaign_label, VICIDIAL_TEMPLATE),
                )
            else:
                cur.execute(
                    """
                    UPDATE vicidial_campaigns SET
                        campaign_name = %s,
                        campaign_cid = %s,
                        campaign_description = %s
                    WHERE campaign_id = %s
                    """,
                    (campaign_label[:40], trunk_cid[:20], campaign_label, cid),
                )
            list_id = svc._ensure_list(cur, cid, campaign_label, list_name=list_name)
            cur.execute(
                """
                UPDATE vicidial_campaigns SET
                    omit_phone_code = 'Y',
                    dial_prefix = '34'
                WHERE campaign_id = %s
                """,
                (cid,),
            )
            conn.commit()
            cur.close()
            svc.ensure_spain_outbound_dialing(cid)
            svc.set_campaign_cid(cid, trunk_cid)
            return {"campaign_id": cid, "list_id": list_id, "campaign_cid": trunk_cid}
        finally:
            conn.close()

    def _ensure_demo_campaign(
        self, company, agent_profile, vicidial_id, owner_name, sip_trunk
    ):
        Campaign = self.env["doorway.campaign"].sudo()
        camp = Campaign.search([("company_id", "=", company.id)], limit=1)
        template = Campaign.search(
            [("vicidial_campaign_id", "=", VICIDIAL_TEMPLATE), ("company_id", "=", False)],
            limit=1,
        )
        vals = {
            "name": "Demo Espagne — Sofía (%s)" % owner_name.split()[0],
            "company_id": company.id,
            "vicidial_campaign_id": vicidial_id,
            "sip_trunk_id": sip_trunk.id,
            "pipeline": template.pipeline if template else "renovation",
            "campaign_mode": "mixed",
            "state": "ready",
            "ia_agent_id": agent_profile.id,
            "amd_enabled": True,
            "description": _(
                "Campagne demo Espagne — trunk %s, DID = nom trunk (opérateur), agent Sofía."
            )
            % DEMO_TRUNK_NAME,
        }
        if template:
            vals["vicidial_list_id"] = template.vicidial_list_id
        if camp:
            camp.write(vals)
        else:
            camp = Campaign.create(vals)
        return camp

    def _ensure_vicidial_agent(self, user, full_name, vicidial_campaign_id):
        AgentUser = self.env["doorway.campaign.agent.user"].sudo()
        vicidial_login = (user.login.split("@")[0].replace(".", ""))[:20]
        agent = AgentUser.search([("user_id", "=", user.id)], limit=1)
        team = self.env.ref(
            "doorway_vicidial_campaigns.crm_team_vicidial_qualification_france",
            raise_if_not_found=False,
        )
        stage = self.env.ref(
            "doorway_vicidial_campaigns.crm_stage_vicidial_nouveau",
            raise_if_not_found=False,
        )
        vals = {
            "user_id": user.id,
            "vicidial_user": vicidial_login,
            "full_name": full_name,
            "vicidial_qualification_active": True,
            "active": True,
        }
        if team:
            vals["vicidial_crm_team_id"] = team.id
        if stage:
            vals["vicidial_crm_stage_id"] = stage.id
        if agent:
            agent.write(vals)
        else:
            agent = AgentUser.create(vals)
        try:
            agent.action_sync_vicidial()
        except Exception:  # noqa: BLE001
            _logger.exception("Sync VICIdial impossible pour %s", vicidial_login)
        self._link_vicidial_campaign(vicidial_login, vicidial_campaign_id)
        qualifier = self.env.ref(
            "doorway_vicidial_campaigns.group_vicidial_qualifier",
            raise_if_not_found=False,
        )
        if qualifier and qualifier not in user.group_ids:
            user.write({"group_ids": [(4, qualifier.id)]})
        return agent

    def _link_vicidial_campaign(self, vicidial_login, campaign_id):
        from odoo.addons.doorway_vicidial_campaigns.services.vicidial_service import (
            VicidialService,
        )

        svc = VicidialService(self.env)
        if not svc.is_available():
            _logger.warning("MySQL VICIdial indisponible — lien campagne ignoré")
            return False
        conn = svc._connect()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT 1 FROM vicidial_campaign_agents
                WHERE user = %s AND campaign_id = %s LIMIT 1
                """,
                (vicidial_login[:20], campaign_id[:20]),
            )
            if not cur.fetchone():
                cur.execute(
                    """
                    INSERT INTO vicidial_campaign_agents (
                        user, campaign_id, campaign_rank, campaign_weight, campaign_grade
                    ) VALUES (%s, %s, 1, 10, 1)
                    """,
                    (vicidial_login[:20], campaign_id[:20]),
                )
            conn.commit()
            cur.close()
        finally:
            conn.close()
        return True

    def _unlink_vicidial_campaign(self, vicidial_login, campaign_id):
        from odoo.addons.doorway_vicidial_campaigns.services.vicidial_service import (
            VicidialService,
        )

        svc = VicidialService(self.env)
        if not svc.is_available():
            return False
        conn = svc._connect()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                DELETE FROM vicidial_campaign_agents
                WHERE user = %s AND campaign_id = %s
                """,
                (vicidial_login[:20], campaign_id[:20]),
            )
            conn.commit()
            cur.close()
        finally:
            conn.close()
        return True

    def upgrade_pilot_abdallah(self, user=None):
        """Réaligne le pilote Abdallah : campagne dédiée, trunk propre, DID = nom trunk."""
        user = user or self.env["res.users"].sudo().search(
            [("login", "=", PILOT_LOGIN.lower())], limit=1
        )
        if not user:
            return {"error": "user_not_found"}
        company = user.company_id
        sip_trunk = self._ensure_demo_sip_trunk(company)
        self._setup_demo_vicidial(
            VICIDIAL_CAMPAIGN,
            DEMO_TRUNK_NAME,
            DEMO_LIST_NAME,
            "Demo Espagne — Abdallah",
        )
        agent_profile = user.doorway_agent_profile_id
        if not agent_profile:
            agent_profile = self._clone_sofia_agent(company, SOFIA_EXTERNAL_ID, PILOT_NAME)
            user.write({"doorway_agent_profile_id": agent_profile.id})
        campaign = self._ensure_demo_campaign(
            company, agent_profile, VICIDIAL_CAMPAIGN, PILOT_NAME, sip_trunk
        )
        vicidial_login = (user.login.split("@")[0].replace(".", ""))[:20]
        self._unlink_vicidial_campaign(vicidial_login, "DW_ESREN")
        vicidial_user = self._ensure_vicidial_agent(user, PILOT_NAME, VICIDIAL_CAMPAIGN)
        if vicidial_user:
            campaign.write({"human_agent_ids": [(4, vicidial_user.id)]})
        _logger.info(
            "Pilote demo Abdallah mis à jour — campagne %s, trunk %s, DID %s",
            VICIDIAL_CAMPAIGN,
            sip_trunk.name,
            DEMO_TRUNK_NAME,
        )
        return {
            "upgraded": True,
            "user_id": user.id,
            "campaign_id": campaign.id,
            "vicidial_campaign": VICIDIAL_CAMPAIGN,
            "sip_trunk": sip_trunk.name,
            "campaign_cid": "34632395675",
        }

    def provision_pilot_abdallah(self):
        existing = self.env["res.users"].sudo().search(
            [("login", "=", PILOT_LOGIN.lower())], limit=1
        )
        if existing and existing.demo_call_center:
            return self.upgrade_pilot_abdallah(existing)
        return self.provision_demo_user(
            name=PILOT_NAME,
            login=PILOT_LOGIN,
            company_name=PILOT_COMPANY,
        )
