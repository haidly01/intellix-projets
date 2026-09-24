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
    anciennete_mois: d.anciennete_mois,
    revenus_100k: d.revenus_100k,
    compte_entreprise: d.compte_entreprise,
    hot_lead: !!d.hot_lead,
    transcript: (session.transcript_log || []).join('\n'),
    recording_url: ev.recording_url || '',
    duration_sec: Math.max(parseInt(session.duree_sec, 10) || 0, parseInt(ev.duration_sec, 10) || 0),
    campaign: $env.VICIDIAL_CAMPAIGN || 'DW_QCB2B',
    agent_id: 'driven-b2b-qc-2026',
  };
}

if (ev.event_type === 'call_ended' || ev.action === 'hangup') {
  const sd = $getWorkflowStaticData('global');
  const session = (sd.driven_b2b_sessions || {})[ev.call_sid];
  const crm_payload = session ? buildCrmPayload(session, ev, {
    qualified: session.crm_action === 'tag_lead_chaud_driven',
    statut: session.crm_action || 'non_qualifie',
  }) : null;
  return [{ json: { action: 'hangup', call_sid: ev.call_sid, crm_payload, session, event: ev } }];
}

const callSid = ev.call_sid || '';
const sd = $getWorkflowStaticData('global');
if (!sd.driven_b2b_sessions) sd.driven_b2b_sessions = {};
let session = sd.driven_b2b_sessions[callSid];

if (!session) {
  session = {
    etape: 'GREETING',
    telephone: ev.to || ev.from || '',
    prenom: ev.prenom || ev.nombre || '',
    duree_sec: 0,
    turn_count: 0,
    silence_count: 0,
    soft_limit: parseInt($env.AGENT_SOFT_LIMIT_SEC || '120', 10),
    crm_action: null,
    data: {
      prenom: ev.prenom || ev.nombre || '',
      telephone: ev.to || ev.from || '',
      anciennete_mois: null,
      revenus_100k: null,
      compte_entreprise: null,
      hot_lead: false,
    },
    transcript_log: [],
  };
  sd.driven_b2b_sessions[callSid] = session;
}

const A = buildClips();

if (ev.event_type === 'call_start' || (!ev.recording_url && session.etape === 'GREETING' && !ev.event_type)) {
  return [{ json: {
    action: 'play_audio', audio_url: A.ouverture, call_sid: callSid,
    qualified: false, statut: 'en_cours', session, event: ev,
  } }];
}

if (ev.event_type !== 'recording_ready' || (!ev.recording_url && !ev.transcript && !ev.recording_b64)) {
  return [{ json: { action: 'hangup', error: 'no_recording', event: ev } }];
}

let transcript = (ev.transcript || '').toString().trim();
if (!transcript) {
  const odooBase = ($env.ODOO_URL || 'https://intellixcrm.com').replace(/\/$/, '');
  const sttBody = ev.recording_b64
    ? { recording_b64: ev.recording_b64, language: 'fr-CA' }
    : { recording_url: ev.recording_url, language: 'fr-CA' };
  try {
    const sttRes = await this.helpers.httpRequest({
      method: 'POST',
      url: odooBase + '/api/renov/stt/deepgram',
      headers: { 'Content-Type': 'application/json', 'X-Renov-Stt-Key': ($env.SOFIA_STT_WEBHOOK_KEY || 'doorway-sofia-stt') },
      body: sttBody,
      json: true,
      timeout: 90000,
    });
    transcript = ((sttRes && sttRes.transcript) || '').toString().trim();
  } catch (_e) {
    transcript = '';
  }
}

session.turn_count += 1;
const etape = session.etape;

function normTranscript(raw) {
  return (raw || '')
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-z0-9\s]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

const t = normTranscript(transcript);

function parseMonths(text) {
  const m = text.match(/(\d+)\s*(an|ans|annee|annees|year)/);
  if (m) return parseInt(m[1], 10) * 12;
  const mo = text.match(/(\d+)\s*(mois|month)/);
  if (mo) return parseInt(mo[1], 10);
  if (/(plusieurs an|longtemps|depuis longtemps|10 ans|15 ans|20 ans)/i.test(text)) return 24;
  if (/(un an|1 an|une annee)/i.test(text)) return 12;
  if (/(six mois|6 mois)/i.test(text)) return 6;
  if (/(deux ans|2 ans)/i.test(text)) return 24;
  if (/(trois ans|3 ans)/i.test(text)) return 36;
  return null;
}

