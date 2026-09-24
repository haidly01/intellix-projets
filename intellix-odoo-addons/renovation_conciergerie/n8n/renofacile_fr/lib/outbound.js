const item = $input.first().json;
const body = item.body || item;

function normFr(p) {
  if (!p) return '';
  const s = String(p).trim();
  const d = s.replace(/\D/g, '');
  if (d.startsWith('33') && d.length > 9) return '+' + d;
  if (d.length === 9) return '+33' + d;
  if (d.length === 10 && d.startsWith('0')) return '+33' + d.slice(1);
  if (s.startsWith('+')) return '+' + d;
  return d ? '+' + d : '';
}

const phone = normFr(body.telephone || body.phone || body.phone_number);
if (!phone) throw new Error('telephone requis');

const vicUrl = ($env.VICIDIAL_API_URL || '').replace(/\/$/, '');
const user = $env.VICIDIAL_USER || '';
const pass = $env.VICIDIAL_PASS || '';
const campaign = $env.VICIDIAL_CAMPAIGN || 'DW_FRB2C';
const listId = $env.VICIDIAL_LIST || '1004';

const qs = new URLSearchParams({
  source: 'doorway_n8n',
  user,
  pass,
  function: 'external_dial',
  value: phone,
  phone_code: '1',
  search: 'YES',
  preview: 'NO',
  focus: 'NO',
  campaign_id: campaign,
  dial_prefix: '',
  group_alias: '',
  alt_dial: 'SEARCH',
  vendor_lead_code: body.lead_id || body.partner_id || '',
  lead_id: body.lead_id || '',
  phone_number: phone,
  list_id: listId,
});

const res = await this.helpers.httpRequest({
  method: 'GET',
  url: vicUrl + '?' + qs.toString(),
  timeout: 30000,
});
const text = typeof res === 'string' ? res : JSON.stringify(res);
const ok = /SUCCESS|started/i.test(text);

return [{
  json: {
    ok,
    telephone: phone,
    campaign,
    provider: 'vicidial',
    agent_id: $env.AGENT_ID || 'marenofacile',
    response: text.slice(0, 300),
  },
}];
