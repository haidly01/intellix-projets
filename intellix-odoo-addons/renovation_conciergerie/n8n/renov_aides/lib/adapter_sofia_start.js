const b = $input.first().json.body || $input.first().json;
function norm(p) {
  if (!p) return '';
  const s = String(p).trim();
  if (s.startsWith('+')) return '+' + s.replace(/\D/g, '');
  const d = s.replace(/\D/g, '');
  if (d.length === 9) return '+34' + d;
  return '+' + d;
}
const callSid = b.CallSid || '';
const telephone = norm(b.To);
const sd = $getWorkflowStaticData('global');
if (!sd.sofia_sessions) sd.sofia_sessions = {};
sd.sofia_sessions[callSid] = {
  etape: 'ouverture',
  telephone,
  duree_sec: 0,
  hors_sujet_count: 0,
  soft_limit: parseInt($env.AGENT_SOFT_LIMIT_SEC || '110', 10) || 110,
  data: {
    proprietaire: null, type_logement: null, code_postal: null, combles: null,
    acces_combles: null, calefaccion: null, creneau_rappel: null, nom_contact: null, telephone_final: null,
  },
  transcript_log: [],
  non_owner_count: 0,
  silence_count: 0,
};
const base = ($env.N8N_WEBHOOK_URL || '').replace(/\/$/, '');
const bucket = ($env.STORAGE_BUCKET_URL || '').replace(/\/$/, '');
const hook = bucket ? bucket + '/sofia_hook.mp3' : '';
const question = bucket ? bucket + '/sofia_question_propietario.mp3' : '';
const recTimeout = parseInt($env.SOFIA_RECORD_TIMEOUT || '5', 10) || 5;
const recMax = parseInt($env.SOFIA_RECORD_MAXLENGTH || '10', 10) || 10;
const pauseSec = parseInt($env.SOFIA_RECORD_PAUSE_SEC || '2', 10) || 2;
let twiml = '<?xml version="1.0" encoding="UTF-8"?><Response>';
if (hook && question) {
  twiml += '<Play>' + hook + '</Play>';
  twiml += '<Play>' + question + '</Play>';
} else if (bucket) {
  twiml += '<Play>' + bucket + '/sofia_ouverture.mp3</Play>';
}
twiml += '<Pause length="' + pauseSec + '"/>';
twiml += '<Record action="' + base + '/telephony/twilio/transcribe" maxLength="' + recMax + '" timeout="' + recTimeout + '" playBeep="false" trim="trim-silence"/>';
twiml += '</Response>';
return [{ json: { twiml, call_sid: callSid, telephone } }];
