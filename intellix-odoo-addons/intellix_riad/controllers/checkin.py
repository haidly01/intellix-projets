# -*- coding: utf-8 -*-

import base64
import logging
from datetime import datetime

from odoo import fields, http
from odoo.http import request

_logger = logging.getLogger(__name__)

LANGS = ("fr", "en", "ar")

I18N = {
    "fr": {
        "title": "Fiche d'arrivée",
        "identity": "Identité",
        "stay": "Séjour",
        "signature": "Signature",
        "resident_q": "Êtes-vous résident marocain ?",
        "yes": "Oui — j'ai une CIN",
        "no": "Non — passeport étranger",
        "continue": "Continuer",
        "lastname": "Nom",
        "firstname": "Prénom",
        "birth_date": "Date de naissance",
        "birth_place": "Lieu de naissance",
        "nationality": "Nationalité",
        "passport": "N° de passeport",
        "entry": "Date d'entrée au Maroc",
        "arrival": "Arrivée",
        "departure": "Départ",
        "phone": "Téléphone",
        "email": "E-mail",
        "photo": "Photo du passeport",
        "sign_hint": "Signez avec le doigt",
        "clear": "Effacer",
        "submit": "Valider et signer",
        "ma_done": "Aucune fiche de police n'est requise pour un résident marocain.",
        "thanks": "Merci, votre fiche est enregistrée.",
        "otp": "Un code de signature vous est envoyé. Signez ensuite le document.",
        "expired": "Ce lien a expiré ou a déjà été utilisé.",
        "invalid": "Lien invalide.",
        "need_fields": "Merci de remplir tous les champs.",
        "readonly": "Dates de votre réservation — non modifiables",
        "otp_send": "Recevoir le code de signature",
        "otp_code": "Code reçu",
        "otp_verify": "Signer la fiche",
        "otp_sent": "Code envoyé. Saisissez-le ci-dessous.",
    },
    "en": {
        "title": "Arrival form",
        "identity": "Identity",
        "stay": "Stay",
        "signature": "Signature",
        "resident_q": "Are you a Moroccan resident?",
        "yes": "Yes — I have a CIN",
        "no": "No — foreign passport",
        "continue": "Continue",
        "lastname": "Last name",
        "firstname": "First name",
        "birth_date": "Date of birth",
        "birth_place": "Place of birth",
        "nationality": "Nationality",
        "passport": "Passport number",
        "entry": "Date of entry into Morocco",
        "arrival": "Arrival",
        "departure": "Departure",
        "phone": "Phone",
        "email": "Email",
        "photo": "Passport photo",
        "sign_hint": "Sign with your finger",
        "clear": "Clear",
        "submit": "Confirm and sign",
        "ma_done": "No police form is required for Moroccan residents.",
        "thanks": "Thank you, your form is saved.",
        "otp": "A signature code will be sent. Then sign the document.",
        "expired": "This link has expired or was already used.",
        "invalid": "Invalid link.",
        "need_fields": "Please fill in every field.",
        "readonly": "Your booking dates — read only",
        "otp_send": "Send the signature code",
        "otp_code": "Code received",
        "otp_verify": "Sign the form",
        "otp_sent": "Code sent. Enter it below.",
    },
    "ar": {
        "title": "استمارة الوصول",
        "identity": "الهوية",
        "stay": "الإقامة",
        "signature": "التوقيع",
        "resident_q": "هل أنت مقيم مغربي؟",
        "yes": "نعم — بطاقة التعريف الوطنية",
        "no": "لا — جواز سفر أجنبي",
        "continue": "متابعة",
        "lastname": "الاسم العائلي",
        "firstname": "الاسم الشخصي",
        "birth_date": "تاريخ الازدياد",
        "birth_place": "مكان الازدياد",
        "nationality": "الجنسية",
        "passport": "رقم جواز السفر",
        "entry": "تاريخ الدخول إلى المغرب",
        "arrival": "الوصول",
        "departure": "المغادرة",
        "phone": "الهاتف",
        "email": "البريد الإلكتروني",
        "photo": "صورة جواز السفر",
        "sign_hint": "وقّع بإصبعك",
        "clear": "مسح",
        "submit": "تأكيد والتوقيع",
        "ma_done": "لا يلزم ملء ورقة الشرطة للمقيم المغربي.",
        "thanks": "شكرًا، تم حفظ استمارتك.",
        "otp": "سيتم إرسال رمز التوقيع. ثم وقّع الوثيقة.",
        "expired": "هذا الرابط منتهٍ أو سبق استعماله.",
        "invalid": "رابط غير صالح.",
        "need_fields": "يرجى ملء جميع الحقول.",
        "readonly": "تواريخ حجزك — للقراءة فقط",
        "otp_send": "إرسال رمز التوقيع",
        "otp_code": "الرمز المستلم",
        "otp_verify": "توقيع الاستمارة",
        "otp_sent": "تم إرسال الرمز. أدخله أدناه.",
    },
}


