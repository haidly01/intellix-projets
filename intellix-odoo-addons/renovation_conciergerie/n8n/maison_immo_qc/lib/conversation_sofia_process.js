const A = {
  ouverture: audioUrl('sophie_ouverture'),
  timeline_chaud: audioUrl('sophie_timeline_chaud'),
  timeline_tiede: audioUrl('sophie_timeline_tiede'),
  sonder_futur: audioUrl('sophie_sonder_futur'),
  futur_liste: audioUrl('sophie_futur_liste'),
  closing: audioUrl('sophie_closing'),
  exit_courtier: audioUrl('sophie_exit_courtier'),
  exit_pi: audioUrl('sophie_exit_pi'),
  exit_dnc: audioUrl('sophie_exit_dnc'),
  fallback: audioUrl('sophie_fallback'),
  timeout: audioUrl('sophie_exit_timeout'),
};

const _raw = $input.first().json;
const ev = (_raw && _raw.body && typeof _raw.body === 'object') ? _raw.body : _raw;

if (ev.event_type === 'amd_result' && ['machine', 'fax', 'not_sure'].includes((ev.amd_result || '').toLowerCase())) {
  return [{ json: { action: 'hangup', call_sid: ev.call_sid, qualified: false, statut: 'messagerie', crm_action: null, event: ev } }];
}

function buildCrmPayload(session, ev, opts) {
  const phone = session?.data?.telephone || session?.telephone || ev.to || ev.from || '';
  if (!phone || !session) return null;
  const d = session.data || {};
  return {
    call_sid: ev.call_sid || '',
    partner_id: ev.partner_id || ev.lead_id || '',
    prenom: d.prenom || ev.prenom || ev.nombre || '',
    telephone: phone,
    qualified: !!(opts && opts.qualified),
    statut: (opts && opts.statut) || session.crm_action || 'en_cours',
    crm_action: session.crm_action || null,
    intention_vente: d.intention_vente,
    timeline: d.timeline || '',
    courtier_existant: !!d.courtier_existant,
    preference_rappel: d.dispo_rappel || '',
    transcript: (session.transcript_log || []).join('\n'),
    recording_url: ev.recording_url || '',
    duration_sec: session.duree_sec || ev.duration_sec || 0,
    campaign: $env.CAMPAIGN_ID || 'MR_IMMO_QC',
  };
}

if (ev.event_type === 'call_ended' || ev.action === 'hangup') {
  const sd = $getWorkflowStaticData('global');
  const session = (sd.mr_qc_sessions || {})[ev.call_sid];
  const crm_payload = session ? buildCrmPayload(session, ev, {
    qualified: session.crm_action === 'tag_lead_qualifie',
    statut: session.crm_action || 'non_qualifie',
  }) : null;
  return [{ json: { action: 'hangup', call_sid: ev.call_sid, crm_payload, session, event: ev } }];
}

const callSid = ev.call_sid || '';
const sd = $getWorkflowStaticData('global');
if (!sd.mr_qc_sessions) sd.mr_qc_sessions = {};
let session = sd.mr_qc_sessions[callSid];

if (!session) {
  session = {
    etape: 'GREETING',
    telephone: ev.to || ev.from || '',
    prenom: ev.prenom || ev.nombre || '',
    duree_sec: 0,
    turn_count: 0,
    silence_count: 0,
    soft_limit: parseInt($env.AGENT_SOFT_LIMIT_SEC || '90', 10),
    crm_action: null,
    data: {
      prenom: ev.prenom || ev.nombre || '',
      intention_vente: null,
      timeline: null,
      courtier_existant: false,
      dispo_rappel: null,
      telephone: ev.to || ev.from || '',
    },
    transcript_log: [],
  };
  sd.mr_qc_sessions[callSid] = session;
}

if (ev.event_type === 'call_start' || (!ev.recording_url && session.etape === 'GREETING' && !ev.event_type)) {
  return [{ json: { action: 'play_audio', audio_url: A.ouverture, call_sid: callSid, qualified: false, statut: 'en_cours', session, event: ev } }];
}

if (ev.event_type !== 'recording_ready' || !ev.recording_url) {
  return [{ json: { action: 'hangup', error: 'no_recording', event: ev } }];
}

let transcript = '';
const odooBase = ($env.ODOO_URL || 'https://intellixcrm.com').replace(/\/$/, '');
try {
  const sttRes = await this.helpers.httpRequest({
    method: 'POST',
    url: odooBase + '/api/renov/stt/deepgram',
    headers: { 'Content-Type': 'application/json', 'X-Renov-Stt-Key': ($env.SOFIA_STT_WEBHOOK_KEY || 'doorway-sofia-stt') },
    body: { recording_url: ev.recording_url, language: 'fr-CA' },
    json: true,
    timeout: 25000,
  });
  transcript = (sttRes && sttRes.transcript) || '';
} catch (e) {
  transcript = '';
}

session.turn_count += 1;
const etape = session.etape;
const t = (transcript || '').toLowerCase();

