// SOFIA_FR_EMPTY_FIX — audio_url clips, silence_count, pickReaskClip, AGI transcript prefer
function norm(t) {
  return (t || '').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '').trim();
}

const bucket = ($env.STORAGE_BUCKET_URL || 'https://intellixcrm.com/sofia-tts').replace(/\/$/, '');
const audioFile = (name) => `${bucket}/${name}.mp3`;

function pickReaskClip(etape) {
  const map = {
    intro: 'sofia_q1_clarif',
    q1_statut: 'sofia_question_propietario',
    q2_logement: 'sofia_q2',
    q3_chauffage: 'sofia_q3_repeat',
    q4_travaux: 'sofia_q4',
    q5_consentement: 'sofia_q5',
  };
  return audioFile(map[etape] || 'sofia_fallback');
}

function classify(etape, transcript) {
  const t = norm(transcript);
  if (!t) return { intent: 'silence' };
  const oui = /\b(oui|ouais|ok|daccord|dac|bien sur|volontiers|exact|correct)\b/.test(t);
  const non = /^(non|nan|nop)\b/.test(t) || /\b(pas interesse|non merci|laissez|arretez)\b/.test(t);
  if (etape === 'intro') {
    if (non) return { intent: 'non' };
    if (/\b(allo|bonjour|salut|ouin|hey|oui allo)\b/.test(t)) return { intent: 'oui' };
    if (/^(oui|ouais|ouin)\s*$/.test(t)) return { intent: 'oui' };
    if (oui) return { intent: 'oui' };
  }
  if (etape === 'q1_statut') {
    if (/\b(proprietaire|proprio|proprietaire|a moi|chez moi|ma maison|c est a moi|appartient)\b/.test(t)) return { intent: 'ok', valeur: 'proprietaire' };
    if (/\b(je suis proprio|en propriete)\b/.test(t)) return { intent: 'ok', valeur: 'proprietaire' };
    if (/\b(locataire|je loue|location|loc)\b/.test(t)) return { intent: 'ok', valeur: 'locataire' };
    if (/\b(ne sais pas|pas sur|je sais pas)\b/.test(t)) return { intent: 'ok', valeur: 'ne_sait_pas' };
  }
  if (etape === 'q2_logement') {
    if (/\b(maison|pavillon|villa)\b/.test(t)) return { intent: 'ok', valeur: 'maison' };
    if (/\b(appartement|appart|studio|flat)\b/.test(t)) return { intent: 'ok', valeur: 'appartement' };
  }
  if (etape === 'q3_chauffage') {
    if (/\bgaz\b/.test(t)) return { intent: 'ok', valeur: 'gaz' };
    if (/\bfioul\b/.test(t)) return { intent: 'ok', valeur: 'fioul' };
    if (/\b(electrique|elec)\b/.test(t)) return { intent: 'ok', valeur: 'electrique' };
    if (t) return { intent: 'ok', valeur: 'autre' };
  }
  if (etape === 'q4_travaux') {
    if (/\b(les deux|isolation et|panneaux et)\b/.test(t)) return { intent: 'ok', valeur: 'oui_les_deux' };
    if (/\b(isolation|isole)\b/.test(t)) return { intent: 'ok', valeur: 'oui_isolation' };
    if (/\b(panneau|solaire|pv|photovoltaique)\b/.test(t)) return { intent: 'ok', valeur: 'oui_pv' };
    if (/\b(non|pas encore|jamais|aucun)\b/.test(t)) return { intent: 'ok', valeur: 'non' };
    if (/\b(ne sais pas|pas sur)\b/.test(t)) return { intent: 'ok', valeur: 'ne_sait_pas' };
  }
  if (etape === 'q5_consentement') {
    if (/\b(oui|ouais|d accord|volontiers|pas de probleme|accepte|ok pour)\b/.test(t) && !/\bnon\b/.test(t)) return { intent: 'ok', valeur: 'oui' };
    if (non) return { intent: 'ok', valeur: 'non' };
  }
  if (oui) return { intent: 'oui' };
  if (non) return { intent: 'non' };
  return { intent: 'incertain' };
}

const _raw = $input.first().json;
const ev = (_raw && _raw.body && typeof _raw.body === 'object') ? _raw.body : _raw;

