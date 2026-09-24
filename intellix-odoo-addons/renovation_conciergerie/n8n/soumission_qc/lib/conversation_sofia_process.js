const A = {
  ouverture: audioUrl('emilie_ouverture'),
  question_projet: audioUrl('emilie_question_projet'),
  capturer_dispo: audioUrl('emilie_capturer_dispo'),
  closing: audioUrl('emilie_closing'),
  sonder_futur: audioUrl('emilie_sonder_futur'),
  exit_loc: audioUrl('emilie_exit_locataire'),
  exit_futur: audioUrl('emilie_exit_futur'),
  exit_pi: audioUrl('emilie_exit_pas_interesse'),
  exit_dnc: audioUrl('emilie_exit_dnc'),
  objection: audioUrl('emilie_objection_entrepreneur'),
  fallback: audioUrl('emilie_fallback'),
  timeout: audioUrl('emilie_exit_timeout'),
};

const _raw = $input.first().json;
const ev = (_raw && _raw.body && typeof _raw.body === 'object') ? _raw.body : _raw;

if (ev.event_type === 'amd_result' && ['machine', 'fax', 'not_sure'].includes((ev.amd_result || '').toLowerCase())) {
  return [{ json: {
    action: 'hangup', call_sid: ev.call_sid, qualified: false, statut: 'messagerie',
    crm_action: null, event: ev,
  } }];
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
    type_projet: d.type_projet || '',
    preference_rappel: d.dispo_rappel || '',
    futur_3mois: !!d.futur_3mois,
    transcript: (session.transcript_log || []).join('\n'),
    recording_url: ev.recording_url || '',
    duration_sec: session.duree_sec || ev.duration_sec || 0,
    campaign: $env.CAMPAIGN_ID || 'SE_RENOV_QC',
  };
}

if (ev.event_type === 'call_ended' || ev.action === 'hangup') {
  const sd = $getWorkflowStaticData('global');
  const session = (sd.sofia_qc_sessions || {})[ev.call_sid];
  const crm_payload = session ? buildCrmPayload(session, ev, {
    qualified: session.crm_action === 'tag_lead_qualifie',
    statut: session.crm_action || 'non_qualifie',
  }) : null;
  return [{ json: { action: 'hangup', call_sid: ev.call_sid, crm_payload, session, event: ev } }];
}

const callSid = ev.call_sid || '';
const sd = $getWorkflowStaticData('global');
if (!sd.sofia_qc_sessions) sd.sofia_qc_sessions = {};
let session = sd.sofia_qc_sessions[callSid];

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
      proprietaire: null,
      type_projet: null,
      dispo_rappel: null,
      futur_3mois: false,
      telephone: ev.to || ev.from || '',
    },
    transcript_log: [],
  };
  sd.sofia_qc_sessions[callSid] = session;
}

if (ev.event_type === 'call_start' || (!ev.recording_url && session.etape === 'GREETING' && !ev.event_type)) {
  return [{ json: {
    action: 'play_audio', audio_url: A.ouverture, call_sid: callSid,
    qualified: false, statut: 'en_cours', session, event: ev,
  } }];
}

if (ev.event_type !== 'recording_ready' || !ev.recording_url) {
  return [{ json: { action: 'hangup', error: 'no_recording', event: ev } }];
}

