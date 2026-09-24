/**
 * Sofía — moteur conversation (state machine + Claude Haiku + TTS cache).
 * Utilisé dans le workflow n8n « renov-aides — 03 Conversation Engine ».
 */
function bucketUrl() {
  return ($env.STORAGE_BUCKET_URL || '').replace(/\/$/, '');
}

function getSession(callSid) {
  const sd = $getWorkflowStaticData('global');
  if (!sd.sofia_sessions) sd.sofia_sessions = {};
  return sd.sofia_sessions[callSid] || null;
}

function saveSession(callSid, session) {
  const sd = $getWorkflowStaticData('global');
  if (!sd.sofia_sessions) sd.sofia_sessions = {};
  sd.sofia_sessions[callSid] = session;
}

function initSession(callSid, telephone) {
  const session = {
    etape: 'ouverture',
    telephone: telephone || '',
    duree_sec: 0,
    hors_sujet_count: 0,
    soft_limit: parseInt($env.AGENT_SOFT_LIMIT_SEC || '110', 10) || 110,
    data: {
      proprietaire: null,
      type_logement: null,
      code_postal: null,
      combles: null,
      acces_combles: null,
      creneau_rappel: null,
      nom_contact: null,
      telephone_final: null,
    },
  };
  saveSession(callSid, session);
  return session;
}

function audioFile(name) {
  const b = bucketUrl();
  return b ? `${b}/${name}.mp3` : '';
}

async function classifyIntent(etape, transcript) {
  const system = `Tu es un classificateur de réponses pour un agent vocal outbound en espagnol.
Réponds UNIQUEMENT avec un objet JSON valide, sans texte autour, sans markdown.
Étape actuelle : ${etape}

Q1 (ouverture/proprietaire) → { "intent": "oui"|"non"|"incertain"|"refus"|"pas_interesse"|"do_not_call"|"hors_sujet"|"silence" }
Q1_clarif → { "intent": "oui"|"non"|"incertain"|"refus"|"pas_interesse"|"do_not_call"|"hors_sujet"|"silence" }
Q2 → { "intent": "unifamilial"|"appartement"|"incertain"|"refus"|"hors_sujet"|"silence" }
Q2_appt → { "intent": "oui"|"non"|"refus"|"silence" }
Q3 → { "intent": "ok", "valeur": "<code postal>" } OU { "intent": "inconnu"|"silence" }
Q4 → { "intent": "oui"|"non"|"incertain"|"refus"|"hors_sujet"|"silence" }
Q4_non → { "intent": "oui"|"non"|"silence" }
Q5 → { "intent": "oui"|"non"|"incertain"|"refus"|"hors_sujet"|"silence" }
Q5_non → { "intent": "oui"|"non"|"silence" }
collect_creneau → { "intent": "ok", "valeur": "<créneau>" } OU { "intent": "silence" }
collect_nom → { "intent": "ok", "valeur": "<nom complet>" } OU { "intent": "silence" }
collect_tel → { "intent": "confirme" } OU { "intent": "nouveau", "valeur": "<numéro>" } OU { "intent": "silence" }

Détection globale : "no me interesa" → pas_interesse ; "no llame más" → do_not_call ; silence → silence`;
  const res = await this.helpers.httpRequest({
    method: 'POST',
    url: 'https://api.anthropic.com/v1/messages',
    headers: {
      'x-api-key': $env.ANTHROPIC_API_KEY,
      'anthropic-version': '2023-06-01',
      'Content-Type': 'application/json',
    },
    body: {
      model: 'claude-3-5-haiku-20241022',
      max_tokens: 120,
      system,
      messages: [{ role: 'user', content: `Transcription : "${transcript || ''}"` }],
    },
    json: true,
  });
  const text = (res.content && res.content[0] && res.content[0].text) || '{}';
  const m = text.match(/\{[\s\S]*\}/);
  try {
    return JSON.parse(m ? m[0] : text);
  } catch (e) {
    return { intent: 'silence' };
  }
}

