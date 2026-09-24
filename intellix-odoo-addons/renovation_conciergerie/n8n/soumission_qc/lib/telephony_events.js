const b = $input.first().json.body || $input.first().json;
const ev = {
  event_type: b.event_type || 'recording_ready',
  call_sid: b.call_sid || b.CallSid || b.uniqueid || '',
  from: b.from || b.From || '',
  to: b.to || b.To || '',
  recording_url: b.recording_url || b.RecordingUrl || b.recording_path || '',
  amd_result: (b.amd_result || b.AnsweredBy || 'unknown').toLowerCase(),
  duration_sec: parseInt(b.duration_sec || b.CallDuration || b.duration || 0, 10) || 0,
  provider: b.provider || 'vicidial',
  partner_id: b.partner_id || b.lead_id || '',
  prenom: b.prenom || b.nombre || b.first_name || '',
  raw: b,
};

const base = ($env.N8N_WEBHOOK_URL || '').replace(/\/$/, '');
const engine = await this.helpers.httpRequest({
  method: 'POST',
  url: base + '/soumission-qc/conversation',
  body: ev,
  json: true,
});
const out = engine && engine.action ? engine : (Array.isArray(engine) ? engine[0] : { normalized: ev, engine });

if (ev.event_type === 'call_ended' || out.action === 'hangup') {
  const odooUrl = ($env.ODOO_URL || 'https://intellixcrm.com').replace(/\/$/, '');
  const cp = out.crm_payload || {};
  try {
    await this.helpers.httpRequest({
      method: 'POST',
      url: odooUrl + '/doorway/api/soumission-qc/call-ended',
      body: {
        jsonrpc: '2.0',
        method: 'call',
        params: { tenant_api_key: $env.DOORWAY_TENANT_API_KEY, ...cp },
        id: Date.now(),
      },
      json: true,
      timeout: 15000,
    });
  } catch (e) {
    out.odoo_error = (e.message || String(e)).slice(0, 200);
  }
  if (cp.crm_action === 'tag_lead_qualifie') {
    try {
      await this.helpers.httpRequest({
        method: 'POST',
        url: base + '/soumission-qc/qualified',
        body: cp,
        json: true,
      });
    } catch (_e) { /* qualified wf */ }
  } else if (cp.crm_action) {
    try {
      await this.helpers.httpRequest({
        method: 'POST',
        url: base + '/soumission-qc/non-qualified',
        body: cp,
        json: true,
      });
    } catch (_e) { /* non-qualified wf */ }
  }
}
return [{ json: out }];