let transcript = '';
let classification = { intent: 'silence' };
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
  if (/(stop|retir|ne plus|pas intéressé d'être contact|do not call|dnc)/i.test(text)) {
    return { intent: 'dnc' };
  }
  if (/(pas intéressé|non merci|laissez-moi|au revoir)/i.test(text)) {
    return { intent: 'pas_interesse' };
  }
  if (step === 'GREETING' || step === 'GREETING_CLARIF') {
    if (/(locataire|je loue|pas ma maison|pas propriétaire|non)/i.test(text) && !/oui|propriétaire|c'est ma maison/i.test(text)) {
      return { intent: 'locataire' };
    }
    if (/(propriétaire|oui|c'est ma maison|c est ma maison)/i.test(text)) {
      return { intent: 'proprietaire' };
    }
    return { intent: 'incertain' };
  }
  if (step === 'QUESTION_PROJET' || step === 'SONDER_FUTUR') {
    const projets = /(cuisine|salle de bain|toiture|fenêtre|sous-sol|agrandissement|isolation|plancher|terrasse|patio|garage|peinture|électricité|plomberie|rénovation|travaux)/i;
    if (projets.test(text)) return { intent: 'projet', valeur: text.slice(0, 80) };
    if (/(pas vraiment|pas pour l'instant|pas sûr|non)/i.test(text)) return { intent: 'pas_projet' };
    if (/(oui|peut-être|peut être|un peu|quelque chose)/i.test(text)) return { intent: 'projet', valeur: text.slice(0, 80) };
  }
  if (step === 'CAPTURER_DISPO') {
    if (/(matin|avant-midi|avant midi)/i.test(text)) return { intent: 'dispo', valeur: 'matin' };
    if (/(après-midi|après midi|apres-midi)/i.test(text)) return { intent: 'dispo', valeur: 'après-midi' };
    if (/(soir|après 5|après 17|apres 5)/i.test(text)) return { intent: 'dispo', valeur: 'soir' };
    if (/\d{1,2}\s*h/i.test(text)) return { intent: 'dispo', valeur: text.slice(0, 30) };
    if (/(oui|ok|correct|confirme)/i.test(text)) return { intent: 'confirme' };
  }
  if (/(déjà un entrepreneur|j'ai un entrepreneur)/i.test(text)) {
    return { intent: 'objection_entrepreneur' };
  }
  return { intent: 'silence' };
}

classification = detectIntent(etape, t);
let intent = classification.intent || 'silence';
const valeur = classification.valeur || '';
session.transcript_log.push(`[${etape}] ${transcript || '(silence)'} → ${intent}${valeur ? '/' + valeur : ''}`);
session.duree_sec += Math.max(4, parseInt(ev.duration_sec, 10) || 6);

let route = { hangup: false, qualified: false, audioUrl: A.fallback, crm_action: null };

if (session.duree_sec >= session.soft_limit || session.turn_count > 7) {
  route = { hangup: true, audioUrl: A.timeout, crm_action: null };
} else if (intent === 'dnc') {
  route = { hangup: true, audioUrl: A.exit_dnc, crm_action: 'tag_dnc' };
} else if (intent === 'pas_interesse') {
  route = { hangup: true, audioUrl: A.exit_pi, crm_action: 'tag_pas_interesse' };
} else if (intent === 'silence') {
  session.silence_count += 1;
  if (session.silence_count >= 2) {
    route = { hangup: true, audioUrl: A.timeout, crm_action: null };
  } else if (etape === 'GREETING') {
    session.etape = 'GREETING_CLARIF';
    route = { hangup: false, audioUrl: A.fallback };
  } else {
    route = { hangup: false, audioUrl: A.fallback };
  }
} else {
  session.silence_count = 0;
  if (etape === 'GREETING' || etape === 'GREETING_CLARIF') {
    if (intent === 'proprietaire') {
      session.data.proprietaire = true;
      session.etape = 'QUESTION_PROJET';
      route = { hangup: false, audioUrl: A.question_projet };
    } else if (intent === 'locataire') {
      route = { hangup: true, audioUrl: A.exit_loc, crm_action: 'tag_locataire' };
    } else {
      session.etape = 'GREETING_CLARIF';
      route = { hangup: false, audioUrl: A.fallback };
    }
  } else if (etape === 'QUESTION_PROJET') {
    if (intent === 'projet') {
      session.data.type_projet = valeur || transcript.slice(0, 80);
      session.etape = 'CAPTURER_DISPO';
      route = { hangup: false, audioUrl: A.capturer_dispo };
    } else if (intent === 'pas_projet') {
      session.etape = 'SONDER_FUTUR';
      route = { hangup: false, audioUrl: A.sonder_futur };
    } else if (intent === 'objection_entrepreneur') {
      route = { hangup: false, audioUrl: A.objection };
    }
  } else if (etape === 'SONDER_FUTUR') {
    if (intent === 'projet') {
      session.data.type_projet = valeur || transcript.slice(0, 80);
      session.etape = 'CAPTURER_DISPO';
      route = { hangup: false, audioUrl: A.capturer_dispo };
    } else {
      session.data.futur_3mois = true;
      route = { hangup: true, audioUrl: A.exit_futur, crm_action: 'tag_pas_projet' };
    }
  } else if (etape === 'CAPTURER_DISPO') {
    if (intent === 'dispo' || intent === 'confirme') {
      session.data.dispo_rappel = valeur || session.data.dispo_rappel || 'matin';
      session.etape = 'CLOSING';
      session.crm_action = 'tag_lead_qualifie';
      route = { hangup: true, qualified: true, audioUrl: A.closing, crm_action: 'tag_lead_qualifie' };
    }
  }
}

session.crm_action = route.crm_action || session.crm_action;
sd.sofia_qc_sessions[callSid] = session;

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
