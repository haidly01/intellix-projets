const _raw = $input.first().json;
const ev = (_raw && _raw.body && typeof _raw.body === 'object' && !Array.isArray(_raw.body))
  ? _raw.body
  : _raw;
const action = ev.action || '';

if (ev.event_type === 'amd_result' && (ev.amd_result === 'machine' || ev.amd_result === 'fax')) {
  const tel = (ev.to || ev.from || ev.raw?.To || ev.raw?.From || '').toString();
  return [{ json: {
    action: 'hangup', call_sid: ev.call_sid, provider: ev.provider, qualified: false,
    write_sheet: !!tel, statut: 'repondeur', event: ev,
    sheet_payload: tel ? {
      telefono: tel, nombre: '', qualified: false, transcript: 'repondeur',
      recording_url: '', call_sid: ev.call_sid, provider: ev.provider || 'twilio', statut: 'repondeur',
    } : null,
  } }];
}

function buildSheetPayload(session, ev, opts) {
  const telefono = (session?.data?.telephone_final || session?.telephone || ev.to || ev.from || '').toString();
  if (!telefono || !session) return null;
  const qualified = !!(opts && opts.qualified);
  const statut = (opts && opts.statut)
    || (qualified ? 'qualifie' : (session.data.proprietaire ? 'partiel' : 'non_qualifie'));
  return {
    telefono,
    nombre: session.data.nom_contact || 'Prospect',
    qualified,
    transcript: [(session.transcript_log || []).join('\n'), session.etape ? `[etape:${session.etape}]` : ''].filter(Boolean).join('\n'),
    transcripcion: [(session.transcript_log || []).join('\n'), session.etape ? `[etape:${session.etape}]` : ''].filter(Boolean).join('\n'),
    recording_url: ev.recording_url || '',
    call_sid: ev.call_sid || '',
    provider: ev.provider || 'twilio',
    lead_id: $env.CAMPAIGN_ID || 'sofia-test-maroc-juin2026',
    statut,
    campaign_id: $env.CAMPAIGN_ID || 'sofia-test-maroc-juin2026',
    sheet_name: $env.GOOGLE_SHEETS_TAB || 'Leads_Sofia_Test',
    proprietaire: session.data.proprietaire,
    type_logement: session.data.type_logement || '',
    code_postal: session.data.code_postal || '',
    combles: session.data.combles,
    acces_combles: session.data.acces_combles,
    calefaccion: session.data.calefaccion || '',
    creneau_rappel: session.data.creneau_rappel || '',
    duree_sec: session.duree_sec || 0,
  };
}

if (ev.event_type === 'call_ended' || action === 'hangup') {
  const sdEnd = $getWorkflowStaticData('global');
  const session = (sdEnd.sofia_sessions || {})[ev.call_sid];
  const sheet_payload = session ? buildSheetPayload(session, ev, {
    qualified: !!session.data.creneau_rappel,
    statut: session.data.creneau_rappel ? 'qualifie' : (session.data.proprietaire ? 'partiel' : 'non_qualifie'),
  }) : null;
  if (sheet_payload && !sdEnd.sofia_sheet_written) sdEnd.sofia_sheet_written = {};
  const write_sheet = !!sheet_payload && !(sdEnd.sofia_sheet_written || {})[ev.call_sid];
  if (write_sheet) sdEnd.sofia_sheet_written[ev.call_sid] = true;
  return [{ json: {
    action: 'hangup',
    call_sid: ev.call_sid,
    provider: ev.provider,
    write_sheet,
    sheet_payload,
    event: ev,
    session,
  } }];
}

const callSid = ev.call_sid || '';
const sd = $getWorkflowStaticData('global');
if (!sd.sofia_sessions) sd.sofia_sessions = {};
const recDurEnd = parseInt(ev.duration_sec, 10) || 0;
if (ev.event_type === 'recording_ready' && recDurEnd > 25) {
  const sessionEnd = sd.sofia_sessions[callSid];
  const sheet_payload = sessionEnd ? buildSheetPayload(sessionEnd, ev, {
    qualified: !!sessionEnd.data.creneau_rappel,
    statut: sessionEnd.data.creneau_rappel ? 'qualifie' : (sessionEnd.data.proprietaire ? 'partiel' : 'non_qualifie'),
  }) : null;
  if (!sd.sofia_sheet_written) sd.sofia_sheet_written = {};
  const write_sheet = !!sheet_payload && !sd.sofia_sheet_written[callSid];
  if (write_sheet) sd.sofia_sheet_written[callSid] = true;
  return [{ json: {
    action: 'hangup',
    call_sid: callSid,
    provider: ev.provider || 'twilio',
    write_sheet,
    sheet_payload,
    session: sessionEnd,
    event: ev,
  } }];
}
const bucketEarly = ($env.STORAGE_BUCKET_URL || '').replace(/\/$/, '');
const audioFileEarly = (n) => (bucketEarly ? `${bucketEarly}/${n}.mp3` : '');

