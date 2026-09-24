const item = $input.first().json;
const body = item.body || item;

function normCa(p) {
  if (!p) return '';
  const d = String(p).replace(/\D/g, '');
  if (d.length === 10) return '+1' + d;
  if (d.length === 11 && d.startsWith('1')) return '+' + d;
  if (String(p).startsWith('+')) return '+' + d;
  return d ? '+1' + d : '';
}

const phone = normCa(body.telephone || body.phone || body.phone_number);
if (!phone) throw new Error('telephone requis');

const provider = ($env.TELEPHONY_PROVIDER || 'vicidial').toLowerCase();
const odooUrl = ($env.ODOO_URL || 'https://intellixcrm.com').replace(/\/$/, '');

if (provider === 'twilio') {
  const sid = $env.TWILIO_ACCOUNT_SID;
  const auth = Buffer.from(`${sid}:${$env.TWILIO_AUTH_TOKEN}`).toString('base64');
  const from = $env.TWILIO_FROM_SOUMISSION || '+15817058118';
  const base = ($env.N8N_WEBHOOK_URL || '').replace(/\/$/, '');
  await this.helpers.httpRequest({
    method: 'POST',
    url: `https://api.twilio.com/2010-04-01/Accounts/${sid}/Calls.json`,
    headers: { Authorization: 'Basic ' + auth, 'Content-Type': 'application/x-www-form-urlencoded' },
    body: `To=${encodeURIComponent(phone)}&From=${encodeURIComponent(from)}&Url=${encodeURIComponent(base + '/soumission-qc/twilio/voice')}&StatusCallback=${encodeURIComponent(base + '/soumission-qc/event')}`,
  });
  return [{ json: { ok: true, telephone: phone, provider: 'twilio', campaign: $env.VICIDIAL_CAMPAIGN || 'DW_QCB2C' } }];
}

const res = await this.helpers.httpRequest({
  method: 'POST',
  url: odooUrl + '/doorway/api/soumission-qc/dial',
  body: {
    jsonrpc: '2.0',
    method: 'call',
    params: {
      tenant_api_key: $env.DOORWAY_TENANT_API_KEY,
      telephone: phone,
      prenom: body.prenom || body.nombre || body.name || '',
      partner_id: body.partner_id || body.lead_id || '',
    },
    id: Date.now(),
  },
  json: true,
  timeout: 30000,
});
const result = res.result || res;
return [{
  json: {
    telephone: phone,
    campaign: $env.VICIDIAL_CAMPAIGN || 'DW_QCB2C',
    provider: 'vicidial',
    ok: !!(result.ok || result.success),
    ...result,
  },
}];