function routeTransition(session, intent, valeur) {
  const B = bucketUrl();
  session.duree_sec += 18;
  if (session.duree_sec >= session.soft_limit) {
    return { next: 'exit_timeout', audioUrl: audioFile('sofia_exit_timeout'), hangup: true };
  }
  if (intent === 'hors_sujet') {
    session.hors_sujet_count += 1;
    if (session.hors_sujet_count >= 3) {
      return { next: 'exit_polite', audioUrl: audioFile('sofia_exit_polite'), hangup: true };
    }
    return { next: 'fallback', audioUrl: audioFile('sofia_fallback'), hangup: false, retryEtape: session.etape };
  }
  if (intent === 'pas_interesse' || intent === 'refus') {
    return { next: 'exit_polite', audioUrl: audioFile('sofia_exit_polite'), hangup: true };
  }
  if (intent === 'do_not_call') {
    return { next: 'exit_dnc', audioUrl: audioFile('sofia_exit_dnc'), hangup: true };
  }
  if (intent === 'silence') {
    return { next: 'retry', audioUrl: audioFile(`sofia_${session.etape}`) || audioFile('sofia_fallback'), hangup: false };
  }
  session.hors_sujet_count = 0;

  const etape = session.etape;
  if (etape === 'ouverture') {
    if (intent === 'oui') {
      session.data.proprietaire = true;
      session.etape = 'Q2';
      return { next: 'play', audioUrl: audioFile('sofia_q2'), hangup: false };
    }
    if (intent === 'non') {
      return { next: 'exit_non_proprio', audioUrl: audioFile('sofia_exit_non_proprio'), hangup: true };
    }
    if (intent === 'incertain') {
      session.etape = 'Q1_clarif';
      return { next: 'play', audioUrl: audioFile('sofia_q1_clarif'), hangup: false };
    }
  }
  if (etape === 'Q1_clarif') {
    if (intent === 'oui') {
      session.data.proprietaire = true;
      session.etape = 'Q2';
      return { next: 'play', audioUrl: audioFile('sofia_q2'), hangup: false };
    }
    return { next: 'exit_non_proprio', audioUrl: audioFile('sofia_exit_non_proprio'), hangup: true };
  }
  if (etape === 'Q2') {
    if (intent === 'unifamilial') {
      session.data.type_logement = 'unifamilial';
      session.etape = 'Q3';
      return { next: 'play', audioUrl: audioFile('sofia_q3'), hangup: false };
    }
    if (intent === 'appartement') {
      session.data.type_logement = 'appartement';
      session.etape = 'Q2_appt';
      return { next: 'play', audioUrl: audioFile('sofia_q2_appt'), hangup: false };
    }
  }
  if (etape === 'Q2_appt') {
    if (intent === 'oui') {
      session.etape = 'collect_creneau';
      return { next: 'play', audioUrl: audioFile('sofia_conclusion'), hangup: false };
    }
    return { next: 'exit_polite', audioUrl: audioFile('sofia_exit_polite'), hangup: true };
  }
  if (etape === 'Q3') {
    if (intent === 'ok') {
      session.data.code_postal = valeur || '';
      session.etape = 'Q4';
      return { next: 'play', audioUrl: audioFile('sofia_q4'), hangup: false };
    }
    if (intent === 'inconnu') {
      session.data.code_postal = 'inconnu';
      session.etape = 'Q4';
      return { next: 'play_chain', audioUrls: [audioFile('sofia_q3_noknow'), audioFile('sofia_q4')], hangup: false };
    }
  }
  if (etape === 'Q4') {
    if (intent === 'oui') {
      session.data.combles = true;
      session.etape = 'Q5';
      return { next: 'play', audioUrl: audioFile('sofia_q5'), hangup: false };
    }
    if (intent === 'non') {
      session.data.combles = false;
      session.etape = 'Q4_non';
      return { next: 'play', audioUrl: audioFile('sofia_q4_non'), hangup: false };
    }
  }
  if (etape === 'Q4_non') {
    if (intent === 'oui') {
      session.etape = 'collect_creneau';
      return { next: 'play', audioUrl: audioFile('sofia_conclusion'), hangup: false };
    }
    return { next: 'exit_polite', audioUrl: audioFile('sofia_exit_polite'), hangup: true };
  }
  if (etape === 'Q5') {
    if (intent === 'oui') {
      session.data.acces_combles = true;
      session.etape = 'collect_creneau';
      return { next: 'play', audioUrl: audioFile('sofia_conclusion'), hangup: false };
    }
    if (intent === 'non') {
      session.data.acces_combles = false;
      session.etape = 'Q5_non';
      return { next: 'play', audioUrl: audioFile('sofia_q5_non'), hangup: false };
    }
  }
  if (etape === 'Q5_non') {
    if (intent === 'oui') {
      session.etape = 'collect_creneau';
      return { next: 'play', audioUrl: audioFile('sofia_conclusion'), hangup: false };
    }
    return { next: 'exit_polite', audioUrl: audioFile('sofia_exit_polite'), hangup: true };
  }
  if (etape === 'collect_creneau' && intent === 'ok') {
    session.data.creneau_rappel = valeur || '';
    session.etape = 'collect_nom';
    return { next: 'dynamic', template: 'collect_nom', hangup: false };
  }
  if (etape === 'collect_nom' && intent === 'ok') {
    session.data.nom_contact = valeur || '';
    session.etape = 'collect_tel';
    return { next: 'dynamic', template: 'collect_tel', hangup: false };
  }
  if (etape === 'collect_tel') {
    if (intent === 'confirme') {
      session.data.telephone_final = session.telephone;
      session.etape = 'fin_succes';
      return { next: 'dynamic', template: 'fin_succes', hangup: true, qualified: true };
    }
    if (intent === 'nouveau') {
      session.data.telephone_final = valeur || session.telephone;
      session.etape = 'fin_succes';
      return { next: 'dynamic', template: 'fin_succes', hangup: true, qualified: true };
    }
  }
  return { next: 'retry', audioUrl: audioFile('sofia_fallback'), hangup: false };
}

