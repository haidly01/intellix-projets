const b = $input.first().json.body || $input.first().json;
const ev = {
  event_type: b.event_type || 'recording_ready',
  call_sid: b.call_sid || b.uniqueid || '',
  from: b.from || b.phone_number || '',
  to: b.to || '',
  recording_url: b.recording_url || b.recording_path || '',
  recording_b64: b.recording_b64 || '',
  amd_result: (b.amd_result || 'unknown').toLowerCase(),
  duration_sec: parseInt(b.duration_sec || b.duration || 0, 10) || 0,
  provider: 'vicidial',
  partner_id: b.partner_id || b.lead_id || '',
  prenom: b.prenom || b.nombre || b.first_name || '',
  ville: b.ville || b.city || '',
  campaign: b.campaign || $env.VICIDIAL_CAMPAIGN || 'DW_FRB2C',
  agent_id: b.agent_id || $env.AGENT_ID || 'marenofacile',
  raw: b,
};

const base = ($env.N8N_WEBHOOK_URL || '').replace(/\/$/, '');
const engine = await this.helpers.httpRequest({
  method: 'POST',
  url: base + '/renofacile-fr/conversation',
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
      url: odooUrl + '/doorway/api/renofacile-fr/call-ended',
      body: {
        jsonrpc: '2.0',
        method: 'call',
        params: {
          tenant_api_key: $env.DOORWAY_TENANT_API_KEY,
          call_sid: ev.call_sid,
          duration_sec: ev.duration_sec || cp.duration_sec || 0,
          amd_result: ev.amd_result,
          partner_id: cp.partner_id || ev.partner_id,
          lead_id: cp.lead_id || ev.partner_id,
          prenom: cp.prenom || ev.prenom,
          ville: cp.ville || ev.ville,
          telephone: cp.telephone || ev.to || ev.from,
          statut: cp.statut || cp.etat_final,
          etat_final: cp.etat_final || cp.statut,
          statut_propriete: cp.statut_propriete,
          type_logement: cp.type_logement,
          chauffage: cp.chauffage,
          travaux_existants: cp.travaux_existants,
          consentement_recontact: cp.consentement_recontact,
          qualification_complete: cp.qualification_complete,
          transcript: cp.transcript || '',
          recording_url: cp.recording_url || ev.recording_url,
          campaign: cp.campaign || ev.campaign || 'DW_FRB2C',
          agent_id: cp.agent_id || ev.agent_id || 'marenofacile',
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
