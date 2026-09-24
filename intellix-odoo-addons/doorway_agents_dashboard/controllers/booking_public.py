# -*- coding: utf-8 -*-
"""Page publique de prise de RDV démo Intellix — calendrier Zakaria."""
import hashlib
import hmac
import json
import logging
from datetime import datetime, timedelta

import pytz
import requests

from odoo import fields, http
from odoo.http import request

from odoo.addons.doorway_agents_dashboard.services.config_loader import get_secret

_logger = logging.getLogger(__name__)

from odoo.addons.doorway_agents_dashboard.services.calendar_availability_service import (
    CalendarAvailabilityService,
)

BOOKING_LOGIN = "zakaria@agencedoorway.com"
BOOKING_TZ = "Africa/Casablanca"
BOOKING_DURATION_MIN = 10
WEEKDAYS_FR = [
    "lundi",
    "mardi",
    "mercredi",
    "jeudi",
    "vendredi",
    "samedi",
    "dimanche",
]
MONTHS_FR = [
    "janvier",
    "février",
    "mars",
    "avril",
    "mai",
    "juin",
    "juillet",
    "août",
    "septembre",
    "octobre",
    "novembre",
    "décembre",
]


def format_booking_when(dt_naive_utc, tz_name="America/Toronto"):
    """UTC naïf Odoo → libellé local FR (évite 13 h Toronto affiché 17 h)."""
    if not dt_naive_utc:
        return ""
    tz = pytz.timezone(tz_name)
    if getattr(dt_naive_utc, "tzinfo", None):
        local = dt_naive_utc.astimezone(tz)
    else:
        local = pytz.UTC.localize(dt_naive_utc).astimezone(tz)
    return "%s %s %s à %sh%s" % (
        WEEKDAYS_FR[local.weekday()],
        local.day,
        MONTHS_FR[local.month - 1],
        local.strftime("%H"),
        local.strftime("%M"),
    )

# Dictée vocale RDV — aligné avec doorway_crm/static/src/js/intellix_voice_fill.js
VOICE_FILL_SCRIPT = r"""
(function () {
  function normalizeSpokenPhone(text) {
    var t = (text || "").toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");
    var digits = { zero: "0", un: "1", une: "1", deux: "2", trois: "3", quatre: "4", cinq: "5", six: "6", sept: "7", huit: "8", neuf: "9" };
    Object.keys(digits).forEach(function (w) {
      t = t.replace(new RegExp("\\b" + w + "\\b", "g"), digits[w]);
    });
    var nums = t.replace(/[^\d+]/g, "");
    return nums || (text || "").trim();
  }
  function fold(s) {
    return (s || "").toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");
  }
  function parseVoiceCommand(transcript) {
    var raw = (transcript || "").trim();
    if (!raw) return { field: null, value: "" };
    var folded = fold(raw);
    var rules = [
      { field: "nom_centre", re: /^(?:nom du centre|centre|entreprise|compagnie|soci[eé]t[eé])\s*[:\-]?\s*(.+)$/i },
      { field: "adresse", re: /^(?:adresses?|addresses?)\s*[:\-]?\s*(.+)$/i },
      { field: "phone", re: /^(?:t[eé]l[eé]phones?|tels?|mobiles?|cellulaires?|num[eé]ros?)\s*[:\-]?\s*(.+)$/i },
      { field: "email", re: /^(?:e-?mails?|courriels?|mails?)\s*[:\-]?\s*(.+)$/i },
      { field: "prenom", re: /^(?:pr[eé]noms?)\s*[:\-]?\s*(.+)$/i },
      { field: "nom", re: /^(?:noms? de famille|noms?)\s*[:\-]?\s*(.+)$/i }
    ];
    for (var i = 0; i < rules.length; i++) {
      var mRaw = raw.match(rules[i].re);
      var m = mRaw || folded.match(rules[i].re);
      if (m) {
        var value = (m[1] || "").trim();
        if (rules[i].field === "phone") value = normalizeSpokenPhone(value);
        if (rules[i].field === "email") value = value.replace(/\s+/g, "").replace(/arobase/gi, "@").replace(/point/gi, ".");
        return { field: rules[i].field, value: value };
      }
    }
    return { field: null, value: raw };
  }
  function SpeechCtor() {
    return window.SpeechRecognition || window.webkitSpeechRecognition || null;
  }
  function setValue(input, value) {
    if (!input) return;
    input.value = value;
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.dispatchEvent(new Event("change", { bubbles: true }));
  }
  function initVoiceFill() {
    var form = document.getElementById("confirmCard");
    if (!form || form.dataset.voiceReady === "1") return;
    form.dataset.voiceReady = "1";
    var bar = document.createElement("div");
    bar.className = "voice-bar";
    bar.innerHTML = '<button type="button" class="voice-global" id="voiceGlobalBtn">🎙 Remplir au vocal</button><span class="voice-status" id="voiceStatus"></span>';
    var grid = form.querySelector(".form-grid");
    if (grid) form.insertBefore(bar, grid);
    var status = document.getElementById("voiceStatus");
    var globalBtn = document.getElementById("voiceGlobalBtn");
    var Ctor = SpeechCtor();
    if (!Ctor) {
      status.className = "voice-status error";
      status.textContent = "Dictée non supportée sur ce navigateur (Chrome/Edge recommandé).";
      if (globalBtn) globalBtn.disabled = true;
      return;
    }
    status.textContent = "Dites « prénom Marie », « téléphone 514… », « email … »…";
    var activeRec = null;
    var activeBtn = null;
    function stopRec() {
      if (activeRec) { try { activeRec.stop(); } catch (e) {} }
      if (activeBtn) activeBtn.classList.remove("listening");
      activeRec = null;
      activeBtn = null;
    }
    function startListen(btn, mode, targetInput) {
      if (activeRec) { stopRec(); return; }
      var rec = new Ctor();
      rec.lang = "fr-CA";
      rec.interimResults = false;
      rec.maxAlternatives = 1;
      rec.onresult = function (ev) {
        var text = (ev.results[0] && ev.results[0][0] && ev.results[0][0].transcript) || "";
        var parsed = parseVoiceCommand(text);
        if (mode === "field" && targetInput) {
          setValue(targetInput, parsed.value);
          status.textContent = "Champ rempli.";
          return;
        }
        if (parsed.field) {
          var input = form.querySelector('[name="' + parsed.field + '"]');
          if (input) {
            setValue(input, parsed.value);
            status.textContent = "Rempli : " + parsed.field;
          } else {
            status.textContent = "Champ « " + parsed.field + " » absent sur ce formulaire.";
          }
        } else {
          var focused = form.querySelector("input:focus");
          if (focused && focused.name) {
            setValue(focused, parsed.value);
            status.textContent = "Dictée dans le champ focus.";
          } else {
            status.textContent = "Précisez : « prénom … », « téléphone … »…";
          }
        }
      };
      rec.onend = function () {
        if (btn) btn.classList.remove("listening");
        if (activeRec === rec) { activeRec = null; activeBtn = null; }
      };
      rec.onerror = function () {
        status.className = "voice-status error";
        status.textContent = "Erreur micro — autorisez le micro dans le navigateur.";
        stopRec();
      };
      activeRec = rec;
      activeBtn = btn;
      btn.classList.add("listening");
      status.className = "voice-status";
      status.textContent = "Écoute…";
      try { rec.start(); } catch (e) { stopRec(); }
    }
    if (globalBtn) {
      globalBtn.addEventListener("click", function (e) {
        e.preventDefault();
        startListen(globalBtn, "global", null);
      });
    }
    form.querySelectorAll(".form-field input").forEach(function (input) {
      if (!input.name || input.type === "hidden") return;
      var wrap = document.createElement("div");
      wrap.className = "voice-input-wrap";
      input.parentNode.insertBefore(wrap, input);
      wrap.appendChild(input);
      var mic = document.createElement("button");
      mic.type = "button";
      mic.className = "voice-mic";
      mic.title = "Dicter dans ce champ";
      mic.setAttribute("aria-label", "Dicter");
      mic.textContent = "🎙";
      mic.addEventListener("click", function (e) {
        e.preventDefault();
        startListen(mic, "field", input);
      });
      wrap.appendChild(mic);
    });
  }
  var card = document.getElementById("confirmCard");
  if (!card) return;
  var obs = new MutationObserver(function () {
    if (card.classList.contains("visible")) initVoiceFill();
  });
  obs.observe(card, { attributes: true, attributeFilter: ["class"] });
  if (card.classList.contains("visible")) initVoiceFill();
})();
"""