async function dynamicTts(session, template) {
  const templates = {
    collect_nom: `Perfecto. Le contactaremos ${session.data.creneau_rappel || 'pronto'}. ¿Puede confirmarme su nombre completo para que el asesor prepare su ficha?`,
    collect_tel: `Perfecto, ${session.data.nom_contact || ''}. ¿El número en el que le llamamos ahora es el mejor para usted?`,
    fin_succes: `Perfecto. Queda registrado. Recibirá la llamada de nuestro asesor ${session.data.creneau_rappel || 'pronto'}. Muchas gracias por su tiempo, ${session.data.nom_contact || ''}. ¡Que tenga un buen día!`,
  };
  const text = templates[template] || 'Gracias.';
  const audio = await this.helpers.httpRequest({
    method: 'POST',
    url: `https://api.elevenlabs.io/v1/text-to-speech/${$env.ELEVENLABS_VOICE_ID}`,
    headers: {
      'xi-api-key': $env.ELEVENLABS_API_KEY,
      'Content-Type': 'application/json',
      Accept: 'audio/mpeg',
    },
    body: { text, model_id: 'eleven_multilingual_v2', voice_settings: { stability: 0.75, similarity_boost: 0.85 } },
    json: false,
    encoding: 'arraybuffer',
  });
  return 'data:audio/mpeg;base64,' + Buffer.from(audio).toString('base64');
}

function statutFromSession(session, route) {
  if (route.next === 'exit_non_proprio') return 'non_proprietaire';
  if (route.next === 'exit_dnc') return 'do_not_call';
  if (route.next === 'exit_polite' || route.next === 'exit_timeout') return 'non_qualifie';
  if (route.qualified || session.etape === 'fin_succes') return 'qualifie';
  if (session.data.proprietaire && session.data.type_logement === 'appartement') return 'qualifie_partiel';
  return 'en_cours';
}

module.exports = {
  bucketUrl,
  getSession,
  saveSession,
  initSession,
  audioFile,
  classifyIntent,
  routeTransition,
  dynamicTts,
  statutFromSession,
};
