# -*- coding: utf-8 -*-
import json
import logging

from odoo import api, fields, models

from ..services import claude_email_builder, email_generator

_logger = logging.getLogger(__name__)

WELCOME_MESSAGE = (
    "Bonjour ! Je suis Léa, votre assistante de rédaction d'emails. "
    "Décrivez-moi votre objectif : la cible (persona), le ton souhaité, "
    "l'offre / proposition de valeur et l'appel à l'action (CTA). Vous pouvez "
    "aussi remplir le brief à gauche, puis cliquer sur « Générer l'email »."
)

ACK_MESSAGE = (
    "C'est noté ✦ J'ai bien pris en compte ces éléments. Ajoutez d'autres "
    "détails si besoin, puis cliquez sur « Générer l'email » (ou « Mettre à "
    "jour » pour itérer)."
)


class EmailBrief(models.Model):
    _name = "doorway.email.brief"
    _description = "Brief d'email — Email Builder IA"
    _order = "id desc"

    name = fields.Char(string="Nom de la campagne", required=True, default="Nouvelle campagne email")
    language = fields.Char(string="Langue", default="fr")
    brand = fields.Char(string="Marque")
    objective = fields.Text(string="Objectif")
    persona = fields.Text(string="Persona / cible")
    tone = fields.Char(string="Ton souhaité")
    offer = fields.Text(string="Offre / proposition de valeur")
    cta = fields.Char(string="Appel à l'action (CTA)")
    sequence_length = fields.Integer(string="Nombre d'emails (séquence)", default=1)

    create_campaigns = fields.Boolean(
        string="Créer aussi des campagnes multi-contacts",
        default=True,
        help="Si activé, génère également des doorway.message.campaign (canal "
        "Email) prêtes à recevoir des contacts via le flux de campagne.",
    )

    state = fields.Selection(
        [
            ("draft", "Brouillon"),
            ("generated", "Email(s) généré(s)"),
            ("sent", "Envoyé"),
            ("error", "Erreur"),
        ],
        string="État",
        default="draft",
        required=True,
    )
    send_charged = fields.Boolean(
        string="Envoi facturé", default=False, copy=False,
        help="Vrai dès qu'un crédit a été consommé pour envoyer cette campagne "
        "(évite toute double facturation lors d'un renvoi).",
    )

    payload_json = fields.Text(string="Emails IA (JSON)")
    artifact_map_json = fields.Text(string="Mapping artefacts (JSON)")
    emails_json = fields.Text(string="Emails générés (JSON)")
    last_error = fields.Text(string="Dernière erreur")

    message_ids = fields.One2many(
        "doorway.email.chat.message", "brief_id", string="Conversation"
    )

    # ------------------------------------------------------------------
    # Helpers internes
    # ------------------------------------------------------------------
    def _add_message(self, role, content):
        if not content:
            return
        self.env["doorway.email.chat.message"].create(
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
            "campaign_name": self.name or "Campagne email",
            "language": self.language or "fr",
            "brand": self.brand or "",
            "objective": self.objective or "",
            "persona": self.persona or "",
            "tone": self.tone or "",
            "offer": self.offer or "",
            "cta": self.cta or "",
            "sequence_length": self.sequence_length or 1,
            "chat_transcript": transcript,
        }

    def _load_json(self, field_value, default):
        if not field_value:
            return default
        try:
            return json.loads(field_value)
        except (ValueError, TypeError):
            return default

    def get_payload(self):
        """Données complètes pour rafraîchir l'UI OWL."""
        self.ensure_one()
        emails = self._load_json(self.emails_json, [])
        payload = self._load_json(self.payload_json, None)
        credit_api = self.env["doorway.credit.api"]
        send_cost = credit_api.get_cost("doorway_credits.cost_email_send", 1.0)
        balance = credit_api.get_balance(self.env.company)
        return {
            "id": self.id,
            "name": self.name,
            "language": self.language,
            "brand": self.brand,
            "objective": self.objective,
            "persona": self.persona,
            "tone": self.tone,
            "offer": self.offer,
            "cta": self.cta,
            "sequence_length": self.sequence_length,
            "create_campaigns": self.create_campaigns,
            "state": self.state,
            "last_error": self.last_error,
            "emails": emails,
            "preview": email_generator.payload_preview(payload) if payload else "",
            "messages": [m.to_dict() for m in self.message_ids],
            "claude_available": claude_email_builder.is_available(self.env),
            # --- Paywall (envoi payant, génération/preview gratuites) ---
            "credit_balance": balance,
            "send_cost": send_cost,
            "send_charged": self.send_charged,
            "is_sent": self.state == "sent",
        }

    # ------------------------------------------------------------------
    # API appelée depuis l'OWL client action
    # ------------------------------------------------------------------
    @api.model
    def get_or_create_session(self):
        """Renvoie le brief le plus récent de l'utilisateur, ou en crée un."""
        brief = self.search([("create_uid", "=", self.env.uid)], limit=1)
        if not brief:
            brief = self.create({"name": "Nouvelle campagne email"})
            brief._add_message("assistant", WELCOME_MESSAGE)
        return brief.get_payload()

    @api.model
    def create_session(self):
        brief = self.create({"name": "Nouvelle campagne email"})
        brief._add_message("assistant", WELCOME_MESSAGE)
        return brief.get_payload()

    def update_brief(self, vals):
        """Met à jour les champs du brief depuis le panneau de gauche."""
        self.ensure_one()
        allowed = {
            "name",
            "language",
            "brand",
            "objective",
            "persona",
            "tone",
            "offer",
            "cta",
            "sequence_length",
            "create_campaigns",
        }
        clean = {k: v for k, v in (vals or {}).items() if k in allowed}
        if "sequence_length" in clean:
            try:
                clean["sequence_length"] = max(1, min(int(clean["sequence_length"]), 5))
            except (TypeError, ValueError):
                clean.pop("sequence_length")
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
        """Génère (ou met à jour) le(s) email(s) puis construit les artefacts.

        :param instruction: consigne d'itération facultative ; si présente, elle
            est aussi enregistrée comme message utilisateur.
        """
        self.ensure_one()
        instruction = (instruction or "").strip()
        if instruction:
            self._add_message("user", instruction)

        previous = self._load_json(self.payload_json, None)
        previous_emails = (previous or {}).get("emails") if previous else None

        payload, message = claude_email_builder.generate_emails(
            self.env,
            self._brief_dict(),
            previous_emails=previous_emails,
            instruction=instruction or None,
        )
        if payload is None:
            self.write({"state": "error", "last_error": message})
            self._add_message("assistant", "⚠️ " + message)
            return self.get_payload()

        self.write({"payload_json": json.dumps(payload, ensure_ascii=False)})

        try:
            result = email_generator.generate_emails(
                self.env,
                payload,
                artifact_map=self._load_json(self.artifact_map_json, {}),
                create_campaigns=self.create_campaigns,
            )
        except Exception as exc:  # noqa: BLE001
            _logger.exception("Email builder : échec génération artefacts")
            self.write({"state": "error", "last_error": str(exc)})
            self._add_message(
                "assistant", "⚠️ La construction des emails a échoué : %s" % exc
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
                "artifact_map_json": json.dumps(
                    result.get("artifact_map") or {}, ensure_ascii=False
                ),
                "emails_json": json.dumps(result.get("emails") or [], ensure_ascii=False),
            }
        )

        summary = payload.get("assistant_message") or message
        warn = result.get("warnings") or []
        reply = summary + "\n\n" + result.get("message", "")
        if warn:
            reply += "\n\nÀ noter :\n- " + "\n- ".join(warn)
        reply += (
            "\n\nVos emails sont prêts : retrouvez-les dans les Templates email, "
            "le Marketing Email, et les campagnes Messaging. Demandez-moi un "
            "ajustement si besoin (« plus court », « plus premium », « ajoute "
            "une remise », « transforme en séquence de 3 emails »)."
        )
        self._add_message("assistant", reply)
        return self.get_payload()

    def action_open_mailing(self):
        """Ouvre la liste des mailings générés par ce brief."""
        self.ensure_one()
        ids = []
        for entry in self._load_json(self.emails_json, []):
            if entry.get("mailing_id"):
                ids.append(entry["mailing_id"])
        return {
            "type": "ir.actions.act_window",
            "name": "Emails générés",
            "res_model": "mailing.mailing",
            "domain": [("id", "in", ids)],
            "view_mode": "list,form",
            "target": "current",
        }

    def _generated_mailing_ids(self):
        self.ensure_one()
        return [
            e["mailing_id"]
            for e in self._load_json(self.emails_json, [])
            if e.get("mailing_id")
        ]

    # ------------------------------------------------------------------
    # ENVOI / PUBLICATION (action payante — consomme des crédits)
    # ------------------------------------------------------------------
    def publish(self):
        """Envoie le(s) mailing(s) généré(s) après vérification/consommation de crédits.

        Génération et prévisualisation restent gratuites ; seul l'ENVOI (mise en
        file du mailing.mailing) est facturé. Idempotent par brief : un renvoi ne
        refacture pas. En cas de solde insuffisant : paywall et les mailings
        restent en brouillon.
        """
        self.ensure_one()
        credit_api = self.env["doorway.credit.api"]
        cost = credit_api.get_cost("doorway_credits.cost_email_send", 1.0)
        company = self.env.company
        idem = "email_send:brief:%s" % self.id

        if self.state not in ("generated", "sent"):
            payload = self.get_payload()
            payload["publish_error"] = "Générez d'abord l'email avant de l'envoyer."
            self._add_message("assistant", "⚠️ Générez d'abord l'email avant de l'envoyer.")
            return payload

        mailing_ids = self._generated_mailing_ids()
        if not mailing_ids:
            payload = self.get_payload()
            payload["publish_error"] = "Aucun mailing à envoyer."
            self._add_message("assistant", "⚠️ Aucun mailing généré à envoyer.")
            return payload

        already = bool(self.send_charged) or bool(
            self.env["doorway.credit.transaction"]
            .sudo()
            .search([("idempotency_key", "=", idem)], limit=1)
        )

        # GATE : si pas encore payé et solde insuffisant → paywall (rien n'est envoyé).
        if not already and not credit_api.has_credits(company, cost):
            payload = self.get_payload()
            payload["paywall"] = credit_api.action_open_paywall(
                company,
                required=cost,
                service="email_send",
                message="Solde insuffisant pour envoyer cette campagne email.",
            )
            self._add_message(
                "assistant",
                "🔒 Solde de crédits insuffisant pour envoyer. Achetez un pack — la "
                "génération et la prévisualisation restent gratuites. Vos mailings "
                "restent en brouillon.",
            )
            return payload

        # Envoi effectif : mise en file des mailings (le cron mass_mailing envoie).
        Mailing = self.env["mailing.mailing"].sudo()
        mailings = Mailing.browse(mailing_ids).exists()
        warnings = []
        launched = 0
        for mailing in mailings:
            try:
                if mailing.state == "draft":
                    mailing.action_launch()
                launched += 1
            except Exception as exc:  # noqa: BLE001
                _logger.exception("Email builder : échec envoi mailing %s", mailing.id)
                warnings.append("Mailing « %s » non envoyé : %s" % (mailing.subject, exc))

        if not launched:
            payload = self.get_payload()
            payload["publish_error"] = "; ".join(warnings) or "Aucun mailing envoyé."
            self._add_message(
                "assistant",
                "⚠️ Aucun mailing n'a pu être envoyé : " + ("; ".join(warnings) or "erreur."),
            )
            return payload

        # CONSOMMATION : une seule fois par envoi réussi (idempotent).
        if not already:
            res = credit_api.consume(
                company,
                cost,
                "Envoi campagne email « %s »" % (self.name or self.id),
                ref="brief:%s" % self.id,
                service="email_send",
                idempotency_key=idem,
            )
            if res.get("success"):
                self.send_charged = True

        self.write({"state": "sent", "last_error": False})
        reply = "✅ %d mailing(s) mis en file d'envoi." % launched
        if warnings:
            reply += "\n\nÀ noter :\n- " + "\n- ".join(warnings)
        self._add_message("assistant", reply)
        payload = self.get_payload()
        payload["sent"] = True
        return payload
