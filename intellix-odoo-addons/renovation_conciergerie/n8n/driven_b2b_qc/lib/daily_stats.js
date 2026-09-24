const today = new Date().toISOString().slice(0, 10);
const odooUrl = ($env.ODOO_URL || 'https://intellixcrm.com').replace(/\/$/, '');

let stats = { date: today, calls: 0, hot_leads: 0, disqualified: 0 };
try {
  const res = await this.helpers.httpRequest({
    method: 'POST',
    url: odooUrl + '/doorway/api/driven-b2b/daily-stats',
    body: {
      jsonrpc: '2.0',
      method: 'call',
      params: { tenant_api_key: $env.DOORWAY_TENANT_API_KEY, date: today },
      id: Date.now(),
    },
    json: true,
  });
  stats = { ...stats, ...(res.result || res) };
} catch (_e) { /* optional */ }

const pct = stats.calls ? Math.round((stats.hot_leads / stats.calls) * 100) : 0;
const body =
  `Rapport Alex Driven B2B — ${today}\n` +
  `📞 Appels : ${stats.calls}\n` +
  `🔥 Leads chauds : ${stats.hot_leads} (${pct}%)\n` +
  `❌ Disqualifiés : ${stats.disqualified}`;

return [{ json: { ok: true, stats, report: body } }];
