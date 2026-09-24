const b = $input.first().json.body || $input.first().json;
const now = new Date().toLocaleString('es-ES', { timeZone: 'Europe/Madrid' });
const telefono = (b.telefono || b.telephone || b.to || '').toString();
if (!telefono) return [{ json: { ok: false, error: 'telefono requis' } }];
const webhook = $env.GOOGLE_SHEETS_WEBHOOK_URL;
if (!webhook) throw new Error('GOOGLE_SHEETS_WEBHOOK_URL requis');
const amd = (b.amd_result || '').toLowerCase();
const dur = parseInt(b.duree_sec || b.duration_seconds || 0, 10) || 0;
const cost = amd === 'machine' || amd === 'not_sure' ? 0 : Math.round((dur * 0.22 / 60) * 10000) / 10000;
const leadGanador = !!(b.qualified || b.lead_ganador || b.statut === 'qualifie' || b.lead_gagnant === 'OUI');
const sinCp = b.code_postal === 'desconocido' || b.code_postal === 'inconnu' || b.etat_final === 'q3_sin_cp';
const tab = b.sheet_name || $env.GOOGLE_SHEETS_TAB || 'Leads_Sofia_Espagne';
const bodyOut = {
  sheet_name: tab,
  row: [
    now,
    b.nombre || b.nom_complet || '',
    telefono,
    b.email || '',
    b.adresse || b.address || '',
    b.ville || b.city || '',
    b.code_postal || '',
    b.call_sid || '',
    amd || 'unknown',
    dur,
    cost,
    b.proprietaire === true ? 'OUI' : (b.proprietaire === false ? 'NON' : (b.propietario || '?')),
    b.type_logement || b.tipo_vivienda || '',
    leadGanador ? 'OUI' : (sinCp ? 'SUPERVISEUR_RAPPELLE' : 'NON'),
    b.statut || b.etat_final || '',
    b.recording_url || b.url_enregistrement || '',
    b.transcript || b.transcripcion || '',
    b.score_ia || '',
    b.notes_sofia || '',
    sinCp || leadGanador ? 'RAPPEL_SUPERVISEUR' : 'AUCUNE',
    sinCp || leadGanador ? 'OUI' : 'NON',
  ],
};
await this.helpers.httpRequest({ method: 'POST', url: webhook, body: bodyOut, json: true });
return [{ json: { ok: true, telefono, cost, lead_ganador: leadGanador } }];
