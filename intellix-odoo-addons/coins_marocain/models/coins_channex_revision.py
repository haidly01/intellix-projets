# -*- coding: utf-8 -*-
import json
import logging
from datetime import datetime

from odoo import api, fields, models

from odoo.addons.coins_marocain.services.channex_service import (
    ChannexNotConfigured,
    ChannexService,
)

_logger = logging.getLogger(__name__)

OTA_SOURCE = {
    "booking.com": "booking",
    "bookingcom": "booking",
    "booking": "booking",
    "airbnb": "airbnb",
    "expedia": "expedia",
}


class CoinsChannexRevision(models.Model):
    """Inbound OTA : on stocke tout, on n'ignore jamais une confirmation."""

    _name = "coins.channex.revision"
    _description = "Révision booking Channex (inbound OTA)"
    _order = "id desc"

    name = fields.Char(string="Libellé", compute="_compute_name", store=True)
    revision_id = fields.Char(string="ID révision", index=True)
    booking_id = fields.Char(string="ID booking Channex", index=True)
    property_channex_id = fields.Char(string="UUID propriété Channex")
    ota_status = fields.Selection(
        [
            ("new", "Nouvelle"),
            ("modified", "Modifiée"),
            ("cancelled", "Annulée"),
            ("unknown", "Inconnue"),
        ],
        string="Statut OTA",
        default="unknown",
    )
    raw_json = fields.Text(string="Payload brut")
    state = fields.Selection(
        [
            ("pending", "À traiter"),
            ("done", "Intégrée"),
            ("error", "Erreur — à traiter"),
            ("ignored", "Ignorée"),
        ],
        string="Statut",
        default="pending",
        required=True,
        index=True,
    )
    error_message = fields.Text(string="Erreur")
    reservation_id = fields.Many2one(
        "coins.reservation",
        string="Réservation",
        ondelete="set null",
    )

    @api.depends("booking_id", "ota_status", "revision_id")
    def _compute_name(self):
        for rec in self:
            rec.name = rec.booking_id or rec.revision_id or "révision #%s" % rec.id

    @api.model
    def queue_webhook_only(self, raw):
        """Webhook : stocke la notif et ACK. Aucun GET Channex dans la requête HTTP."""
        try:
            payload = json.loads(raw or "{}")
        except ValueError:
            payload = {"raw": (raw or "")[:4000]}
        if isinstance(payload, dict) and payload.get("event"):
            return self._queue_webhook_envelope(payload, raw, pull=False)
        return self.queue_raw(raw)

    @api.model
    def process_after_webhook(self):
        """Après le 200 : feed (pas liste / by-id) + full sync demandé."""
        pending = self.search(
            [
                ("state", "=", "pending"),
                ("error_message", "ilike", "request_full_sync"),
            ],
            limit=5,
        )
        for rec in pending:
            rec._run_requested_full_sync()
        self.ingest_from_feed()
        return True

    @api.model
    def queue_raw(self, raw):
        try:
            payload = json.loads(raw or "{}")
        except ValueError:
            payload = {"raw": (raw or "")[:4000]}
        if isinstance(payload, dict) and payload.get("event"):
            return self._queue_webhook_envelope(payload, raw, pull=False)
        node = payload.get("data", payload) if isinstance(payload, dict) else {}
        if isinstance(node, list):
            created = self.browse()
            for item in node:
                created |= self.queue_raw(json.dumps(item))
            return created
        attrs = node.get("attributes") or node if isinstance(node, dict) else {}
        if not isinstance(attrs, dict):
            attrs = {}
        rev_id = str(node.get("id") or attrs.get("id") or attrs.get("revision_id") or "")
        if rev_id:
            existing = self.search([("revision_id", "=", rev_id)], limit=1)
            if existing:
                if existing.state != "done":
                    existing.write(
                        {
                            "raw_json": raw if isinstance(raw, str) else json.dumps(payload),
                            "booking_id": existing.booking_id
                            or str(attrs.get("booking_id") or attrs.get("unique_id") or "")
                            or existing.booking_id,
                            "property_channex_id": existing.property_channex_id
                            or str(attrs.get("property_id") or "")
                            or existing.property_channex_id,
                            "ota_status": existing.ota_status
                            if existing.ota_status != "unknown"
                            else self._normalize_status(
                                attrs.get("status") or attrs.get("action")
                            ),
                            "state": "pending",
                            "error_message": False,
                        }
                    )
                    existing._ingest()
                return existing
        rec = self.create(
            {
                "revision_id": rev_id or False,
                "booking_id": str(attrs.get("booking_id") or attrs.get("unique_id") or ""),
                "property_channex_id": str(
                    attrs.get("property_id") or attrs.get("property_channex_id") or ""
                ),
                "ota_status": self._normalize_status(attrs.get("status") or attrs.get("action")),
                "raw_json": raw if isinstance(raw, str) else json.dumps(payload),
                "state": "pending",
            }
        )
        rec._ingest()
        return rec

    @api.model
    def _queue_webhook_envelope(self, payload, raw, pull=False):
        """Notif webhook (event + revision_id). pull=False pendant l'ACK HTTP."""
        inner = payload.get("payload") if isinstance(payload.get("payload"), dict) else {}
        event = str(payload.get("event") or "")
        rev_id = str(
            inner.get("revision_id")
            or inner.get("booking_revision_id")
            or ""
        )
        booking_id = str(inner.get("booking_id") or "")
        prop_id = str(inner.get("property_id") or payload.get("property_id") or "")
        status = self._status_from_event(event)
        if event in ("request_full_sync", "full_sync"):
            return self.create(
                {
                    "revision_id": rev_id or False,
                    "booking_id": booking_id or False,
                    "property_channex_id": prop_id or False,
                    "ota_status": "unknown",
                    "raw_json": raw if isinstance(raw, str) else json.dumps(payload),
                    "state": "pending",
                    "error_message": "request_full_sync",
                }
            )
        if any(
            inner.get(key)
            for key in (
                "arrival_date",
                "departure_date",
                "rooms",
                "customer",
                "attributes",
            )
        ):
            wrapped = inner
            if not inner.get("id") and not inner.get("attributes"):
                wrapped = {
                    "id": rev_id,
                    "type": "booking_revision",
                    "attributes": dict(
                        inner,
                        booking_id=booking_id or inner.get("booking_id"),
                        property_id=prop_id or inner.get("property_id"),
                    ),
                }
            return self.queue_raw(json.dumps({"data": wrapped}))
        existing = self.browse()
        if rev_id:
            existing = self.search([("revision_id", "=", rev_id)], limit=1)
            if existing and existing.state == "done":
                return existing
        if pull:
            created = self.ingest_from_feed(revision_id=rev_id, property_id=prop_id)
            if created:
                return created
        if existing:
            return existing
        return self.create(
            {
                "revision_id": rev_id or False,
                "booking_id": booking_id or False,
                "property_channex_id": prop_id or False,
                "ota_status": status,
                "raw_json": raw if isinstance(raw, str) else json.dumps(payload),
                "state": "pending",
                "error_message": "Notif webhook reçue — en attente du feed.",
            }
        )

    def _run_requested_full_sync(self):
        self.ensure_one()
        mapping = self.env["coins.channex.mapping"].search(
            [
                ("kind", "=", "property"),
                ("channex_id", "=", self.property_channex_id or ""),
            ],
            limit=1,
        )
        if not mapping or not mapping.property_id:
            self.write(
                {
                    "state": "error",
                    "error_message": "request_full_sync — propriété non mappée",
                }
            )
            return
        try:
            result = self.env["coins.channex.push"].full_sync_property(
                mapping.property_id.id
            )
            self.write(
                {
                    "state": "done",
                    "error_message": "full_sync %s" % result,
                }
            )
        except Exception as exc:  # noqa: BLE001
            _logger.exception("channex request_full_sync")
            self.write({"state": "error", "error_message": str(exc)[:2000]})

    @api.model
    def _status_from_event(self, event):
        raw = (event or "").strip().lower()
        if raw in ("booking_new", "booking"):
            return "new"
        if raw in ("booking_modification", "booking_modified"):
            return "modified"
        if raw in ("booking_cancellation", "booking_cancelled"):
            return "cancelled"
        return self._normalize_status(raw)

    @api.model
    def ingest_from_feed(self, revision_id=None, property_id=None):
        svc = ChannexService(self.env)
        if not svc.ready:
            return self.browse()
        try:
            data = svc.feed_booking_revisions(property_id=property_id or None)
        except ChannexNotConfigured:
            return self.browse()
        except Exception:  # noqa: BLE001
            _logger.exception("channex feed booking_revisions")
            return self.browse()
        items = data
        if isinstance(data, dict):
            items = data.get("data") or data.get("values") or [data]
        if not isinstance(items, list):
            items = [items]
        created = self.browse()
        for item in items:
            if not item:
                continue
            if isinstance(item, list):
                for sub in item:
                    created |= self.queue_raw(
                        json.dumps(sub) if not isinstance(sub, str) else sub
                    )
                continue
            if not isinstance(item, dict):
                continue
            node = item.get("data", item)
            if isinstance(node, list):
                for sub in node:
                    created |= self.queue_raw(
                        json.dumps(sub) if not isinstance(sub, str) else sub
                    )
                continue
            if not isinstance(node, dict):
                continue
            attrs = node.get("attributes") or node
            if not isinstance(attrs, dict):
                attrs = {}
            item_id = str(node.get("id") or attrs.get("id") or "")
            if revision_id and item_id and item_id != revision_id:
                continue
            created |= self.queue_raw(json.dumps(item))
        return created

    @api.model
    def _normalize_status(self, value):
        raw = (value or "").strip().lower()
        if raw in ("new", "created", "booked", "confirmed"):
            return "new"
        if raw in ("modified", "updated", "modified"):
            return "modified"
        if raw in ("cancelled", "canceled", "cancelled"):
            return "cancelled"
        return "unknown"

    def action_retry(self):
        self.write({"state": "pending", "error_message": False})
        self._ingest()

    def _ingest(self):
        for rec in self:
            try:
                rec._ingest_one()
            except Exception as exc:  # noqa: BLE001
                _logger.exception("channex revision %s", rec.id)
                rec.write({"state": "error", "error_message": str(exc)[:2000]})

    def _payload(self):
        self.ensure_one()
        try:
            payload = json.loads(self.raw_json or "{}")
        except ValueError:
            return {}
        node = payload.get("data", payload) if isinstance(payload, dict) else {}
        if isinstance(node, list):
            node = node[0] if node else {}
        attrs = node.get("attributes") or node if isinstance(node, dict) else {}
        return attrs if isinstance(attrs, dict) else {}

    def _ingest_one(self):
        self.ensure_one()
        attrs = self._payload()
        booking_id = self.booking_id or str(attrs.get("booking_id") or "")
        status = self.ota_status or self._normalize_status(attrs.get("status"))
        if status == "cancelled":
            existing = self.env["coins.reservation"].search(
                [("channex_booking_id", "=", booking_id)], limit=1
            ) if booking_id else self.browse()
            if existing and existing.state != "cancelled":
                existing.action_cancel()
            self.write({"state": "done", "reservation_id": existing.id if existing else False})
            self._ack()
            return

        mapping = self.env["coins.channex.mapping"].search(
            [
                ("kind", "=", "property"),
                ("channex_id", "=", self.property_channex_id or attrs.get("property_id") or ""),
            ],
            limit=1,
        )
        if not mapping or not mapping.property_id:
            self.write(
                {
                    "state": "error",
                    "error_message": "Propriété Channex non mappée — on garde le payload, à relier.",
                }
            )
            return

        check_in, check_out = self._parse_dates(attrs)
        if not check_in or not check_out:
            self.write(
                {
                    "state": "error",
                    "error_message": "Dates arrivée/départ absentes du payload.",
                }
            )
            return

        guest = attrs.get("customer") or attrs.get("guest") or {}
        if isinstance(guest, list):
            guest = guest[0] if guest else {}
        if not isinstance(guest, dict):
            guest = {}
        name = (
            " ".join(
                filter(
                    None,
                    [
                        guest.get("name") or guest.get("first_name"),
                        guest.get("surname") or guest.get("last_name"),
                    ],
                )
            )
            or attrs.get("guest_name")
            or "Invité OTA"
        )
        email = guest.get("email") or guest.get("mail") or attrs.get("email") or ""
        phone = guest.get("phone") or attrs.get("phone") or ""
        partner = self._find_or_create_partner(name, email, phone)
        ota = self._source_from_attrs(attrs)
        existing = self.env["coins.reservation"].search(
            [("channex_booking_id", "=", booking_id)], limit=1
        ) if booking_id else self.env["coins.reservation"]
        occ = attrs.get("occupancy")
        if isinstance(occ, dict):
            voyageurs = int(occ.get("adults") or 0) + int(occ.get("children") or 0)
        else:
            try:
                voyageurs = int(occ or attrs.get("adults") or 1)
            except (TypeError, ValueError):
                voyageurs = 1
        if voyageurs < 1:
            voyageurs = 1
        vals = {
            "traveler_id": partner.id,
            "property_id": mapping.property_id.id,
            "check_in": check_in,
            "check_out": check_out,
            "source": ota,
            "booking_channel": "ota",
            "client_nom": name,
            "client_email": email or False,
            "client_telephone": phone or False,
            "channex_booking_id": booking_id or False,
            "voyageurs": voyageurs,
            "notes": "Import OTA Channex %s" % (booking_id or self.revision_id or ""),
        }
        if existing:
            existing.write(vals)
            resa = existing
        else:
            resa = self.env["coins.reservation"].create(vals)
        if resa.state == "draft":
            resa.action_confirm()
        elif status == "modified":
            last = resa._stay_last_night()
            resa.property_id._close_otas(
                resa.check_in,
                last,
                "ota",
                resa.name or "",
                source="ota",
                extra={"reservation_id": resa.id},
            )
        self.write({"state": "done", "reservation_id": resa.id, "error_message": False})
        if booking_id:
            Map = self.env["coins.channex.mapping"]
            if not Map.search([("kind", "=", "booking"), ("local_id", "=", resa.id)], limit=1):
                Map.create(
                    {
                        "kind": "booking",
                        "local_id": resa.id,
                        "channex_id": booking_id,
                        "property_id": mapping.property_id.id,
                    }
                )
        self._ack()

    def _parse_dates(self, attrs):
        arrival = attrs.get("arrival_date") or attrs.get("check_in") or attrs.get("arrival")
        departure = attrs.get("departure_date") or attrs.get("check_out") or attrs.get("departure")
        rooms = attrs.get("rooms") or []
        if isinstance(rooms, list) and rooms:
            first = rooms[0] if isinstance(rooms[0], dict) else {}
            arrival = arrival or first.get("checkin_date") or first.get("arrival_date")
            departure = (
                departure or first.get("checkout_date") or first.get("departure_date")
            )
        return self._to_date(arrival), self._to_date(departure)

    def _to_date(self, value):
        if not value:
            return False
        if hasattr(value, "year"):
            return value
        text = str(value)[:10]
        try:
            return datetime.strptime(text, "%Y-%m-%d").date()
        except ValueError:
            return False

    def _source_from_attrs(self, attrs):
        raw = (
            attrs.get("ota_name")
            or attrs.get("channel")
            or attrs.get("platform")
            or ""
        )
        key = str(raw).strip().lower().replace(" ", "")
        return OTA_SOURCE.get(key, "channex")

    def _find_or_create_partner(self, name, email, phone):
        Partner = self.env["res.partner"]
        partner = False
        if email:
            partner = Partner.search([("email", "=ilike", email)], limit=1)
        if not partner:
            partner = Partner.create(
                {
                    "name": name or "Invité OTA",
                    "email": email or False,
                    "phone": phone or False,
                    "comment": "Créé via réservation OTA / Channex",
                }
            )
        return partner

    def _ack(self):
        svc = ChannexService(self.env)
        if not svc.ready or not self.revision_id:
            return
        try:
            svc.ack_revision(self.revision_id)
        except ChannexNotConfigured:
            return
        except Exception:  # noqa: BLE001
            _logger.exception("channex ack %s", self.revision_id)

    @api.model
    def cron_poll_revisions(self):
        """Backup feed uniquement — pas de liste /bookings ni GET by-id."""
        self.ingest_from_feed()
        return True
