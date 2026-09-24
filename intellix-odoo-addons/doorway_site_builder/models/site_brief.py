# -*- coding: utf-8 -*-
import json
import logging

from odoo import api, fields, models

from ..services import claude_site_builder, site_generator

_logger = logging.getLogger(__name__)

WELCOME_MESSAGE = (
    "Bonjour ! Je suis Léa, votre assistante de création de site. "
    "Décrivez-moi votre projet : votre activité, vos clients cibles, vos "
    "objectifs, le ton souhaité et les pages que vous aimeriez. Vous pouvez "
    "aussi remplir le brief à gauche. Quand vous êtes prêt·e, cliquez sur "
    "« Générer le site »."
)

ACK_MESSAGE = (
    "C'est noté ✦ J'ai bien pris en compte ces éléments. Ajoutez d'autres "
    "détails si besoin, puis cliquez sur « Générer le site » (ou « Mettre à "
    "jour le site » pour itérer)."
)


class SiteBrief(models.Model):
    _name = "doorway.site.brief"
    _description = "Brief de site web — Site Builder IA"
    _order = "id desc"

    name = fields.Char(string="Nom du projet", required=True, default="Nouveau site")
    language = fields.Char(string="Langue", default="fr")
    sector = fields.Char(string="Secteur")
    tone = fields.Char(string="Ton souhaité")
    inspiration = fields.Text(string="Inspiration / références")
    personas = fields.Text(string="Personas / cibles")
    objectives = fields.Text(string="Objectifs")
    pages_wanted = fields.Char(string="Pages souhaitées")

    set_as_homepage = fields.Boolean(
        string="Définir l'accueil comme page d'accueil du site",
        default=True,
        help="Si activé, la page d'accueil générée devient la racine '/' du site.",
    )

    state = fields.Selection(
        [
            ("draft", "Brouillon"),
            ("planned", "Plan généré"),
            ("generated", "Site généré"),
            ("published", "Site publié"),
            ("error", "Erreur"),
        ],
        string="État",
        default="draft",
        required=True,
    )
    publish_charged = fields.Boolean(
        string="Publication facturée", default=False, copy=False,
        help="Vrai dès qu'un crédit a été consommé pour publier ce site (évite "
        "toute double facturation lors d'une re-publication).",
    )

    plan_json = fields.Text(string="Plan IA (JSON)")
    slug_map_json = fields.Text(string="Mapping pages (JSON)")
    pages_json = fields.Text(string="Pages générées (JSON)")
    homepage_url = fields.Char(string="URL accueil")
    last_error = fields.Text(string="Dernière erreur")

    message_ids = fields.One2many(
        "doorway.site.chat.message", "brief_id", string="Conversation"
    )

    # ------------------------------------------------------------------
    # Helpers internes
    # ------------------------------------------------------------------
    def _add_message(self, role, content):
        if not content:
            return
        self.env["doorway.site.chat.message"].create(
            {"brief_id": self.id, "role": role, "content": content}
        )

    def _brief_dict(self):
        self.ensure_one()
        transcript = [
            {"role": m.role, "content": m.content}
            for m in self.message_ids
            if m.role in ("user", "assistant")
        ]
        return {
            "site_name": self.name or "Mon site",
            "language": self.language or "fr",
            "sector": self.sector or "",
            "tone": self.tone or "",
            "inspiration": self.inspiration or "",
            "personas": self.personas or "",
            "objectives": self.objectives or "",
            "pages_wanted": self.pages_wanted or "",
            "chat_transcript": transcript,
        }

    def _load_plan(self):
        if not self.plan_json:
            return None
        try:
            return json.loads(self.plan_json)
        except (ValueError, TypeError):
            return None

    def _load_slug_map(self):
        if not self.slug_map_json:
            return {}
        try:
            data = json.loads(self.slug_map_json)
            return data if isinstance(data, dict) else {}
        except (ValueError, TypeError):
            return {}

    def get_payload(self):
        """Données complètes pour rafraîchir l'UI OWL."""
        self.ensure_one()
        try:
            pages = json.loads(self.pages_json) if self.pages_json else []
        except (ValueError, TypeError):
            pages = []
        plan = self._load_plan()
        credit_api = self.env["doorway.credit.api"]
        publish_cost = credit_api.get_cost("doorway_credits.cost_site_publish", 1.0)
        balance = credit_api.get_balance(self.env.company)
        return {
            "id": self.id,
            "name": self.name,
            "language": self.language,
            "sector": self.sector,
            "tone": self.tone,
            "inspiration": self.inspiration,
            "personas": self.personas,
            "objectives": self.objectives,
            "pages_wanted": self.pages_wanted,
            "set_as_homepage": self.set_as_homepage,
            "state": self.state,
            "last_error": self.last_error,
            "homepage_url": self.homepage_url,
            "pages": pages,
            "plan_summary": site_generator.plan_preview(plan) if plan else "",
            "palette": (plan or {}).get("palette") or {},
            "messages": [m.to_dict() for m in self.message_ids],
            "claude_available": claude_site_builder.is_available(self.env),
            # --- Paywall (publication payante, génération/preview gratuites) ---
            "credit_balance": balance,
            "publish_cost": publish_cost,
            "publish_charged": self.publish_charged,
            "is_published": self.state == "published",
        }

    # ------------------------------------------------------------------
    # API appelée depuis l'OWL client action
    # ------------------------------------------------------------------
    @api.model
    def get_or_create_session(self):
        """Renvoie le brief le plus récent de l'utilisateur, ou en crée un."""
        brief = self.search([("create_uid", "=", self.env.uid)], limit=1)
        if not brief:
            brief = self.create({"name": "Nouveau site"})
            brief._add_message("assistant", WELCOME_MESSAGE)
        return brief.get_payload()

    @api.model
    def create_session(self):
        brief = self.create({"name": "Nouveau site"})
        brief._add_message("assistant", WELCOME_MESSAGE)
        return brief.get_payload()

    def update_brief(self, vals):
        """Met à jour les champs du brief depuis le panneau de gauche."""
        self.ensure_one()
        allowed = {
            "name",
            "language",
            "sector",
            "tone",
            "inspiration",
            "personas",
            "objectives",
            "pages_wanted",
            "set_as_homepage",
        }
        clean = {k: v for k, v in (vals or {}).items() if k in allowed}
        if clean:
            self.write(clean)
        return self.get_payload()

    def post_message(self, body):
        """Enregistre un message utilisateur + accusé de réception assistant."""
        self.ensure_one()
        body = (body or "").strip()
        if body:
            self._add_message("user", body)
            self._add_message("assistant", ACK_MESSAGE)
        return self.get_payload()

    def generate(self, instruction=None):
        """Génère (ou met à jour) le plan IA puis construit les pages.

        :param instruction: consigne d'itération facultative ; si présente, elle
            est aussi enregistrée comme message utilisateur.
        """
        self.ensure_one()
        instruction = (instruction or "").strip()
        if instruction:
            self._add_message("user", instruction)

        previous_plan = self._load_plan()
        plan, message = claude_site_builder.generate_plan(
            self.env,
            self._brief_dict(),
            previous_plan=previous_plan,
            instruction=instruction or None,
        )
        if plan is None:
            self.write({"state": "error", "last_error": message})
            self._add_message("assistant", "⚠️ " + message)
            return self.get_payload()

        self.write({"plan_json": json.dumps(plan, ensure_ascii=False), "state": "planned"})

        try:
            # GRATUIT : on génère/MAJ les pages mais on ne PUBLIE pas (preview).
            result = site_generator.generate_site(
                self.env,
                plan,
                slug_map=self._load_slug_map(),
                set_homepage=self.set_as_homepage,
                publish=False,
            )
        except Exception as exc:  # noqa: BLE001
            _logger.exception("Site builder : échec génération")
            self.write({"state": "error", "last_error": str(exc)})
            self._add_message(
                "assistant", "⚠️ La construction des pages a échoué : %s" % exc
            )
            return self.get_payload()

        if not result.get("ok"):
            self.write({"state": "error", "last_error": result.get("message")})
            self._add_message("assistant", "⚠️ " + (result.get("message") or "Échec."))
            return self.get_payload()

        self.write(
            {
                "state": "generated",
                "last_error": False,
                "slug_map_json": json.dumps(result.get("slug_map") or {}, ensure_ascii=False),
                "pages_json": json.dumps(result.get("pages") or [], ensure_ascii=False),
                "homepage_url": result.get("homepage_url"),
            }
        )

        summary = plan.get("assistant_message") or message
        warn = result.get("warnings") or []
        reply = summary + "\n\n" + result.get("message", "")
        if warn:
            reply += "\n\nÀ noter :\n- " + "\n- ".join(warn)
        reply += (
            "\n\nVous pouvez prévisualiser le site gratuitement, ou me demander des "
            "ajustements. Quand vous êtes prêt·e, cliquez sur « Publier » pour le "
            "mettre en ligne (consomme un crédit)."
        )
        self._add_message("assistant", reply)
        return self.get_payload()

    # ------------------------------------------------------------------
    # PUBLICATION (action payante — consomme des crédits)
    # ------------------------------------------------------------------
    def publish(self):
        """Met le site EN LIGNE après vérification/consommation de crédits.

        Génération et prévisualisation restent gratuites ; seule la mise en
        ligne (pages publiques + page d'accueil + menus) est facturée. La
        consommation est idempotente par brief : re-publier ne refacture pas.
        """
        self.ensure_one()
        credit_api = self.env["doorway.credit.api"]
        cost = credit_api.get_cost("doorway_credits.cost_site_publish", 1.0)
        company = self.env.company
        idem = "site_publish:brief:%s" % self.id

        if self.state not in ("generated", "published"):
            payload = self.get_payload()
            payload["publish_error"] = "Générez d'abord le site avant de le publier."
            self._add_message("assistant", "⚠️ Générez d'abord le site avant de le publier.")
            return payload

        # Déjà facturé pour ce site ? (re-publication => pas de double charge)
        already = bool(self.publish_charged) or bool(
            self.env["doorway.credit.transaction"]
            .sudo()
            .search([("idempotency_key", "=", idem)], limit=1)
        )

        # GATE : si pas encore payé et solde insuffisant → paywall (pas de publication).
        if not already and not credit_api.has_credits(company, cost):
            payload = self.get_payload()
            payload["paywall"] = credit_api.action_open_paywall(
                company,
                required=cost,
                service="site_publish",
                message="Solde insuffisant pour publier votre site web.",
            )
            self._add_message(
                "assistant",
                "🔒 Solde de crédits insuffisant pour publier. Achetez un pack pour "
                "mettre votre site en ligne (la prévisualisation reste gratuite).",
            )
            return payload

        # Publication effective.
        plan = self._load_plan()
        try:
            result = site_generator.publish_site(
                self.env,
                plan,
                slug_map=self._load_slug_map(),
                set_homepage=self.set_as_homepage,
            )
        except Exception as exc:  # noqa: BLE001
            _logger.exception("Site builder : échec publication")
            payload = self.get_payload()
            payload["publish_error"] = str(exc)
            self._add_message("assistant", "⚠️ La publication a échoué : %s" % exc)
            return payload

        if not result.get("ok"):
            payload = self.get_payload()
            payload["publish_error"] = result.get("message")
            self._add_message("assistant", "⚠️ " + (result.get("message") or "Publication impossible."))
            return payload

        # CONSOMMATION : une seule fois par publication réussie (idempotent).
        if not already:
            res = credit_api.consume(
                company,
                cost,
                "Publication du site « %s »" % (self.name or self.id),
                ref="brief:%s" % self.id,
                service="site_publish",
                idempotency_key=idem,
            )
            if res.get("success"):
                self.publish_charged = True

        self.write(
            {
                "state": "published",
                "homepage_url": result.get("homepage_url") or self.homepage_url,
                "last_error": False,
            }
        )
        warn = result.get("warnings") or []
        reply = "✅ " + result.get("message", "Site publié.")
        if warn:
            reply += "\n\nÀ noter :\n- " + "\n- ".join(warn)
        reply += "\n\nVotre site est maintenant en ligne."
        self._add_message("assistant", reply)
        payload = self.get_payload()
        payload["published"] = True
        return payload
