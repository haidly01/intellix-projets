/**
 * renov-aides — Webhook Google Sheets (Intellix / n8n / Odoo)
 *
 * Déploiement :
 * 1. Ouvrir le Sheet → Extensions → Apps Script
 * 2. Coller ce fichier → Enregistrer
 * 3. Déployer → Nouveau déploiement → Application Web
 *    - Exécuter en tant que : Moi (travailkarine123@gmail.com)
 *    - Qui a accès : Tout le monde
 * 4. Copier l'URL …/macros/s/…/exec → GOOGLE_SHEETS_WEBHOOK_URL (n8n + Odoo)
 */
var SPREADSHEET_ID = '1twVFnI9xFjmflhTJzF2jglwzff0bO_ZCp8abTvIYy4Y';
var DEFAULT_SHEET = 'Leads_Sofia_Test';
var LEGACY_HEADERS = [
  'Fecha', 'Nombre', 'Telefono', 'Calificado', 'Transcripcion',
  'Grabacion', 'CallSid', 'Provider', 'LeadId'
];
var SOFIA_HEADERS = [
  'timestamp', 'campaign_id', 'telephony_provider', 'telephone', 'nom_contact',
  'statut', 'proprietaire', 'type_logement', 'code_postal', 'combles',
  'acces_combles', 'creneau_rappel', 'duree_appel_sec', 'url_enregistrement',
  'call_sid', 'transcripcion'
];

function ensureSheet_(sheetName, headers) {
  var ss = SpreadsheetApp.openById(SPREADSHEET_ID);
  var sh = ss.getSheetByName(sheetName);
  if (!sh) {
    sh = ss.insertSheet(sheetName);
  }
  if (sh.getLastRow() === 0) {
    sh.appendRow(headers);
  }
  return sh;
}

function doPost(e) {
  try {
    var body = {};
    if (e && e.postData && e.postData.contents) {
      body = JSON.parse(e.postData.contents);
    }
    var sheetName = body.sheet_name || DEFAULT_SHEET;
    var headers = body.headers || SOFIA_HEADERS;
    var sh = ensureSheet_(sheetName, headers);
    var row = body.row;
    if (!row || !row.length) {
      row = [
        body.date || new Date().toISOString(),
        body.nombre || body.agent_name || body.nom_contact || '',
        body.telefono || body.telephone || body.to || '',
        body.qualified ? 'SI' : (body.qualified === false ? 'NO' : ''),
        body.transcript || body.transcripcion || '',
        body.recording_url || body.url_enregistrement || '',
        body.call_sid || '',
        body.provider || '',
        body.lead_id || body.campaign_id || body.statut || ''
      ];
      sh = ensureSheet_(body.sheet_name || 'Appels IA', LEGACY_HEADERS);
    }
    sh.appendRow(row);
    return ContentService
      .createTextOutput(JSON.stringify({ ok: true, row: row.length }))
      .setMimeType(ContentService.MimeType.JSON);
  } catch (err) {
    return ContentService
      .createTextOutput(JSON.stringify({ ok: false, error: String(err) }))
      .setMimeType(ContentService.MimeType.JSON);
  }
}

function doGet() {
  return ContentService
    .createTextOutput(JSON.stringify({ ok: true, ping: 'renov-aides sheets webhook' }))
    .setMimeType(ContentService.MimeType.JSON);
}