if (ev.event_type !== 'recording_ready' || !ev.recording_url) {
  const session = sd.sofia_sessions[callSid];
  if (session) {
    session.transcript_log = session.transcript_log || [];
    session.transcript_log.push(`[${session.etape}] (sin grabacion) → reintento`);
    sd.sofia_sessions[callSid] = session;
    return [{ json: {
      action: 'play_audio',
      audio_url: audioFileEarly('sofia_q1_clarif'),
      call_sid: callSid,
      provider: ev.provider || 'twilio',
      qualified: false,
      statut: 'en_cours',
      session,
      event: ev,
    } }];
  }
  return [{ json: { action: 'hangup', error: 'no_recording', event: ev } }];
}

let session = sd.sofia_sessions[callSid];
if (!session) {
  session = {
    etape: 'ouverture', telephone: ev.to || ev.from || '', duree_sec: 0, hors_sujet_count: 0,
    non_owner_count: 0, silence_count: 0,
    soft_limit: parseInt($env.AGENT_SOFT_LIMIT_SEC || '110', 10) || 110,
    data: { proprietaire: null, type_logement: null, code_postal: null, combles: null, acces_combles: null, calefaccion: null, creneau_rappel: null, nom_contact: null, telephone_final: null },
    transcript_log: [],
  };
  sd.sofia_sessions[callSid] = session;
}
if (!session.transcript_log) session.transcript_log = [];
if (session.non_owner_count == null) session.non_owner_count = 0;
if (session.silence_count == null) session.silence_count = 0;

const bucket = ($env.STORAGE_BUCKET_URL || '').replace(/\/$/, '');
const audioFile = (n) => (bucket ? `${bucket}/${n}.mp3` : '');

function stripAgentEcho(transcript) {
  const t = (transcript || '').trim();
  if (!t || t.length < 80) return t;
  const low = t.toLowerCase();
  const markers = [
    '¿es usted propietario',
    'es usted propietario',
    'propietario de una vivienda',
    'le llamo para comprobar',
    'codigo postal',
    'código postal',
    'facilitarme su codigo',
    'facilitarme su código',
    'donde viva',
  ];
  for (const m of markers) {
    const idx = low.lastIndexOf(m);
    if (idx >= 0) {
      const tail = t.slice(idx + m.length).replace(/^[\s,.:;?¿!¡-]+/, '').trim();
      if (tail.length >= 2) return tail;
    }
  }
  return t;
}

const sttBypass = ['1', 'true', 'yes'].includes(($env.SOFIA_STT_BYPASS || '').toLowerCase())
  || !($env.DEEPGRAM_API_KEY || '').trim();
const mockByEtape = {
  ouverture: { intent: 'oui' },
  Q1_clarif: { intent: 'oui' },
  Q2: { intent: 'oui' },
  Q2_appt: { intent: 'oui' },
  Q3: { intent: 'ok', valeur: '28001' },
  Q4: { intent: 'ok', valeur: 'gas' },
  Q4_non: { intent: 'oui' },
  Q5: { intent: 'oui' },
  Q5_non: { intent: 'oui' },
  collect_creneau: { intent: 'ok', valeur: 'mañana por la mañana' },
  collect_nom: { intent: 'ok', valeur: 'Test Usuario' },
  collect_tel: { intent: 'confirme' },
};

let transcript = '';
let classification = { intent: 'silence' };

