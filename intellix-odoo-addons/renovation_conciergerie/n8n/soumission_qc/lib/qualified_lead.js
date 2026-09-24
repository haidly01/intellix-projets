const p = $input.first().json.body || $input.first().json;
const phone = p.telephone || p.phone || '';
const prenom = p.prenom || (p.nom || '').split(' ')[0] || 'Bonjour';
const jour = p.jour || 'cette semaine';
const moment = p.preference_rappel === 'avant_midi' ? 'avant-midi' : 'après-midi';

const msg =
  `Bonjour ${prenom} ! 😊\nMerci pour votre temps.\n` +
  `Notre directeur des travaux vous contactera ${jour} en ${moment}.\n` +
  `Des questions ? Répondez à ce message !\n— Soumission Entrepreneurs`;

if (!phone) return [{ json: { ok: false, error: 'no_phone' } }];

const sid = $env.TWILIO_ACCOUNT_SID;
const auth = Buffer.from(`${sid}:${$env.TWILIO_AUTH_TOKEN}`).toString('base64');
const from = $env.TWILIO_FROM_SOUMISSION || '+15817058118';

await this.helpers.httpRequest({
  method: 'POST',
  url: `https://api.twilio.com/2010-04-01/Accounts/${sid}/Messages.json`,
  headers: { Authorization: 'Basic ' + auth, 'Content-Type': 'application/x-www-form-urlencoded' },
  body: `To=${encodeURIComponent(phone)}&From=${encodeURIComponent(from)}&Body=${encodeURIComponent(msg)}`,
});

const odooUrl = ($env.ODOO_URL || 'https://intellixcrm.com').replace(/\/$/, '');
let odoo = {};
try {
  const res = await this.helpers.httpRequest({
    method: 'POST',
    url: odooUrl + '/doorway/api/soumission-qc/qualified',
    body: {
      jsonrpc: '2.0',
      method: 'call',
      params: { tenant_api_key: $env.DOORWAY_TENANT_API_KEY, ...p },
      id: Date.now(),
    },
    json: true,
  });
  odoo = res.result || res;
} catch (e) {
  odoo = { error: (e.message || String(e)).slice(0, 200) };
}

return [{ json: { ok: true, sms_sent: true, odoo } }];
