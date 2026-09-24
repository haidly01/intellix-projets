# -*- coding: utf-8 -*-
import logging
import secrets

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

_logger = logging.getLogger(__name__)

ITEX_TEAM_ID = 112
DRIVEN_TEAM_ID = 94

PUBLISH_STATES = [
    ("draft", "Brouillon"),
    ("moderation", "En modération"),
    ("published", "Publié"),
    ("rejected", "Refusé"),
]


class CoinsQuebecPartenariatPortal(models.Model):
    """Portail Mon Coin — étend la fiche prospection, ne crée pas de jumeau."""

    _inherit = "coins.quebec.partenariat"

    publish_state = fields.Selection(
        PUBLISH_STATES,
        string="Publication (carte)",
        default="draft",
        required=True,
        tracking=True,
        index=True,
        help="Indépendant du pipeline prospection (Nouveau / Contacté / Entente…). "
        "Une fiche n’apparaît sur la carte qu’après validation humaine.",
    )
    partner_id = fields.Many2one("res.partner", string="Fiche contact", ondelete="set null")
    portal_user_id = fields.Many2one(
        "res.users",
        string="Utilisateur portail",
        ondelete="set null",
        index=True,
        copy=False,
    )
    description = fields.Text(string="Description publique")
    video_url = fields.Char(string="Vidéo (YouTube ou MP4)")
    service_ids = fields.One2many(
        "coins.quebec.partenariat.service", "partenariat_id", string="Services & prix"
    )
    offer_ids = fields.One2many(
        "coins.quebec.partenariat.forfait", "partenariat_id", string="Forfaits"
    )
    photo_ids = fields.One2many(
        "coins.quebec.partenariat.photo", "partenariat_id", string="Photos"
    )
    pin_view_count = fields.Integer(string="Vues pin", default=0, copy=False)
    pin_click_count = fields.Integer(string="Clics fiche", default=0, copy=False)
    reservation_public_count = fields.Integer(
        string="Réservations (fiche)",
        compute="_compute_reservation_public_count",
    )
    itex_lead_id = fields.Many2one("crm.lead", string="Lead ITEX", copy=False)
    driven_lead_id = fields.Many2one("crm.lead", string="Lead Driven", copy=False)
    boost_ids = fields.One2many(
        "coins.quebec.boost.request", "partenariat_id", string="Demandes de boost"
    )
    authorize_login = fields.Char(string="Authorize.net API Login ID", copy=False)
    authorize_trans_key = fields.Char(
        string="Authorize.net Transaction Key", copy=False
    )
    authorize_connected = fields.Boolean(
        string="Terminal connecté",
        compute="_compute_authorize_connected",
    )
    checklist_description = fields.Boolean(compute="_compute_checklist")
    checklist_video = fields.Boolean(compute="_compute_checklist")
    checklist_photo = fields.Boolean(compute="_compute_checklist")
    checklist_services = fields.Boolean(compute="_compute_checklist")
    checklist_address = fields.Boolean(compute="_compute_checklist")
    checklist_done_count = fields.Integer(compute="_compute_checklist")

    @api.depends("authorize_login", "authorize_trans_key")
    def _compute_authorize_connected(self):
        for rec in self:
            rec.authorize_connected = bool(
                (rec.authorize_login or "").strip()
                and (rec.authorize_trans_key or "").strip()
            )

    @api.depends(
        "description",
        "video_url",
        "photo_ids",
        "service_ids",
        "street",
        "city",
    )
    def _compute_checklist(self):
        for rec in self:
            rec.checklist_description = bool((rec.description or "").strip())
            rec.checklist_video = bool((rec.video_url or "").strip())
            rec.checklist_photo = bool(rec.photo_ids)
            rec.checklist_services = bool(rec.service_ids)
            rec.checklist_address = bool((rec.street or rec.city or "").strip())
            rec.checklist_done_count = sum(
                [
                    rec.checklist_description,
                    rec.checklist_video,
                    rec.checklist_photo,
                    rec.checklist_services,
                    rec.checklist_address,
                ]
            )

    def _compute_reservation_public_count(self):
        Resa = self.env["coins.quebec.reservation"].sudo()
        for rec in self:
            prop_id = rec.sudo().property_id.id
            if prop_id:
                rec.reservation_public_count = Resa.search_count(
                    [
                        ("property_id", "=", prop_id),
                        ("state", "not in", ("cancelled", "draft")),
                    ]
                )
            else:
                rec.reservation_public_count = 0

    def action_submit_moderation(self):
        for rec in self:
            rec.publish_state = "moderation"
            rec.message_post(
                body=_("Fiche envoyée en modération depuis le portail Mon Coin.")
            )
            rec._notify_moderation()
        return True

    def action_publish_fiche(self):
        if not self.env.user.has_group("coins_quebec.group_coins_quebec_user"):
            raise AccessError(_("Seule l’équipe Doorway publie une fiche."))
        for rec in self:
            rec.publish_state = "published"
            rec.message_post(body=_("Fiche publiée sur la carte Coins Québec."))
        return True

    def action_reject_fiche(self):
        if not self.env.user.has_group("coins_quebec.group_coins_quebec_user"):
            raise AccessError(_("Seule l’équipe Doorway refuse une fiche."))
        for rec in self:
            rec.publish_state = "rejected"
            rec.message_post(body=_("Fiche refusée — le commerçant peut corriger."))
        return True

    def action_unpublish_fiche(self):
        if not self.env.user.has_group("coins_quebec.group_coins_quebec_user"):
            raise AccessError(_("Seule l’équipe Doorway retire une fiche."))
        self.write({"publish_state": "draft"})
        return True

    def _notify_moderation(self):
        Activity = self.env["mail.activity"].sudo()
        act_type = self.env.ref(
            "mail.mail_activity_data_todo", raise_if_not_found=False
        )
        for rec in self:
            user = rec.coins_commercial_assigne or rec.user_id
            if not user or user.share:
                user = self.env.ref("base.user_admin", raise_if_not_found=False)
            if not user or not act_type:
                continue
            Activity.create(
                {
                    "res_model_id": self.env["ir.model"]._get(rec._name).id,
                    "res_id": rec.id,
                    "activity_type_id": act_type.id,
                    "summary": _("Modération fiche — %s") % rec.name,
                    "note": _(
                        "Le commerçant a envoyé sa fiche Mon Coin. "
                        "Relire puis Publier (carte) ou Refuser."
                    ),
                    "user_id": user.id,
                }
            )

    def _ensure_partner(self):
        self.ensure_one()
        if self.partner_id:
            return self.partner_id
        partner = self.env["res.partner"].sudo().create(
            {
                "name": self.name,
                "email": self.email or False,
                "phone": self.phone or False,
                "street": self.street or False,
                "city": self.city or False,
                "is_company": True,
            }
        )
        self.sudo().write({"partner_id": partner.id})
        return partner

    def _portal_group_ids(self):
        portal = self.env.ref("base.group_portal", raise_if_not_found=False)
        commercant = self.env.ref(
            "coins_quebec.group_coins_quebec_commercant", raise_if_not_found=False
        )
        ids = []
        if portal:
            ids.append(portal.id)
        if commercant:
            ids.append(commercant.id)
        return ids

    def action_create_portal_user(self, password=None):
        """Crée le compte portail lié 1-1 à cette fiche."""
        self.ensure_one()
        if self.portal_user_id:
            return self.portal_user_id
        email = (self.email or "").strip().lower()
        if not email:
            raise UserError(_("Indiquez un courriel avant de créer le compte portail."))
        existing = (
            self.env["res.users"]
            .sudo()
            .with_context(active_test=False)
            .search([("login", "=", email)], limit=1)
        )
        if existing:
            raise UserError(_("Ce courriel a déjà un compte : %s") % email)
        partner = self._ensure_partner()
        pwd = password or secrets.token_urlsafe(12)
        vals = {
            "name": self.contact_name or self.name,
            "login": email,
            "email": email,
            "password": pwd,
            "partner_id": partner.id,
            "share": True,
        }
        groups = self._portal_group_ids()
        if "group_ids" in self.env["res.users"]._fields:
            vals["group_ids"] = [(6, 0, groups)]
        else:
            vals["groups_id"] = [(6, 0, groups)]
        user = (
            self.env["res.users"]
            .sudo()
            .with_context(no_reset_password=True, mail_create_nolog=True)
            .create(vals)
        )
        self.sudo().write({"portal_user_id": user.id, "partner_id": partner.id})
        return user

    def _finance_team(self, brand):
        if brand == "itex":
            team = self.env.ref(
                "intellix_finance.crm_team_itex", raise_if_not_found=False
            )
            return team or self.env["crm.team"].sudo().browse(ITEX_TEAM_ID)
        if brand == "driven":
            team = self.env.ref(
                "renovation_conciergerie.crm_team_driven", raise_if_not_found=False
            )
            return team or self.env["crm.team"].sudo().browse(DRIVEN_TEAM_ID)
        return self.env["crm.team"]

    def action_take_itex_boost(self, note=""):
        """Create/update crm.lead team ITEX (112) — pas d’entonnoir parallèle."""
        self.ensure_one()
        if self.is_demo or self.env.context.get("mon_coin_demo"):
            raise UserError(_("Mode démo — aucun lead ITEX n’est créé."))
        team = self._finance_team("itex")
        if not team or not team.exists():
            raise UserError(_("Équipe ITEX introuvable (team 112)."))
        partner = self._ensure_partner()
        Lead = self.env["crm.lead"].sudo()
        lead = self.itex_lead_id
        vals = {
            "name": _("ITEX — %s") % self.name,
            "team_id": team.id,
            "partner_id": partner.id,
            "contact_name": self.contact_name or False,
            "email_from": self.email or False,
            "phone": self.phone or False,
            "type": "opportunity",
            "description": note
            or _("Demande « Je prends mon boost » — portail Mon Coin."),
        }
        if "cq_partenariat_id" in Lead._fields:
            vals["cq_partenariat_id"] = self.id
        if "itex_funnel_stage" in Lead._fields and (not lead or not lead.itex_funnel_stage):
            vals["itex_funnel_stage"] = "nouveau"
        stage = self.env.ref(
            "intellix_finance.crm_stage_itex_nouveau", raise_if_not_found=False
        )
        if stage and (not lead or lead.stage_id != stage):
            vals["stage_id"] = stage.id
        if lead and lead.exists():
            lead.write(vals)
        else:
            lead = Lead.create(vals)
            self.sudo().write({"itex_lead_id": lead.id})
        boost = self._create_boost_request("itex", note, lead=lead)
        return lead, boost

    def action_take_driven_boost(self, note=""):
        """Create/update crm.lead team Driven (94) — pas de 3e pipeline."""
        self.ensure_one()
        if self.is_demo or self.env.context.get("mon_coin_demo"):
            raise UserError(_("Mode démo — aucun lead Driven n’est créé."))
        team = self._finance_team("driven")
        if not team or not team.exists():
            raise UserError(_("Équipe Driven introuvable (team 94)."))
        partner = self._ensure_partner()
        Lead = self.env["crm.lead"].sudo()
        lead = self.driven_lead_id
        vals = {
            "name": _("Driven — %s") % self.name,
            "team_id": team.id,
            "contact_name": self.contact_name or False,
            "phone": self.phone or False,
            "type": "opportunity",
            "description": note
            or _("Demande financement B2B — portail Mon Coin (onglet Driven)."),
        }
        # doorway_crm : email unique sur crm.lead. Le partenaire ITEX
        # recopie email_from — on ne le relie pas ici.
        if self.email and not Lead.search(
            [("email_from", "=", self.email)],
            limit=1,
        ):
            vals["partner_id"] = partner.id
            vals["email_from"] = self.email
        if "cq_partenariat_id" in Lead._fields:
            vals["cq_partenariat_id"] = self.id
        if "finance_brand" in Lead._fields:
            pass
        if "finance_funnel_stage" in Lead._fields and (
            not lead or not lead.finance_funnel_stage
        ):
            vals["finance_funnel_stage"] = "lead_contacted"
        if lead and lead.exists():
            lead.write(vals)
        else:
            lead = Lead.create(vals)
            self.sudo().write({"driven_lead_id": lead.id})
        boost = self._create_boost_request("driven", note, lead=lead)
        return lead, boost

    def action_request_boost(self, kind, note=""):
        self.ensure_one()
        if self.is_demo or self.env.context.get("mon_coin_demo"):
            raise UserError(
                _("Mode démo — aucune demande réelle n’est créée (ITEX / Driven / boost).")
            )
        if kind == "itex":
            return self.action_take_itex_boost(note)
        if kind == "driven":
            return self.action_take_driven_boost(note)
        if kind not in ("radio", "vedette", "influenceurs", "reseaux"):
            raise UserError(_("Type de boost inconnu."))
        boost = self._create_boost_request(kind, note)
        return False, boost

    def _create_boost_request(self, kind, note, lead=None):
        self.ensure_one()
        labels = dict(self.env["coins.quebec.boost.request"]._fields["kind"].selection)
        name = _("Boost %s — %s") % (labels.get(kind, kind), self.name)
        boost = (
            self.env["coins.quebec.boost.request"]
            .sudo()
            .create(
                {
                    "name": name,
                    "partenariat_id": self.id,
                    "kind": kind,
                    "note": note or False,
                    "lead_id": lead.id if lead else False,
                    "lead_ref": str(lead.id) if lead else False,
                }
            )
        )
        act_type = self.env.ref(
            "coins_quebec.mail_activity_boost_%s" % kind, raise_if_not_found=False
        ) or self.env.ref("mail.mail_activity_data_todo", raise_if_not_found=False)
        user = self.coins_commercial_assigne or self.user_id
        if not user or user.share:
            user = self.env.ref("base.user_admin", raise_if_not_found=False)
        if act_type and user:
            activity = (
                self.env["mail.activity"]
                .sudo()
                .create(
                    {
                        "res_model_id": self.env["ir.model"]._get(self._name).id,
                        "res_id": self.id,
                        "activity_type_id": act_type.id,
                        "summary": name,
                        "note": note
                        or _("Demande de boost %s depuis Mon Coin.") % labels.get(kind, kind),
                        "user_id": user.id,
                    }
                )
            )
            boost.activity_id = activity.id
        self.message_post(body=_("Demande de boost : %s") % labels.get(kind, kind))
        return boost

    def increment_pin_view(self):
        real = self.filtered(lambda r: not r.is_demo)
        for rec in real:
            rec.sudo().write({"pin_view_count": (rec.pin_view_count or 0) + 1})

    def increment_pin_click(self):
        real = self.filtered(lambda r: not r.is_demo)
        for rec in real:
            rec.sudo().write({"pin_click_count": (rec.pin_click_count or 0) + 1})

    def save_authorize_credentials(self, login_id, trans_key):
        """Stocke côté serveur — jamais renvoyé au navigateur."""
        self.ensure_one()
        if self.is_demo or self.env.context.get("mon_coin_demo"):
            raise UserError(_("Mode démo — aucune clé Authorize.net n’est enregistrée."))
        login_id = (login_id or "").strip()
        trans_key = (trans_key or "").strip()
        vals = {}
        if login_id:
            vals["authorize_login"] = login_id
        if trans_key:
            vals["authorize_trans_key"] = trans_key
        if vals:
            self.sudo().write(vals)
        return self.authorize_connected

    def clear_authorize_credentials(self):
        self.ensure_one()
        if self.is_demo or self.env.context.get("mon_coin_demo"):
            raise UserError(_("Mode démo — aucune clé Authorize.net n’est enregistrée."))
        self.sudo().write(
            {"authorize_login": False, "authorize_trans_key": False}
        )

    def portal_finance_payload(self):
        """Revenu CQ réel + Driven si lead — zéro honnête si rien."""
        self.ensure_one()
        Resa = self.env["coins.quebec.reservation"].sudo()
        prop = self.sudo().property_id
        domain = [("state", "not in", ("cancelled",))]
        if prop:
            domain.append(("property_id", "=", prop.id))
            mine = Resa.search(domain, order="check_in desc", limit=20)
        else:
            mine = Resa.browse()
        lines = []
        revenue = 0.0
        commission = 0.0
        pct = (prop.commission_pct if prop else 15.0) or 15.0
        for resa in mine:
            if (resa.name or "") == "CQ-RES/2026/0001":
                continue
            amount = resa.amount_property or resa.amount_total or 0.0
            comm = round(amount * pct / 100.0, 2)
            revenue += amount
            commission += comm
            lines.append(
                {
                    "name": resa.name,
                    "date": resa.check_in,
                    "amount": amount,
                    "commission": comm,
                    "payment": resa.payment_status,
                    "demo": bool(self.is_demo or resa.is_demo),
                }
            )
        extra_demo = False
        if self.is_demo:
            extra_demo = False
        elif not lines:
            other = Resa.search(
                [
                    ("state", "not in", ("cancelled", "draft")),
                    ("name", "!=", "CQ-RES/2026/0001"),
                ],
                order="check_in desc",
                limit=1,
            )
            if other:
                extra_demo = {
                    "name": other.name,
                    "date": other.check_in,
                    "amount": other.amount_property or other.amount_total or 0.0,
                    "commission": 0.0,
                    "payment": other.payment_status,
                    "demo": True,
                    "label": _(
                        "Exemple plateforme (autre établissement) — pas votre revenu"
                    ),
                }
        driven = False
        lead = self.sudo().driven_lead_id
        if lead:
            driven = {
                "name": lead.name,
                "stage": lead.finance_funnel_stage
                if "finance_funnel_stage" in lead._fields
                else False,
                "amount": lead.expected_revenue or 0.0,
                "monthly": lead.driven_monthly_revenue
                if "driven_monthly_revenue" in lead._fields
                else 0.0,
                "status": lead.finance_prequal_status
                if "finance_prequal_status" in lead._fields
                else False,
            }
        return {
            "revenue": revenue,
            "commission": commission,
            "lines": lines,
            "extra_demo": extra_demo,
            "driven": driven,
        }

    def to_public_listing(self):
        self.ensure_one()
        region_label = dict(self._fields["region"].selection).get(self.region, "")
        cat_map = {
            "resto": "gourmand",
            "hebergement": "hebergement",
            "spa": "bien-etre",
            "activite": "plein-air",
            "evenement": "evenement",
            "autre": "autre",
        }
        photos = []
        for photo in self.photo_ids:
            photos.append(
                "/coins-quebec/carte/photo/%s" % photo.id
            )
        return {
            "id": "cq_%s" % self.id,
            "odoo_id": self.id,
            "name": self.name,
            "role": "merchant",
            "status": self.publish_state,
            "region": region_label,
            "category": cat_map.get(self.type_partenaire, "autre"),
            "themes": [cat_map.get(self.type_partenaire, "autre")],
            "description": self.description or "",
            "address": ", ".join(
                [p for p in [self.street, self.city, "QC"] if p]
            ),
            "lat": self.partner_lat or None,
            "lng": self.partner_lng or None,
            "video_url": self.video_url or "",
            "photos": photos,
            "photos_carte": photos,
            "services": [
                {
                    "name": s.name,
                    "price": ("%.2f $" % s.price) if s.price else "",
                    "unit": s.unit or "",
                }
                for s in self.service_ids
            ],
            "packages": [
                {
                    "name": o.name,
                    "price": ("%.2f $" % o.price) if o.price else "",
                    "unit": o.unit or "",
                }
                for o in self.offer_ids
            ],
            "featured": False,
            "stats": {
                "views": self.pin_view_count or 0,
                "clicks": self.pin_click_count or 0,
                "bookings": self.reservation_public_count or 0,
            },
            "contact_public": {
                "phone": self.phone or "",
                "email": self.email or "",
            },
        }