if (sttBypass) {
  transcript = `[TEST sans Deepgram — ${session.etape}]`;
  classification = mockByEtape[session.etape] || { intent: 'oui' };
} else {
  const recUrl = (ev.recording_url || '').endsWith('.mp3') ? ev.recording_url : (ev.recording_url || '') + '.mp3';
  const odooBase = ($env.ODOO_URL || 'https://intellixcrm.com').replace(/\/$/, '');
  const sttKey = ($env.SOFIA_STT_WEBHOOK_KEY || 'doorway-sofia-stt').trim();
  try {
    const sttRes = await this.helpers.httpRequest({
      method: 'POST',
      url: odooBase + '/api/renov/stt/deepgram',
      headers: {
        'Content-Type': 'application/json',
        'X-Renov-Stt-Key': sttKey,
      },
      body: {
        recording_url: ev.recording_url || recUrl,
        recording_b64: ev.recording_b64 || '',
        language: 'es',
      },
      json: true,
      timeout: 25000,
    });
    if (sttRes && sttRes.error) {
      throw new Error(sttRes.error);
    }
    transcript = stripAgentEcho((sttRes && sttRes.transcript) || '');
  } catch (e) {
    transcript = `[Deepgram error — ${session.etape}: ${(e.message || e).toString().slice(0, 120)}]`;
    classification = { intent: 'silence' };
  }
  const recDurStt = parseInt(ev.duration_sec, 10) || 0;
  if (transcript.startsWith('[Deepgram error') && recDurStt >= 3) {
    session.stt_retry_count = (session.stt_retry_count || 0) + 1;
  }
  const fast = !transcript.startsWith('[Deepgram error')
    ? fastClassifyIntent(session.etape, transcript)
    : null;
  if (fast) {
    classification = fast;
  } else if (!transcript.trim() || transcript.startsWith('[Deepgram error')) {
    classification = { intent: 'silence' };
  } else if (!classification.intent || classification.intent === 'silence') {
    const etape = session.etape;
    const sys = `Classificateur JSON — conversation 100% en ESPAGNOL. Étape: ${etape}. Réponds UNIQUEMENT JSON.
ouverture/Q1_clarif: intent=oui|non|incertain|refus|pas_interesse|do_not_call|hors_sujet|silence
IMPORTANT ouverture: "propietario","propietaria","sí","si","soy propietario","titular","dueño" → oui
IMPORTANT ouverture: "inquilino","arrendatario","no soy propietario" → non (pas "no" seul si phrase incomplète)
Q2/Q5/Q5_non: oui|non|silence
Q2_appt/Q4_non: oui|non|silence
Q3: {intent:ok,valeur:CP} ou {intent:inconnu}
Q4: {intent:ok,valeur:gas|gasoleo|electricidad} ou inconnu|silence
collect_creneau: {intent:ok,valeur:...}
collect_nom: {intent:ok,valeur:nom}
collect_tel: confirme ou {intent:nouveau,valeur:num}`;
    const cl = await this.helpers.httpRequest({
      method: 'POST',
      url: 'https://api.anthropic.com/v1/messages',
      headers: { 'x-api-key': $env.ANTHROPIC_API_KEY, 'anthropic-version': '2023-06-01', 'Content-Type': 'application/json' },
      body: { model: 'claude-3-5-haiku-20241022', max_tokens: 40, system: sys, messages: [{ role: 'user', content: `Transcription: "${transcript}"` }] },
      json: true,
      timeout: 12000,
    });
    try {
      const txt = (cl.content && cl.content[0] && cl.content[0].text) || '{}';
      const m = txt.match(/\{[\s\S]*\}/);
      classification = JSON.parse(m ? m[0] : txt);
    } catch (e) {
      classification = mockByEtape[session.etape] || { intent: 'oui' };
    }
    const fast2 = fastClassifyIntent(session.etape, transcript);
    if (fast2) classification = fast2;
  }
}

let intent = classification.intent || 'silence';
const valeur = classification.valeur || '';
const etape = session.etape;
const transcriptNorm = (transcript || '').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '').trim();

const ownerOverride = fastClassifyIntent(etape, transcript);
if (intent === 'non' && ownerOverride && ownerOverride.intent === 'oui') {
  intent = 'oui';
}
if ((intent === 'silence' || intent === 'incertain' || intent === 'hors_sujet') && ownerOverride && ownerOverride.intent === 'oui') {
  intent = 'oui';
}
const recDur = parseInt(ev.duration_sec, 10) || 0;
if (recDur > 0 && recDur < 2 && !transcript.trim()) {
  intent = 'silence';
}
const explicitTenant = /\b(no soy|no soy propietari|inquilino|arrendatari|alquil|no es mio|no es mia|no es de mi)\b/.test(transcriptNorm);
const bareNo = /^(no|nop)$/.test(transcriptNorm);
const partialOwner = /\bpropiet/i.test(transcriptNorm);
if ((etape === 'ouverture' || etape === 'Q1_clarif') && partialOwner && intent !== 'oui') {
  intent = 'oui';
}
if ((etape === 'ouverture' || etape === 'Q1_clarif') && intent === 'non' && !explicitTenant) {
  intent = bareNo ? 'incertain' : (transcriptNorm ? 'incertain' : 'silence');
}

