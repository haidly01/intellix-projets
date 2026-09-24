# -*- coding: utf-8 -*-
from markupsafe import Markup

from odoo import api, fields, models, _
from odoo.exceptions import UserError

TEST_TO = "doorwaydigital1@gmail.com"

CM_BRAND = {
    "id": "coins_marocain",
    "label": "Coins Marocain",
    "kicker": "COINS MAROCAIN — ESPACE PARTENAIRE",
    "lead": (
        "Votre partenariat est confirmé — il ne reste qu'à remplir les "
        "informations de votre établissement pour qu'il soit visible auprès de nos clients."
    ),
    "categories": [
        {"id": "decouverte", "label": "Découverte", "desc": "Activité ou expérience à l'unité"},
        {"id": "hebergement", "label": "Hébergement", "desc": "Chambres louables à l'unité"},
        {"id": "evenements", "label": "Événements", "desc": "Réceptions, mariages, séminaires"},
        {"id": "privatisation", "label": "Privatisation", "desc": "Lieu complet en exclusivité"},
        {"id": "bienetre", "label": "Bien-être", "desc": "Massages, soins, hammam", "wide": True},
    ],
}


def _esc(value):
    return (
        str(value or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


class CoinsSendFicheWizard(models.TransientModel):
    _name = "coins.send.fiche.wizard"
    _description = "Envoyer la fiche partenaire (courriel + maquette)"

    lead_id = fields.Many2one("crm.lead", required=True, string="Fiche")
    test_mode = fields.Boolean(default=False, string="Envoi-test (pas le partenaire)")
    email_to = fields.Char(required=True, string="Destinataire")
    partner_email = fields.Char(readonly=True, string="Email de la fiche")
    subject = fields.Char(required=True, string="Objet")
    lien_fiche = fields.Char(readonly=True, string="Lien maquette")
    body_html = fields.Html(sanitize=False, string="Courriel")
    maquette_html = fields.Html(sanitize=False, string="Maquette")

    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)
        lead = self.env["crm.lead"].browse(vals.get("lead_id") or self.env.context.get("default_lead_id"))
        if lead:
            pack = self._pack_from_lead(lead)
            vals.setdefault("partner_email", pack["partner_email"])
            vals.setdefault("email_to", pack["partner_email"])
            vals.setdefault("test_mode", False)
            vals.setdefault("subject", pack["subject"])
            vals.setdefault("lien_fiche", pack["lien"])
            vals.setdefault("body_html", pack["body_html"])
            vals.setdefault("maquette_html", pack["maquette_html"])
        return vals

    @api.onchange("test_mode")
    def _onchange_test_mode(self):
        if self.test_mode:
            self.email_to = TEST_TO
        elif self.partner_email:
            self.email_to = self.partner_email

    def _pack_from_lead(self, lead):
        prop = lead._coins_ensure_partner_property()
        base = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("web.base.url", "https://intellixcrm.com")
            .rstrip("/")
        )
        token = (prop.portal_token or "").strip()
        lien = "%s/coins/completer-fiche/%s" % (base, token) if token else lead.coins_partner_lien
        prenom = (lead.contact_name or "bonjour").split()[0]
        etab = lead.coins_etablissement or prop.name or lead.name
        partner_email = (lead.email_from or prop.onboarding_email or "").strip()
        subject = "Votre fiche Coins Marocain — dernière étape avant votre mise en ligne"
        body = self._render_email_html(prenom, etab, lien, test=False)
        maquette = self._render_maquette_html(lead, prop, lien)
        return {
            "partner_email": partner_email,
            "subject": subject,
            "lien": lien,
            "body_html": body,
            "maquette_html": maquette,
        }

    def _render_email_html(self, prenom, etab, lien, test=False):
        banner = (
            """
            <div style="background:#efe9f9;color:#6a4bab;padding:10px 16px;font-size:13px;border-bottom:1px solid #d9cdee;">
              TEST interne Doorway — envoyé à doorwaydigital1@gmail.com, pas à la partenaire.
            </div>
            """
            if test
            else ""
        )
        return Markup(
            """
<div style="margin:0;background:#f6f4ef;font-family:Inter,Segoe UI,sans-serif;color:#2a2620;">
  %(banner)s
  <div style="max-width:600px;margin:0 auto;background:#ffffff;border:1px solid #e2ddd0;">
    <div style="background:#7c5cbf;padding:24px 28px;color:#fff;">
      <div style="font-size:11px;letter-spacing:.16em;text-transform:uppercase;opacity:.9;">Coins Marocain</div>
      <div style="font-size:24px;font-weight:600;margin-top:6px;">Complétez votre fiche</div>
    </div>
    <div style="padding:28px;">
      <p>Bonjour <strong>%(prenom)s</strong>,</p>
      <p>Nous sommes ravis de vous compter parmi les partenaires Coins Marocain.</p>
      <p>
        Il ne reste qu'une dernière étape avant que <strong>%(etab)s</strong> soit visible
        auprès de notre clientèle : compléter votre fiche partenaire. Ça prend quelques minutes —
        les informations que vous nous avez déjà partagées sont pré-remplies, il ne reste qu'à
        ajouter ce qui manque (photos, tarifs, espaces communs, et tout ce qui rend votre lieu unique).
      </p>
      <p style="text-align:center;margin:28px 0;">
        <a href="%(lien)s" style="display:inline-block;background:#7c5cbf;color:#fff;text-decoration:none;font-weight:600;padding:13px 26px;border-radius:10px;">
          Compléter ma fiche
        </a>
      </p>
      <p style="font-size:13px;color:#8a8375;">Lien : <a href="%(lien)s" style="color:#7c5cbf;word-break:break-all;">%(lien)s</a></p>
      <p>Si vous avez des questions ou besoin d'aide pour la remplir, répondez simplement à ce courriel.</p>
      <p>Au plaisir de vous accueillir dans le réseau,<br/>Zakaria — Coins Marocain</p>
    </div>
  </div>
</div>
            """
            % {
                "banner": banner,
                "prenom": _esc(prenom),
                "etab": _esc(etab),
                "lien": _esc(lien),
            }
        )

    def _render_maquette_html(self, lead, prop, lien):
        etab = _esc(lead.coins_etablissement or prop.name or "")
        contact = _esc(lead.contact_name or prop.onboarding_contact_name or "")
        ville = _esc(
            " ".join(
                p
                for p in [
                    lead._coins_ville_label() if hasattr(lead, "_coins_ville_label") else "",
                    lead.coins_quartier or prop.district or "",
                ]
                if p
            ).replace("  ", " ")
            or " ".join(p for p in [prop.city or "", prop.district or ""] if p)
        )
        tel = _esc(lead.phone or prop.onboarding_phone or "")
        mail = _esc(lead.email_from or prop.onboarding_email or "")
        cats = prop.category_ids.mapped("code") if prop.category_ids else ["hebergement"]
        chips = []
        for cat in CM_BRAND["categories"]:
            selected = cat["id"] in cats or (
                cat["id"] == "hebergement" and "hebergement" in cats
            )
            border = "#7c5cbf" if selected else "#e2ddd0"
            bg = "#efe9f9" if selected else "#fff"
            chips.append(
                '<div style="border:2px solid %s;background:%s;border-radius:10px;padding:12px 14px;font-size:13px;">'
                '<div style="font-weight:600;">%s</div>'
                '<div style="color:#8a8375;font-size:12px;">%s</div></div>'
                % (border, bg, cat["label"], cat["desc"])
            )
        field = (
            lambda label, value: (
                '<div style="margin-bottom:12px;"><div style="font-size:12px;font-weight:500;margin-bottom:4px;">%s'
                ' <span style="float:right;font-size:10px;background:#efe9f9;color:#6a4bab;padding:1px 8px;border-radius:10px;">Depuis la fiche Odoo</span>'
                '</div><div style="border:1px solid #e2ddd0;border-radius:8px;padding:9px 12px;background:#fff;">%s</div></div>'
            )
            % (label, value or "—")
        )
        return Markup(
            """
<div style="background:#f6f4ef;border:1px solid #e2ddd0;border-radius:14px;padding:20px 18px;font-family:Inter,Segoe UI,sans-serif;color:#2a2620;">
  <div style="font-size:11px;letter-spacing:.12em;color:#c9a876;margin-bottom:8px;">COINS MAROCAIN — ESPACE PARTENAIRE</div>
  <div style="font-size:22px;font-weight:600;margin-bottom:6px;">Complétez votre fiche</div>
  <div style="color:#8a8375;font-size:13px;line-height:1.45;margin-bottom:16px;">Votre partenariat est confirmé — il ne reste qu'à remplir les informations de votre établissement pour qu'il soit visible auprès de nos clients.</div>
  <div style="display:flex;gap:6px;margin-bottom:16px;">
    <div style="flex:1;height:3px;background:#7c5cbf;border-radius:3px;"></div>
    <div style="flex:1;height:3px;background:#e2ddd0;border-radius:3px;"></div>
    <div style="flex:1;height:3px;background:#e2ddd0;border-radius:3px;"></div>
    <div style="flex:1;height:3px;background:#e2ddd0;border-radius:3px;"></div>
  </div>
  <div style="font-size:12px;color:#8a8375;margin-bottom:12px;">Étape <span style="color:#7c5cbf;font-weight:500;">1</span> sur 4 — Coordonnées</div>
  <div style="background:#fff;border:1px solid #e2ddd0;border-radius:12px;padding:16px;">
    %(etab)s
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;">
      %(ville)s
      %(contact)s
      %(tel)s
      %(mail)s
    </div>
  </div>
  <div style="font-size:12px;color:#8a8375;margin:16px 0 8px;">Catégories (étape 2)</div>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;">%(chips)s</div>
  <div style="margin-top:16px;text-align:right;">
    <a href="%(lien)s" target="_blank" style="display:inline-block;background:#7c5cbf;color:#fff;text-decoration:none;font-weight:600;padding:12px 22px;border-radius:10px;">Ouvrir la maquette</a>
  </div>
</div>
            """
            % {
                "etab": field("Nom de l'établissement", etab),
                "ville": field("Ville / région", ville),
                "contact": field("Nom du contact", contact),
                "tel": field("Téléphone / WhatsApp", tel),
                "mail": field("Courriel", mail),
                "chips": "".join(chips),
                "lien": _esc(lien),
            }
        )

    def action_send(self):
        self.ensure_one()
        to = (self.email_to or "").strip()
        if not to or "@" not in to:
            raise UserError(_("Indiquez un destinataire valide."))
        if not self.test_mode and to.lower() == TEST_TO:
            raise UserError(_("Décochez « Envoi-test » pour envoyer au partenaire, ou laissez-le coché pour doorwaydigital1."))
        if self.test_mode and to.lower() != TEST_TO:
            raise UserError(_("Envoi-test : le destinataire doit rester %s.") % TEST_TO)
        lead = self.lead_id
        outgoing = lead._coins_zakaria_outgoing()
        subject = (self.subject or "").replace("[TEST] ", "").strip()
        if self.test_mode and not subject.startswith("[TEST]"):
            subject = "[TEST] %s" % subject
        body = self._render_email_html(
            (lead.contact_name or "bonjour").split()[0],
            lead.coins_etablissement or lead.name,
            self.lien_fiche,
            test=self.test_mode,
        )
        mail = self.env["mail.mail"].sudo().create(
            {
                "subject": subject,
                "body_html": body,
                "email_to": to,
                "email_from": outgoing["email_from"],
                "mail_server_id": outgoing["mail_server_id"] or False,
                "model": "crm.lead",
                "res_id": lead.id,
                "auto_delete": False,
                "reply_to": "zakaria@agencedoorway.com",
            }
        )
        mail.send()
        lead.message_post(
            body=_(
                "Fiche partenaire envoyée à %s%s — %s"
            )
            % (
                to,
                _(" (test interne)") if self.test_mode else "",
                self.lien_fiche,
            )
        )
        if not self.test_mode and lead.coins_property_id:
            lead.coins_property_id.write({"onboarding_status": "lien_envoye"})
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Fiche envoyée"),
                "message": _("Courriel envoyé à %s") % to,
                "type": "success",
                "sticky": False,
            },
        }
