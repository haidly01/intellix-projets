# -*- coding: utf-8 -*-
"""ITEX sur crm.lead partagé (comme Driven / CM), pas un modèle coins.itex.*.

Équipe ITEX + vues / actions dédiées (fin-itex). Ne jamais hériter ni
réutiliser le formulaire partenariat Coins Marocain.
"""
import logging
from datetime import timedelta

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

ITEX_FUNNEL_STAGES = [
    ("nouveau", "Nouveau / à pitcher"),
    ("pitch_fait", "Pitch fait"),
    ("interet_confirme", "Intérêt confirmé"),
    ("documentation", "Documentation"),
    ("reporte", "Reporté"),
    ("paiement_initial", "Paiement initial"),
    ("adherent", "Adhérent / mensualités"),
    ("perdu", "Perdu"),
]
ITEX_FUNNEL_SEQ = {key: idx + 1 for idx, (key, _label) in enumerate(ITEX_FUNNEL_STAGES)}
ITEX_STAGE_XMLIDS = {
    "nouveau": "intellix_finance.crm_stage_itex_nouveau",
    "pitch_fait": "intellix_finance.crm_stage_itex_pitch_fait",
    "interet_confirme": "intellix_finance.crm_stage_itex_interet_confirme",
    "documentation": "intellix_finance.crm_stage_itex_documentation",
    "reporte": "intellix_finance.crm_stage_itex_reporte",
    "paiement_initial": "intellix_finance.crm_stage_itex_paiement_initial",
    "adherent": "intellix_finance.crm_stage_itex_adherent",
    "perdu": "intellix_finance.crm_stage_itex_perdu",
}
ITEX_DEFAULT_DOCS = ("Infos entreprise", "Preuves financières")
ITEX_RELANCABLE = ("interet_confirme", "reporte")
ITEX_PAID_TX_STATES = ("done", "authorized")
ITEX_HAPPY_PATH = [
    "nouveau",
    "pitch_fait",
    "interet_confirme",
    "documentation",
    "paiement_initial",
    "adherent",
]

STAGE_FROM_NAME = (
    (("sans réponse", "sans reponse", "silence"), "perdu"),
    (("perdu", "lost"), "perdu"),
    (("adhérent", "adherent", "mensual"), "adherent"),
    (("paiement", "500", "adhésion pay", "adhesion pay"), "paiement_initial"),
    (("report", "plus tard", "later"), "reporte"),
    (("doc",), "documentation"),
    (("intérêt", "interet", "interest"), "interet_confirme"),
    (("pitch",), "pitch_fait"),
    (("nouveau", "new", "pitcher"), "nouveau"),
)


