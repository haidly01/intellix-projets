const item = $input.first().json;
const body = item.body || item;
function norm(p) {
  if (!p) return '';
  const s = String(p).trim();
  const d = s.replace(/\D/g, '');
  if (d.startsWith('34') && d.length > 9) return '+' + d;
  if (d.length === 9) return '+34' + d;
  if (s.startsWith('+')) return '+' + d;
  return '+' + d;
}
const phone = norm(body.telephone || body.phone || body.phone_number);
if (!phone) throw new Error('telephone requis');
const odooUrl = ($env.ODOO_URL || 'https://intellixcrm.com').replace(/\/$/, '');
const res = await this.helpers.httpRequest({
  method: 'POST',
  url: odooUrl + '/doorway/api/sofia-es/dial',
  body: {
    jsonrpc: '2.0',
    method: 'call',
    params: {
      tenant_api_key: $env.DOORWAY_TENANT_API_KEY,
      telephone: phone,
      nombre: body.nombre || body.name || '',
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
    campaign: $env.VICIDIAL_CAMPAIGN || 'DW_ESREN',
    provider: 'vicidial',
    trunk: 'TrustSIP-Espagne',
    ok: !!(result.ok || result.success),
    ...result,
  },
}];
