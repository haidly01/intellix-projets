const p = $input.first().json.body || $input.first().json;
const phone = p.telephone || p.phone || '';
const prenom = p.prenom || (p.nom || '').split(' ')[0] || 'Bonjour';
const msg = drivenSmsBody(prenom, 'j0');

if (!phone) return [{ json: { ok: false, error: 'no_phone' } }];

const sid = $env.TWILIO_ACCOUNT_SID;
const auth = Buffer.from(`${sid}:${$env.TWILIO_AUTH_TOKEN}`).toString('base64');
const from = $env.TWILIO_FROM_SOUMISSION || '+15817058118';

let sms_sent = false;
try {
  await this.helpers.httpRequest({
    method: 'POST',
    url: `https://api.twilio.com/2010-04-01/Accounts/${sid}/Messages.json`,
    headers: { Authorization: 'Basic ' + auth, 'Content-Type': 'application/x-www-form-urlencoded' },
    body: `To=${encodeURIComponent(phone)}&From=${encodeURIComponent(from)}&Body=${encodeURIComponent(msg)}`,
  });
  sms_sent = true;
} catch (_e) { /* fail-open SMS */ }

const odooUrl = ($env.ODOO_URL || 'https://intellixcrm.com').replace(/\/$/, '');
let odoo = {};
try {
  const res = await this.helpers.httpRequest({
    method: 'POST',
    url: odooUrl + '/doorway/api/driven-b2b/qualified',
    body: {
      jsonrpc: '2.0',
      method: 'call',
      params: { tenant_api_key: $env.DOORWAY_TENANT_API_KEY, ...p, sms_sent },
      id: Date.now(),
    },
    json: true,
  });
  odoo = res.result || res;
} catch (e) {
  odoo = { error: (e.message || String(e)).slice(0, 200) };
}

return [{ json: { ok: true, sms_sent, odoo } }];
