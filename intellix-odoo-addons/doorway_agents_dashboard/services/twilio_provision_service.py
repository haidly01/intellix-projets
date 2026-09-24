# -*- coding: utf-8 -*-
"""Recherche, achat et inventaire numéros Twilio."""
import logging
import re

from odoo import _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

E164_RE = re.compile(r"^\+[1-9]\d{6,14}$")


class TwilioProvisionService:
    def __init__(self, env):
        self.env = env
        from .twilio_service import TwilioService

        self._twilio = TwilioService(env)

    def _client(self):
        if not self._twilio.is_available():
            raise UserError(
                _(
                    "Twilio non configuré. Renseignez Account SID et Auth Token "
                    "dans Paramètres → Agents IA."
                )
            )
        return self._twilio._client()

    @staticmethod
    def normalize_e164(phone_number):
        raw = (phone_number or "").strip()
        if not raw:
            return ""
        if not raw.startswith("+"):
            digits = re.sub(r"\D", "", raw)
            if len(digits) == 10:
                raw = "+1%s" % digits
            elif digits:
                raw = "+%s" % digits
        if not E164_RE.match(raw):
            raise UserError(
                _("Numéro invalide (%(phone)s). Format E.164 requis, ex. +15141234567.")
                % {"phone": phone_number}
            )
        return raw

    def search_available_numbers(self, country="CA", area_code=None, limit=12):
        """Liste des numéros disponibles à l'achat sur Twilio."""
        client = self._client()
        country = (country or "CA").upper()
        area_code = (area_code or "").strip() or None
        try:
            resource = client.available_phone_numbers(country)
            if area_code and hasattr(resource, "local"):
                numbers = resource.local.list(area_code=area_code, limit=limit)
            elif hasattr(resource, "local"):
                numbers = resource.local.list(limit=limit)
            elif hasattr(resource, "mobile"):
                numbers = resource.mobile.list(limit=limit)
            else:
                numbers = []
        except Exception as exc:  # noqa: BLE001
            _logger.warning("Twilio search_available_numbers: %s", exc)
            raise UserError(_("Recherche Twilio échouée : %s") % exc) from exc

        rows = []
        for item in numbers:
            phone = getattr(item, "phone_number", None) or ""
            if not phone:
                continue
            rows.append(
                {
                    "phone_number": phone,
                    "friendly_name": getattr(item, "friendly_name", "") or phone,
                    "locality": getattr(item, "locality", "") or "",
                    "region": getattr(item, "region", "") or "",
                }
            )
        return rows

    def purchase_number(self, phone_number, friendly_name=None):
        """Achète un numéro Twilio et retourne sid + E.164."""
        client = self._client()
        phone_number = self.normalize_e164(phone_number)
        try:
            incoming = client.incoming_phone_numbers.create(
                phone_number=phone_number,
                friendly_name=friendly_name or phone_number,
            )
        except Exception as exc:  # noqa: BLE001
            _logger.warning("Twilio purchase_number %s: %s", phone_number, exc)
            raise UserError(_("Achat numéro Twilio échoué : %s") % exc) from exc
        return {
            "phone_number": incoming.phone_number,
            "sid": incoming.sid,
            "friendly_name": incoming.friendly_name or phone_number,
        }

    def list_account_numbers(self, limit=50):
        """Numéros déjà possédés sur le compte Twilio."""
        client = self._client()
        try:
            numbers = client.incoming_phone_numbers.list(limit=limit)
        except Exception as exc:  # noqa: BLE001
            _logger.warning("Twilio list_account_numbers: %s", exc)
            raise UserError(_("Liste numéros Twilio échouée : %s") % exc) from exc
        rows = []
        for item in numbers:
            rows.append(
                {
                    "phone_number": item.phone_number,
                    "sid": item.sid,
                    "friendly_name": item.friendly_name or item.phone_number,
                }
            )
        return rows

    def release_number(self, twilio_incoming_sid):
        """Libère un numéro acheté via Twilio (si géré par Odoo)."""
        if not twilio_incoming_sid:
            return False
        client = self._client()
        try:
            client.incoming_phone_numbers(twilio_incoming_sid).delete()
            return True
        except Exception as exc:  # noqa: BLE001
            _logger.warning("Twilio release_number %s: %s", twilio_incoming_sid, exc)
            return False
