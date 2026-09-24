const b = $input.first().json.body || $input.first().json;
const now = new Date().toISOString();
const telefono = (b.telefono || b.telephone || b.to || '').toString();
if (!telefono) {
  return [{ json: { ok: false, error: 'telefono requis' } }];
}
const nombre = b.nombre || b.nom_contact || '';
const qualified = !!b.qualified || b.statut === 'qualifie';
const transcript = b.transcript || b.transcripcion || '';
const webhook = $env.GOOGLE_SHEETS_WEBHOOK_URL;
if (!webhook) throw new Error('GOOGLE_SHEETS_WEBHOOK_URL requis');

const tab = b.sheet_name || $env.GOOGLE_SHEETS_TAB || 'Leads_Sofia_Test';
const campaign = b.campaign_id || b.lead_id || $env.CAMPAIGN_ID || '';

let body;
if (tab === 'Leads_Sofia_Test' || tab === 'Leads_Sofia') {
  body = {
    sheet_name: tab,
    row: [
      now,
      campaign,
      b.provider || 'twilio',
      telefono,
      nombre,
      b.statut || (qualified ? 'qualifie' : 'non_qualifie'),
      b.proprietaire === true ? 'SI' : (b.proprietaire === false ? 'NO' : ''),
      b.type_logement || '',
      b.code_postal || '',
      b.combles === true ? 'SI' : (b.combles === false ? 'NO' : ''),
      b.acces_combles === true ? 'SI' : (b.acces_combles === false ? 'NO' : ''),
      b.creneau_rappel || '',
      b.duree_sec || 0,
      b.recording_url || b.url_enregistrement || '',
      b.call_sid || '',
      transcript,
    ],
  };
} else {
  body = {
    date: now,
    nombre,
    telefono,
    qualified,
    transcript,
    recording_url: b.recording_url || b.url_enregistrement || '',
    call_sid: b.call_sid || '',
    provider: b.provider || 'twilio',
    lead_id: campaign,
    statut: b.statut || (qualified ? 'qualifie' : 'non_qualifie'),
    sheet_name: tab,
  };
}

await this.helpers.httpRequest({
  method: 'POST',
  url: webhook,
  body,
  json: true,
});
return [{ json: { ok: true, mode: 'webhook', telefono, qualified, transcript_len: transcript.length } }];