if (ev.event_type === 'amd_result' && ['machine', 'fax', 'not_sure'].includes((ev.amd_result || '').toLowerCase())) {
  return [{ json: {
    action: 'hangup', call_sid: ev.call_sid, qualified: false, statut: 'messagerie',
    audio_url: audioFile('sofia_exit_timeout'),
    crm_payload: {
      telephone: ev.to || ev.from || '',
      statut: 'messagerie', etat_final: 'messagerie',
      campaign: ev.campaign || 'DW_FRB2C', agent_id: ev.agent_id || 'marenofacile',
    },
    event: ev,
  } }];
}

function buildCrmPayload(session, ev, opts) {
  const phone = session?.data?.telephone || session?.telephone || ev.to || ev.from || '';
  if (!phone || !session) return null;
  const d = session.data || {};
  const consent = d.consentement_recontact;
  const qualified = !!(opts && opts.qualified);
  return {
    call_sid: ev.call_sid || '',
    partner_id: ev.partner_id || ev.lead_id || '',
    lead_id: ev.lead_id || ev.partner_id || '',
    prenom: d.prenom || ev.prenom || '',
    ville: d.ville || ev.ville || '',
    telephone: phone,
    statut: (opts && opts.statut) || session.statut || 'non_fait',
    etat_final: (opts && opts.statut) || session.statut || 'non_fait',
    statut_propriete: d.statut_propriete || '',
    type_logement: d.type_logement || '',
    chauffage: d.chauffage || '',
    travaux_existants: d.travaux_existants || '',
    consentement_recontact: consent,
    qualification_complete: qualified,
    transcript: (session.transcript_log || []).join('\n'),
    recording_url: ev.recording_url || '',
    duration_sec: session.duree_sec || ev.duration_sec || 0,
    campaign: ev.campaign || $env.VICIDIAL_CAMPAIGN || 'DW_FRB2C',
    agent_id: ev.agent_id || $env.AGENT_ID || 'marenofacile',
  };
}

if (ev.event_type === 'call_ended' || ev.action === 'hangup') {
  const sd = $getWorkflowStaticData('global');
  const session = (sd.renofacile_sessions || {})[ev.call_sid];
  const crm_payload = session ? buildCrmPayload(session, ev, {
    qualified: session.qualified,
    statut: session.statut,
  }) : null;
  return [{ json: { action: 'hangup', call_sid: ev.call_sid, crm_payload, session, event: ev } }];
}

const callSid = ev.call_sid || '';
const sd = $getWorkflowStaticData('global');
if (!sd.renofacile_sessions) sd.renofacile_sessions = {};
let session = sd.renofacile_sessions[callSid];

if (!session) {
  session = {
    etape: 'intro',
    telephone: ev.to || ev.from || '',
    prenom: ev.prenom || '',
    ville: ev.ville || '',
    duree_sec: 0,
    silence_count: 0,
    soft_limit: parseInt($env.AGENT_MAX_SEC || '120', 10),
    qualified: false,
    statut: 'en_cours',
    data: {
      prenom: ev.prenom || '',
      ville: ev.ville || '',
      telephone: ev.to || ev.from || '',
      statut_propriete: null,
      type_logement: null,
      chauffage: null,
      travaux_existants: null,
      consentement_recontact: null,
    },
    transcript_log: [],
  };
  sd.renofacile_sessions[callSid] = session;
}
if (session.silence_count == null) session.silence_count = 0;

if (ev.event_type !== 'recording_ready' || (!ev.recording_url && !ev.recording_b64)) {
  if (session.etape === 'intro') {
    return [{ json: {
      action: 'play_audio', call_sid: callSid, qualified: false, statut: 'en_cours',
      audio_url: pickReaskClip('intro'),
      session, event: ev,
    } }];
  }
  return [{ json: { action: 'hangup', error: 'no_recording', event: ev } }];
}

let transcript = (ev.transcript || '').trim();
if (!transcript && (ev.recording_url || ev.recording_b64)) {
  const odooBase = ($env.ODOO_URL || 'https://intellixcrm.com').replace(/\/$/, '');
  const sttKey = ($env.SOFIA_STT_WEBHOOK_KEY || 'doorway-sofia-stt').trim();
  try {
    const sttRes = await this.helpers.httpRequest({
      method: 'POST',
      url: odooBase + '/api/renov/stt/deepgram',
      headers: { 'Content-Type': 'application/json', 'X-Renov-Stt-Key': sttKey },
      body: {
        recording_url: ev.recording_url || '',
        recording_b64: ev.recording_b64 || '',
        language: 'fr',
      },
      json: true,
      timeout: 25000,
    });
    transcript = (sttRes && sttRes.transcript) || '';
  } catch (e) {
    transcript = `[STT error: ${(e.message || e).toString().slice(0, 80)}]`;
  }
}

