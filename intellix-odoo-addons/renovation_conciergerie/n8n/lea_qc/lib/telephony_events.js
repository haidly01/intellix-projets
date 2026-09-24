const b = $input.first().json.body || $input.first().json;
const ev = {
  event_type: b.event_type || 'recording_ready',
  call_sid: b.call_sid || b.CallSid || b.uniqueid || '',
  from: b.from || b.From || '',
  to: b.to || b.To || '',
  recording_url: b.recording_url || b.RecordingUrl || b.recording_path || '',
  recording_path: b.recording_path || '',
  // IMPORTANT : l'AGI fait déjà le STT en local et fournit transcript/confidence
  // (+ recording_b64). Il FAUT les transmettre au moteur, sinon il refait un STT
  // sur recording_url (souvent VIDE -> 403 Cloudflare) et compte un faux
  // "silence" qui raccrochait l'appel dès la 2e réponse (« propriétaire »).
  transcript: b.transcript || '',
  stt_confidence: b.stt_confidence || 0,
  recording_b64: b.recording_b64 || '',
  amd_result: (b.amd_result || b.AnsweredBy || 'unknown').toLowerCase(),
  duration_sec: parseInt(b.duration_sec || b.CallDuration || b.duration || 0, 10) || 0,
  provider: b.provider || 'vicidial',
  partner_id: b.partner_id || b.lead_id || '',
  prenom: b.prenom || b.nombre || b.first_name || '',
  raw: b,
};

// Appels n8n -> n8n (moteur conversation / qualified) : rester en LOCAL (127.0.0.1)
// au lieu de sortir par https://n8n.intellixcrm.com (Cloudflare + nginx) à CHAQUE
// tour. La boucle de conversation est sur le chemin CRITIQUE de latence ; un aller-
// retour Cloudflare ajoutait ~0,3-0,6 s par tour de parole. Surchargeable via
// LEA_INTERNAL_WEBHOOK_URL si jamais n8n n'écoute pas en 127.0.0.1:5678.
const base = ($env.LEA_INTERNAL_WEBHOOK_URL || 'http://127.0.0.1:5678/webhook').replace(/\/$/, '');
const engine = await this.helpers.httpRequest({
  method: 'POST',
  url: base + '/lea-qc/conversation',
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
      url: odooUrl + '/doorway/api/lea-qc/call-ended',
      body: {
        jsonrpc: '2.0',
        method: 'call',
        params: { tenant_api_key: $env.DOORWAY_TENANT_API_KEY, ...cp },
        id: Date.now(),
      },
      json: true,
      timeout: 90000,
    });
  } catch (e) {
    out.odoo_error = (e.message || String(e)).slice(0, 200);
  }
  if (cp.crm_action === 'tag_lead_qualifie') {
    try {
      await this.helpers.httpRequest({
        method: 'POST',
        url: base + '/lea-qc/qualified',
        body: cp,
        json: true,
      });
    } catch (_e) { /* qualified wf */ }
  } else if (cp.crm_action) {
    try {
      await this.helpers.httpRequest({
        method: 'POST',
        url: base + '/lea-qc/non-qualified',
        body: cp,
        json: true,
      });
    } catch (_e) { /* non-qualified wf */ }
  }
}
return [{ json: out }];
