/**
 * n8n Code node — notifier Odoo fin d'appel Sofia ES.
 * Appeler depuis workflow 2 (Telnyx events) sur call.hangup.
 */
const axios = require('axios');

async function notifyOdooCallEnded(payload) {
  const url = ($env.ODOO_URL || 'http://187.124.50.69:8069').replace(/\/$/, '');
  const rpcUrl = `${url}/doorway/api/sofia-es/call-ended`;
  const body = {
    jsonrpc: '2.0',
    method: 'call',
    params: {
      tenant_api_key: $env.DOORWAY_TENANT_API_KEY,
      call_sid: payload.call_sid,
      duration_seconds: payload.duration_seconds || payload.duration_sec || 0,
      amd_result: payload.amd_result || 'unknown',
      partner_id: payload.partner_id,
      nombre: payload.nombre || payload.nom_complet,
      telephone: payload.telephone || payload.telefono,
      email: payload.email,
      lead_ganador: payload.lead_ganador,
      propietario: payload.propietario,
      tipo_vivienda: payload.tipo_vivienda,
      codigo_postal: payload.codigo_postal,
      etat_final: payload.etat_final || payload.estado_final,
      transcript: payload.transcript,
      recording_url: payload.recording_url || payload.url_enregistrement,
      campaign: 'sofia_es_avatrade',
      timestamp: payload.timestamp_appel || new Date().toISOString(),
    },
    id: Date.now(),
  };
  const res = await axios.post(rpcUrl, body, {
    headers: { 'Content-Type': 'application/json' },
    timeout: 15000,
  });
  return res.data?.result || res.data;
}

// Usage dans n8n :
// const result = await notifyOdooCallEnded($json.sheet_payload || $json);
// return [{ json: { odoo: result } }];

module.exports = { notifyOdooCallEnded };
