# -*- coding: utf-8 -*-
import json
import logging
from datetime import datetime, timedelta

import pytz

from odoo import fields, http
from odoo.http import request

_logger = logging.getLogger(__name__)

JASON_LOGIN = 'jason@jasonthomasassurance.ca'
JASON_TZ = 'America/Moncton'
BOOKING_DURATION_MIN = 30


class JasonThomasBookingController(http.Controller):

    def _jason_user(self):
        return request.env['res.users'].sudo().search([('login', '=', JASON_LOGIN)], limit=1)

    def _jason_slots(self):
        user = self._jason_user()
        if not user:
            return [], user
        tz = pytz.timezone(JASON_TZ)
        now = datetime.now(tz)
        slots = []
        day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        for _ in range(21):
            day += timedelta(days=1)
            if day.weekday() >= 5:
                continue
            for hour in range(9, 17):
                for minute in (0, 30):
                    slot_local = day.replace(hour=hour, minute=minute)
                    if slot_local <= now:
                        continue
                    slot_utc = slot_local.astimezone(pytz.utc).replace(tzinfo=None)
                    stop_utc = slot_utc + timedelta(minutes=BOOKING_DURATION_MIN)
                    existing = request.env['calendar.event'].sudo().search([
                        ('user_id', '=', user.id),
                        ('start', '<', stop_utc),
                        ('stop', '>', slot_utc),
                    ], limit=1)
                    if not existing:
                        slots.append((slot_utc, slot_local))
        return slots[:60], user

    def _slots_ui(self, slots_tuples):
        months_fr = ['jan', 'fév', 'mar', 'avr', 'mai', 'jun', 'jul', 'aoû', 'sep', 'oct', 'nov', 'déc']
        weekdays_fr = ['Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam', 'Dim']
        by_day = {}
        for slot_utc, slot_local in slots_tuples:
            day_key = slot_local.strftime('%Y-%m-%d')
            if day_key not in by_day:
                wd = weekdays_fr[slot_local.weekday()]
                by_day[day_key] = {
                    'date': day_key,
                    'label': f'{wd} {slot_local.day} {months_fr[slot_local.month - 1]}',
                    'times': [],
                    'time_values': {},
                }
            display = slot_local.strftime('%H:%M')
            by_day[day_key]['times'].append(display)
            by_day[day_key]['time_values'][display] = slot_utc.strftime('%Y-%m-%d %H:%M:%S')
        result = []
        for day in by_day.values():
            day['count'] = len(day['times'])
            result.append(day)
        return result

    def _find_or_create_jt_client(self, prenom, nom, phone, email):
        Client = request.env['jt.client'].sudo()
        email = (email or '').strip()
        phone = (phone or '').strip()
        if email:
            client = Client.search([('email', '=ilike', email)], limit=1)
            if client:
                return client
        if phone:
            for field in ('cell_phone', 'home_phone', 'office_phone'):
                client = Client.search([(field, 'ilike', phone[-10:])], limit=1)
                if client:
                    return client
        vals = {
            'source': 'ago',
            'first_name': prenom,
            'last_name': nom,
            'cell_phone': phone or False,
            'email': email or False,
        }
        return Client.create(vals)

    def _render_page(self, user, slots):
        name = user.name or 'Jason Thomas'
        slots_json = json.dumps(slots, ensure_ascii=False)
        html = f"""<!DOCTYPE html>
<html lang="fr"><head><meta charset="UTF-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Rendez-vous — Jason Thomas Assurance</title>
<style>
:root{{--navy:#0d1e40;--gold:#c9952a;--bg:#f4f5f8;--border:#dbe1ea}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:Georgia,"Times New Roman",serif;background:var(--bg);color:#1a1a2e}}
.wrap{{max-width:920px;margin:0 auto;padding:2rem 1.25rem 3rem;display:grid;grid-template-columns:260px 1fr;gap:24px}}
aside{{background:var(--navy);color:#fff;border-radius:14px;padding:24px 20px}}
aside h1{{font-size:1.25rem;color:var(--gold);margin-bottom:.35rem}}
aside p{{font-size:.85rem;opacity:.8;line-height:1.5}}
.badge{{display:inline-block;margin-top:12px;padding:4px 10px;border-radius:999px;background:rgba(201,149,42,.15);color:var(--gold);font-size:11px}}
main{{background:#fff;border:1px solid var(--border);border-radius:14px;padding:22px}}
h2{{font-size:1.35rem;color:var(--navy);margin-bottom:4px}}
.sub{{color:#64748b;font-size:.9rem;margin-bottom:18px}}
.days{{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:16px}}
.day-btn,.time-btn{{border:1.5px solid var(--border);background:#fff;border-radius:10px;padding:12px;cursor:pointer;text-align:left;font:inherit}}
.day-btn.selected,.time-btn.selected{{border-color:var(--navy);background:#eef2ff}}
.times{{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:16px}}
form{{display:none;border-top:1px solid var(--border);padding-top:16px}}
form.visible{{display:block}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:10px}}
label{{font-size:11px;font-weight:700;color:#64748b;text-transform:uppercase;display:block;margin-bottom:4px}}
input{{width:100%;padding:10px;border:1.5px solid var(--border);border-radius:8px;font:inherit}}
button[type=submit]{{margin-top:14px;width:100%;padding:12px;background:var(--navy);color:var(--gold);border:none;border-radius:10px;font-weight:700;cursor:pointer}}
@media(max-width:720px){{.wrap{{grid-template-columns:1fr}}.days,.grid{{grid-template-columns:1fr}}.times{{grid-template-columns:repeat(2,1fr)}}}}
</style></head><body>
<div class="wrap">
<aside>
  <h1>Jason Thomas</h1>
  <p>Consultation assurance vie — {BOOKING_DURATION_MIN} minutes</p>
  <p style="margin-top:10px">Lun–Ven, 9h–17h<br/>Heure du Nouveau-Brunswick</p>
  <span class="badge">Téléphone ou visio</span>
</aside>
<main>
  <h2>Réservez votre rendez-vous</h2>
  <p class="sub">Choisissez le moment qui vous convient. Vous recevrez ensuite votre confirmation par courriel.</p>
  <div class="days" id="daysGrid"></div>
  <div class="times" id="timesGrid"></div>
  <form id="bookForm" method="post" action="/intellix/rdv/jason/book">
    <input type="hidden" name="slot" id="slotInput"/>
    <div class="grid">
      <div><label>Prénom *</label><input name="prenom" required/></div>
      <div><label>Nom *</label><input name="nom" required/></div>
      <div><label>Téléphone *</label><input name="phone" required/></div>
      <div><label>Courriel</label><input name="email" type="email"/></div>
    </div>
    <button type="submit">Confirmer le rendez-vous</button>
  </form>
</main></div>
<script>
const SLOTS = {slots_json};
let selectedDay = null;
const daysGrid = document.getElementById('daysGrid');
const timesGrid = document.getElementById('timesGrid');
const form = document.getElementById('bookForm');
if (!SLOTS.length) {{
  daysGrid.innerHTML = '<p>Aucune disponibilité pour le moment — contactez-nous par téléphone.</p>';
}} else {{
  SLOTS.forEach(day => {{
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'day-btn';
    btn.innerHTML = `<strong>${{day.label}}</strong><br/><span style="color:#64748b;font-size:12px">${{day.count}} ${{day.count > 1 ? 'disponibilités' : 'disponibilité'}}</span>`;
    btn.onclick = () => selectDay(day, btn);
    daysGrid.appendChild(btn);
  }});
}}
function selectDay(day, btn) {{
  document.querySelectorAll('.day-btn').forEach(b => b.classList.remove('selected'));
  btn.classList.add('selected');
  selectedDay = day;
  timesGrid.innerHTML = '';
  form.classList.remove('visible');
  day.times.forEach(t => {{
    const tb = document.createElement('button');
    tb.type = 'button';
    tb.className = 'time-btn';
    tb.textContent = t;
    tb.onclick = () => selectTime(t, tb);
    timesGrid.appendChild(tb);
  }});
}}
function selectTime(t, btn) {{
  document.querySelectorAll('.time-btn').forEach(b => b.classList.remove('selected'));
  btn.classList.add('selected');
  document.getElementById('slotInput').value = selectedDay.time_values[t];
  form.classList.add('visible');
  form.scrollIntoView({{behavior:'smooth'}});
}}
</script></body></html>"""
        return html

    @http.route('/intellix/rdv/jason', type='http', auth='public', website=False, csrf=False)
    def booking_page(self, **kwargs):
        user = self._jason_user()
        if not user:
            return request.make_response(
                '<h2>Calendrier indisponible</h2>',
                headers=[('Content-Type', 'text/html; charset=utf-8')],
                status=503,
            )
        raw, _user = self._jason_slots()
        html = self._render_page(user, self._slots_ui(raw))
        return request.make_response(html, headers=[('Content-Type', 'text/html; charset=utf-8')])

    @http.route('/intellix/rdv/jason/book', type='http', auth='public', methods=['POST'], csrf=False)
    def booking_submit(self, slot=None, prenom=None, nom=None, phone=None, email=None, **kwargs):
        user = self._jason_user()
        prenom = (prenom or '').strip()
        nom = (nom or '').strip()
        phone = (phone or '').strip()
        email = (email or '').strip()
        if not user or not slot or not prenom or not nom or not phone:
            return request.redirect('/intellix/rdv/jason?error=1')
        try:
            start = datetime.strptime(slot, '%Y-%m-%d %H:%M:%S')
            stop = start + timedelta(minutes=BOOKING_DURATION_MIN)
            client = self._find_or_create_jt_client(prenom, nom, phone, email)
            partner = client.partner_id
            if not partner:
                partner = request.env['res.partner'].sudo().create({
                    'name': client.full_name or f'{prenom} {nom}',
                    'email': email or client.email or False,
                    'phone': phone or client.cell_phone or False,
                })
                client.write({'partner_id': partner.id})

            event = request.env['calendar.event'].sudo().create({
                'name': f'Consultation — {client.full_name or f"{prenom} {nom}"}',
                'start': start,
                'stop': stop,
                'user_id': user.id,
                'partner_ids': [(4, user.partner_id.id), (4, partner.id)],
                'jt_client_id': client.id,
                'description': (
                    f'Réservation publique /intellix/rdv/jason\n'
                    f'Client JT #{client.id}\nTél: {phone}\nCourriel: {email or "—"}'
                ),
            })
            request.env['jt.tache'].sudo().create({
                'name': f'RDV — {client.full_name}',
                'client_id': client.id,
                'due_date': start.date(),
                'state': 'confirm',
                'source': 'manual',
                'description': f'Rendez-vous réservé en ligne (événement calendrier #{event.id}).',
            })
            tz = pytz.timezone(JASON_TZ)
            start_local = pytz.utc.localize(start).astimezone(tz)
            label = start_local.strftime('%A %d %B %Y à %Hh%M')
            html = f"""<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8"/>
<title>RDV confirmé</title></head>
<body style="font-family:Georgia,serif;max-width:520px;margin:2rem auto;padding:1rem">
<h1 style="color:#0d1e40">Rendez-vous confirmé</h1>
<p>Bonjour <strong>{prenom}</strong>, votre consultation avec Jason Thomas est planifiée.</p>
<p><strong>{label}</strong> (heure du Nouveau-Brunswick)</p>
<p style="color:#64748b">Durée : {BOOKING_DURATION_MIN} minutes. Un courriel de confirmation vous sera envoyé si vous avez indiqué votre adresse.</p>
</body></html>"""
            return request.make_response(html, headers=[('Content-Type', 'text/html; charset=utf-8')])
        except Exception:
            _logger.exception('Jason booking failed')
            return request.redirect('/intellix/rdv/jason?error=1')