def _lang(kwargs):
    raw = (kwargs.get("lang") or request.httprequest.cookies.get("riad_lang") or "fr").lower()
    return raw if raw in LANGS else "fr"


def _t(lang, key):
    return I18N.get(lang, I18N["fr"]).get(key, I18N["fr"][key])


class RiadCheckinController(http.Controller):
    def _resa(self, token):
        if not token:
            return request.env["coins.reservation"]
        return (
            request.env["coins.reservation"]
            .sudo()
            .search([("riad_checkin_token", "=", token)], limit=1)
        )

    def _token_ok(self, resa):
        if not resa:
            return False
        if resa.riad_checkin_used_at:
            return False
        if resa.riad_checkin_expiry and resa.riad_checkin_expiry < fields.Datetime.now():
            return False
        return True

    def _page(self, template, values, lang="fr"):
        html = request.env["ir.qweb"].sudo()._render(template, values)
        response = request.make_response(
            html, headers=[("Content-Type", "text/html; charset=utf-8")]
        )
        response.set_cookie("riad_lang", lang, max_age=60 * 60 * 24 * 30)
        return response

    def _values(self, resa, lang, extra=None):
        estab = resa._riad_establishment() if resa else request.env["intellix.riad.establishment"]
        countries = request.env["res.country"].sudo().search([], order="name")
        vals = {
            "lang": lang,
            "rtl": lang == "ar",
            "t": lambda k: _t(lang, k),
            "resa": resa,
            "estab_name": estab.name if estab else "",
            "estab_city": (estab.property_id.city if estab and estab.property_id else "")
            or "Marrakech",
            "check_in": resa.check_in.strftime("%d/%m/%Y") if resa and resa.check_in else "",
            "check_out": resa.check_out.strftime("%d/%m/%Y") if resa and resa.check_out else "",
            "token": resa.riad_checkin_token if resa else "",
            "countries": countries,
            "prefill": {
                "lastname": "",
                "firstname": "",
                "phone": "",
                "email": "",
            },
        }
        if resa:
            lastname, firstname = resa._split_client_name()
            email, phone, _name = resa._guest_contact()
            vals["prefill"] = {
                "lastname": lastname,
                "firstname": firstname,
                "phone": phone,
                "email": email,
            }
        if extra:
            vals.update(extra)
        return vals

    @http.route(
        "/checkin/<string:token>",
        type="http",
        auth="public",
        website=False,
        csrf=False,
    )
    def checkin_form(self, token, **kwargs):
        lang = _lang(kwargs)
        resa = self._resa(token)
        if not resa:
            return request.make_response(
                "<h2>%s</h2>" % _t(lang, "invalid"),
                headers=[("Content-Type", "text/html; charset=utf-8")],
            )
        if not self._token_ok(resa):
            return request.make_response(
                "<h2>%s</h2>" % _t(lang, "expired"),
                headers=[("Content-Type", "text/html; charset=utf-8")],
            )
        if resa._riad_is_moroccan_guest():
            return self._page(
                "intellix_riad.checkin_done",
                self._values(resa, lang, {"message": _t(lang, "ma_done")}),
                lang,
            )
        step = kwargs.get("step")
        if not step:
            step = "form" if resa.riad_guest_residency == "foreign" else "residency"
        return self._page(
            "intellix_riad.checkin_form",
            self._values(resa, lang, {"step": step}),
            lang,
        )

    @http.route(
        "/checkin/<string:token>/residency",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def checkin_residency(self, token, **kwargs):
        lang = _lang(kwargs)
        resa = self._resa(token)
        if not self._token_ok(resa):
            return request.redirect("/checkin/%s?lang=%s" % (token, lang))
        answer = (kwargs.get("resident_ma") or "").strip()
        if answer == "yes":
            morocco = request.env["res.country"].sudo().search([("code", "=", "MA")], limit=1)
            resa.write(
                {
                    "riad_guest_residency": "moroccan",
                    "riad_guest_nationality_id": morocco.id if morocco else False,
                    "riad_checkin_used_at": fields.Datetime.now(),
                }
            )
            resa._ensure_police_fiches()
            for fiche in resa.riad_police_fiche_ids:
                fiche.write(
                    {
                        "id_document_type": "cin",
                        "nationality_id": morocco.id if morocco else fiche.nationality_id.id,
                    }
                )
            return self._page(
                "intellix_riad.checkin_done",
                self._values(resa, lang, {"message": _t(lang, "ma_done")}),
                lang,
            )
        resa.riad_guest_residency = "foreign"
        return request.redirect("/checkin/%s?step=form&lang=%s" % (token, lang))

    @http.route(
        "/checkin/<string:token>/submit",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def checkin_submit(self, token, **kwargs):
        lang = _lang(kwargs)
        resa = self._resa(token)
        if not self._token_ok(resa):
            return request.redirect("/checkin/%s?lang=%s" % (token, lang))
        if resa._riad_is_moroccan_guest():
            return request.redirect("/checkin/%s?lang=%s" % (token, lang))
        required = (
            "lastname",
            "firstname",
            "birth_date",
            "birth_place",
            "nationality_id",
            "passport_number",
            "entry_date",
            "phone",
            "email",
        )
        if any(not (kwargs.get(key) or "").strip() for key in required):
            return self._page(
                "intellix_riad.checkin_form",
                self._values(
                    resa, lang, {"step": "form", "error": _t(lang, "need_fields")}
                ),
                lang,
            )
        morocco = request.env["res.country"].sudo().browse(int(kwargs.get("nationality_id") or 0))
        if morocco.exists() and (morocco.code or "").upper() == "MA":
            resa.write(
                {
                    "riad_guest_residency": "moroccan",
                    "riad_guest_nationality_id": morocco.id,
                    "riad_checkin_used_at": fields.Datetime.now(),
                }
            )
            resa._ensure_police_fiches()
            resa.riad_police_fiche_ids.write(
                {"nationality_id": morocco.id, "id_document_type": "cin"}
            )
            return self._page(
                "intellix_riad.checkin_done",
                self._values(resa, lang, {"message": _t(lang, "ma_done")}),
                lang,
            )
        resa._ensure_police_fiches()
        fiche = resa.riad_police_fiche_ids.sorted("sequence")[:1]
        if not fiche:
            return request.make_response(
                "<h2>%s</h2>" % _t(lang, "invalid"),
                headers=[("Content-Type", "text/html; charset=utf-8")],
            )
        photo = kwargs.get("passport_image")
        photo_b64 = False
        filename = False
        if photo and hasattr(photo, "read"):
            raw = photo.read()
            if raw:
                photo_b64 = base64.b64encode(raw)
                filename = getattr(photo, "filename", "passeport.jpg")
        sign_data = (kwargs.get("signature_data") or "").strip()
        sign_b64 = False
        if sign_data.startswith("data:image"):
            sign_b64 = sign_data.split(",", 1)[-1]
        vals = {
            "lastname": kwargs.get("lastname"),
            "firstname": kwargs.get("firstname"),
            "birth_date": kwargs.get("birth_date"),
            "birth_place": kwargs.get("birth_place"),
            "nationality_id": int(kwargs.get("nationality_id") or 0),
            "passport_number": kwargs.get("passport_number"),
            "entry_date": kwargs.get("entry_date"),
            "phone": kwargs.get("phone"),
            "email": kwargs.get("email"),
            "id_document_type": "passport",
        }
        if photo_b64:
            vals["passport_image"] = photo_b64
            vals["passport_filename"] = filename
        if sign_b64:
            vals["signature_image"] = sign_b64
        fiche.write(vals)
        resa.write(
            {
                "riad_guest_residency": "foreign",
                "riad_guest_nationality_id": fiche.nationality_id.id,
            }
        )
        try:
            sig = fiche.action_create_signature_request()
        except Exception as exc:  # noqa: BLE001
            _logger.exception("check-in signature create: %s", exc)
            return self._page(
                "intellix_riad.checkin_done",
                self._values(resa, lang, {"message": _t(lang, "thanks")}),
                lang,
            )
        return request.redirect("/sign/contract/%s?lang=%s" % (sig.token, lang))


def _pe_related_record(sig):
    if not sig:
        return None
    if hasattr(sig, "get_related_record"):
        try:
            return sig.get_related_record()
        except Exception:  # noqa: BLE001
            pass
    model = getattr(sig, "res_model", None) or getattr(sig, "document_model", None)
    rec_id = getattr(sig, "res_id", None) or getattr(sig, "document_id", None)
    if model and rec_id:
        return request.env[model].sudo().browse(int(rec_id))
    return None


def _pe_document_html(sig, record):
    if sig and hasattr(sig, "get_document_html"):
        try:
            return sig.get_document_html() or ""
        except Exception:  # noqa: BLE001
            pass
    if record and hasattr(record, "_get_signature_html"):
        return record._get_signature_html() or ""
    return ""


class RiadPoliceSignatureController(http.Controller):
    """Étend /sign/contract/<token> pour la fiche de police — pas un second moteur."""

    @http.route("/sign/contract/<string:token>", type="http", auth="public", website=False)
    def sign_page(self, token, **kwargs):
        from odoo.addons.people_engine.controllers.signature_controller import (
            SignatureController,
        )

        sig = (
            request.env["pe.electronic.signature"]
            .sudo()
            .search([("token", "=", token)], limit=1)
        )
        record = _pe_related_record(sig)
        if not (record and record._name == "intellix.riad.police.fiche"):
            return SignatureController().sign_page(token, **kwargs)

        lang = _lang(kwargs)
        if sig.state == "signed":
            return request.make_response(
                "<h2>%s</h2>" % _t(lang, "thanks"),
                headers=[("Content-Type", "text/html; charset=utf-8")],
            )
        expiry = getattr(sig, "token_expiry", None)
        if sig.state == "expired" or (expiry and expiry < datetime.now()):
            if sig.state != "expired":
                sig.write({"state": "expired"})
            return request.make_response(
                "<h2>%s</h2>" % _t(lang, "expired"),
                headers=[("Content-Type", "text/html; charset=utf-8")],
            )
        html = request.env["ir.qweb"].sudo()._render(
            "intellix_riad.checkin_sign",
            {
                "lang": lang,
                "rtl": lang == "ar",
                "t": lambda k: _t(lang, k),
                "sig": sig,
                "token": token,
                "document_html": _pe_document_html(sig, record),
                "estab_name": record.establishment_id.name or "",
                "check_in": record.check_in.strftime("%d/%m/%Y") if record.check_in else "",
                "check_out": record.check_out.strftime("%d/%m/%Y") if record.check_out else "",
                "resa": record.reservation_id,
            },
        )
        return request.make_response(
            html, headers=[("Content-Type", "text/html; charset=utf-8")]
        )
