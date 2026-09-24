const p = $input.first().json.body || $input.first().json;
const action = p.crm_action || p.statut || '';

const odooUrl = ($env.ODOO_URL || 'https://intellixcrm.com').replace(/\/$/, '');
let odoo = {};
try {
  const res = await this.helpers.httpRequest({
    method: 'POST',
    url: odooUrl + '/doorway/api/soumission-qc/non-qualified',
    body: {
      jsonrpc: '2.0',
      method: 'call',
      params: { tenant_api_key: $env.DOORWAY_TENANT_API_KEY, ...p, crm_action: action },
      id: Date.now(),
    },
    json: true,
  });
  odoo = res.result || res;
} catch (e) {
  odoo = { error: (e.message || String(e)).slice(0, 200) };
}

return [{ json: { ok: true, action, odoo } }];
