# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import _, api, fields, models


class CoinsReservation(models.Model):
    _name = "coins.reservation"
    _description = "Réservation (Coins Marocain)"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "check_in desc, id desc"

    _CALENDAR_SYNC_STATES = ("confirmed", "in_progress", "done")

    name = fields.Char(
        string="Référence",
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _("Nouveau"),
    )
    active = fields.Boolean(default=True)

    traveler_id = fields.Many2one(
        "res.partner",
        string="Voyageur",
        required=True,
        tracking=True,
    )
    lead_id = fields.Many2one(
        "crm.lead",
        string="Fiche voyageur",
        index=True,
        ondelete="set null",
        tracking=True,
        help="Même réservation que dans Réservations — pas un second système.",
    )
    property_id = fields.Many2one(
        "coins.property",
        string="Bien réservé",
        required=True,
        tracking=True,
    )
    partner_activity_ids = fields.Many2many(
        "coins.partner_activity",
        string="Activités",
    )
    driver_id = fields.Many2one(
        "coins.driver",
        string="Chauffeur assigné",
    )

    check_in = fields.Date(string="Arrivée", required=True, tracking=True)
    check_out = fields.Date(string="Départ", required=True, tracking=True)
    nights = fields.Integer(
        string="Nuits",
        compute="_compute_nights",
        store=True,
    )

    state = fields.Selection(
        [
            ("draft", "Brouillon"),
            ("confirmed", "Confirmée"),
            ("in_progress", "En cours"),
            ("done", "Terminée"),
            ("cancelled", "Annulée"),
        ],
        string="Statut",
        default="draft",
        required=True,
        tracking=True,
    )

    source = fields.Selection(
        [
            ("direct", "Direct"),
            ("referral", "Parrainage"),
            ("viator", "Viator"),
            ("booking", "Booking.com"),
            ("airbnb", "Airbnb"),
            ("expedia", "Expedia"),
            ("channex", "OTA (Channex)"),
            ("ads", "Publicité"),
        ],
        string="Source",
        default="direct",
    )
    referral_code = fields.Char(string="Code parrainage utilisé")

    currency_id = fields.Many2one(
        "res.currency",
        string="Devise",
        default=lambda self: self.env.company.currency_id.id,
    )
    amount_property = fields.Monetary(
        string="Montant bien", currency_field="currency_id"
    )
    amount_activities = fields.Monetary(
        string="Montant activités", currency_field="currency_id"
    )
    amount_transport = fields.Monetary(
        string="Montant transport", currency_field="currency_id"
    )
    amount_total = fields.Monetary(
        string="Montant total",
        currency_field="currency_id",
        compute="_compute_amount_total",
        store=True,
    )

    payment_method = fields.Selection(
        [
            ("stripe", "Stripe (carte)"),
            ("rib", "RIB / virement"),
            ("especes", "Espèces"),
        ],
        string="Mode de paiement",
        tracking=True,
        help="Stripe, RIB/virement ou espèces.",
    )
    payment_status = fields.Selection(
        [
            ("unpaid", "Non payé"),
            ("partial", "Partiel"),
            ("paid", "Payé"),
        ],
        string="Statut paiement",
        default="unpaid",
        tracking=True,
    )
    payment_reference = fields.Char(
        string="Réf. paiement",
        help="ID Stripe, référence virement RIB, ou reçu espèces.",
    )

    # --- Checkout site / Stripe (CAD) ---
    client_nom = fields.Char(string="Nom client (site)")
    client_email = fields.Char(string="Email client (site)")
    client_telephone = fields.Char(string="Téléphone client (site)")
    stripe_checkout_session_id = fields.Char(
        string="Stripe Checkout Session", copy=False, index=True
    )
    stripe_payment_intent_id = fields.Char(
        string="Stripe PaymentIntent", copy=False, index=True
    )
    booking_channel = fields.Selection(
        [
            ("backoffice", "Back-office"),
            ("website", "Site coinsmarocain.com"),
            ("ota", "OTA / Channex"),
        ],
        string="Canal",
        default="backoffice",
    )
    ligne_ids = fields.One2many(
        "coins.reservation.line",
        "reservation_id",
        string="Cross-sell",
    )
    amount_cross_sell = fields.Monetary(
        string="Montant cross-sell CAD",
        currency_field="currency_id",
        compute="_compute_amount_cross_sell",
        store=True,
    )
    blocage_id = fields.Many2one(
        "coins.property.blocage",
        string="Blocage calendrier",
        copy=False,
        ondelete="set null",
    )

    notes = fields.Text(string="Notes")
    is_demo = fields.Boolean(
        string="Démo Channex (fictif)",
        default=False,
        index=True,
        copy=False,
        help="Réservation fictive de démonstration. "
        "Ne jamais la confondre avec une réservation réelle.",
    )

    voyageurs = fields.Integer(string="Voyageurs", default=1)
    room_id = fields.Many2one(
        "coins.property.room",
        string="Chambre",
        domain="[('property_id', '=', property_id), ('active', '=', True)]",
        ondelete="set null",
    )
    daypass_piscine = fields.Boolean(string="Daypass piscine")
    meal_breakfast = fields.Boolean(string="Petit-déjeuner")
    meal_lunch = fields.Boolean(string="Déjeuner")
    meal_dinner = fields.Boolean(string="Dîner")
    allergies = fields.Text(string="Allergies / régimes")
    ops_slot_ids = fields.One2many(
        "coins.property.ops.slot",
        "reservation_id",
        string="Créneaux ops",
    )
    concierge_line_ids = fields.One2many(
        "coins.concierge.line",
        "reservation_id",
        string="Dossier conciergerie",
    )
    concierge_state = fields.Selection(
        [
            ("none", "Pas encore"),
            ("open", "En cours"),
            ("ready", "Séjour calé"),
        ],
        string="Conciergerie",
        default="none",
        tracking=True,
    )
    overbooking = fields.Boolean(
        string="Overbooking OTA",
        help="Résa OTA sur une plage déjà fermée (événement ou résa Coins). On garde la résa, on traite à la main.",
        tracking=True,
    )
    channex_booking_id = fields.Char(
        string="ID booking Channex",
        copy=False,
        index=True,
    )

    pickup_address = fields.Char(string="Lieu de départ")
    dropoff_address = fields.Char(string="Destination")
    pickup_time = fields.Float(string="Heure prise en charge")
    trip_status = fields.Selection(
        [
            ("upcoming", "À venir"),
            ("in_progress", "En cours"),
            ("done", "Terminé"),
        ],
        string="Statut course",
        default="upcoming",
    )

    calendar_event_id = fields.Many2one(
        "calendar.event",
        string="Événement calendrier",
        copy=False,
        ondelete="set null",
    )
    calendar_color = fields.Integer(
        string="Couleur calendrier",
        default=8,
        help="Index couleur vue calendrier (locations = 8).",
    )

    @api.depends("check_in", "check_out")
    def _compute_nights(self):
        for rec in self:
            if rec.check_in and rec.check_out and rec.check_out > rec.check_in:
                rec.nights = (rec.check_out - rec.check_in).days
            else:
                rec.nights = 0

    @api.depends("amount_property", "amount_activities", "amount_transport", "amount_cross_sell")
    def _compute_amount_total(self):
        for rec in self:
            rec.amount_total = (
                (rec.amount_property or 0.0)
                + (rec.amount_activities or 0.0)
                + (rec.amount_transport or 0.0)
                + (rec.amount_cross_sell or 0.0)
            )

    @api.depends("ligne_ids.amount_cad")
    def _compute_amount_cross_sell(self):
        for rec in self:
            rec.amount_cross_sell = sum(rec.ligne_ids.mapped("amount_cad"))

    @api.onchange("property_id", "check_in", "check_out")
    def _onchange_property_price(self):
        for rec in self:
            if (
                rec.property_id
                and rec.property_id.price_per_night
                and rec.nights
                and not rec.amount_property
            ):
                rec.amount_property = rec.property_id.price_per_night * rec.nights

    def action_confirm_website_booking(self):
        """Confirmation post-paiement Stripe : blocage + recalcul + mails."""
        for rec in self:
            rec._confirm_website_booking()
        return True

    def _confirm_website_booking(self):
        self.ensure_one()
        if self.state == "confirmed":
            return
        prop = self.property_id
        # Dernière nuit inclusive = veille du check_out
        from datetime import timedelta

        last_night = self.check_out - timedelta(days=1)
        if not prop.est_disponible(self.check_in, last_night):
            raise ValueError("dates_no_longer_available")

        Blocage = self.env["coins.property.blocage"].sudo()
        blocage = Blocage.create(
            {
                "property_id": prop.id,
                "date_debut": self.check_in,
                "date_fin": last_night,
                "source": "direct",
                "statut": "confirme",
                "reservation_id": self.id,
                "summary": "Coins site %s" % (self.name or ""),
            }
        )
        self.write(
            {
                "state": "confirmed",
                "payment_status": "paid",
                "payment_method": "stripe",
                "blocage_id": blocage.id,
            }
        )
        prop._recalculer_disponibilites()
        self._sync_ops_slots()
        self._on_confirmed()
        self._send_booking_emails()

    def _sync_ops_slots(self):
        """Crée les créneaux ops (daypass / repas / check-in) à la confirmation."""
        self.ensure_one()
        Slot = self.env["coins.property.ops.slot"].sudo()
        # Remplace les créneaux liés à cette réservation
        self.ops_slot_ids.unlink()
        prop = self.property_id
        if not prop or not self.check_in:
            return
        start_dt = fields.Datetime.to_datetime(
            "%s 15:00:00" % fields.Date.to_string(self.check_in)
        )
        slots = [
            {
                "property_id": prop.id,
                "reservation_id": self.id,
                "slot_type": "check_in",
                "name": _("Check-in %s") % (self.name or ""),
                "date_start": start_dt,
                "notes": self.allergies or False,
            }
        ]
        if self.daypass_piscine:
            slots.append(
                {
                    "property_id": prop.id,
                    "reservation_id": self.id,
                    "slot_type": "daypass",
                    "name": _("Daypass piscine — %s") % (self.client_nom or self.name or ""),
                    "date_start": fields.Datetime.to_datetime(
                        "%s 10:00:00" % fields.Date.to_string(self.check_in)
                    ),
                    "date_end": fields.Datetime.to_datetime(
                        "%s 18:00:00" % fields.Date.to_string(self.check_in)
                    ),
                    "notes": _("Voyageurs : %s") % (self.voyageurs or 1),
                }
            )
        meal_map = [
            ("meal_breakfast", "breakfast", _("Petit-déjeuner"), "08:00:00"),
            ("meal_lunch", "lunch", _("Déjeuner"), "13:00:00"),
            ("meal_dinner", "dinner", _("Dîner"), "20:00:00"),
        ]
        for field_name, stype, label, hhmm in meal_map:
            if getattr(self, field_name):
                slots.append(
                    {
                        "property_id": prop.id,
                        "reservation_id": self.id,
                        "slot_type": stype,
                        "name": "%s — %s" % (label, self.name or ""),
                        "date_start": fields.Datetime.to_datetime(
                            "%s %s" % (fields.Date.to_string(self.check_in), hhmm)
                        ),
                        "notes": self.allergies or False,
                    }
                )
        Slot.create(slots)

    def _send_booking_emails(self):
        self.ensure_one()
        Mail = self.env["mail.mail"].sudo()
        prop = self.property_id
        body_client = _(
            "<p>Bonjour %(name)s,</p>"
            "<p>Votre réservation <b>%(ref)s</b> pour <b>%(prop)s</b> "
            "(%(cin)s → %(cout)s) est confirmée.</p>"
            "<p>Montant prélevé : <b>%(total).2f CAD</b>.</p>"
            "<p>À bientôt — Coins Marocain</p>"
        ) % {
            "name": self.client_nom or (self.traveler_id.name or ""),
            "ref": self.name or "",
            "prop": prop.name or "",
            "cin": self.check_in,
            "cout": self.check_out,
            "total": self.amount_total or 0.0,
        }
        if self.client_email:
            Mail.create(
                {
                    "subject": _("Confirmation réservation %s") % (self.name or ""),
                    "body_html": body_client,
                    "email_to": self.client_email,
                    "auto_delete": True,
                }
            ).send()

        notify = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param(
                "coins_marocain.booking_notify_email",
                "karine@agencedoorway.com",
            )
        )
        owner_mail = prop.owner_id.email if prop.owner_id else False
        recipients = [x for x in [notify, owner_mail] if x]
        body_ops = _(
            "<p>Nouvelle réservation site <b>%(ref)s</b></p>"
            "<ul>"
            "<li>Bien : %(prop)s</li>"
            "<li>Client : %(nom)s — %(email)s — %(tel)s</li>"
            "<li>Dates : %(cin)s → %(cout)s</li>"
            "<li>Total : %(total).2f CAD</li>"
            "</ul>"
            "<p><b>Action propriétaire :</b> bloquer manuellement ces dates "
            "sur l’annonce Airbnb (pas d’export automatique).</p>"
        ) % {
            "ref": self.name or "",
            "prop": prop.name or "",
            "nom": self.client_nom or "",
            "email": self.client_email or "",
            "tel": self.client_telephone or "",
            "cin": self.check_in,
            "cout": self.check_out,
            "total": self.amount_total or 0.0,
        }
        if recipients:
            Mail.create(
                {
                    "subject": _("[Coins] Réservation confirmée %s") % (self.name or ""),
                    "body_html": body_ops,
                    "email_to": ",".join(recipients),
                    "auto_delete": True,
                }
            ).send()

    def _should_sync_calendar(self):
        self.ensure_one()
        return bool(
            self.check_in
            and self.state in self._CALENDAR_SYNC_STATES
            and self.active
        )

    def _prepare_calendar_event_vals(self):
        self.ensure_one()
        start_dt = fields.Datetime.to_datetime(self.check_in)
        end_date = self.check_out or (self.check_in + timedelta(days=1))
        stop_dt = fields.Datetime.to_datetime(end_date)
        categ = self.env.ref(
            "coins_marocain.calendar_categ_coins_location", raise_if_not_found=False
        )
        alarm = self.env.ref(
            "coins_marocain.calendar_alarm_coins_24h", raise_if_not_found=False
        )
        desc = "<p>" + "<br/>".join(
            [
                _("Réf. : %s") % (self.name or ""),
                _("Bien : %s") % (self.property_id.name or ""),
                _("Voyageur : %s") % (self.traveler_id.name or ""),
                _("Statut : %s")
                % dict(self._fields["state"].selection).get(self.state, self.state),
                _("Nuits : %s") % (self.nights or 0),
            ]
        ) + "</p>"
        model = self.env["ir.model"]._get(self._name)
        return {
            "name": _("%(prop)s — %(traveler)s")
            % {
                "prop": self.property_id.name or _("Location"),
                "traveler": self.traveler_id.name or _("Voyageur"),
            },
            "description": desc,
            "start": start_dt,
            "stop": stop_dt,
            "allday": True,
            "partner_ids": [(6, 0, self.traveler_id.ids)],
            "categ_ids": [(6, 0, categ.ids)] if categ else [],
            "alarm_ids": [(6, 0, alarm.ids)] if alarm else [],
            "res_model_id": model.id,
            "res_id": self.id,
            "user_id": self.env.user.id,
        }

    def _sync_calendar_event(self):
        Event = self.env["calendar.event"].sudo()
        for rec in self:
            if not rec._should_sync_calendar():
                if rec.calendar_event_id:
                    rec.calendar_event_id.sudo().write({"active": False})
                continue
            vals = rec._prepare_calendar_event_vals()
            if rec.calendar_event_id and rec.calendar_event_id.exists():
                rec.calendar_event_id.sudo().write({**vals, "active": True})
            else:
                event = Event.create(vals)
                rec.with_context(skip_calendar_sync=True).write(
                    {"calendar_event_id": event.id}
                )

    def action_open_calendar_event(self):
        self.ensure_one()
        if not self.calendar_event_id:
            self._sync_calendar_event()
        if not self.calendar_event_id:
            return False
        return {
            "type": "ir.actions.act_window",
            "res_model": "calendar.event",
            "res_id": self.calendar_event_id.id,
            "view_mode": "form",
            "target": "current",
        }

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("name") or vals["name"] == _("Nouveau"):
                vals["name"] = self.env["ir.sequence"].next_by_code(
                    "coins.reservation"
                ) or _("Nouveau")
        records = super().create(vals_list)
        if not self.env.context.get("skip_calendar_sync"):
            records._sync_calendar_event()
        return records

    def write(self, vals):
        date_keys = {"check_in", "check_out", "property_id", "state", "active"}
        old_rows = []
        if date_keys.intersection(vals):
            for rec in self:
                old_rows.append(
                    {
                        "rec": rec,
                        "check_in": rec.check_in,
                        "last": rec._stay_last_night(),
                        "property": rec.property_id,
                        "state": rec.state,
                    }
                )
        res = super().write(vals)
        if self.env.context.get("skip_calendar_sync"):
            return res
        if {
            "state",
            "check_in",
            "check_out",
            "traveler_id",
            "property_id",
            "active",
            "notes",
        }.intersection(vals):
            self._sync_calendar_event()
        if old_rows and not self.env.context.get("skip_channex_sync"):
            self._sync_channex_after_write(old_rows)
        return res

    def _sync_channex_after_write(self, old_rows):
        # Move confirmed stay: reopen old dates + close new dates (certif modify).
        Blocage = self.env["coins.property.blocage"]
        for row in old_rows:
            rec = row["rec"]
            if rec.state != "confirmed" or not rec.active:
                continue
            if row["state"] != "confirmed":
                continue
            dates_moved = (
                rec.check_in != row["check_in"]
                or rec._stay_last_night() != row["last"]
                or rec.property_id != row["property"]
            )
            if not dates_moved:
                continue
            blocks = Blocage.search(
                [("reservation_id", "=", rec.id), ("statut", "=", "confirme")]
            )
            if blocks:
                blocks.write({"statut": "annule"})
            row["property"]._release_otas_if_free(
                row["check_in"], row["last"], origin="%s move" % (rec.name or "")
            )
            rec.property_id._close_otas(
                rec.check_in,
                rec._stay_last_night(),
                "reservation",
                rec.name or "",
                source="direct",
                extra={"reservation_id": rec.id},
            )

    def unlink(self):
        events = self.mapped("calendar_event_id")
        res = super().unlink()
        events.sudo().unlink()
        return res

    def action_confirm(self):
        self.write({"state": "confirmed"})
        for rec in self:
            rec._sync_ops_slots()
            rec._on_confirmed()
        self._notify_driver_on_confirm()

    def _stay_last_night(self):
        self.ensure_one()
        if self.check_out:
            return self.check_out - timedelta(days=1)
        return self.check_in

    def _is_ota_source(self):
        return self.source in ("booking", "airbnb", "expedia", "channex")

    def _on_confirmed(self):
        """Ferme le calendrier (priorité Coins), file Channex, ouvre le dossier conciergerie."""
        Line = self.env["coins.concierge.line"]
        for rec in self:
            last = rec._stay_last_night()
            already = rec.property_id._channex_range_closed(
                rec.check_in, last, exclude_reservation_id=rec.id
            )
            if rec._is_ota_source() and already:
                rec.overbooking = True
            reason = "ota" if rec._is_ota_source() else "reservation"
            source = "ota" if rec._is_ota_source() else "direct"
            rec.property_id._close_otas(
                rec.check_in,
                last,
                reason,
                rec.name or "",
                source=source,
                extra={"reservation_id": rec.id},
            )
            Line._seed_for_reservation(rec)
            if rec.concierge_state == "none":
                rec.concierge_state = "open"
            rec._schedule_experience_call()

    def _schedule_experience_call(self):
        self.ensure_one()
        existing = self.activity_ids.filtered(
            lambda a: a.summary and "Valider l'expérience" in (a.summary or "")
        )
        if existing:
            return
        try:
            self.activity_schedule(
                "mail.mail_activity_data_call",
                summary="Valider l'expérience",
                note=_(
                    "Appeler dès confirmation : arrivée, voyageurs, transferts, "
                    "voiture, restos, activités, événements. Source : %s"
                )
                % (dict(self._fields["source"].selection).get(self.source) or self.source),
            )
        except Exception:  # noqa: BLE001
            self.activity_schedule(
                "mail.mail_activity_data_todo",
                summary="Valider l'expérience",
                note=_("Appeler le voyageur pour caler le séjour."),
            )

    def _notify_driver_on_confirm(self):
        import logging

        try:
            from odoo.addons.coins_marocain.services.confirmation_service import (
                CoinsConfirmationService,
            )
        except (ImportError, AttributeError):
            logging.getLogger(__name__).warning(
                "CoinsConfirmationService absent — skip WA chauffeur"
            )
            return

        svc = CoinsConfirmationService(self.env)
        for rec in self:
            if not rec.driver_id:
                continue
            rec.driver_id._ensure_portal_token()
            prop = rec.property_id
            addr = ", ".join(
                filter(None, [prop.street, prop.district, prop.city or "Marrakech"])
            )
            pickup = rec.pickup_address or addr
            dropoff = rec.dropoff_address or addr
            body = svc.build_driver_message(
                date=fields.Date.to_string(rec.check_in) if rec.check_in else "",
                time=svc._format_time(rec.pickup_time),
                client=rec.traveler_id.name,
                n_pers=prop.capacity or 1,
                pickup=pickup,
                dropoff=dropoff,
                portal_url=rec.driver_id.portal_url,
            )
            phone = rec.driver_id.phone or ""
            if not phone and rec.driver_id.partner_id:
                phone = rec.driver_id.partner_id.phone or ""
            if phone:
                svc.wa.send_whatsapp(phone, body)

    def action_start(self):
        self.write({"state": "in_progress", "trip_status": "in_progress"})

    def action_done(self):
        self.write({"state": "done", "trip_status": "done"})
        from odoo.addons.coins_marocain.services.driver_ledger_service import (
            DriverLedgerService,
        )

        svc = DriverLedgerService(self.env)
        for rec in self:
            try:
                svc.record_from_reservation(rec)
            except Exception:  # noqa: BLE001
                import logging

                logging.getLogger(__name__).exception(
                    "driver ledger reservation %s", rec.id
                )

    def action_cancel(self):
        self.write({"state": "cancelled"})
        Blocage = self.env["coins.property.blocage"]
        for rec in self:
            blocks = Blocage.search(
                [("reservation_id", "=", rec.id), ("statut", "=", "confirme")]
            )
            if blocks:
                blocks.write({"statut": "annule"})
            last = rec._stay_last_night()
            rec.property_id._release_otas_if_free(
                rec.check_in, last, origin=rec.name or ""
            )
            rec.concierge_line_ids.filtered(lambda l: l.state == "todo").write(
                {"state": "cancelled"}
            )

    def action_reset_draft(self):
        self.write({"state": "draft"})