function detectIntent(step, text) {
  if (!text.trim()) return { intent: 'silence' };
  if (/(stop|retir|ne plus|do not call|dnc)/i.test(text)) return { intent: 'dnc' };
  if (/(déjà un courtier|j'ai un courtier|mon courtier)/i.test(text)) return { intent: 'courtier' };
  if (/(pas intéressé|non merci)/i.test(text)) return { intent: 'pas_interesse' };
  if (step === 'GREETING') {
    if (/(oui|justement|peut-être|peut être|je pense)/i.test(text)) return { intent: 'oui_vendre' };
    if (/(non|pas pour l'instant|pas prévu)/i.test(text)) return { intent: 'non_vendre' };
  }
  if (step === 'QUALIFIER_TIMELINE') {
    if (/(cette année|bientôt|dans les mois|6 mois)/i.test(text)) return { intent: 'timeline', valeur: 'CHAUD' };
    if (/(l'an prochain|an prochain|6 à 12|pas pressé)/i.test(text)) return { intent: 'timeline', valeur: 'TIEDE' };
    if (/(2 ans|éventuellement|pas sûr|futur)/i.test(text)) return { intent: 'timeline', valeur: 'FUTUR' };
    if (/(oui)/i.test(text)) return { intent: 'timeline', valeur: 'CHAUD' };
  }
  if (step === 'SONDER_FUTUR') {
    if (/(oui|possible|retraite|déménagement|peut-être)/i.test(text)) return { intent: 'futur_oui' };
    if (/(non|pas du tout|jamais)/i.test(text)) return { intent: 'futur_non' };
  }
  if (step === 'CAPTURER_DISPO' || step === 'FUTUR_LISTE') {
    if (/(matin|avant-midi)/i.test(text)) return { intent: 'dispo', valeur: 'matin' };
    if (/(après-midi|apres-midi)/i.test(text)) return { intent: 'dispo', valeur: 'après-midi' };
    if (/(soir)/i.test(text)) return { intent: 'dispo', valeur: 'soir' };
    if (/\d{1,2}\s*h/i.test(text)) return { intent: 'dispo', valeur: text.slice(0, 30) };
    if (/(oui|ok|correct)/i.test(text)) return { intent: 'confirme' };
  }
  return { intent: 'silence' };
}

const classification = detectIntent(etape, t);
const intent = classification.intent || 'silence';
const valeur = classification.valeur || '';
session.transcript_log.push(`[${etape}] ${transcript || '(silence)'} → ${intent}${valeur ? '/' + valeur : ''}`);
session.duree_sec += Math.max(4, parseInt(ev.duration_sec, 10) || 6);

let route = { hangup: false, qualified: false, audioUrl: A.fallback, crm_action: null };

if (session.duree_sec >= session.soft_limit || session.turn_count > 7) {
  route = { hangup: true, audioUrl: A.timeout, crm_action: null };
} else if (intent === 'dnc') {
  route = { hangup: true, audioUrl: A.exit_dnc, crm_action: 'tag_dnc' };
} else if (intent === 'courtier') {
  route = { hangup: true, audioUrl: A.exit_courtier, crm_action: 'tag_pas_interesse' };
} else if (intent === 'pas_interesse') {
  route = { hangup: true, audioUrl: A.exit_pi, crm_action: 'tag_pas_interesse' };
} else if (intent === 'silence') {
  session.silence_count += 1;
  route = session.silence_count >= 2
    ? { hangup: true, audioUrl: A.timeout, crm_action: null }
    : { hangup: false, audioUrl: A.fallback };
} else {
  session.silence_count = 0;
  if (etape === 'GREETING') {
    if (intent === 'oui_vendre') {
      session.data.intention_vente = true;
      session.etape = 'QUALIFIER_TIMELINE';
      route = { hangup: false, audioUrl: A.timeline_chaud };
    } else if (intent === 'non_vendre') {
      session.etape = 'SONDER_FUTUR';
      route = { hangup: false, audioUrl: A.sonder_futur };
    }
  } else if (etape === 'QUALIFIER_TIMELINE' && intent === 'timeline') {
    session.data.timeline = valeur;
    session.etape = 'CAPTURER_DISPO';
    route = {
      hangup: false,
      audioUrl: valeur === 'TIEDE' ? A.timeline_tiede : A.timeline_chaud,
    };
  } else if (etape === 'SONDER_FUTUR') {
    if (intent === 'futur_oui') {
      session.data.timeline = 'FUTUR';
      session.etape = 'FUTUR_LISTE';
      route = { hangup: false, audioUrl: A.futur_liste };
    } else {
      route = { hangup: true, audioUrl: A.exit_pi, crm_action: 'tag_pas_interesse' };
    }
  } else if ((etape === 'CAPTURER_DISPO' || etape === 'FUTUR_LISTE') && (intent === 'dispo' || intent === 'confirme')) {
    session.data.dispo_rappel = valeur || session.data.dispo_rappel || 'matin';
    session.crm_action = 'tag_lead_qualifie';
    route = { hangup: true, qualified: true, audioUrl: A.closing, crm_action: 'tag_lead_qualifie' };
  }
}

session.crm_action = route.crm_action || session.crm_action;
sd.mr_qc_sessions[callSid] = session;
const crm_payload = route.hangup
  ? buildCrmPayload(session, ev, { qualified: route.qualified, statut: session.crm_action || 'non_qualifie' })
  : null;

return [{
  json: {
    action: route.hangup ? 'hangup' : 'play_audio',
    audio_url: route.audioUrl,
    call_sid: callSid,
    qualified: !!route.qualified,
    crm_action: session.crm_action,
    crm_payload,
    transcript,
    statut: session.crm_action || 'en_cours',
    session,
    event: ev,
  },
}];
