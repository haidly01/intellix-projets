const today = new Date().toISOString().slice(0, 10);
const odooUrl = ($env.ODOO_URL || 'https://intellixcrm.com').replace(/\/$/, '');

let stats = { date: today, calls: 0, qualified: 0, pas_interesse: 0, locataire: 0, pas_projet: 0 };
try {
  const res = await this.helpers.httpRequest({
    method: 'POST',
    url: odooUrl + '/doorway/api/soumission-qc/daily-stats',
    body: {
      jsonrpc: '2.0',
      method: 'call',
      params: { tenant_api_key: $env.DOORWAY_TENANT_API_KEY, date: today },
      id: Date.now(),
    },
    json: true,
  });
  stats = { ...stats, ...(res.result || res) };
} catch (_e) { /* stats optional */ }

const pct = stats.calls ? Math.round((stats.qualified / stats.calls) * 100) : 0;
const body =
  `Rapport Sofia — ${today}\n` +
  `📞 Appels : ${stats.calls}\n` +
  `✅ Qualifiés : ${stats.qualified} (${pct}%)\n` +
  `❌ Pas intéressés : ${stats.pas_interesse}\n` +
  `🏠 Locataires : ${stats.locataire}\n` +
  `📋 Sans projet : ${stats.pas_projet}`;

const email = $env.MANAGER_EMAIL || $env.DIRECTOR_EMAIL;
if (email) {
  try {
    await this.helpers.httpRequest({
      method: 'POST',
      url: odooUrl + '/doorway/api/soumission-qc/send-report',
      body: {
        jsonrpc: '2.0',
        method: 'call',
        params: { tenant_api_key: $env.DOORWAY_TENANT_API_KEY, email, subject: `Rapport Sofia SE — ${today}`, body },
        id: Date.now(),
      },
      json: true,
    });
  } catch (_e) { /* email optional */ }
}

return [{ json: { ok: true, stats, report: body } }];
