const b = $input.first().json.body || $input.first().json;
const ev = {
  event_type: b.event_type || 'recording_ready',
  call_sid: b.call_sid || b.uniqueid || '',
  from: b.from || b.phone_number || '',
  to: b.to || '',
  recording_url: b.recording_url || b.recording_path || '',
  amd_result: (b.amd_result || 'unknown').toLowerCase(),
  duration_sec: parseInt(b.duration_sec || b.duration || 0, 10) || 0,
  provider: 'vicidial',
  partner_id: b.partner_id || b.lead_id || '',
  nombre: b.nombre || b.first_name || '',
  raw: b,
};
const base = ($env.N8N_WEBHOOK_URL || '').replace(/\/$/, '');
const engine = await this.helpers.httpRequest({
  method: 'POST',
  url: base + '/sofia-es/conversation',
  body: ev,
  json: true,
});
const out = engine && engine.action ? engine : (Array.isArray(engine) ? engine[0] : { normalized: ev, engine });
if (ev.event_type === 'call_ended' || out.action === 'hangup') {
  const odooUrl = ($env.ODOO_URL || 'https://intellixcrm.com').replace(/\/$/, '');
  const sp = out.sheet_payload || {};
  const amd = (ev.amd_result || sp.amd_result || 'unknown').toLowerCase();
  const dur = ev.duration_sec || sp.duree_sec || 0;
  const cost = amd === 'machine' || amd === 'not_sure' ? 0 : Math.round((dur * 0.22 / 60) * 10000) / 10000;
  try {
    await this.helpers.httpRequest({
      method: 'POST',
      url: odooUrl + '/doorway/api/sofia-es/call-ended',
      body: {
        jsonrpc: '2.0',
        method: 'call',
        params: {
          tenant_api_key: $env.DOORWAY_TENANT_API_KEY,
          call_sid: ev.call_sid,
          duration_seconds: dur,
          amd_result: amd,
          partner_id: sp.partner_id || ev.partner_id,
          nombre: sp.nombre || ev.nombre,
          telephone: sp.telefono || ev.to || ev.from,
          lead_ganador: sp.qualified || sp.lead_ganador,
          propietario: sp.proprietaire,
          tipo_vivienda: sp.type_logement,
          codigo_postal: sp.code_postal,
          etat_final: sp.statut || sp.etat_final,
          transcript: sp.transcript || '',
          recording_url: sp.recording_url || ev.recording_url,
          cost_euros: cost,
          campaign: 'sofia_es_avatrade',
        },
        id: Date.now(),
      },
      json: true,
      timeout: 15000,
    });
  } catch (e) {
    out.odoo_error = (e.message || String(e)).slice(0, 200);
  }
}
return [{ json: out }];