session.transcript_log.push(
  `[${etape}] ${transcript || '(silencio)'} → ${intent}${valeur ? ' / ' + valeur : ''}`
);
session.duree_sec += Math.max(4, parseInt(ev.duration_sec, 10) || 6);
let route = { next: 'retry', hangup: false, qualified: false };
if (session.duree_sec >= session.soft_limit) route = { next: 'exit_timeout', audioUrl: audioFile('sofia_exit_timeout'), hangup: true };
else if (intent === 'hors_sujet') {
  session.hors_sujet_count += 1;
  route = session.hors_sujet_count >= 3
    ? { next: 'exit_polite', audioUrl: audioFile('sofia_exit_polite'), hangup: true }
    : { next: 'fallback', audioUrl: audioFile('sofia_fallback'), hangup: false };
} else if (intent === 'pas_interesse' || intent === 'refus') route = { next: 'exit_polite', audioUrl: audioFile('sofia_exit_polite'), hangup: true };
else if (intent === 'do_not_call') route = { next: 'exit_dnc', audioUrl: audioFile('sofia_exit_dnc'), hangup: true };
else if (intent === 'silence') {
  session.silence_count += 1;
  const retryAudio = (etape === 'ouverture' || etape === 'Q1_clarif')
    ? audioFile('sofia_q1_clarif')
    : (audioFile(`sofia_${etape}`) || audioFile('sofia_fallback'));
  if (etape === 'ouverture') session.etape = 'Q1_clarif';
  route = { next: 'retry', audioUrl: retryAudio, hangup: false };
}
else {
  session.hors_sujet_count = 0;
  session.silence_count = 0;
  if (etape === 'ouverture') {
    if (intent === 'oui') { session.data.proprietaire = true; session.etape = 'Q2'; route = { next: 'play', audioUrl: audioFile('sofia_q2'), hangup: false }; }
    else if (intent === 'non') {
      session.non_owner_count += 1;
      session.etape = 'Q1_clarif';
      route = { next: 'play', audioUrl: audioFile('sofia_q1_clarif'), hangup: false };
    }
    else if (intent === 'incertain') { session.etape = 'Q1_clarif'; route = { next: 'play', audioUrl: audioFile('sofia_q1_clarif'), hangup: false }; }
    else { session.etape = 'Q1_clarif'; route = { next: 'play', audioUrl: audioFile('sofia_q1_clarif'), hangup: false }; }
  } else if (etape === 'Q1_clarif') {
    if (intent === 'oui') { session.data.proprietaire = true; session.etape = 'Q2'; route = { next: 'play', audioUrl: audioFile('sofia_q2'), hangup: false }; }
    else if (intent === 'non') {
      session.non_owner_count += 1;
      if (session.non_owner_count >= 2 && (explicitTenant || bareNo)) {
        route = { next: 'exit_non_proprio', audioUrl: audioFile('sofia_exit_non_proprio'), hangup: true };
      } else {
        route = { next: 'retry', audioUrl: audioFile('sofia_q1_clarif'), hangup: false };
      }
    }
    else route = { next: 'retry', audioUrl: audioFile('sofia_q1_clarif'), hangup: false };
  } else if (etape === 'Q2') {
    if (intent === 'oui') { session.data.combles = true; session.etape = 'Q3'; route = { next: 'play', audioUrl: audioFile('sofia_q3'), hangup: false }; }
    else if (intent === 'non') { session.data.combles = false; session.etape = 'Q3'; route = { next: 'play', audioUrl: audioFile('sofia_q3'), hangup: false }; }
    else route = { next: 'retry', audioUrl: audioFile('sofia_q2'), hangup: false };
  } else if (etape === 'Q2_appt') {
    if (intent === 'oui') { session.etape = 'collect_creneau'; route = { next: 'play', audioUrl: audioFile('sofia_conclusion'), hangup: false }; }
    else route = { next: 'exit_polite', audioUrl: audioFile('sofia_exit_polite'), hangup: true };
  } else if (etape === 'Q3') {
    if (intent === 'ok') {
      session.data.code_postal = valeur || extractPostalCode(transcriptNorm) || transcript.slice(0, 12);
      session.etape = 'Q4';
      route = { next: 'play', audioUrl: audioFile('sofia_q4'), hangup: false };
    } else if (intent === 'inconnu') {
      session.data.code_postal = 'inconnu';
      session.etape = 'Q4';
      route = { next: 'play', audioUrl: audioFile('sofia_q4'), hangup: false };
    } else {
      session.q3_retry = (session.q3_retry || 0) + 1;
      if (session.q3_retry >= 3) {
        session.data.code_postal = 'inconnu';
        session.etape = 'Q4';
        route = { next: 'play', audioUrl: audioFile('sofia_q4'), hangup: false };
      } else {
        const retryAudio = session.q3_retry >= 2
          ? audioFile('sofia_q3_noknow')
          : (audioFile('sofia_q3_repeat') || audioFile('sofia_q3'));
        route = { next: 'retry', audioUrl: retryAudio, hangup: false };
      }
    }
  } else if (etape === 'Q4') {
    if (intent === 'ok') {
      session.data.calefaccion = valeur || transcript.slice(0, 40);
      session.etape = 'collect_creneau';
      route = { next: 'play', audioUrl: audioFile('sofia_conclusion'), hangup: false };
    } else if (intent === 'inconnu') {
      session.data.calefaccion = 'inconnu';
      session.etape = 'collect_creneau';
      route = { next: 'play', audioUrl: audioFile('sofia_conclusion'), hangup: false };
    } else route = { next: 'retry', audioUrl: audioFile('sofia_q4_non'), hangup: false };
  } else if (etape === 'Q4_non') {
    if (intent === 'ok') {
      session.data.calefaccion = valeur || transcript.slice(0, 40);
      session.etape = 'collect_creneau';
      route = { next: 'play', audioUrl: audioFile('sofia_conclusion'), hangup: false };
    } else route = { next: 'retry', audioUrl: audioFile('sofia_q4_non'), hangup: false };
  } else if (etape === 'Q5') {
    if (intent === 'oui') { session.data.acces_combles = true; session.etape = 'collect_creneau'; route = { next: 'play', audioUrl: audioFile('sofia_conclusion'), hangup: false }; }
    else if (intent === 'non') { session.data.acces_combles = false; session.etape = 'Q5_non'; route = { next: 'play', audioUrl: audioFile('sofia_q5_non'), hangup: false }; }
  } else if (etape === 'Q5_non') {
    if (intent === 'oui') { session.etape = 'collect_creneau'; route = { next: 'play', audioUrl: audioFile('sofia_conclusion'), hangup: false }; }
    else route = { next: 'exit_polite', audioUrl: audioFile('sofia_exit_polite'), hangup: true };
  } else if (etape === 'collect_creneau' && intent === 'ok') {
    session.data.creneau_rappel = valeur; session.etape = 'collect_nom'; route = { next: 'play', audioUrl: audioFile('sofia_collect_nom'), hangup: false };
  } else if (etape === 'collect_nom' && intent === 'ok') {
    session.data.nom_contact = valeur; session.etape = 'collect_tel'; route = { next: 'play', audioUrl: audioFile('sofia_collect_tel'), hangup: false };
  } else if (etape === 'collect_tel') {
    if (intent === 'confirme') { session.data.telephone_final = session.telephone; session.etape = 'fin_succes'; route = { next: 'play', audioUrl: audioFile('sofia_fin_succes'), hangup: true, qualified: true }; }
    else if (intent === 'nouveau') { session.data.telephone_final = valeur || session.telephone; session.etape = 'fin_succes'; route = { next: 'play', audioUrl: audioFile('sofia_fin_succes'), hangup: true, qualified: true }; }
  }
}