function detectIntent(step, text) {
  if (!text.trim()) return { intent: 'silence' };
  if (/(stop|retir|ne plus|pas interesse d.etre contact|do not call|dnc)/i.test(text)) {
    return { intent: 'dnc' };
  }
  if (/(pas interesse|non merci|laissez moi|au revoir)/i.test(text)) {
    return { intent: 'pas_interesse' };
  }
  if (step === 'GREETING' || step === 'GREETING_CLARIF') {
    if (/(oui|interesse|interessant|peut etre|pourquoi pas|ok|d accord|bien sur|certainement|absolument|go ahead|parlez)/i.test(text)) {
      return { intent: 'interesse' };
    }
    if (/(non|pas vraiment|pas pour l instant|pas le temps)/i.test(text)) {
      return { intent: 'pas_interesse' };
    }
    return { intent: 'incertain' };
  }
  if (step === 'Q1_ANCIENNETE') {
    const months = parseMonths(text);
    if (months !== null) {
      return months >= 6 ? { intent: 'oui', valeur: months } : { intent: 'non', valeur: months };
    }
    if (/(oui|plus de|depuis|deja|longtemps)/i.test(text) && !/(non|moins|recent|nouveau|demarre)/i.test(text)) {
      return { intent: 'oui' };
    }
    if (/(non|moins de|recent|nouveau|demarre|commence|debut)/i.test(text)) {
      return { intent: 'non' };
    }
  }
  if (step === 'Q2_REVENUS') {
    if (/(oui|plus de|au moins|100|150|200|500|million|k\$)/i.test(text) && !/(non|moins|pas)/i.test(text)) {
      return { intent: 'oui' };
    }
    if (/(non|moins|pas encore|pas assez|inferieur)/i.test(text)) {
      return { intent: 'non' };
    }
  }
  if (step === 'Q3_COMPTE') {
    if (/(oui|bien sur|absolument|on en a|j en ai|affaires)/i.test(text) && !/(non|pas)/i.test(text)) {
      return { intent: 'oui' };
    }
    if (/(non|pas encore|personnel|pas de compte)/i.test(text)) {
      return { intent: 'non' };
    }
  }
  return text.trim() ? { intent: 'incertain' } : { intent: 'silence' };
}

const classification = detectIntent(etape, t);
const intent = classification.intent || 'silence';
const valeur = classification.valeur;
session.transcript_log.push(`[${etape}] ${transcript || '(silence)'} → ${intent}${valeur != null ? '/' + valeur : ''}`);
session.duree_sec += Math.max(4, parseInt(ev.duration_sec, 10) || 6);

let route = { hangup: false, qualified: false, audioUrl: A.fallback, crm_action: null, trigger_sms: false };

if (session.duree_sec >= session.soft_limit || session.turn_count > 10) {
  route = { hangup: true, audioUrl: A.timeout, crm_action: null };
} else if (intent === 'dnc') {
  route = { hangup: true, audioUrl: A.exit_dnc, crm_action: 'tag_dnc' };
} else if (intent === 'pas_interesse') {
  route = { hangup: true, audioUrl: A.exit_pi, crm_action: 'tag_pas_interesse' };
} else if (intent === 'silence') {
  session.silence_count += 1;
  if (session.silence_count >= 3) {
    route = { hangup: true, audioUrl: A.timeout, crm_action: null };
  } else if (etape === 'GREETING') {
    session.etape = 'GREETING_CLARIF';
    route = { hangup: false, audioUrl: A.fallback };
  } else {
    route = { hangup: false, audioUrl: A.fallback };
  }
} else if (intent === 'incertain') {
  route = { hangup: false, audioUrl: A.fallback };
} else {
  session.silence_count = 0;
  if (etape === 'GREETING' || etape === 'GREETING_CLARIF') {
    if (intent === 'interesse') {
      session.etape = 'Q1_ANCIENNETE';
      route = { hangup: false, audioUrl: A.q1_anciennete };
    } else {
      session.etape = 'GREETING_CLARIF';
      route = { hangup: false, audioUrl: A.fallback };
    }
  } else if (etape === 'Q1_ANCIENNETE') {
    if (intent === 'oui') {
      session.data.anciennete_mois = valeur || 12;
      session.etape = 'Q2_REVENUS';
      route = { hangup: false, audioUrl: A.q2_revenus };
    } else if (intent === 'non') {
      session.data.anciennete_mois = valeur || 0;
      route = { hangup: true, audioUrl: A.exit_anciennete, crm_action: 'tag_disqualifie_anciennete' };
    }
  } else if (etape === 'Q2_REVENUS') {
    if (intent === 'oui') {
      session.data.revenus_100k = true;
      session.etape = 'Q3_COMPTE';
      route = { hangup: false, audioUrl: A.q3_compte };
    } else if (intent === 'non') {
      session.data.revenus_100k = false;
      route = { hangup: true, audioUrl: A.exit_revenus, crm_action: 'tag_disqualifie_revenus' };
    }
  } else if (etape === 'Q3_COMPTE') {
    if (intent === 'oui') {
      session.data.compte_entreprise = true;
      session.data.hot_lead = true;
      session.etape = 'CLOSING';
      session.crm_action = 'tag_lead_chaud_driven';
      route = {
        hangup: true,
        qualified: true,
        audioUrl: A.closing_prequal,
        crm_action: 'tag_lead_chaud_driven',
        trigger_sms: true,
      };
    } else if (intent === 'non') {
      session.data.compte_entreprise = false;
      session.crm_action = 'tag_info_sans_compte';
      route = {
        hangup: true,
        audioUrl: A.no_compte,
        crm_action: 'tag_info_sans_compte',
        trigger_sms: true,
      };
    }
  }
}

session.crm_action = route.crm_action || session.crm_action;
sd.driven_b2b_sessions[callSid] = session;

const crm_payload = route.hangup
  ? buildCrmPayload(session, ev, { qualified: route.qualified, statut: session.crm_action || 'non_qualifie' })
  : null;
if (crm_payload && route.trigger_sms) {
  crm_payload.trigger_sms = true;
}

return [{
  json: {
    action: route.hangup ? 'hangup' : 'play_audio',
    audio_url: route.audioUrl,
    call_sid: callSid,
    qualified: !!route.qualified,
    crm_action: session.crm_action,
    crm_payload,
    trigger_sms: !!route.trigger_sms,
    transcript,
    statut: session.crm_action || 'en_cours',
    session,
    event: ev,
  },
}];