class CrmLeadItex(models.Model):
    _inherit = "crm.lead"

    itex_funnel_stage = fields.Selection(
        ITEX_FUNNEL_STAGES,
        string="Étape ITEX",
        tracking=True,
        index=True,
    )
    itex_max_stage_seq = fields.Integer(default=0)
    itex_lost_subtype = fields.Selection(
        [
            ("sans_reponse", "Perdu — sans réponse"),
            ("autre", "Perdu — autre"),
        ],
        string="Sous-type de perte ITEX",
        tracking=True,
    )
    itex_date_relance = fields.Date(
        string="Date de relance suggérée",
        tracking=True,
        help="Pour un lead Reporté : date de suivi. Défaut = N jours ouvrés.",
    )
    itex_relance_count = fields.Integer(string="Tentatives de relance ITEX", default=0)
    itex_last_relance = fields.Datetime(string="Dernière relance ITEX")
    itex_relance_due = fields.Boolean(
        string="ITEX à relancer",
        compute="_compute_itex_relance_due",
        store=True,
        index=True,
    )
    itex_document_ids = fields.One2many(
        "itex.lead.document",
        "lead_id",
        string="Documentation reçue",
    )
    itex_service_offered_ids = fields.Many2many(
        "itex.exchange.service",
        "itex_lead_service_offered_rel",
        "lead_id",
        "service_id",
        string="Services offerts",
    )
    itex_service_sought_ids = fields.Many2many(
        "itex.exchange.service",
        "itex_lead_service_sought_rel",
        "lead_id",
        "service_id",
        string="Services recherchés",
    )
    itex_payment_status = fields.Selection(
        [
            ("non_paye", "Non payé"),
            ("adhesion_payee", "Adhésion payée"),
            ("mensualite_ok", "Mensualité en règle"),
            ("mensualite_retard", "Mensualité en retard"),
        ],
        string="Statut de paiement ITEX",
        compute="_compute_itex_payment_status",
        store=True,
        index=True,
    )
    itex_payment_provider_id = fields.Many2one(
        "payment.provider",
        string="Passerelle ITEX (CAD)",
        ondelete="set null",
        help="Authorize.net — même fondation CAD qu'Hébergement Coins Québec.",
    )
    itex_initial_transaction_id = fields.Many2one(
        "payment.transaction",
        string="Transaction adhésion 500 $",
        ondelete="set null",
        copy=False,
    )
    itex_monthly_transaction_ids = fields.One2many(
        "payment.transaction",
        "itex_monthly_lead_id",
        string="Transactions mensualités",
    )
    itex_payment_confirmed = fields.Boolean(
        string="Paiement initial confirmé",
        compute="_compute_itex_payment_status",
        store=True,
        help="Vert uniquement si payment.transaction est done/authorized.",
    )
    itex_initial_amount = fields.Monetary(
        string="Montant adhésion",
        currency_field="company_currency",
        default=500.0,
    )
    itex_monthly_amount = fields.Monetary(
        string="Montant mensualité",
        currency_field="company_currency",
    )
    itex_next_monthly_date = fields.Date(string="Prochaine mensualité")
    itex_late_alert_sent = fields.Boolean(string="Alerte retard envoyée", default=False)
    itex_secteur = fields.Char(
        string="Secteur d'activité",
        tracking=True,
        help="Secteur de l'entreprise ITEX — pas la catégorie / zone scrape Coins Marocain.",
    )

    def _itex_team(self):
        return self._finance_team("itex")

    @api.model
    def _read_group_stage_ids(self, stages, domain):
        """Colonnes ITEX = les 8 étapes de l'équipe 112, pas Nouveau global / Voyageurs."""
        team = self._itex_team()
        raw = self.env.context.get("default_team_id") or self.env.context.get(
            "renovation_active_pipeline_team_id"
        )
        if isinstance(raw, (list, tuple)):
            raw = raw[0] if raw else False
        try:
            ctx_team = int(raw) if raw else False
        except (TypeError, ValueError):
            ctx_team = False
        if team and (
            self.env.context.get("finance_pipeline") == "itex" or ctx_team == team.id
        ):
            dedicated = self.env["crm.stage"].search(
                [("team_ids", "in", [team.id])],
                order="sequence, id",
            )
            if dedicated:
                return dedicated
        return super()._read_group_stage_ids(stages, domain)

    def _itex_context_wants_itex(self):
        team = self._itex_team()
        if not team:
            return False
        if self.env.context.get("finance_pipeline") == "itex":
            return True
        if self.env.context.get("default_itex_funnel_stage"):
            return True
        raw = self.env.context.get("default_team_id") or self.env.context.get(
            "renovation_active_pipeline_team_id"
        )
        if isinstance(raw, (list, tuple)):
            raw = raw[0] if raw else False
        try:
            return bool(raw) and int(raw) == team.id
        except (TypeError, ValueError):
            return False

    def _itex_force_team_vals(self, vals):
        team = self._itex_team()
        if not team:
            return vals
        vals["team_id"] = team.id
        vals.setdefault("type", "opportunity")
        vals.setdefault("itex_funnel_stage", "nouveau")
        if "coins_fiche_type" in self._fields:
            vals["coins_fiche_type"] = False
        return vals

    @api.model
    def default_get(self, fields_list):
        defaults = super().default_get(fields_list)
        team = self._itex_team()
        if team and self._itex_context_wants_itex():
            if "team_id" in fields_list:
                defaults["team_id"] = team.id
            if "type" in fields_list:
                defaults["type"] = "opportunity"
            if "itex_funnel_stage" in fields_list:
                defaults.setdefault("itex_funnel_stage", "nouveau")
            if "coins_fiche_type" in fields_list:
                defaults["coins_fiche_type"] = False
        return defaults

    def _itex_is_itex(self):
        self.ensure_one()
        return self.finance_brand == "itex"

    def _itex_stage_record(self, key):
        xmlid = ITEX_STAGE_XMLIDS.get(key or "")
        return self.env.ref(xmlid, raise_if_not_found=False) if xmlid else self.env["crm.stage"]

    def _itex_key_from_stage(self, stage):
        for key, xmlid in ITEX_STAGE_XMLIDS.items():
            rec = self.env.ref(xmlid, raise_if_not_found=False)
            if rec and stage and rec.id == stage.id:
                return key
        name = (stage.display_name or stage.name or "").lower() if stage else ""
        for needles, key in STAGE_FROM_NAME:
            if any(n in name for n in needles):
                return key
        return "nouveau"

    def _itex_relance_business_days(self):
        raw = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("intellix_finance.itex_relance_business_days", "5")
        )
        try:
            return max(1, int(raw))
        except (TypeError, ValueError):
            return 5

    def _itex_relance_max_attempts(self):
        raw = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("intellix_finance.itex_relance_max_attempts", "3")
        )
        try:
            return max(2, int(raw))
        except (TypeError, ValueError):
            return 3

    def _itex_add_business_days(self, start, days):
        cursor = start
        added = 0
        while added < days:
            cursor += timedelta(days=1)
            if cursor.weekday() < 5:
                added += 1
        return cursor

    def _itex_business_days_between(self, start, end):
        if hasattr(self, "_reno_business_days_between"):
            return self._reno_business_days_between(start, end)
        if end < start:
            return 0
        days = 0
        cursor = start
        while cursor < end:
            cursor += timedelta(days=1)
            if cursor.weekday() < 5:
                days += 1
        return days

    @api.depends(
        "finance_brand",
        "itex_funnel_stage",
        "itex_date_relance",
        "itex_last_relance",
        "date_last_stage_update",
        "write_date",
        "create_date",
    )
    def _compute_itex_relance_due(self):
        today = fields.Date.context_today(self)
        n_days = self._itex_relance_business_days()
        for lead in self:
            if lead.finance_brand != "itex" or lead.itex_funnel_stage not in ITEX_RELANCABLE:
                lead.itex_relance_due = False
                continue
            if lead.itex_funnel_stage == "reporte" and lead.itex_date_relance:
                lead.itex_relance_due = today >= lead.itex_date_relance
                continue
            start = lead.itex_last_relance or lead.date_last_stage_update or lead.write_date or lead.create_date
            if not start:
                lead.itex_relance_due = False
                continue
            start_d = fields.Datetime.context_timestamp(lead, start).date() if hasattr(start, "hour") else start
            lead.itex_relance_due = lead._itex_business_days_between(start_d, today) >= n_days

    def _itex_initial_tx_done(self):
        self.ensure_one()
        tx = self.itex_initial_transaction_id
        return bool(tx and tx.state in ITEX_PAID_TX_STATES)

    @api.depends(
        "finance_brand",
        "itex_initial_transaction_id",
        "itex_initial_transaction_id.state",
        "itex_monthly_transaction_ids.state",
        "itex_next_monthly_date",
    )
    def _compute_itex_payment_status(self):
        today = fields.Date.context_today(self)
        for lead in self:
            if lead.finance_brand != "itex":
                lead.itex_payment_confirmed = False
                lead.itex_payment_status = False
                continue
            confirmed = lead._itex_initial_tx_done()
            lead.itex_payment_confirmed = confirmed
            if not confirmed:
                lead.itex_payment_status = "non_paye"
                continue
            monthly_done = lead.itex_monthly_transaction_ids.filtered(
                lambda t: t.state in ITEX_PAID_TX_STATES
            )
            if lead.itex_next_monthly_date and lead.itex_next_monthly_date < today:
                lead.itex_payment_status = "mensualite_retard"
            elif monthly_done:
                lead.itex_payment_status = "mensualite_ok"
            else:
                lead.itex_payment_status = "adhesion_payee"

    @api.model_create_multi
    def create(self, vals_list):
        team = self._itex_team()
        force = self._itex_context_wants_itex()
        for vals in vals_list:
            wants_itex = force or (team and vals.get("team_id") == team.id)
            if wants_itex:
                self._itex_force_team_vals(vals)
        leads = super().create(vals_list)
        leads._itex_sync_funnel_side_effects()
        leads._itex_ensure_default_documents()
        return leads

    def write(self, vals):
        if "itex_funnel_stage" in vals:
            gated = {}
            for lead in self:
                target = vals.get("itex_funnel_stage")
                if (
                    lead.finance_brand == "itex"
                    and target == "adherent"
                    and not lead._itex_initial_tx_done()
                ):
                    gated[lead.id] = True
            if gated and len(self) == 1:
                vals = dict(vals, itex_funnel_stage="paiement_initial")
            elif gated:
                others = self.filtered(lambda l: l.id not in gated)
                blocked = self.browse(list(gated))
                if others:
                    super(CrmLeadItex, others).write(vals)
                blocked_vals = dict(vals, itex_funnel_stage="paiement_initial")
                res = super(CrmLeadItex, blocked).write(blocked_vals)
                (others | blocked)._itex_sync_funnel_side_effects()
                if any(
                    key in vals
                    for key in ("team_id", "stage_id", "itex_funnel_stage")
                ):
                    (others | blocked)._itex_ensure_default_documents()
                return res
        team = self._itex_team()
        if self._itex_context_wants_itex() and team:
            vals = dict(vals)
            vals["team_id"] = team.id
            if "coins_fiche_type" in self._fields and "coins_fiche_type" not in vals:
                vals["coins_fiche_type"] = False
        elif team and vals.get("team_id") == team.id and "coins_fiche_type" in self._fields:
            vals = dict(vals)
            vals["coins_fiche_type"] = False
        res = super().write(vals)
        if any(
            key in vals
            for key in (
                "itex_funnel_stage",
                "itex_lost_subtype",
                "team_id",
                "stage_id",
                "itex_date_relance",
            )
        ):
            self._itex_sync_funnel_side_effects(
                prefer_stage="stage_id" in vals and "itex_funnel_stage" not in vals,
                prefer_field="itex_funnel_stage" in vals,
            )
        if any(key in vals for key in ("team_id", "itex_funnel_stage")):
            self._itex_ensure_default_documents()
        return res

    def _itex_sync_funnel_side_effects(self, prefer_stage=False, prefer_field=False):
        today = fields.Date.context_today(self)
        n_days = self._itex_relance_business_days()
        for lead in self:
            if lead.finance_brand != "itex":
                if lead.itex_funnel_stage:
                    super(CrmLeadItex, lead).write({"itex_funnel_stage": False})
                continue
            updates = {}
            key_from_stage = lead._itex_key_from_stage(lead.stage_id) if lead.stage_id else False
            key_from_field = lead.itex_funnel_stage
            if prefer_stage and key_from_stage:
                key = key_from_stage
                if key != key_from_field:
                    updates["itex_funnel_stage"] = key
            elif key_from_field:
                key = key_from_field
            else:
                key = key_from_stage or "nouveau"
                updates["itex_funnel_stage"] = key
            seq = ITEX_FUNNEL_SEQ.get(updates.get("itex_funnel_stage") or key or "", 0)
            if seq > (lead.itex_max_stage_seq or 0):
                updates["itex_max_stage_seq"] = seq
            stage_key = updates.get("itex_funnel_stage") or key
            if stage_key == "reporte" and not (updates.get("itex_date_relance") or lead.itex_date_relance):
                updates["itex_date_relance"] = lead._itex_add_business_days(today, n_days)
            if stage_key == "paiement_initial" and not lead.itex_initial_transaction_id:
                try:
                    with lead.env.cr.savepoint():
                        lead._itex_prepare_initial_transaction()
                except Exception:  # noqa: BLE001
                    _logger.exception("ITEX: préparation paiement initial ignorée")
            if stage_key == "adherent" and not lead._itex_initial_tx_done():
                updates["itex_funnel_stage"] = "paiement_initial"
                stage_key = "paiement_initial"
            if stage_key != "perdu" and lead.itex_lost_subtype:
                updates["itex_lost_subtype"] = False
            target_stage = lead._itex_stage_record(stage_key)
            if target_stage and lead.stage_id != target_stage:
                updates["stage_id"] = target_stage.id
            if not lead.itex_payment_provider_id:
                provider = lead._itex_cad_payment_provider()
                if provider:
                    updates["itex_payment_provider_id"] = provider.id
            if updates:
                super(CrmLeadItex, lead).write(updates)

    def _itex_ensure_default_documents(self):
        Doc = self.env["itex.lead.document"]
        for lead in self:
            if lead.finance_brand != "itex" or lead.itex_document_ids:
                continue
            for name in ITEX_DEFAULT_DOCS:
                Doc.create({"lead_id": lead.id, "name": name, "status": "attendu"})

    def _itex_cad_payment_provider(self):
        """CAD path = Authorize.net, same lookup as Hébergement Coins Québec."""
        if "payment.provider" not in self.env:
            return self.env["payment.provider"]
        Provider = self.env["payment.provider"].sudo()
        if self.itex_payment_provider_id:
            return self.itex_payment_provider_id
        prov = Provider.search([("code", "=", "authorize")], limit=1)
        if not prov:
            prov = Provider.search([("name", "ilike", "Authorize")], limit=1)
        return prov

    def _itex_cad_currency(self):
        return self.env["res.currency"].search([("name", "=", "CAD")], limit=1) or self.env.company.currency_id

    def _itex_payment_method(self):
        if "payment.method" not in self.env:
            return self.env["payment.method"]
        Method = self.env["payment.method"].sudo().with_context(active_test=False)
        return Method.search([("code", "=", "card")], limit=1) or Method.search([], limit=1)

    def _itex_prepare_initial_transaction(self):
        if "payment.transaction" not in self.env:
            return self.env["payment.transaction"]
        created = self.env["payment.transaction"]
        Tx = self.env["payment.transaction"].sudo()
        cad = self._itex_cad_currency()
        for lead in self:
            if lead.itex_initial_transaction_id:
                created |= lead.itex_initial_transaction_id
                continue
            provider = lead._itex_cad_payment_provider()
            if not provider:
                continue
            partner = lead.partner_id or lead.env.user.partner_id
            amount = lead.itex_initial_amount or 500.0
            vals = {
                "provider_id": provider.id,
                "amount": amount,
                "currency_id": cad.id,
                "partner_id": partner.id,
                "reference": "ITEX-INIT-%s" % lead.id,
                "itex_initial_lead_id": lead.id,
            }
            method = self._itex_payment_method()
            if "payment_method_id" in Tx._fields and method:
                vals["payment_method_id"] = method.id
            try:
                with lead.env.cr.savepoint():
                    tx = Tx.create(vals)
                    if hasattr(tx, "_set_pending"):
                        try:
                            tx._set_pending()
                        except Exception:  # noqa: BLE001
                            tx.write({"state": "pending"})
                    super(CrmLeadItex, lead).write({"itex_initial_transaction_id": tx.id})
                    created |= tx
            except Exception:  # noqa: BLE001
                _logger.exception("ITEX: création payment.transaction initiale échouée")
                continue
        return created

    def action_itex_prepare_initial_payment(self):
        self.ensure_one()
        tx = self._itex_prepare_initial_transaction()
        if not tx:
            return False
        return {
            "type": "ir.actions.act_window",
            "res_model": "payment.transaction",
            "res_id": tx.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_itex_capture_initial_payment(self):
        """Capture manuelle — même idée qu'Hébergement (riad action_capture_payment)."""
        self.ensure_one()
        tx = self.itex_initial_transaction_id or self._itex_prepare_initial_transaction()
        if not tx:
            return False
        if tx.state in ITEX_PAID_TX_STATES:
            self._itex_on_initial_payment_confirmed()
            return True
        if hasattr(tx, "_send_capture_request"):
            try:
                tx._send_capture_request()
                if tx.state in ITEX_PAID_TX_STATES:
                    self._itex_on_initial_payment_confirmed()
                return True
            except Exception:  # noqa: BLE001
                _logger.exception("ITEX: capture Authorize.net non disponible")
        return {
            "type": "ir.actions.act_window",
            "res_model": "payment.transaction",
            "res_id": tx.id,
            "view_mode": "form",
            "target": "current",
        }

    def _itex_on_initial_payment_confirmed(self):
        today = fields.Date.context_today(self)
        for lead in self:
            if lead.itex_funnel_stage == "adherent" and lead.itex_next_monthly_date:
                continue
            updates = {
                "itex_funnel_stage": "adherent",
                "itex_late_alert_sent": False,
            }
            if not lead.itex_next_monthly_date:
                updates["itex_next_monthly_date"] = today + timedelta(days=30)
            seq = ITEX_FUNNEL_SEQ["adherent"]
            if seq > (lead.itex_max_stage_seq or 0):
                updates["itex_max_stage_seq"] = seq
            super(CrmLeadItex, lead).write(updates)
            lead._itex_sync_funnel_side_effects()
            lead.message_post(
                body="Paiement initial ITEX confirmé (payment.transaction %s). "
                "Étape 7 Adhérent / mensualités ouverte."
                % (lead.itex_initial_transaction_id.reference or lead.itex_initial_transaction_id.id)
            )

    def _itex_prepare_monthly_transaction(self):
        if "payment.transaction" not in self.env:
            return self.env["payment.transaction"]
        Tx = self.env["payment.transaction"].sudo()
        cad = self._itex_cad_currency()
        created = Tx.browse()
        for lead in self:
            if not lead._itex_initial_tx_done():
                continue
            pending = lead.itex_monthly_transaction_ids.filtered(
                lambda t: t.state in ("draft", "pending")
            )
            if pending:
                created |= pending[:1]
                continue
            provider = lead._itex_cad_payment_provider()
            if not provider:
                continue
            amount = lead.itex_monthly_amount or 0.0
            if amount <= 0:
                continue
            partner = lead.partner_id or lead.env.user.partner_id
            vals = {
                "provider_id": provider.id,
                "amount": amount,
                "currency_id": cad.id,
                "partner_id": partner.id,
                "reference": "ITEX-MENSU-%s-%s" % (lead.id, fields.Date.context_today(lead)),
                "itex_monthly_lead_id": lead.id,
            }
            method = self._itex_payment_method()
            if "payment_method_id" in Tx._fields and method:
                vals["payment_method_id"] = method.id
            try:
                with lead.env.cr.savepoint():
                    tx = Tx.create(vals)
                    created |= tx
            except Exception:  # noqa: BLE001
                _logger.exception("ITEX: création payment.transaction mensualité échouée")
                continue
        return created

    def _itex_on_monthly_payment_confirmed(self):
        today = fields.Date.context_today(self)
        for lead in self:
            super(CrmLeadItex, lead).write(
                {
                    "itex_next_monthly_date": today + timedelta(days=30),
                    "itex_late_alert_sent": False,
                }
            )

    def _itex_send_package_late_alert(self):
        """Reuse Réno Immobilier forfait late-alert (same helper + destination)."""
        self.ensure_one()
        Package = self.env["renovation.partner.package"]
        pkg = Package.browse()
        if self.partner_id:
            pkg = Package.search([("partner_id", "=", self.partner_id.id)], limit=1)
        if pkg and hasattr(pkg, "_send_renewal_alert"):
            pkg._send_renewal_alert()
            return True
        email_to = "comptabilite@agencedoorway.com"
        template = self.env.ref(
            "renovation_conciergerie.mail_template_renewal_alert",
            raise_if_not_found=False,
        )
        if template and pkg:
            template.send_mail(
                pkg.id,
                force_send=True,
                email_values={"email_to": email_to},
            )
            return True
        self.message_post(
            body="Alerte mensualité ITEX en retard — circuit alerte forfait Réno Immobilier."
        )
        self.env["mail.mail"].sudo().create(
            {
                "subject": "ITEX — mensualité en retard",
                "email_to": email_to,
                "body_html": "<p>Mensualité en retard pour %s.</p>" % (self.display_name,),
            }
        ).send()
        return True

    def _itex_notify_relance(self, to_prospect=False):
        template = self.env.ref(
            "intellix_finance.mail_template_itex_relance",
            raise_if_not_found=False,
        )
        for lead in self:
            if lead.user_id:
                try:
                    lead.activity_schedule(
                        "mail.mail_activity_data_todo",
                        user_id=lead.user_id.id,
                        summary="Relance ITEX",
                        note="Lead resté à « %s » sans progression."
                        % dict(ITEX_FUNNEL_STAGES).get(lead.itex_funnel_stage, lead.itex_funnel_stage),
                    )
                except Exception:  # noqa: BLE001
                    _logger.exception("ITEX: activité de relance")
                if template:
                    try:
                        template.send_mail(lead.id, force_send=False)
                    except Exception:  # noqa: BLE001
                        _logger.exception("ITEX: email relance commercial")
            if to_prospect and lead.email_from and template:
                try:
                    template.send_mail(
                        lead.id,
                        force_send=False,
                        email_values={"email_to": lead.email_from},
                    )
                except Exception:  # noqa: BLE001
                    _logger.exception("ITEX: email relance prospect")
            if to_prospect and (lead.mobile or lead.phone) and hasattr(lead, "_message_sms"):
                try:
                    lead._message_sms(
                        "ITEX : nous relançons votre dossier d'adhésion. "
                        "Votre conseiller vous recontacte.",
                    )
                except Exception:  # noqa: BLE001
                    _logger.exception("ITEX: SMS relance prospect")

    @api.model
    def _cron_itex_relance(self):
        to_prospect = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("intellix_finance.itex_relance_prospect", "0")
        ) in ("1", "true", "True")
        max_attempts = self._itex_relance_max_attempts()
        leads = self.sudo().search(
            [
                ("finance_brand", "=", "itex"),
                ("itex_funnel_stage", "in", list(ITEX_RELANCABLE)),
                ("itex_relance_due", "=", True),
            ]
        )
        for lead in leads:
            count = (lead.itex_relance_count or 0) + 1
            if count >= max_attempts:
                super(CrmLeadItex, lead).write(
                    {
                        "itex_funnel_stage": "perdu",
                        "itex_lost_subtype": "sans_reponse",
                        "itex_relance_count": count,
                        "itex_last_relance": fields.Datetime.now(),
                    }
                )
                lead._itex_sync_funnel_side_effects()
                lead.message_post(
                    body="Escalade ITEX : %s relances sans progression → Perdu — sans réponse."
                    % count
                )
                continue
            super(CrmLeadItex, lead).write(
                {
                    "itex_relance_count": count,
                    "itex_last_relance": fields.Datetime.now(),
                }
            )
            lead._itex_notify_relance(to_prospect=to_prospect)
        return len(leads)

    @api.model
    def _cron_itex_monthly_late(self):
        today = fields.Date.context_today(self)
        leads = self.sudo().search(
            [
                ("finance_brand", "=", "itex"),
                ("itex_payment_confirmed", "=", True),
                ("itex_next_monthly_date", "!=", False),
                ("itex_next_monthly_date", "<", today),
                ("itex_late_alert_sent", "=", False),
            ]
        )
        for lead in leads:
            lead._itex_send_package_late_alert()
            super(CrmLeadItex, lead).write({"itex_late_alert_sent": True})
            lead._itex_prepare_monthly_transaction()
        return len(leads)

    @api.model
    def _itex_ensure_funnel(self):
        """Crée / réordonne les 8 étapes ITEX sans supprimer de leads."""
        team = self._itex_team()
        if not team:
            return 0
        specs = [
            ("nouveau", "Nouveau / à pitcher", 10, False),
            ("pitch_fait", "Pitch fait", 20, False),
            ("interet_confirme", "Intérêt confirmé", 30, False),
            ("documentation", "Documentation", 40, False),
            ("reporte", "Reporté", 50, False),
            ("paiement_initial", "Paiement initial", 60, False),
            ("adherent", "Adhérent / mensualités", 70, True),
            ("perdu", "Perdu", 80, False),
        ]
        Stage = self.env["crm.stage"].sudo()
        Imd = self.env["ir.model.data"].sudo()
        for key, name, sequence, is_won in specs:
            stage = self._itex_stage_record(key)
            vals = {
                "name": name,
                "sequence": sequence,
                "fold": False,
                "team_ids": [(6, 0, [team.id])],
            }
            if "is_won" in Stage._fields:
                vals["is_won"] = is_won
            xmlid_name = ITEX_STAGE_XMLIDS[key].split(".")[-1]
            imd = Imd.search(
                [("module", "=", "intellix_finance"), ("name", "=", xmlid_name)],
                limit=1,
            )
            if stage:
                stage.write(vals)
            elif imd and imd.res_id:
                stage = Stage.browse(imd.res_id)
                if stage.exists():
                    stage.write(vals)
                else:
                    stage = Stage.create(vals)
                    imd.write({"res_id": stage.id, "model": "crm.stage"})
            else:
                stage = Stage.create(vals)
                Imd.create(
                    {
                        "name": xmlid_name,
                        "module": "intellix_finance",
                        "model": "crm.stage",
                        "res_id": stage.id,
                        "noupdate": True,
                    }
                )
                _logger.info("ITEX: étape %s créée (id %s)", key, stage.id)
        self._itex_reclaim_test_lead()
        return self._itex_remap_leads()

    @api.model
    def _itex_reclaim_test_lead(self):
        """Replace le lead test Martin Houle (2127) sur l'équipe ITEX, sans le supprimer."""
        team = self._itex_team()
        if not team:
            return False
        Lead = self.sudo().with_context(active_test=False)
        lead = Lead.browse(2127)
        if not lead.exists() or "[TEST] Appel ITEX" not in (lead.name or ""):
            lead = Lead.search(
                [("name", "ilike", "[TEST] Appel ITEX — Martin Houle")],
                limit=1,
            )
        if not lead:
            return False
        vals = {
            "team_id": team.id,
            "type": "opportunity",
            "itex_funnel_stage": lead.itex_funnel_stage or "nouveau",
        }
        if "coins_fiche_type" in lead._fields:
            vals["coins_fiche_type"] = False
        lead.write(vals)
        lead._itex_sync_funnel_side_effects()
        lead._itex_ensure_default_documents()
        _logger.info(
            "ITEX: lead test %s (%s) remis sur l'équipe ITEX %s",
            lead.id,
            lead.name,
            team.id,
        )
        return lead.id

    @api.model
    def _itex_remap_leads(self):
        team = self._itex_team()
        if not team:
            return 0
        leads = self.sudo().with_context(active_test=False).search([("team_id", "=", team.id)])
        remapped = 0
        for lead in leads:
            key = lead.itex_funnel_stage or lead._itex_key_from_stage(lead.stage_id)
            if not lead.itex_funnel_stage or lead.itex_funnel_stage != key:
                super(CrmLeadItex, lead).write({"itex_funnel_stage": key})
                remapped += 1
            lead._itex_sync_funnel_side_effects()
            lead._itex_ensure_default_documents()
        self._itex_spread_demo_stages(leads)
        return remapped

    def _itex_spread_demo_stages(self, leads):
        """Répartit uniquement les démos ITEX pour rendre l'entonnoir lisible."""
        from .crm_lead_finance import DEMO_NAME_PREFIX

        demo = leads.filtered(lambda l: (l.name or "").startswith(DEMO_NAME_PREFIX + " Itex"))
        if not demo or any(
            l.itex_funnel_stage and l.itex_funnel_stage != "nouveau" for l in demo
        ):
            return
        keys = [key for key, _lab in ITEX_FUNNEL_STAGES if key not in ("adherent", "paiement_initial")]
        for idx, lead in enumerate(demo):
            key = keys[idx % len(keys)]
            super(CrmLeadItex, lead).write({"itex_funnel_stage": key})
            lead._itex_sync_funnel_side_effects()

    def _itex_funnel_stats(self, province=False, lang=False):
        team = self._itex_team()
        empty_stages = [
            {
                "key": key,
                "label": lab,
                "count": 0,
                "seq": ITEX_FUNNEL_SEQ[key],
                "confirmed": 0,
                "green": False,
            }
            for key, lab in ITEX_FUNNEL_STAGES
        ]
        empty = {
            "stages": empty_stages,
            "conversions": [],
            "silence": {
                "label": "Abandon intérêt → silence",
                "lost": 0,
                "reached": 0,
                "rate": None,
            },
            "documentary": {
                "label": "Abandon documentaire",
                "lost": 0,
                "reached": 0,
                "rate": None,
            },
            "in_funnel": 0,
            "adherent": 0,
            "approval_rate": None,
            "cycle_days_avg": None,
            "target_approval": 0.30,
            "team_id": team.id if team else False,
        }
        if not team:
            return empty
        domain = [
            ("team_id", "=", team.id),
            ("type", "in", ("lead", "opportunity")),
        ] + self._finance_segment_domain(province, lang)
        leads = self.sudo().search(domain)
        empty["in_funnel"] = len(leads)
        if not leads:
            return empty
        stage_counts = {key: 0 for key, _lab in ITEX_FUNNEL_STAGES}
        confirmed_pay = 0
        for lead in leads:
            key = lead.itex_funnel_stage
            if key in stage_counts:
                stage_counts[key] += 1
            if key == "paiement_initial" and lead.itex_payment_confirmed:
                confirmed_pay += 1
        empty["stages"] = [
            {
                "key": key,
                "label": lab,
                "count": stage_counts[key],
                "seq": ITEX_FUNNEL_SEQ[key],
                "confirmed": confirmed_pay if key == "paiement_initial" else 0,
                "green": bool(key == "paiement_initial" and confirmed_pay),
            }
            for key, lab in ITEX_FUNNEL_STAGES
        ]

        def _reached(min_seq):
            return leads.filtered(lambda l: (l.itex_max_stage_seq or 0) >= min_seq)

        labels = dict(ITEX_FUNNEL_STAGES)
        conversions = []
        for idx, key in enumerate(ITEX_HAPPY_PATH[:-1]):
            nxt_key = ITEX_HAPPY_PATH[idx + 1]
            reached = _reached(ITEX_FUNNEL_SEQ[key])
            nxt = _reached(ITEX_FUNNEL_SEQ[nxt_key])
            conversions.append(
                {
                    "from_key": key,
                    "from_label": labels[key],
                    "to_key": nxt_key,
                    "to_label": labels[nxt_key],
                    "reached": len(reached),
                    "next": len(nxt),
                    "rate": (len(nxt) / len(reached)) if reached else None,
                }
            )
        empty["conversions"] = conversions
        interest = _reached(ITEX_FUNNEL_SEQ["interet_confirme"])
        silence = leads.filtered(
            lambda l: l.itex_funnel_stage == "perdu" and l.itex_lost_subtype == "sans_reponse"
        )
        empty["silence"] = {
            "label": "Abandon intérêt → silence",
            "lost": len(silence),
            "reached": len(interest),
            "rate": (len(silence) / len(interest)) if interest else None,
        }
        doc_reached = _reached(ITEX_FUNNEL_SEQ["documentation"])
        doc_lost = leads.filtered(
            lambda l: (l.itex_max_stage_seq or 0) >= ITEX_FUNNEL_SEQ["documentation"]
            and l.itex_funnel_stage == "perdu"
            and l.itex_lost_subtype != "sans_reponse"
        )
        empty["documentary"] = {
            "label": "Abandon documentaire",
            "lost": len(doc_lost),
            "reached": len(doc_reached),
            "rate": (len(doc_lost) / len(doc_reached)) if doc_reached else None,
        }
        adherent = leads.filtered(lambda l: l.itex_funnel_stage == "adherent")
        empty["adherent"] = len(adherent)
        empty["approval_rate"] = (len(adherent) / len(leads)) if leads else None
        cycles = []
        for lead in adherent:
            start = lead.create_date
            end = lead.date_last_stage_update or lead.write_date
            if start and end and end >= start:
                cycles.append((end - start).days)
        empty["cycle_days_avg"] = round(sum(cycles) / len(cycles), 1) if cycles else None
        return empty