class IntellixPublicBookingController(http.Controller):
    def _booking_user(self):
        icp = request.env["ir.config_parameter"].sudo()
        login = icp.get_param(
            "doorway_agents_dashboard.booking_demo_user_login",
            BOOKING_LOGIN,
        )
        return request.env["res.users"].sudo().search([("login", "=", login)], limit=1)

    def _notify_n8n_demo_booked(self, event, prenom, phone, email, nom_centre, partner_id):
        """Arme les workflows n8n rappel H-30 et no-show."""
        base = get_secret(
            request.env,
            "N8N_BASE_URL",
            "doorway_agents_dashboard.n8n_base_url",
        ).rstrip("/")
        if not base:
            return
        start_dt = event.start
        payload = {
            "event_id": event.id,
            "prenom": prenom,
            "phone": phone,
            "email": email,
            "nom_centre": nom_centre,
            "partner_id": partner_id,
            "event_start": fields.Datetime.to_string(start_dt),
            "event_stop": fields.Datetime.to_string(event.stop),
            "event_start_minus_30": fields.Datetime.to_string(
                start_dt - timedelta(minutes=30)
            ),
            "event_start_plus_15": fields.Datetime.to_string(
                start_dt + timedelta(minutes=15)
            ),
        }
        for path in ("/webhook/intellix/demo-booked", "/webhook/intellix/demo-booked-noshow"):
            try:
                requests.post(f"{base}{path}", json=payload, timeout=8)
            except requests.RequestException as exc:
                _logger.warning("n8n %s: %s", path, exc)

    def _collect_slots(self, user, days=30):
        svc = CalendarAvailabilityService(request.env(su=True))
        partner_ref = user.partner_id.id
        slots = []
        today = fields.Date.today()
        for offset in range(days):
            day = today + timedelta(days=offset)
            if day.weekday() >= 5:
                continue
            result = svc.find_free_slots(
                [partner_ref],
                day,
                duration_minutes=BOOKING_DURATION_MIN,
                tz_name=BOOKING_TZ,
                work_start=9,
                work_end=22,
                slot_step=15,
            )
            for slot in result.get("slots") or []:
                slots.append(slot)
            if len(slots) >= 800:
                break
        return slots[:800]

    @http.route(
        "/intellix/rdv/zakaria/book",
        type="http",
        auth="public",
        methods=["POST"],
        website=False,
        csrf=False,
    )
    def booking_submit(self, **post):
        user = self._booking_user()
        slot = (post.get("slot") or "").strip()
        prenom = (post.get("prenom") or "").strip()
        phone = (post.get("phone") or "").strip()
        email = (post.get("email") or "").strip()
        nom_centre = (post.get("nom_centre") or "").strip()

        if not user or not slot or "|" not in slot or not prenom or not phone:
            return request.redirect("/intellix/rdv/zakaria?error=1")

        start, stop = slot.split("|", 1)
        partner = request.env["res.partner"].sudo()
        if email:
            partner = partner.search([("email", "=ilike", email)], limit=1)
        if not partner and phone:
            partner = partner.search([("phone", "=", phone)], limit=1)
        if not partner:
            partner = partner.create(
                {
                    "name": f"{prenom} {nom_centre}".strip() or prenom,
                    "email": email or False,
                    "phone": phone,
                    "company_name": nom_centre or False,
                }
            )

        title = f"Démo Intellix — {prenom}"
        if nom_centre:
            title += f" ({nom_centre})"

        event = request.env["calendar.event"].sudo().doorway_create_meeting_with_videocall(
            name=title,
            start=start,
            stop=stop,
            partner_ids=[user.partner_id.id, partner.id],
            user_id=user.id,
            description="Tag: Démo Intellix\nRéservation publique /intellix/rdv/zakaria",
        )

        self._notify_n8n_demo_booked(
            event=event,
            prenom=prenom,
            phone=phone,
            email=email,
            nom_centre=nom_centre,
            partner_id=partner.id,
        )

        join = event.videocall_location or ""
        if join.startswith("/"):
            join = request.httprequest.host_url.rstrip("/") + join

        html = f"""<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8"/>
<title>RDV confirmé</title></head><body style="font-family:system-ui;max-width:520px;margin:2rem auto">
<h1>✅ Rendez-vous confirmé</h1>
<p>Bonjour <strong>{prenom}</strong>, votre démo est planifiée.</p>
<ul>
<li><strong>Début :</strong> {fields.Datetime.to_string(event.start)}</li>
<li><strong>Fin :</strong> {fields.Datetime.to_string(event.stop)}</li>
</ul>
{"<p><a href='" + join + "'>Rejoindre la visioconférence</a></p>" if join else ""}
<p>Vous recevrez une confirmation par WhatsApp.</p>
</body></html>"""
        return request.make_response(html, headers=[("Content-Type", "text/html; charset=utf-8")])

    @http.route("/api/intellix/booking/url", type="http", auth="public", methods=["GET"], csrf=False)
    def booking_url_api(self, **kwargs):
        icp = request.env["ir.config_parameter"].sudo()
        url = icp.get_param("doorway_agents_dashboard.booking_demo_url") or (
            request.httprequest.host_url.rstrip("/") + "/intellix/rdv/zakaria"
        )
        return request.make_response(
            json.dumps({"url": url, "user": BOOKING_LOGIN}),
            headers=[("Content-Type", "application/json")],
        )



    BADGES_BY_LOGIN = {
        "martin@agencedoorway.com": ["IntelliX CRM", "Agents IA", "Financement Driven", "Démonstration"],
        "dave@agencedoorway.com": ["Immobilier QC", "Évaluation", "Mise en marché", "IntelliX"],
        "dave.pichette@remax-quebec.com": ["Immobilier QC", "Évaluation", "Mise en marché", "IntelliX"],
        "zakaria@agencedoorway.com": ["Call center IA", "Maroc", "France", "IntelliX CRM", "Démo live"],
    }

    def _martin_slots(self):
        """Créneaux Martin — lun-ven 9h-15h Toronto, pause 12h-13h, 30 min.

        Un RDV dans l'agenda de Martin (organisateur ou invité) retire le créneau,
        y compris s'il se le pose lui-même. Même logique que Hiba (doorway_hiba_qualif).
        """
        Event = request.env["calendar.event"].sudo()
        if hasattr(Event, "doorway_martin_free_slots"):
            return Event.doorway_martin_free_slots()
        user = request.env["res.users"].sudo().search([
            ("login", "=", "martin@agencedoorway.com")
        ], limit=1)
        if not user:
            return [], user
        from datetime import datetime, timedelta
        import pytz
        tz = pytz.timezone("America/Toronto")
        now = datetime.now(tz)
        slots = []
        day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        for _ in range(30):
            day += timedelta(days=1)
            if day.weekday() >= 5:
                continue
            for hour in (9, 10, 11, 13, 14):
                for minute in [0, 30]:
                    slot_local = day.replace(hour=hour, minute=minute)
                    if slot_local <= now:
                        continue
                    slot_utc = slot_local.astimezone(pytz.utc).replace(tzinfo=None)
                    existing = Event.search([
                        "|",
                        ("user_id", "=", user.id),
                        ("partner_ids", "in", [user.partner_id.id]),
                        ("start", "<", slot_utc + timedelta(minutes=30)),
                        ("stop", ">", slot_utc),
                    ])
                    if not existing:
                        slots.append((slot_utc, slot_local))
        return slots[:800], user

    def _dave_slots(self):
        """Créneaux Dave Pichette — 7j/7, 9h-20h Toronto"""
        user = request.env["res.users"].sudo().search([
            ("login", "=", "dave.pichette@remax-quebec.com")
        ], limit=1)
        if not user:
            user = request.env["res.users"].sudo().search([
                ("login", "=", "dave@agencedoorway.com")
            ], limit=1)
        if not user:
            return [], user
        from datetime import datetime, timedelta
        import pytz
        tz = pytz.timezone("America/Toronto")
        now = datetime.now(tz)
        slots = []
        day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        for _ in range(30):
            day += timedelta(days=1)
            for hour in range(9, 20):
                for minute in [0, 30]:
                    slot_local = day.replace(hour=hour, minute=minute)
                    if slot_local <= now:
                        continue
                    slot_utc = slot_local.astimezone(pytz.utc).replace(tzinfo=None)
                    existing = request.env["calendar.event"].sudo().search([
                        ("user_id", "=", user.id),
                        ("start", "<", slot_utc + timedelta(minutes=30)),
                        ("stop", ">", slot_utc),
                    ])
                    if not existing:
                        slots.append((slot_utc, slot_local))
        return slots[:800], user

    def _slots_ui_from_calendar_tuples(self, slots_tuples, tz_name="America/Toronto"):
        """Convert (utc_naive, local_dt) tuples to UI slot groups."""
        import pytz
        from collections import OrderedDict
        tz = pytz.timezone(tz_name)
        months_fr = ["jan", "fév", "mar", "avr", "mai", "jun", "jul", "aoû", "sep", "oct", "nov", "déc"]
        weekdays_fr = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]
        by_day = OrderedDict()
        for slot_utc, slot_local in slots_tuples:
            if slot_local.tzinfo is None:
                slot_local = slot_utc.replace(tzinfo=pytz.utc).astimezone(tz)
            day_key = slot_local.strftime("%Y-%m-%d")
            if day_key not in by_day:
                wd = weekdays_fr[slot_local.weekday()]
                by_day[day_key] = {
                    "date": day_key,
                    "label": f"{wd} {slot_local.day} {months_fr[slot_local.month - 1]}",
                    "times": [],
                    "time_values": {},
                }
            display = slot_local.strftime("%H:%M")
            by_day[day_key]["times"].append(display)
            by_day[day_key]["time_values"][display] = slot_utc.strftime("%Y-%m-%d %H:%M:%S")
        result = []
        for day in by_day.values():
            day["count"] = len(day["times"])
            result.append(day)
        return result

    def _slots_ui_from_zakaria(self, slots):
        """Convert CalendarAvailabilityService slots to UI groups."""
        from collections import OrderedDict
        by_day = OrderedDict()
        for s in slots:
            start_local = s.get("start_local") or ""
            parts = start_local.split(" ")
            day_label = parts[0] if parts else start_local
            time_part = parts[1] if len(parts) > 1 else ""
            date_key = (s.get("start") or "")[:10]
            if not date_key:
                continue
            if date_key not in by_day:
                by_day[date_key] = {
                    "date": date_key,
                    "label": day_label,
                    "times": [],
                    "time_values": {},
                }
            display = time_part[:5] if len(time_part) >= 5 else time_part
            if display and display not in by_day[date_key]["time_values"]:
                by_day[date_key]["times"].append(display)
                by_day[date_key]["time_values"][display] = f'{s["start"]}|{s["stop"]}'
        result = []
        for day in by_day.values():
            day["count"] = len(day["times"])
            result.append(day)
        return result


    def _zakaria_slots(self):
        """Créneaux Zakaria — lun-ven 9h-22h Casablanca, comme Dave/Martin."""
        user = request.env["res.users"].sudo().search(
            [("login", "=", "zakaria@agencedoorway.com")], limit=1
        )
        if not user:
            return [], user
        from datetime import datetime, timedelta
        import pytz
        tz = pytz.timezone(BOOKING_TZ)
        now = datetime.now(tz)
        Event = request.env["calendar.event"].sudo()
        slots = []
        day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        duration = timedelta(minutes=BOOKING_DURATION_MIN)
        for _ in range(30):
            day += timedelta(days=1)
            if day.weekday() >= 5:
                continue
            for hour in range(9, 22):
                for minute in (0, 30):
                    slot_local = day.replace(hour=hour, minute=minute)
                    if slot_local <= now:
                        continue
                    slot_utc = slot_local.astimezone(pytz.utc).replace(tzinfo=None)
                    existing = Event.search(
                        [
                            "|",
                            ("user_id", "=", user.id),
                            ("partner_ids", "in", [user.partner_id.id]),
                            ("start", "<", slot_utc + duration),
                            ("stop", ">", slot_utc),
                        ],
                        limit=1,
                    )
                    if not existing:
                        slots.append((slot_utc, slot_local))
        return slots[:800], user

    def _slots_ui_from_zakaria_tuples(self, slots_tuples):
        """Même grille que Dave/Martin, format start|stop du POST Zakaria."""
        ui = self._slots_ui_from_calendar_tuples(
            slots_tuples, tz_name=BOOKING_TZ
        )
        duration = timedelta(minutes=BOOKING_DURATION_MIN)
        for day in ui:
            mapped = {}
            for display, start_s in (day.get("time_values") or {}).items():
                start_dt = fields.Datetime.from_string(start_s)
                stop_dt = start_dt + duration
                mapped[display] = "%s|%s" % (
                    fields.Datetime.to_string(start_dt),
                    fields.Datetime.to_string(stop_dt),
                )
            day["time_values"] = mapped
        return ui

    def _slots_ui_from_dave(self, slots_tuples):
        """Dave book endpoint expects ISO slot values."""
        ui = self._slots_ui_from_calendar_tuples(slots_tuples)
        for day in ui:
            iso_values = {}
            for display, val in day["time_values"].items():
                iso_values[display] = val.replace(" ", "T", 1)[:16]
            day["time_values"] = iso_values
        return ui

    def _generate_slots(self, user):
        """Créneaux disponibles pour la page publique — logique inchangée par conseiller."""
        login = user.login or ""
        if login == "martin@agencedoorway.com":
            raw, _user = self._martin_slots()
            return self._slots_ui_from_calendar_tuples(raw) if _user else []
        if login in ("dave@agencedoorway.com", "dave.pichette@remax-quebec.com"):
            raw, _user = self._dave_slots()
            return self._slots_ui_from_dave(raw) if _user else []
        if login == "zakaria@agencedoorway.com" or login == BOOKING_LOGIN:
            user.sudo()._doorway_ensure_public_calendar()
            raw, _user = self._zakaria_slots()
            return self._slots_ui_from_zakaria_tuples(raw) if _user else []
        return []

    def _booking_page_config(self, user):
        """Paramètres d'affichage par conseiller (book URL, durée, champs)."""
        login = user.login or ""
        defaults = {
            "book_url": "/intellix/rdv/martin/book",
            "book_type": "martin",
            "duration_min": 30,
            "availability_html": (
                "Lun–Ven, 9h–15h (pause 12h–13h)<br>"
                '<span style="color:var(--muted);font-size:12px">Heure de Toronto · 30 min · Hiba</span>'
            ),
            "extra_fields_html": "",
            "confirm_label": "Confirmer le rendez-vous",
        }
        configs = {
            "martin@agencedoorway.com": defaults,
            "dave@agencedoorway.com": {
                **defaults,
                "book_url": "/intellix/rdv/dave/book",
                "book_type": "dave",
                "availability_html": (
                    "7 jours, 9h–20h<br>"
                    '<span style="color:var(--muted);font-size:12px">Heure de Toronto (EST)</span>'
                ),
                "extra_fields_html": (
                    '<div class="form-field full"><label>Adresse du bien *</label>'
                    '<input name="adresse" required placeholder="123 rue des Érables, Québec"/></div>'
                ),
                "confirm_label": "Confirmer l'évaluation gratuite",
            },
            "dave.pichette@remax-quebec.com": {
                **defaults,
                "book_url": "/intellix/rdv/dave/book",
                "book_type": "dave",
                "availability_html": (
                    "7 jours, 9h–20h<br>"
                    '<span style="color:var(--muted);font-size:12px">Heure de Toronto (EST)</span>'
                ),
                "extra_fields_html": (
                    '<div class="form-field full"><label>Adresse du bien *</label>'
                    '<input name="adresse" required placeholder="123 rue des Érables, Québec"/></div>'
                ),
                "confirm_label": "Confirmer l'évaluation gratuite",
            },
            "zakaria@agencedoorway.com": {
                **defaults,
                "book_url": "/intellix/rdv/zakaria/book",
                "book_type": "zakaria",
                "duration_min": BOOKING_DURATION_MIN,
                "availability_html": (
                    "Lun–Ven, 9h–22h<br>"
                    '<span style="color:var(--muted);font-size:12px">Heure de Casablanca</span>'
                ),
                "extra_fields_html": (
                    '<div class="form-field full"><label>Nom du centre</label>'
                    '<input name="nom_centre" placeholder="Nom de votre centre"/></div>'
                ),
                "confirm_label": "Confirmer la démo",
            },
        }
        return configs.get(login, defaults)

    def booking_page(self, user_login, **kwargs):
        """Page de réservation générique — injecte les données du conseiller."""
        user = request.env["res.users"].sudo().search([("login", "=", user_login)], limit=1)
        if not user:
            return request.make_response(
                "<h2>Indisponible</h2>",
                headers=[("Content-Type", "text/html; charset=utf-8")],
                status=503,
            )
        slots = self._generate_slots(user)
        cfg = self._booking_page_config(user)
        html = self._render_booking_html(user, slots, **cfg)
        return request.make_response(html, headers=[("Content-Type", "text/html; charset=utf-8")])

    def _render_booking_html(
        self,
        user,
        slots,
        book_url,
        book_type="martin",
        duration_min=30,
        availability_html="Lun–Ven, 9h–18h<br><span style=\"color:var(--muted);font-size:12px\">Heure de Toronto (EST)</span>",
        extra_fields_html="",
        confirm_label="Confirmer le rendez-vous",
    ):
        """Génère le HTML de la page de réservation — design professionnel blanc/bleu."""
        name = user.name or "Conseiller"
        title = getattr(user, "job_title", None) or user.function or "Conseiller IntelliX"
        email = user.email or user.login or ""
        parts = name.split()
        initiales = "".join(p[0].upper() for p in parts[:2]) if parts else "IX"
        badges = self.BADGES_BY_LOGIN.get(email, self.BADGES_BY_LOGIN.get(user.login, ["IntelliX CRM", "Consultation"]))
        badges_html = "".join(f'<span class="badge">{b}</span>' for b in badges)
        slots_json = json.dumps(slots, ensure_ascii=False)
        book_config_json = json.dumps({"url": book_url, "type": book_type}, ensure_ascii=False)
        login = user.login or ""
        tz_name = "Africa/Casablanca" if "zakaria" in login else "America/Toronto"
        today_iso = datetime.now(pytz.timezone(tz_name)).strftime("%Y-%m-%d")

        html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>RDV avec {name} — IntelliX</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  :root {{
    --navy:  #1B3A6B; --navy-lt: #2A4F8F; --cyan: #0EA5E9; --cyan-lt: #E0F2FE;
    --white: #FFFFFF; --bg: #F1F5F9; --bg2: #E8EEF6; --text: #1E293B;
    --muted: #64748B; --border: #CBD5E1; --success: #16A34A; --r: 12px;
  }}
  html, body {{ min-height:100vh; font-family:'Inter',system-ui,sans-serif; background:var(--bg); color:var(--text); font-size:15px; line-height:1.5; }}
  .progress-bar {{ position:fixed; top:0; left:0; height:3px; background:linear-gradient(90deg,var(--navy),var(--cyan)); transition:width 0.4s ease; z-index:100; }}
  .header {{ background:var(--white); border-bottom:1px solid var(--border); padding:0 2rem; height:60px; display:flex; align-items:center; justify-content:space-between; position:sticky; top:0; z-index:50; }}
  .logo {{ display:flex; align-items:center; gap:10px; font-weight:700; font-size:16px; color:var(--navy); text-decoration:none; }}
  .logo-dot {{ width:28px; height:28px; background:linear-gradient(135deg,var(--navy),var(--cyan)); border-radius:7px; display:grid; place-items:center; color:white; font-size:13px; font-weight:700; }}
  .header-tag {{ font-size:12px; color:var(--muted); background:var(--bg); padding:4px 10px; border-radius:20px; border:1px solid var(--border); }}
  .page {{ max-width:980px; margin:0 auto; padding:2.5rem 1.5rem 4rem; display:grid; grid-template-columns:280px 1fr; gap:28px; align-items:start; }}
  .sidebar {{ background:var(--white); border-radius:var(--r); border:1px solid var(--border); overflow:hidden; position:sticky; top:80px; }}
  .sidebar-top {{ background:linear-gradient(160deg,var(--navy) 0%,var(--navy-lt) 100%); padding:28px 24px 24px; text-align:center; }}
  .avatar {{ width:72px; height:72px; background:linear-gradient(135deg,var(--cyan),#38BDF8); border-radius:50%; display:flex; align-items:center; justify-content:center; font-size:26px; font-weight:700; color:white; margin:0 auto 14px; border:3px solid rgba(255,255,255,0.2); letter-spacing:-1px; }}
  .sidebar-name {{ font-size:17px; font-weight:700; color:white; margin-bottom:3px; }}
  .sidebar-title {{ font-size:12px; color:rgba(255,255,255,0.65); }}
  .sidebar-body {{ padding:20px 22px; }}
  .info-row {{ display:flex; align-items:flex-start; gap:10px; margin-bottom:13px; }}
  .info-icon {{ width:32px; height:32px; background:var(--cyan-lt); border-radius:8px; display:grid; place-items:center; flex-shrink:0; font-size:15px; }}
  .info-label {{ font-size:11px; font-weight:600; color:var(--muted); text-transform:uppercase; letter-spacing:0.05em; margin-bottom:2px; }}
  .info-val {{ font-size:13px; color:var(--text); font-weight:500; }}
  .sidebar-divider {{ height:1px; background:var(--border); margin:16px 0; }}
  .badge-list {{ display:flex; flex-wrap:wrap; gap:6px; }}
  .badge {{ font-size:11px; font-weight:500; padding:4px 10px; border-radius:20px; background:var(--bg); color:var(--navy); border:1px solid var(--bg2); }}
  .booking {{ display:flex; flex-direction:column; gap:20px; }}
  .booking-title {{ font-size:24px; font-weight:700; color:var(--navy); letter-spacing:-0.02em; }}
  .booking-sub {{ font-size:14px; color:var(--muted); margin-top:4px; }}
  .steps {{ display:flex; align-items:center; background:var(--white); border:1px solid var(--border); border-radius:var(--r); padding:14px 20px; }}
  .step {{ display:flex; align-items:center; gap:8px; flex:1; }}
  .step-num {{ width:26px; height:26px; border-radius:50%; display:grid; place-items:center; font-size:12px; font-weight:700; flex-shrink:0; transition:all 0.25s; }}
  .step.active .step-num {{ background:var(--navy); color:white; }}
  .step.done .step-num {{ background:var(--success); color:white; }}
  .step.pending .step-num {{ background:var(--bg2); color:var(--muted); }}
  .step-label {{ font-size:13px; font-weight:500; }}
  .step.active .step-label {{ color:var(--navy); }}
  .step.done .step-label {{ color:var(--success); }}
  .step.pending .step-label {{ color:var(--muted); }}
  .step-arrow {{ color:var(--border); font-size:18px; padding:0 8px; flex-shrink:0; }}
  .card {{ background:var(--white); border:1px solid var(--border); border-radius:var(--r); overflow:hidden; }}
  .card-header {{ padding:16px 22px; border-bottom:1px solid var(--border); display:flex; align-items:center; gap:10px; }}
  .card-header-icon {{ width:32px; height:32px; background:var(--cyan-lt); border-radius:8px; display:grid; place-items:center; font-size:16px; flex-shrink:0; }}
  .card-title {{ font-size:13px; font-weight:700; color:var(--navy); text-transform:uppercase; letter-spacing:0.06em; }}
  .card-body {{ padding:18px 20px; }}
  .days-grid {{ display:grid; grid-template-columns:1fr 1fr; gap:10px; }}
  .section-label {{ font-size:12px; font-weight:700; color:var(--navy); text-transform:uppercase; letter-spacing:0.05em; margin:4px 0 10px; }}
  .cal-block {{ margin-top:20px; padding-top:16px; border-top:1px solid var(--border); }}
  .cal-head {{ display:flex; justify-content:space-between; align-items:baseline; margin-bottom:10px; gap:10px; }}
  .cal-month {{ font-size:14px; font-weight:700; color:var(--navy); }}
  .cal-legend {{ font-size:12px; color:var(--muted); }}
  .cal-grid {{ display:grid; grid-template-columns:repeat(7,minmax(0,1fr)); gap:6px; }}
  .cal-dow {{ text-align:center; font-size:11px; font-weight:600; color:var(--muted); text-transform:uppercase; padding:4px 0; }}
  .cal-pad {{ min-height:42px; }}
  .cal-day {{ min-height:48px; border:1.5px solid var(--border); border-radius:10px; background:var(--white); cursor:pointer; display:flex; flex-direction:column; align-items:center; justify-content:center; gap:2px; font-size:14px; font-weight:600; color:var(--text); font-family:inherit; padding:4px 2px; }}
  .cal-day.has {{ border-color:#93C5FD; }}
  .cal-day.has:hover {{ border-color:var(--cyan); background:var(--cyan-lt); }}
  .cal-day.empty {{ color:var(--muted); opacity:0.4; cursor:default; background:var(--bg); }}
  .cal-day.selected {{ border-color:var(--navy); background:var(--navy); color:white; }}
  .cal-count {{ font-size:9px; font-weight:600; color:var(--cyan); line-height:1; }}
  .cal-day.selected .cal-count {{ color:rgba(255,255,255,0.85); }}
  @media(max-width:720px) {{
    .cal-day {{ min-height:42px; font-size:13px; }}
  }}
  .day-btn {{ display:flex; align-items:center; gap:12px; padding:13px 16px; border:1.5px solid var(--border); border-radius:10px; background:var(--white); cursor:pointer; transition:all 0.18s ease; text-align:left; width:100%; }}
  .day-btn:hover {{ border-color:var(--cyan); background:var(--cyan-lt); transform:translateY(-1px); box-shadow:0 4px 12px rgba(14,165,233,0.15); }}
  .day-btn.selected {{ border-color:var(--navy); background:#EEF2FF; box-shadow:0 0 0 3px rgba(27,58,107,0.1); }}
  .day-icon {{ width:36px; height:36px; border-radius:8px; background:var(--bg); display:flex; flex-direction:column; align-items:center; justify-content:center; flex-shrink:0; transition:background 0.18s; }}
  .day-btn:hover .day-icon {{ background:rgba(14,165,233,0.12); }}
  .day-btn.selected .day-icon {{ background:var(--navy); }}
  .day-num {{ font-size:15px; font-weight:700; color:var(--text); line-height:1; transition:color 0.18s; }}
  .day-btn:hover .day-num {{ color:var(--cyan); }}
  .day-btn.selected .day-num {{ color:white; }}
  .day-month {{ font-size:9px; font-weight:600; text-transform:uppercase; color:var(--muted); letter-spacing:0.05em; transition:color 0.18s; }}
  .day-btn.selected .day-month {{ color:rgba(255,255,255,0.7); }}
  .day-name {{ font-size:14px; font-weight:600; color:var(--text); }}
  .day-slots {{ font-size:12px; color:var(--muted); margin-top:1px; }}
  .day-arrow {{ color:var(--border); font-size:16px; transition:all 0.18s; }}
  .day-btn:hover .day-arrow {{ color:var(--cyan); }}
  .day-btn.selected .day-arrow {{ color:var(--navy); }}
  .times-grid {{ display:grid; grid-template-columns:repeat(3,1fr); gap:8px; }}
  .time-btn {{ padding:11px 8px; border:1.5px solid var(--border); border-radius:9px; background:var(--white); cursor:pointer; font-size:14px; font-weight:600; color:var(--text); transition:all 0.18s; text-align:center; font-family:inherit; }}
  .time-btn:hover {{ border-color:var(--cyan); background:var(--cyan-lt); color:var(--navy); }}
  .time-btn.selected {{ border-color:var(--navy); background:var(--navy); color:white; }}
  .times-empty {{ text-align:center; padding:32px 20px; color:var(--muted); font-size:14px; }}
  .confirm-card {{ background:#EEF2FF; border:1.5px solid #C7D2FE; border-radius:var(--r); padding:20px 22px; display:none; }}
  .confirm-card.visible {{ display:block; }}
  .confirm-title {{ font-size:14px; font-weight:700; color:var(--navy); margin-bottom:12px; }}
  .confirm-row {{ display:flex; justify-content:space-between; align-items:center; padding:8px 0; border-bottom:1px solid #C7D2FE; font-size:13px; }}
  .confirm-row:last-of-type {{ border-bottom:none; }}
  .confirm-key {{ color:var(--muted); font-weight:500; }}
  .confirm-val {{ color:var(--text); font-weight:600; }}
  .form-grid {{ display:grid; grid-template-columns:1fr 1fr; gap:10px; margin-top:14px; }}
  .form-field {{ display:flex; flex-direction:column; gap:4px; }}
  .form-field.full {{ grid-column:1 / -1; }}
  .form-field label {{ font-size:11px; font-weight:600; color:var(--muted); text-transform:uppercase; letter-spacing:0.04em; }}
  .form-field input {{ padding:10px 12px; border:1.5px solid var(--border); border-radius:8px; font-size:14px; font-family:inherit; width:100%; }}
  .form-field input:focus {{ outline:none; border-color:var(--cyan); box-shadow:0 0 0 3px rgba(14,165,233,0.15); }}
  .voice-bar {{ display:flex; flex-wrap:wrap; align-items:center; gap:8px; margin:14px 0 4px; padding:10px 12px; background:#EEF2FF; border:1px solid #C7D2FE; border-radius:10px; }}
  .voice-global {{ display:inline-flex; align-items:center; gap:6px; padding:8px 12px; border-radius:8px; border:1px solid var(--navy); background:var(--navy); color:white; font-weight:600; font-size:13px; cursor:pointer; font-family:inherit; }}
  .voice-global.listening {{ background:#dc2626; border-color:#dc2626; }}
  .voice-status {{ font-size:12px; color:var(--muted); }}
  .voice-status.error {{ color:#b91c1c; }}
  .voice-input-wrap {{ display:flex; align-items:center; gap:6px; }}
  .voice-mic {{ flex-shrink:0; width:36px; height:36px; border-radius:8px; border:1.5px solid var(--border); background:var(--white); cursor:pointer; font-size:15px; line-height:1; }}
  .voice-mic.listening {{ background:#fee2e2; border-color:#ef4444; }}
  .btn-confirm {{ width:100%; margin-top:14px; padding:13px; background:var(--navy); color:white; border:none; border-radius:10px; font-size:15px; font-weight:600; cursor:pointer; font-family:inherit; transition:all 0.18s; display:flex; align-items:center; justify-content:center; gap:8px; }}
  .btn-confirm:hover {{ background:var(--navy-lt); transform:translateY(-1px); box-shadow:0 6px 20px rgba(27,58,107,0.25); }}
  .success-panel {{ background:var(--white); border:1px solid var(--border); border-radius:var(--r); padding:40px 32px; text-align:center; display:none; }}
  .success-panel.visible {{ display:block; }}
  .success-icon {{ width:64px; height:64px; background:#DCFCE7; border-radius:50%; display:flex; align-items:center; justify-content:center; font-size:28px; margin:0 auto 20px; }}
  .success-title {{ font-size:20px; font-weight:700; color:var(--navy); margin-bottom:8px; }}
  .success-sub {{ font-size:14px; color:var(--muted); }}
  .footer {{ text-align:center; font-size:12px; color:var(--muted); padding:24px; border-top:1px solid var(--border); margin-top:20px; }}
  .footer a {{ color:var(--cyan); text-decoration:none; }}
  @media(max-width:720px) {{
    .page {{ grid-template-columns:1fr; }}
    .sidebar {{ position:static; }}
    .days-grid {{ grid-template-columns:1fr; }}
    .times-grid {{ grid-template-columns:repeat(2,1fr); }}
    .form-grid {{ grid-template-columns:1fr; }}
  }}
</style>
</head>
<body>
<div class="progress-bar" id="progressBar" style="width:33%"></div>
<header class="header">
  <a href="/" class="logo">
    <div class="logo-dot">IX</div>IntelliX
  </a>
  <span class="header-tag">Prise de rendez-vous</span>
</header>
<main class="page">
  <aside class="sidebar">
    <div class="sidebar-top">
      <div class="avatar">{initiales}</div>
      <div class="sidebar-name">{name}</div>
      <div class="sidebar-title">{title}</div>
    </div>
    <div class="sidebar-body">
      <div class="info-row">
        <div class="info-icon">⏱</div>
        <div><div class="info-label">Durée</div><div class="info-val">{duration_min} minutes</div></div>
      </div>
      <div class="info-row">
        <div class="info-icon">📍</div>
        <div><div class="info-label">Format</div><div class="info-val">Appel vidéo ou téléphone</div></div>
      </div>
      <div class="info-row">
        <div class="info-icon">🕘</div>
        <div><div class="info-label">Disponibilités</div><div class="info-val">{availability_html}</div></div>
      </div>
      <div class="sidebar-divider"></div>
      <div class="info-label" style="margin-bottom:10px">Sujets abordés</div>
      <div class="badge-list">{badges_html}</div>
    </div>
  </aside>
  <div class="booking">
    <div>
      <h1 class="booking-title">Réserver un rendez-vous</h1>
      <p class="booking-sub" id="bookingSub">Choisissez un créneau disponible ci-dessous — confirmation immédiate par email.</p>
    </div>
    <div class="steps">
      <div class="step active" id="step1"><div class="step-num">1</div><span class="step-label">Choisir un jour</span></div>
      <div class="step-arrow">›</div>
      <div class="step pending" id="step2"><div class="step-num">2</div><span class="step-label">Choisir l'heure</span></div>
      <div class="step-arrow">›</div>
      <div class="step pending" id="step3"><div class="step-num">3</div><span class="step-label">Confirmer</span></div>
    </div>
    <div class="card" id="dayCard">
      <div class="card-header">
        <div class="card-header-icon">📅</div>
        <span class="card-title">Sélectionner un jour</span>
      </div>
      <div class="card-body">
        <div class="section-label">5 prochains jours</div>
        <div class="days-grid" id="daysGrid"></div>
        <div class="cal-block">
          <div class="cal-head">
            <div class="cal-month" id="calMonth">30 prochains jours</div>
            <div class="cal-legend">Mode calendrier</div>
          </div>
          <div class="cal-grid" id="calDows"></div>
          <div class="cal-grid" id="calGrid"></div>
        </div>
      </div>
    </div>
    <div class="card" id="timeCard">
      <div class="card-header">
        <div class="card-header-icon">🕐</div>
        <span class="card-title" id="timeCardTitle">Sélectionner une heure</span>
      </div>
      <div class="card-body" id="timeCardBody">
        <div class="times-empty">← Choisissez d'abord un jour</div>
      </div>
    </div>
    <form class="confirm-card" id="confirmCard" method="post" action="{book_url}">
      <input type="hidden" name="slot" id="slotInput"/>
      <div class="confirm-title">✅ Récapitulatif</div>
      <div class="confirm-row"><span class="confirm-key">Conseiller</span><span class="confirm-val">{name}</span></div>
      <div class="confirm-row"><span class="confirm-key">Date</span><span class="confirm-val" id="confirmDate">—</span></div>
      <div class="confirm-row"><span class="confirm-key">Heure</span><span class="confirm-val" id="confirmTime">—</span></div>
      <div class="confirm-row"><span class="confirm-key">Durée</span><span class="confirm-val">{duration_min} minutes</span></div>
      <div class="confirm-row"><span class="confirm-key">Format</span><span class="confirm-val">Appel vidéo / téléphone</span></div>
      <div class="form-grid">
        <div class="form-field"><label>Prénom *</label><input name="prenom" required placeholder="Votre prénom"/></div>
        <div class="form-field"><label>Nom *</label><input name="nom" required placeholder="Votre nom"/></div>
        <div class="form-field"><label>Téléphone *</label><input name="phone" required placeholder="+1 514 000 0000"/></div>
        <div class="form-field"><label>Email</label><input name="email" type="email" placeholder="votre@email.com"/></div>
        {extra_fields_html}
      </div>
      <button class="btn-confirm" type="submit">
        <span>{confirm_label}</span><span>→</span>
      </button>
    </form>
    <div class="success-panel" id="successPanel">
      <div class="success-icon">✓</div>
      <div class="success-title">Rendez-vous confirmé !</div>
      <p class="success-sub" id="successMsg">Un email de confirmation vous a été envoyé.</p>
    </div>
  </div>
</main>
<footer class="footer">
  Propulsé par <a href="https://intellixcrm.com">IntelliX</a> — Plateforme IA call center
</footer>
<script>
const SLOTS = {slots_json};
const BOOK_CONFIG = {book_config_json};
const TODAY = "{today_iso}";
let selectedDay = null, selectedTime = null;

function addDays(iso, n) {{
  const d = new Date(iso + "T12:00:00");
  d.setDate(d.getDate() + n);
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return y + "-" + m + "-" + day;
}}
function parseIso(iso) {{ return new Date(iso + "T12:00:00"); }}
const byDate = {{}};
SLOTS.forEach(day => {{ byDate[day.date] = day; }});
const startIso = byDate[TODAY] ? TODAY : addDays(TODAY, 1);
const monthsFr = ["janvier","février","mars","avril","mai","juin","juillet","août","septembre","octobre","novembre","décembre"];
const dows = ["Lun","Mar","Mer","Jeu","Ven","Sam","Dim"];

function makeDayObj(iso) {{
  if (byDate[iso]) return byDate[iso];
  const d = parseIso(iso);
  const wd = dows[(d.getDay() + 6) % 7];
  const monthsShort = ["jan","fév","mar","avr","mai","jun","jul","aoû","sep","oct","nov","déc"];
  return {{ date: iso, label: wd + " " + d.getDate() + " " + monthsShort[d.getMonth()], count: 0, times: [], time_values: {{}} }};
}}

function renderDayCard(day) {{
  const d = parseIso(day.date);
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "day-btn";
  btn.dataset.date = day.date;
  if (!day.count) btn.disabled = true;
  btn.innerHTML = `
    <div class="day-icon">
      <div class="day-num">${{d.getDate()}}</div>
      <div class="day-month">${{d.toLocaleDateString("fr-CA",{{month:"short"}})}}</div>
    </div>
    <div style="flex:1">
      <div class="day-name">${{day.label}}</div>
      <div class="day-slots">${{day.count ? (day.count + " créneaux disponibles") : "Aucun créneau"}}</div>
    </div>
    <div class="day-arrow">›</div>`;
  if (day.count) btn.addEventListener("click", () => selectDay(day, btn));
  return btn;
}}

const grid = document.getElementById("daysGrid");
if (!SLOTS.length) {{
  grid.innerHTML = '<div class="times-empty">Aucun créneau disponible — contactez-nous directement.</div>';
}} else {{
  for (let i = 0; i < 5; i++) {{
    grid.appendChild(renderDayCard(makeDayObj(addDays(startIso, i))));
  }}
}}

(function renderCalendar() {{
  const dowEl = document.getElementById("calDows");
  const calEl = document.getElementById("calGrid");
  dows.forEach(w => {{
    const el = document.createElement("div");
    el.className = "cal-dow";
    el.textContent = w;
    dowEl.appendChild(el);
  }});
  const first = parseIso(TODAY);
  const last = parseIso(addDays(TODAY, 29));
  const m1 = monthsFr[first.getMonth()];
  const m2 = monthsFr[last.getMonth()];
  document.getElementById("calMonth").textContent = m1 === m2
    ? (m1.charAt(0).toUpperCase() + m1.slice(1) + " " + first.getFullYear())
    : (m1.charAt(0).toUpperCase() + m1.slice(1) + " – " + m2 + " " + last.getFullYear());
  const pad = (first.getDay() + 6) % 7;
  for (let i = 0; i < pad; i++) {{
    const p = document.createElement("div");
    p.className = "cal-pad";
    calEl.appendChild(p);
  }}
  for (let i = 0; i < 30; i++) {{
    const iso = addDays(TODAY, i);
    const day = makeDayObj(iso);
    const d = parseIso(iso);
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "cal-day" + (day.count ? " has" : " empty");
    btn.dataset.date = iso;
    btn.innerHTML = "<span>" + d.getDate() + "</span>" +
      (day.count ? '<span class="cal-count">' + day.count + "</span>" : "");
    if (day.count) btn.addEventListener("click", () => selectDay(day, btn));
    else btn.disabled = true;
    calEl.appendChild(btn);
  }}
}})();

function selectDay(day, btn) {{
  document.querySelectorAll(".day-btn, .cal-day").forEach(b => b.classList.remove("selected"));
  document.querySelectorAll("[data-date='" + day.date + "']").forEach(b => b.classList.add("selected"));
  if (btn) btn.classList.add("selected");
  selectedDay = day; selectedTime = null;
  setStep(1,'done'); setStep(2,'active');
  document.getElementById('progressBar').style.width = '66%';
  document.getElementById('timeCardTitle').textContent = `Heure — ${{day.label}}`;
  document.getElementById('timeCardBody').innerHTML =
    `<div class="times-grid">${{day.times.map(t =>
      `<button type="button" class="time-btn" onclick="selectTime('${{t}}',this)">${{t}}</button>`
    ).join('')}}</div>`;
  document.getElementById('confirmCard').classList.remove('visible');
  document.getElementById('timeCard').scrollIntoView({{behavior:'smooth',block:'nearest'}});
}}

function selectTime(t, btn) {{
  document.querySelectorAll('.time-btn').forEach(b => b.classList.remove('selected'));
  btn.classList.add('selected');
  selectedTime = t;
  setStep(2,'done'); setStep(3,'active');
  document.getElementById('progressBar').style.width = '95%';
  document.getElementById('confirmDate').textContent = selectedDay.label + ' ' + new Date(selectedDay.date+'T12:00:00').getFullYear();
  document.getElementById('confirmTime').textContent = t;
  const slotVal = (selectedDay.time_values && selectedDay.time_values[t]) ? selectedDay.time_values[t] : (selectedDay.date + ' ' + t + ':00');
  document.getElementById('slotInput').value = slotVal;
  const card = document.getElementById('confirmCard');
  card.classList.add('visible');
  card.scrollIntoView({{behavior:'smooth',block:'nearest'}});
}}

function setStep(n, state) {{
  const el = document.getElementById('step'+n);
  el.className = 'step ' + state;
  el.querySelector('.step-num').textContent = state==='done' ? '✓' : n;
}}
</script>
<script>
{VOICE_FILL_SCRIPT}
</script>
</body>
</html>"""
        return html

    @http.route("/intellix/rdv/zakaria", type="http", auth="public", website=False, csrf=False)
    def booking_page_zakaria(self, **kwargs):
        user = self._booking_user()
        if not user:
            return request.make_response(
                "<h1>Calendrier indisponible</h1>",
                headers=[("Content-Type", "text/html; charset=utf-8")],
                status=503,
            )
        return self.booking_page(user_login=user.login, **kwargs)

    @http.route("/intellix/rdv/martin", type="http", auth="public", website=False, csrf=False)
    def booking_page_martin(self, **kwargs):
        return self.booking_page(user_login="martin@agencedoorway.com", **kwargs)

    @http.route("/intellix/rdv/dave", type="http", auth="public", website=False, csrf=False)
    def booking_page_dave(self, **kwargs):
        user = request.env["res.users"].sudo().search([
            ("login", "in", ["dave@agencedoorway.com", "dave.pichette@remax-quebec.com"])
        ], limit=1)
        if not user:
            return request.make_response(
                "<h2>Indisponible</h2>",
                headers=[("Content-Type", "text/html; charset=utf-8")],
                status=503,
            )
        return self.booking_page(user_login=user.login, **kwargs)

    @http.route("/intellix/rdv/martin/book", type="http", auth="public", methods=["POST"], csrf=False)
    def booking_martin_book(self, slot=None, prenom=None, nom=None, phone=None, email=None, **kwargs):
        from datetime import datetime, timedelta
        user = request.env['res.users'].sudo().search([
            ('login', '=', 'martin@agencedoorway.com')
        ], limit=1)
        if not user or not slot:
            return request.redirect('/intellix/rdv/martin?error=1')
        try:
            start = datetime.strptime(slot, '%Y-%m-%d %H:%M:%S')
            Event = request.env['calendar.event'].sudo()
            if hasattr(Event, 'doorway_martin_busy_domain'):
                if Event.search_count(Event.doorway_martin_busy_domain(user, start)):
                    return request.redirect('/intellix/rdv/martin?error=1')
            else:
                if Event.search_count([
                    '|',
                    ('user_id', '=', user.id),
                    ('partner_ids', 'in', [user.partner_id.id]),
                    ('start', '<', start + timedelta(minutes=30)),
                    ('stop', '>', start),
                ]):
                    return request.redirect('/intellix/rdv/martin?error=1')
            stop = start + timedelta(minutes=30)
            partner = request.env['res.partner'].sudo().search([('email', '=', email)], limit=1)
            if not partner and email:
                partner = request.env['res.partner'].sudo().create({
                    'name': f'{prenom} {nom}',
                    'email': email,
                    'phone': phone,
                })
            hiba = request.env['res.users'].sudo().search([
                ('login', '=', 'hiba@agencedoorway.com'),
                ('active', '=', True),
            ], limit=1)
            attendees = [(4, user.partner_id.id)]
            if hiba:
                attendees.append((4, hiba.partner_id.id))
            if partner:
                attendees.append((4, partner.id))
            event_vals = {
                'name': f'RDV {prenom} {nom} — IntelliX',
                'start': start,
                'stop': stop,
                'user_id': user.id,
                'event_tz': 'America/Toronto',
                'partner_ids': attendees,
                'description': f'RDV réservé via IntelliX (suivi Hiba)\nTél: {phone}\nEmail: {email}',
            }
            Part = request.env['coins.quebec.partenariat'].sudo() if 'coins.quebec.partenariat' in request.env else None
            part = None
            if Part is not None and hasattr(Part, '_cq_find_for_booking'):
                part = Part._cq_find_for_booking(email=email, phone=phone)
                if part:
                    model = request.env['ir.model'].sudo()._get('coins.quebec.partenariat')
                    if model:
                        event_vals['res_model_id'] = model.id
                        event_vals['res_id'] = part.id
            event = request.env['calendar.event'].sudo().create(event_vals)
            if part:
                part._cq_mark_en_rdv_from_event(event)
            return self._martin_rdv_result_page(event, created=True)
        except Exception as e:
            return request.redirect('/intellix/rdv/martin?error=1')

    def _rdv_token(self, event):
        secret = (
            request.env["ir.config_parameter"].sudo().get_param("database.secret")
            or "intellix-rdv"
        )
        raw = "%s:%s" % (event.id, event.create_date)
        return hmac.new(secret.encode(), raw.encode(), hashlib.sha256).hexdigest()[:20]

    def _load_martin_event(self, event_id, token):
        event = request.env["calendar.event"].sudo().browse(int(event_id or 0))
        if not event.exists():
            return None
        expected = self._rdv_token(event)
        if not token or not hmac.compare_digest(expected, token):
            return None
        return event

    def _martin_rdv_result_page(self, event, created=False, cancelled=False, message=""):
        token = self._rdv_token(event) if event and event.exists() else ""
        manage = "/intellix/rdv/martin/manage/%s?t=%s" % (event.id, token) if token else ""
        title = "RDV annulé" if cancelled else ("RDV confirmé" if created else "RDV mis à jour")
        heading = (
            "Rendez-vous annulé"
            if cancelled
            else ("RDV confirmé !" if created else "Rendez-vous modifié")
        )
        when = format_booking_when(event.start) if event and event.exists() and not cancelled else ""
        actions = ""
        if manage and not cancelled:
            actions = """
<p style="margin-top:1.5rem;display:flex;gap:12px;justify-content:center;flex-wrap:wrap">
  <a href="%s" style="background:#06b6d4;color:#041018;padding:10px 16px;border-radius:8px;text-decoration:none;font-weight:600">Modifier le créneau</a>
  <a href="%s&amp;cancel=1" style="background:#3f1d1d;color:#fecaca;padding:10px 16px;border-radius:8px;text-decoration:none;font-weight:600">Annuler le RDV</a>
</p>""" % (manage, manage)
        html = """<!DOCTYPE html>
<html lang="fr"><head><meta charset="utf-8"/><title>%s</title>
<style>body{font-family:Arial;max-width:500px;margin:40px auto;padding:20px;background:#0a0a12;color:#fff;text-align:center}
h1{color:#06b6d4}a{color:#67e8f9}</style></head><body>
<h1>✅ %s</h1>
<p>Votre rendez-vous avec <strong>Martin Houle</strong> %s.</p>
%s
<p>Durée : 30 minutes</p>
<p style="color:#aaa">%s</p>
%s
</body></html>""" % (
            title,
            heading,
            "a été annulé" if cancelled else "est confirmé",
            ("<p><strong>%s</strong></p>" % when) if when else "",
            message or ("Vous recevrez une confirmation par email." if not cancelled else ""),
            actions,
        )
        return request.make_response(html, headers=[("Content-Type", "text/html; charset=utf-8")])

    def _martin_slots_html(self, event, token):
        slots_tuples, _user = self._martin_slots()
        # Remettre le créneau actuel dans la liste pour le voir sélectionné.
        current = event.start
        days = {}
        for slot_utc, slot_local in slots_tuples:
            key = slot_local.strftime("%Y-%m-%d")
            days.setdefault(key, []).append((slot_utc, slot_local))
        if current:
            tz = pytz.timezone("America/Toronto")
            local = pytz.UTC.localize(current).astimezone(tz) if not current.tzinfo else current.astimezone(tz)
            key = local.strftime("%Y-%m-%d")
            days.setdefault(key, [])
            if not any(s[0].replace(tzinfo=None) == current.replace(tzinfo=None) for s in days[key]):
                days[key].append((current.replace(tzinfo=None), local))
                days[key].sort(key=lambda x: x[0])
        blocks = []
        for key in sorted(days):
            first = days[key][0][1]
            label = "%s %s %s" % (
                WEEKDAYS_FR[first.weekday()],
                first.day,
                MONTHS_FR[first.month - 1],
            )
            buttons = []
            for slot_utc, slot_local in days[key]:
                value = slot_utc.strftime("%Y-%m-%d %H:%M:%S")
                selected = current and slot_utc.replace(tzinfo=None) == current.replace(tzinfo=None)
                style = (
                    "background:#06b6d4;color:#041018;font-weight:700"
                    if selected
                    else "background:#1e293b;color:#fff"
                )
                buttons.append(
                    '<button type="submit" name="slot" value="%s" style="border:0;border-radius:8px;padding:10px 14px;cursor:pointer;%s">%s</button>'
                    % (value, style, slot_local.strftime("%Hh%M"))
                )
            blocks.append(
                "<div style='margin:1rem 0;text-align:left'><div style='color:#94a3b8;margin-bottom:8px'>%s</div><div style='display:flex;flex-wrap:wrap;gap:8px'>%s</div></div>"
                % (label, "".join(buttons))
            )
        return "".join(blocks) or "<p>Aucun créneau libre pour les 30 prochains jours.</p>"

    @http.route(
        "/intellix/rdv/martin/manage/<int:event_id>",
        type="http",
        auth="public",
        website=False,
        csrf=False,
    )
    def booking_martin_manage(self, event_id, t=None, cancel=None, **kwargs):
        event = self._load_martin_event(event_id, t)
        if not event:
            return request.make_response(
                "<h1>Lien invalide ou expiré</h1>",
                headers=[("Content-Type", "text/html; charset=utf-8")],
                status=404,
            )
        if cancel:
            html = """<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8"/><title>Annuler le RDV</title>
<style>body{font-family:Arial;max-width:500px;margin:40px auto;padding:20px;background:#0a0a12;color:#fff;text-align:center}
h1{color:#f87171}</style></head><body>
<h1>Annuler ce rendez-vous ?</h1>
<p>RDV avec Martin Houle — <strong>%s</strong></p>
<form method="post" action="/intellix/rdv/martin/cancel/%s">
  <input type="hidden" name="t" value="%s"/>
  <button type="submit" style="background:#dc2626;color:#fff;border:0;padding:12px 18px;border-radius:8px;font-weight:700;cursor:pointer">Oui, supprimer le RDV</button>
</form>
<p style="margin-top:1.5rem"><a href="/intellix/rdv/martin/manage/%s?t=%s" style="color:#67e8f9">Retour — modifier plutôt</a></p>
</body></html>""" % (
                format_booking_when(event.start),
                event.id,
                t,
                event.id,
                t,
            )
            return request.make_response(html, headers=[("Content-Type", "text/html; charset=utf-8")])
        slots_html = self._martin_slots_html(event, t)
        html = """<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8"/><title>Modifier le RDV</title>
<style>body{font-family:Arial;max-width:640px;margin:40px auto;padding:20px;background:#0a0a12;color:#fff}
h1{color:#06b6d4;text-align:center}</style></head><body>
<h1>Modifier le rendez-vous</h1>
<p style="text-align:center">Actuellement : <strong>%s</strong> avec Martin Houle (30 min).</p>
<p style="text-align:center;color:#94a3b8">Cliquez sur un nouveau créneau pour déplacer le RDV.</p>
<form method="post" action="/intellix/rdv/martin/reschedule/%s">
  <input type="hidden" name="t" value="%s"/>
  %s
</form>
<p style="text-align:center;margin-top:2rem">
  <a href="/intellix/rdv/martin/manage/%s?t=%s&amp;cancel=1" style="color:#fca5a5">Supprimer ce rendez-vous</a>
</p>
</body></html>""" % (
            format_booking_when(event.start),
            event.id,
            t,
            slots_html,
            event.id,
            t,
        )
        return request.make_response(html, headers=[("Content-Type", "text/html; charset=utf-8")])

    @http.route(
        "/intellix/rdv/martin/reschedule/<int:event_id>",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def booking_martin_reschedule(self, event_id, t=None, slot=None, **kwargs):
        event = self._load_martin_event(event_id, t)
        if not event or not slot:
            return request.redirect("/intellix/rdv/martin?error=1")
        try:
            start = datetime.strptime(slot, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return request.redirect("/intellix/rdv/martin/manage/%s?t=%s" % (event.id, t))
        stop = start + timedelta(minutes=30)
        Event = request.env["calendar.event"].sudo()
        busy = Event.search_count(
            [
                ("id", "!=", event.id),
                "|",
                ("user_id", "=", event.user_id.id),
                ("partner_ids", "in", [event.user_id.partner_id.id]),
                ("start", "<", stop),
                ("stop", ">", start),
            ]
        )
        if busy:
            return request.redirect("/intellix/rdv/martin/manage/%s?t=%s" % (event.id, t))
        event.write({"start": start, "stop": stop})
        return self._martin_rdv_result_page(
            event, created=False, message="Le créneau a été mis à jour dans l'agenda de Martin."
        )

    @http.route(
        "/intellix/rdv/martin/cancel/<int:event_id>",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def booking_martin_cancel(self, event_id, t=None, **kwargs):
        event = self._load_martin_event(event_id, t)
        if not event:
            return request.redirect("/intellix/rdv/martin?error=1")
        event.unlink()
        html = """<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8"/><title>RDV annulé</title>
<style>body{font-family:Arial;max-width:500px;margin:40px auto;padding:20px;background:#0a0a12;color:#fff;text-align:center}
h1{color:#f87171}</style></head><body>
<h1>Rendez-vous annulé</h1>
<p>Le créneau a été libéré dans l'agenda de Martin Houle.</p>
<p><a href="/intellix/rdv/martin" style="color:#67e8f9">Prendre un nouveau RDV</a></p>
</body></html>"""
        return request.make_response(html, headers=[("Content-Type", "text/html; charset=utf-8")])

    @http.route("/intellix/rdv/dave/book", type="http", auth="public", methods=["POST"], website=False, csrf=False)
    def booking_dave_book(self, **kwargs):
        import datetime
        try:
            slot = kwargs.get('slot', '')
            prenom = kwargs.get('prenom', '').strip()
            nom = kwargs.get('nom', '').strip()
            phone = kwargs.get('phone', '').strip()
            email = kwargs.get('email', '').strip()
            adresse = kwargs.get('adresse', '').strip()
            if not slot or not prenom or not phone:
                return request.redirect('/intellix/rdv/dave?error=1')
            start = datetime.datetime.fromisoformat(slot)
            stop = start + datetime.timedelta(minutes=30)
            user = request.env['res.users'].sudo().search([('login', '=', 'dave.pichette@remax-quebec.com')], limit=1)
            if not user:
                user = request.env['res.users'].sudo().search([('name', 'ilike', 'Dave Pichette')], limit=1)
            partner = None
            if email:
                partner = request.env['res.partner'].sudo().search([('email', '=', email)], limit=1)
            if not partner:
                partner = request.env['res.partner'].sudo().create({
                    'name': f'{prenom} {nom}',
                    'phone': phone,
                    'email': email,
                })
            karine = request.env['res.users'].sudo().search(
                [('login', '=', 'karine@agencedoorway.com')], limit=1
            )
            lead = request.env['crm.lead'].sudo().create({
                'name': f'Évaluation — {prenom} {nom} — {adresse}',
                'partner_name': f'{prenom} {nom}',
                'contact_name': f'{prenom} {nom}'.strip(),
                'phone': phone,
                'email_from': email,
                'street': adresse,
                'description': f'Adresse: {adresse}\nRDV proposé: {start.strftime("%d/%m/%Y %Hh%M")}\nSource: Campagne Pichette IntelliX\nEn attente de confirmation avant envoi à Dave.',
                'user_id': karine.id if karine else 1,
                'partner_id': partner.id if partner else False,
            })
            if user and hasattr(lead, '_dave_hold_slot_at'):
                lead._dave_hold_slot_at(start)
            elif user:
                request.env['calendar.event'].sudo().with_context(
                    no_mail_to_attendees=True,
                    doorway_skip_activity_sync=True,
                ).create({
                    'name': f'[À confirmer] Évaluation {prenom} {nom} — {adresse}',
                    'start': start,
                    'stop': stop,
                    'user_id': user.id,
                    'description': f'Évaluation marchande — à confirmer avant envoi à Dave\nAdresse: {adresse}\nTél: {phone}\nEmail: {email}\nSource: Campagne Pichette IntelliX',
                })
            return request.make_response("""<!DOCTYPE html>
<html lang="fr"><head><meta charset="utf-8"/><title>Évaluation demandée</title>
<style>body{font-family:Arial;max-width:500px;margin:40px auto;padding:20px;background:#0a0a12;color:#fff;text-align:center}
h1{color:#06b6d4}.remax{color:#dc2626;font-weight:bold;margin-bottom:20px}</style></head><body>
<div class="remax">🏠 RE/MAX Québec</div>
<h1>✅ Demande reçue</h1>
<p>Votre créneau avec <strong>Dave Pichette</strong> est réservé.</p>
<p style="margin:16px 0;color:#06b6d4;font-size:1.1rem">""" + format_booking_when(start) + """</p>
<p>Durée : 30 minutes</p>
<p style="color:#aaa;margin-top:12px">L’équipe confirme le rendez-vous avant de l’envoyer à Dave. Il vous recontactera.</p>
</body></html>""", headers=[('Content-Type', 'text/html; charset=utf-8')])
        except Exception as e:
            return request.redirect('/intellix/rdv/dave?error=1')


    @http.route("/intellix/rdv/dave/lead", type="http", auth="public", methods=["POST"], website=False, csrf=False)
    def booking_dave_lead(self, **kwargs):
        """crm.lead Dave depuis un INTERESTED Sophie Pichette. Pas de calendar.event."""
        def _json(payload, status=200):
            return request.make_response(
                json.dumps(payload, ensure_ascii=False),
                headers=[('Content-Type', 'application/json; charset=utf-8')],
                status=status,
            )
        try:
            raw = request.httprequest.get_data(as_text=True) or ""
            data = json.loads(raw) if raw.strip().startswith("{") else dict(kwargs or {})
            token = (
                request.httprequest.headers.get("X-Sophie-Token")
                or data.get("token")
                or ""
            ).strip()
            expected = (
                request.env["ir.config_parameter"].sudo().get_param(
                    "renovation_conciergerie.sophie_pichette_ingest_token"
                )
                or ""
            ).strip()
            if not expected or token != expected:
                return _json({"ok": False, "reason": "token"}, 403)
            prenom = (data.get("prenom") or "").strip()
            nom = (data.get("nom") or "").strip()
            phone = (data.get("phone") or data.get("telephone") or "").strip()
            email = (data.get("email") or data.get("courriel") or "").strip()
            adresse = (data.get("adresse") or "").strip()
            secteur = (data.get("secteur") or "").strip()
            type_prop = (data.get("type_propriete") or "").strip()
            horizon = (data.get("horizon") or "").strip()
            dispo = (data.get("dispo") or data.get("callback_when") or "").strip()
            fiche = data.get("fiche") or {}
            source = (data.get("source") or "Sophie Pichette / Meta Ads Maison Recherchée").strip()
            if not phone:
                return _json({"ok": False, "reason": "phone"}, 400)
            user = request.env["res.users"].sudo().search(
                [("login", "=", "dave.pichette@remax-quebec.com")], limit=1
            )
            if not user:
                user = request.env["res.users"].sudo().search(
                    [("name", "ilike", "Dave Pichette")], limit=1
                )
            digits = "".join(c for c in phone if c.isdigit())[-10:]
            Lead = request.env["crm.lead"].sudo()
            domain = [("user_id", "=", user.id)] if user else []
            lead = False
            if digits:
                lead = Lead.search(
                    domain + ["|", ("phone", "ilike", digits), ("mobile", "ilike", digits)],
                    limit=1,
                )
            if not lead and email:
                lead = Lead.search(domain + [("email_from", "=", email)], limit=1)
            fiche_bits = []
            if isinstance(fiche, dict):
                for key, label in (
                    ("bedrooms", "chambres"),
                    ("lot_size", "terrain"),
                    ("quartier", "quartier"),
                    ("garage", "garage"),
                    ("piscine", "piscine"),
                    ("autres", "autres"),
                ):
                    val = str(fiche.get(key) or "").strip()
                    if val:
                        fiche_bits.append("%s: %s" % (label, val))
            note_lines = [
                "Source: %s" % source,
                "Adresse: %s" % adresse if adresse else "",
                "Secteur: %s" % secteur if secteur else "",
                "Type: %s" % type_prop if type_prop else "",
                "Horizon: %s" % horizon if horizon else "",
                "Dispos: %s" % dispo if dispo else "",
                "Fiche: %s" % " | ".join(fiche_bits) if fiche_bits else "",
                "Call: %s" % (data.get("call_sid") or "") if data.get("call_sid") else "",
            ]
            note = "\n".join(x for x in note_lines if x)
            where = adresse or secteur
            name = "Évaluation — %s %s" % (prenom, nom)
            if where:
                name = "%s — %s" % (name.strip(), where)
            if lead:
                prev = lead.description or ""
                lead.write({"description": (prev + "\n" + note).strip()})
                return _json({"ok": True, "lead_id": lead.id, "duplicate": True})
            karine = request.env["res.users"].sudo().search(
                [("login", "=", "karine@agencedoorway.com")], limit=1
            )
            lead = Lead.create(
                {
                    "name": name.strip(),
                    "partner_name": ("%s %s" % (prenom, nom)).strip() or phone,
                    "contact_name": ("%s %s" % (prenom, nom)).strip(),
                    "phone": phone,
                    "email_from": email,
                    "city": secteur,
                    "street": adresse,
                    "description": note,
                    "user_id": karine.id if karine else (user.id if user else 1),
                }
            )
            booking = {}
            if hasattr(lead, "_dave_auto_hold_slot"):
                booking = lead._dave_auto_hold_slot() or {}
            return _json({
                "ok": True,
                "lead_id": lead.id,
                "duplicate": False,
                "dave_booking": booking,
            })
        except Exception as exc:
            _logger.exception("booking_dave_lead failed")
            return _json({"ok": False, "reason": type(exc).__name__}, 500)