let audio_url = route.audioUrl || '';
if (!audio_url && !route.hangup) {
  audio_url = audioFile('sofia_fallback');
}

const statut = route.qualified ? 'qualifie' : (route.next === 'exit_non_proprio' ? 'non_proprietaire' : (route.next === 'exit_dnc' ? 'do_not_call' : (route.hangup ? 'non_qualifie' : 'en_cours')));
sd.sofia_sessions[callSid] = session;
const telefono = session.data.telephone_final || session.telephone || ev.to || ev.from || ev.raw?.To || '';
if (!sd.sofia_sheet_written) sd.sofia_sheet_written = {};
const alreadyWritten = !!sd.sofia_sheet_written[callSid];
const finalStatut = route.qualified ? 'qualifie' : (session.data.proprietaire && route.hangup ? 'partiel' : statut);
const write_sheet = route.hangup && !!telefono && !alreadyWritten && (session.transcript_log || []).length > 0;
const sheet_payload = write_sheet
  ? buildSheetPayload(session, ev, { qualified: !!route.qualified, statut: finalStatut })
  : null;
if (write_sheet) sd.sofia_sheet_written[callSid] = true;
return [{
  json: {
    action: route.hangup ? 'hangup' : 'play_audio',
    audio_url,
    call_sid: callSid,
    provider: ev.provider || 'twilio',
    qualified: !!route.qualified,
    transcript,
    write_sheet,
    statut,
    sheet_payload,
    session,
    event: ev,
  },
}];