const etape = session.etape;
const cls = classify(etape, transcript);
session.transcript_log.push(`[${etape}] ${transcript || '(silence)'} → ${cls.intent}${cls.valeur ? '/' + cls.valeur : ''}`);
session.duree_sec += Math.max(4, parseInt(ev.duration_sec, 10) || 6);

let route = { hangup: false, qualified: false, statut: 'en_cours', audio_url: '' };

if (session.duree_sec >= session.soft_limit) {
  route = { hangup: true, qualified: false, statut: 'non_fait', audio_url: audioFile('sofia_exit_timeout') };
} else if (cls.intent === 'silence' || cls.intent === 'incertain') {
  if (etape === 'intro') {
    session.silence_count += 1;
    if (session.silence_count >= 3) {
      route = { hangup: true, statut: 'non_fait', audio_url: audioFile('sofia_exit_timeout') };
    } else {
      route = { hangup: false, audio_url: pickReaskClip('intro') };
    }
  } else {
    route = { hangup: false, audio_url: pickReaskClip(etape) };
  }
} else if (etape === 'intro') {
  session.silence_count = 0;
  if (cls.intent === 'non') {
    route = { hangup: true, statut: 'pas_interesse', audio_url: audioFile('sofia_exit_polite') };
  } else {
    session.etape = 'q1_statut';
    route = { hangup: false, audio_url: audioFile('sofia_question_propietario') };
  }
} else if (etape === 'q1_statut') {
  session.silence_count = 0;
  if (cls.intent === 'ok') {
    session.data.statut_propriete = cls.valeur;
    if (cls.valeur === 'locataire') {
      route = { hangup: true, statut: 'locataire', audio_url: audioFile('sofia_exit_non_proprio') };
    } else {
      session.etape = 'q2_logement';
      route = { hangup: false, audio_url: audioFile('sofia_q2') };
    }
  } else {
    route = { hangup: false, audio_url: pickReaskClip('q1_statut') };
  }
} else if (etape === 'q2_logement') {
  session.silence_count = 0;
  if (cls.intent === 'ok') {
    session.data.type_logement = cls.valeur;
    session.etape = 'q3_chauffage';
    route = { hangup: false, audio_url: audioFile('sofia_q3_repeat') };
  } else {
    route = { hangup: false, audio_url: pickReaskClip('q2_logement') };
  }
} else if (etape === 'q3_chauffage') {
  session.silence_count = 0;
  if (cls.intent === 'ok') {
    session.data.chauffage = cls.valeur;
    session.etape = 'q4_travaux';
    route = { hangup: false, audio_url: audioFile('sofia_q4') };
  } else {
    route = { hangup: false, audio_url: pickReaskClip('q3_chauffage') };
  }
} else if (etape === 'q4_travaux') {
  session.silence_count = 0;
  if (cls.intent === 'ok') {
    session.data.travaux_existants = cls.valeur;
    session.etape = 'q5_consentement';
    route = { hangup: false, audio_url: audioFile('sofia_q5') };
  } else {
    route = { hangup: false, audio_url: pickReaskClip('q4_travaux') };
  }
} else if (etape === 'q5_consentement') {
  session.silence_count = 0;
  if (cls.intent === 'ok' && cls.valeur === 'oui') {
    session.data.consentement_recontact = 'oui';
    session.etape = 'closing';
    route = { hangup: true, qualified: true, statut: 'a_rappeler', audio_url: audioFile('sofia_fin_succes') };
  } else if (cls.intent === 'ok' && cls.valeur === 'non') {
    session.data.consentement_recontact = 'non';
    route = { hangup: true, qualified: true, statut: 'qualifie', audio_url: audioFile('sofia_exit_polite') };
  } else {
    route = { hangup: false, audio_url: pickReaskClip('q5_consentement') };
  }
}

session.qualified = route.qualified;
session.statut = route.statut;
sd.renofacile_sessions[callSid] = session;

const crm_payload = route.hangup ? buildCrmPayload(session, ev, { qualified: route.qualified, statut: route.statut }) : null;

return [{
  json: {
    action: route.hangup ? 'hangup' : 'play_audio',
    call_sid: callSid,
    qualified: route.qualified,
    statut: route.statut,
    audio_url: route.audio_url,
    crm_payload,
    session,
    transcript,
    event: ev,
  },
}];
