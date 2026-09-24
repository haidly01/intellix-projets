// NB : la table des clips `A` (URLs des répliques) est désormais construite
// PAR VARIANTE, une fois le call_sid connu (voir buildClips / leaVariant dans
// lea_qc_config.js). On garde volontairement le nom de variable `A` pour que la
// variante A (production) reste strictement identique au comportement actuel.

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
    intention_vente: d.intention_vente || '',
    besoin: d.besoin || '',
    proprietaire: !!d.proprietaire,
    preference_rappel: d.dispo_rappel || '',
    futur_3mois: !!d.futur_3mois,
    transcript: (session.transcript_log || []).join('\n'),
    recording_url: ev.recording_url || '',
    duration_sec: Math.max(parseInt(session.duree_sec, 10) || 0, parseInt(ev.duration_sec, 10) || 0),
    campaign: $env.VICIDIAL_CAMPAIGN || 'DW_QCB2C',
    variant: session.variant || leaVariant(ev.call_sid || ''),
  };
}

if (ev.event_type === 'call_ended' || ev.action === 'hangup') {
  const sd = $getWorkflowStaticData('global');
  const session = (sd.lea_qc_sessions || {})[ev.call_sid];
  const crm_payload = session ? buildCrmPayload(session, ev, {
    qualified: session.crm_action === 'tag_lead_qualifie',
    statut: session.crm_action || 'non_qualifie',
  }) : null;
  return [{ json: { action: 'hangup', call_sid: ev.call_sid, crm_payload, session, event: ev } }];
}

const callSid = ev.call_sid || '';
const sd = $getWorkflowStaticData('global');
if (!sd.lea_qc_sessions) sd.lea_qc_sessions = {};
let session = sd.lea_qc_sessions[callSid];

if (!session) {
  session = {
    etape: 'GREETING',
    variant: leaVariant(callSid), // A/B 50/50 déterministe (partagé avec Odoo)
    telephone: ev.to || ev.from || '',
    prenom: ev.prenom || ev.nombre || '',
    duree_sec: 0,
    turn_count: 0,
    silence_count: 0,
    soft_limit: parseInt($env.AGENT_SOFT_LIMIT_SEC || '90', 10),
    crm_action: null,
    pi_soft_attempt: false,
    data: {
      prenom: ev.prenom || ev.nombre || '',
      proprietaire: null,
      besoin: null,
      type_projet: null,
      intention_vente: null,
      dispo_rappel: null,
      futur_3mois: false,
      telephone: ev.to || ev.from || '',
    },
    transcript_log: [],
  };
  sd.lea_qc_sessions[callSid] = session;
}

// Sécurité : sessions pré-existantes (avant déploiement A/B) → assigner le bras.
if (!session.variant) session.variant = leaVariant(callSid);

// Table des clips résolue PAR VARIANTE (A = production inchangée, B = clips B).
const A = buildClips(session.variant);

if (ev.event_type === 'call_start' || (!ev.recording_url && session.etape === 'GREETING' && !ev.event_type)) {
  return [{ json: {
    action: 'play_audio', audio_url: A.ouverture, call_sid: callSid,
    qualified: false, statut: 'en_cours', variant: session.variant, session, event: ev,
  } }];
}

// On NE raccroche que s'il n'y a vraiment RIEN d'exploitable. Un tour avec un
// transcript (STT fait par l'AGI) ou un recording_b64 doit CONTINUER même si
// l'archivage HTTPS (recording_url) a échoué — sinon un échec d'upload ponctuel
// coupait l'appel (« no_recording ») alors que la parole a bien été captée.
if (ev.event_type !== 'recording_ready' || (!ev.recording_url && !ev.transcript && !ev.recording_b64)) {
  return [{ json: { action: 'hangup', error: 'no_recording', event: ev } }];
}

// L'AGI fait déjà le STT en local (sur le fichier WAV) et nous transmet le
// transcript dans le payload. On le PRIVILÉGIE : c'est fiable et ça évite de
// re-télécharger recording_url côté Odoo (qui peut renvoyer un transcript VIDE
// — ex. 403 Cloudflare sur l'URL HTTPS — et faussement déclencher un "silence"
// qui raccrochait l'appel dès la 2e réponse). On ne refait le STT que si l'AGI
// n'a rien fourni, et en réutilisant recording_b64 (pas l'URL) quand possible.
let transcript = (ev.transcript || '').toString().trim();
let sttFailed = false;
async function fetchStt(body) {
  const odooBase = ($env.ODOO_URL || 'http://127.0.0.1:8069').replace(/\/$/, '');
  const sttRes = await this.helpers.httpRequest({
    method: 'POST',
    url: odooBase + '/api/renov/stt/deepgram',
    headers: { 'Content-Type': 'application/json', 'X-Renov-Stt-Key': ($env.SOFIA_STT_WEBHOOK_KEY || 'doorway-sofia-stt') },
    body,
    json: true,
    timeout: 25000,
  });
  return ((sttRes && sttRes.transcript) || '').toString().trim();
}
if (!transcript) {
  const sttBody = ev.recording_b64
    ? { recording_b64: ev.recording_b64, language: 'fr-CA' }
    : ev.recording_url
      ? { recording_url: ev.recording_url, language: 'fr-CA' }
      : null;
  if (sttBody) {
    try {
      transcript = await fetchStt.call(this, sttBody);
      // AGI STT parfois vide alors que l'audio est bon : un 2e essai sur recording_b64
      // évite un faux « silence » au GREETING (ex. « oui » court après fallback).
      if (!transcript && ev.recording_b64 && sttBody.recording_b64) {
        transcript = await fetchStt.call(this, { recording_b64: ev.recording_b64, language: 'fr-CA' });
      }
    } catch (e) {
      transcript = '';
      sttFailed = true;
    }
  }
}

// GREETING : peak audible sans STT (Deepgram vide) → probable « oui » court après ouverture.
if (!transcript && parseFloat(ev.audio_peak || 0) >= 0.3
    && (session.etape === 'GREETING' || session.etape === 'GREETING_CLARIF')) {
  transcript = 'oui';
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

function pickClosing(clips, dispo) {
  const d = (dispo || '').toLowerCase();
  if (/matin/.test(d)) return clips.closing_matin || clips.closing;
  if (/apres|apr[eè]s|midi/.test(d)) return clips.closing_apres_midi || clips.closing;
  if (/soir/.test(d)) return clips.closing_soir || clips.closing;
  return clips.closing;
}

function pickConfirmDispo(clips, dispo) {
  const d = (dispo || '').toLowerCase();
  if (/matin/.test(d)) return clips.confirm_matin || clips.capturer_dispo;
  if (/apres|apr[eè]s|midi/.test(d)) return clips.confirm_apres_midi || clips.capturer_dispo;
  if (/soir/.test(d)) return clips.confirm_soir || clips.capturer_dispo;
  return clips.confirm_matin || clips.capturer_dispo;
}

function pickReaskClip(etape, clips) {
  switch (etape) {
    case 'CAPTURER_DISPO':
    case 'CAPTURER_DISPO_CONFIRM':
      return clips.redemand_dispo || clips.capturer_dispo;
    case 'QUESTION_BESOIN':
      return clips.question_besoin;
    case 'QUESTION_PROJET':
      return clips.question_projet;
    case 'QUESTION_IMMO':
      return clips.question_immo;
    case 'SONDER_FUTUR':
      return clips.sonder_futur;
    case 'GREETING':
    case 'GREETING_CLARIF':
      return clips.ouverture || clips.fallback;
    default:
      return clips.fallback;
  }
}

function detectGreetingIntent(text) {
  if (/(pas le temps|pas le temps la|je n ai pas le temps|occupe|trop occupe|pas disponible|pas le bon moment|periode chargee|trop occupes)/i.test(text)) {
    return { intent: 'pas_le_temps' };
  }
  if (/(pas interesse|ca m interesse pas|non merci|laissez moi|au revoir)/i.test(text)) {
    return { intent: 'pas_interesse' };
  }
  if (/(locataire|je suis locataire|en location|je loue|pas ma maison|pas proprietaire)/i.test(text) && !/oui|ouais|proprietaire|c est ma maison|c est moi/i.test(text)) {
    return { intent: 'locataire' };
  }
  const gVendre = /(vendre|vente|mettre en vente|revendre|revente|me d[ée]barrasser de (ma|la) maison|liquider)/i;
  const gReno = /(r[ée]nov|r[ée]no|travaux|cuisine|salle\s+de\s+bain|toiture|sous-?\s*sol|agrandissement|fen[êe]tre|fenetre|refaire|r[ée]nover)/i;
  if (gVendre.test(text) && gReno.test(text)) return { intent: 'proprietaire', besoin: 'les_deux' };
  if (gVendre.test(text)) return { intent: 'proprietaire', besoin: 'immo' };
  if (gReno.test(text)) return { intent: 'proprietaire', besoin: 'reno' };
  if (/(chalet|residence secondaire|maison de campagne|chalet de lac)/i.test(text)) {
    return { intent: 'proprietaire' };
  }
  // Propriétaire explicite — STT sans accents (normTranscript) : « je suis proprietaire », « maison est a moi », etc.
  if (/(je suis (le )?proprietaire|proprietaire de ma maison|proprietaire de chez moi|maison est a moi|c est ma maison|c est chez moi|chez moi c est|ma maison|\bowner\b|i am the owner|homeowner|i own (this|my|the) (house|home))/i.test(text)) {
    return { intent: 'proprietaire' };
  }
  if (/(^\s*(allo|allô|bonjour|salut|ouin|hey|hello|hi)\b|oui\s+(allo|allô|bonjour)|^(ouin|ouais)\s*$)/i.test(text)) {
    return { intent: 'proprietaire' };
  }
  if (/(proprietaire|proprietaires|\boui\b|ouais|ouaip|yes|yeah|yep|c est ma maison|c est moi|speaking|allo|allô)/i.test(text)) {
    return { intent: 'proprietaire' };
  }
  if (text.length <= 4 && /^(oui|oua|ouin|yes|yep|ok)$/i.test(text.trim())) {
    return { intent: 'proprietaire' };
  }
  return null;
}

function detectDispoIntent(text) {
  if (/(matin|avant.?midi|tot le matin|le matin|t[ôo]t)/i.test(text)) {
    return { intent: 'dispo', valeur: 'matin' };
  }
  if (/(apres.?midi|apr[eè]s.?midi|l apres midi|apres-midi|en milieu de journ[ée]e)/i.test(text)) {
    return { intent: 'dispo', valeur: 'après-midi' };
  }
  if (/(soir|soir[eé]e|fin de journ[ée]e|le soir|apres 5|apres 17|apres 18|tard)/i.test(text)) {
    return { intent: 'dispo', valeur: 'soir' };
  }
  if (/(fin de semaine|week.?end|samedi|dimanche|le weekend)/i.test(text)) {
    return { intent: 'dispo', valeur: 'fin de semaine' };
  }
  if (
    /(disponible|libre|peu importe|n importe|quand vous voulez|comme vous voulez|a votre convenance|ca me va|d accord)/i.test(text) &&
    !/(pas disponible|pas libre|indisponible|je ne suis pas disponible)/i.test(text)
  ) {
    return { intent: 'dispo', valeur: text.slice(0, 30) };
  }
  if (/\d{1,2}\s*h/i.test(text)) return { intent: 'dispo', valeur: text.slice(0, 30) };
  return null;
}

function detectIntent(step, text) {
  if (!text.trim()) return { intent: 'silence' };
  if (/(stop|retir|ne plus|pas interesse d etre contact|do not call|dnc|arretez|retirez mon numero|liste noire|trop d appels|ne plus appeler)/i.test(text)) {
    return { intent: 'dnc' };
  }
  const isDispoStep = step === 'CAPTURER_DISPO' || step === 'CAPTURER_DISPO_CONFIRM';
  if (isDispoStep) {
    const dispoHit = detectDispoIntent(text);
    if (dispoHit) return dispoHit;
    if (step === 'CAPTURER_DISPO_CONFIRM' && /(oui|ok|correct|confirme|parfait|c est ca|c est bien)/i.test(text)) {
      return { intent: 'confirme' };
    }
  }
  // GREETING : propriétaire / oui AVANT objections (évite soft pas_interesse sur affirmatif).
  if (step === 'GREETING' || step === 'GREETING_CLARIF') {
    const greetingHit = detectGreetingIntent(text);
    if (greetingHit) return greetingHit;
  }
  if (/(rappeler plus tard|rappellez plus tard|dans quelques mois|une autre fois|pas maintenant|rappeler un autre jour)/i.test(text)) {
    return { intent: 'rappeler_plus_tard' };
  }
  if (!isDispoStep && /(pas le temps|pas le temps la|je n ai pas le temps|occupe|trop occupe|pas disponible|pas le bon moment|periode chargee|trop occupes)/i.test(text)) {
    return { intent: 'pas_le_temps' };
  }
  if (/(pas interesse|ca m interesse pas|non merci|laissez moi|au revoir)/i.test(text)) {
    return { intent: 'pas_interesse' };
  }
  if (/(c est quoi|c est qui|comment vous avez|comment vous a eu|vous appelez de ou|qui etes vous|soumission entrepreneurs|soumission entrepreneur)/i.test(text)) {
    return { intent: 'qui_etes_vous' };
  }
  if (/(arnaque|scam|pas confiance|je fais pas confiance|appels froids|phishing|frauduleux)/i.test(text)) {
    return { intent: 'arnaque' };
  }
  if (/(deja un entrepreneur|j ai un entrepreneur|j ai mon entrepreneur|mon contracteur|mon beau frere fait ca)/i.test(text)) {
    return { intent: 'objection_entrepreneur' };
  }
  if (step === 'GREETING' || step === 'GREETING_CLARIF') {
    return { intent: 'incertain' };
  }
  if (step === 'QUESTION_BESOIN') {
    if (/(non|pas vraiment|rien|aucun|pas besoin|rien pour l instant|pas de projet|maison est correcte|maison parfaite|rien a faire|vient de finir|on a fini les travaux|on vient de renover|tout est correct|on est bien)/i.test(text)) {
      return { intent: 'pas_besoin' };
    }
    const veutVendre = /(vendre|vente|revendre|revente|immobilier|mettre en vente|valeur|[ée]valu|estim|prix de (ma|la) maison|combien (ç|c)a vaut|combien vaut|je veux vendre|j'aimerais vendre|j aimerais vendre)/i;
    const veutReno = /(r[ée]nov|r[ée]no|travaux|cuisine|salle\s+de\s+bain|toiture|sous-?\s*sol|agrandissement|fen[êe]tre|fenetre|r[ée]nover|refaire|projet)/i;
    // Post-normTranscript : « un peu les 2 », « les deux », « peut etre les deux », etc.
    const lesDeux = /(?:les deux|les[\s-]?2|un peu les(?: deux| 2)?|un peu des|peut etre les|peut.?etre les|autant|\bdeux\b|\b2\b)/i;
    if (lesDeux.test(text) || (veutReno.test(text) && veutVendre.test(text))) {
      return { intent: 'les_deux' };
    }
    if (veutVendre.test(text)) return { intent: 'immo' };
    if (veutReno.test(text)) return { intent: 'reno' };
    return { intent: 'incertain' };
  }
  if (step === 'QUESTION_PROJET' || step === 'SONDER_FUTUR') {
    const projets = /(cuisine|salle\s+de\s+bain|toiture|fenetre|fenetres|sou\s*sol|sous\s*sol|soussol|agrandissement|isolation|plancher|terrasse|patio|garage|peinture|electricite|plomberie|renovation|travaux|salon|chambre|toit|fondation|revetement)/i;
    if (projets.test(text)) return { intent: 'projet', valeur: text.slice(0, 80) };
    if (/(pas vraiment|pas pour l'instant|pas s[ûu]r|non)/i.test(text)) return { intent: 'pas_projet' };
    if (/(oui|peut-être|peut être|un peu|quelque chose)/i.test(text)) return { intent: 'projet', valeur: text.slice(0, 80) };
    // STT renvoie souvent « sous sol » sans tiret — toute réponse audible ≥3 car.
    // compte comme description de projet plutôt que silence (évite le timeout « occupé »).
    if (text.trim().length >= 3) return { intent: 'projet', valeur: text.slice(0, 80) };
    return { intent: 'incertain' };
  }
  if (step === 'QUESTION_IMMO') {
    // « 3 mois », « dans 6 mois », « bientôt » = réponse affirmative au délai de vente.
    if (/(oui|peut-être|peut être|d'ici|dans l'année|prochains mois|bient[oô]t|\d+\s*mois|12 mois|24 mois|6 mois|18 mois)/i.test(text)) {
      return { intent: 'vente_oui', valeur: text.slice(0, 80) };
    }
    if (/(non|pas pour l'instant|pas vraiment)/i.test(text)) return { intent: 'vente_non' };
    // Toute réponse audible ≥3 car. sur le délai de vente → oui (évite fallback/silence).
    if (text.trim().length >= 3) return { intent: 'vente_oui', valeur: text.slice(0, 80) };
  }
  if (isDispoStep) {
    return text.trim() ? { intent: 'incertain' } : { intent: 'silence' };
  }
  // Parole audible non reconnue ≠ silence STT : on redemande sans compter
  // vers le timeout « vous êtes occupé » (3 « silences » consécutifs).
  return text.trim() ? { intent: 'incertain' } : { intent: 'silence' };
}

const classification = detectIntent(etape, t);
const intent = classification.intent || 'silence';
const valeur = classification.valeur || '';
const besoinHint = classification.besoin || '';
session.transcript_log.push(`[${etape}] ${transcript || '(silence)'} → ${intent}${valeur ? '/' + valeur : ''}`);
session.duree_sec += Math.max(4, parseInt(ev.duration_sec, 10) || 6);

let route = { hangup: false, qualified: false, audioUrl: A.fallback, crm_action: null };

if (session.duree_sec >= session.soft_limit || session.turn_count > 8) {
  route = { hangup: true, audioUrl: A.timeout, crm_action: null };
} else if (intent === 'dnc') {
  route = { hangup: true, audioUrl: A.exit_dnc, crm_action: 'tag_dnc' };
} else if (intent === 'rappeler_plus_tard') {
  route = { hangup: true, audioUrl: A.rappeler_plus_tard, crm_action: 'tag_rappeler_plus_tard' };
} else if (intent === 'pas_interesse') {
  if (!session.pi_soft_attempt) {
    session.pi_soft_attempt = true;
    route = { hangup: false, audioUrl: A.objection_pi_soft, crm_action: null };
  } else {
    route = { hangup: true, audioUrl: A.exit_pi, crm_action: 'tag_pas_interesse' };
  }
} else if (intent === 'pas_le_temps') {
  route = { hangup: true, audioUrl: A.exit_pas_temps, crm_action: 'tag_rappeler' };
} else if (intent === 'qui_etes_vous') {
  route = { hangup: false, audioUrl: A.qui_etes_vous, crm_action: null };
} else if (intent === 'arnaque') {
  route = { hangup: true, audioUrl: A.arnaque_sms, crm_action: 'tag_rappeler' };
} else if (intent === 'objection_entrepreneur') {
  route = { hangup: false, audioUrl: A.objection, crm_action: null };
} else if (intent === 'silence') {
  // Silence / STT vide : on RE-DEMANDE (fallback) au lieu de raccrocher tôt.
  // GREETING : seuil 4 (STT court « oui » plus tolérant) ; autres étapes : 3.
  session.silence_count += 1;
  const silenceLimit = (etape === 'GREETING' || etape === 'GREETING_CLARIF') ? 4 : 3;
  if (session.silence_count >= silenceLimit) {
    route = { hangup: true, audioUrl: A.timeout, crm_action: null };
  } else if (etape === 'GREETING') {
    session.etape = 'GREETING_CLARIF';
    route = { hangup: false, audioUrl: A.fallback };
  } else {
    route = { hangup: false, audioUrl: pickReaskClip(etape, A) };
  }
} else if (intent === 'incertain') {
  // Réponse audible mais non classée : « je n'ai pas bien entendu », sans
  // compter comme silence (sinon « sous sol » / « vendre ma maison » mal matchés
  // déclenchaient « je vois que vous êtes occupé » après 3 tours).
  route = { hangup: false, audioUrl: pickReaskClip(etape, A) };
} else {
  session.silence_count = 0;
  if (etape === 'GREETING' || etape === 'GREETING_CLARIF') {
    if (intent === 'proprietaire') {
      session.data.proprietaire = true;
      // Aiguillage DIRECT si le besoin est déjà exprimé au greeting (corrige le
      // vendeur « je veux vendre ma maison » qui se perdait au fallback). Sinon on
      // pose la question d'orientation habituelle.
      if (besoinHint === 'immo') {
        session.data.besoin = 'immo';
        session.etape = 'QUESTION_IMMO';
        route = { hangup: false, audioUrl: A.question_immo };
      } else if (besoinHint === 'reno' || besoinHint === 'les_deux') {
        session.data.besoin = besoinHint;
        session.etape = 'QUESTION_PROJET';
        route = { hangup: false, audioUrl: A.question_projet };
      } else {
        session.etape = 'QUESTION_BESOIN';
        route = { hangup: false, audioUrl: A.question_besoin };
      }
    } else if (intent === 'locataire') {
      route = { hangup: true, audioUrl: A.exit_loc, crm_action: 'tag_locataire' };
    } else {
      session.etape = 'GREETING_CLARIF';
      route = { hangup: false, audioUrl: pickReaskClip(etape, A) };
    }
  } else if (etape === 'QUESTION_BESOIN') {
    if (intent === 'reno' || intent === 'les_deux') {
      session.data.besoin = intent;
      session.etape = 'QUESTION_PROJET';
      route = { hangup: false, audioUrl: A.question_projet };
    } else if (intent === 'immo') {
      session.data.besoin = 'immo';
      session.etape = 'QUESTION_IMMO';
      route = { hangup: false, audioUrl: A.question_immo };
    } else if (intent === 'pas_besoin') {
      session.etape = 'SONDER_FUTUR';
      route = { hangup: false, audioUrl: A.sonder_futur };
    } else {
      route = { hangup: false, audioUrl: pickReaskClip(etape, A) };
    }
  } else if (etape === 'QUESTION_PROJET') {
    if (intent === 'projet') {
      session.data.type_projet = valeur || transcript.slice(0, 80);
      if (session.data.besoin === 'les_deux') {
        session.etape = 'QUESTION_IMMO';
        route = { hangup: false, audioUrl: A.question_immo };
      } else {
        session.etape = 'CAPTURER_DISPO';
        route = { hangup: false, audioUrl: A.capturer_dispo };
      }
    } else if (intent === 'pas_projet') {
      session.etape = 'SONDER_FUTUR';
      route = { hangup: false, audioUrl: A.sonder_futur };
    }
  } else if (etape === 'QUESTION_IMMO') {
    if (intent === 'vente_oui') {
      session.data.intention_vente = valeur || 'oui';
      session.etape = 'CAPTURER_DISPO';
      route = { hangup: false, audioUrl: A.capturer_dispo };
    } else if (intent === 'vente_non') {
      if (session.data.type_projet) {
        session.etape = 'CAPTURER_DISPO';
        route = { hangup: false, audioUrl: A.capturer_dispo };
      } else {
        route = { hangup: true, audioUrl: A.exit_futur, crm_action: 'tag_pas_projet' };
      }
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
    if (intent === 'dispo') {
      const dispoVal = valeur || session.data.dispo_rappel || 'matin';
      session.data.dispo_rappel = dispoVal;
      // Tour de confirmation avant closing — évite le raccrochage perçu dès
      // « le matin / le soir » sans que le prospect ait entendu la validation.
      session.etape = 'CAPTURER_DISPO_CONFIRM';
      route = { hangup: false, audioUrl: pickConfirmDispo(A, dispoVal) };
    } else {
      route = { hangup: false, audioUrl: A.redemand_dispo || A.capturer_dispo };
    }
  } else if (etape === 'CAPTURER_DISPO_CONFIRM') {
    const dispoVal = session.data.dispo_rappel || valeur || 'matin';
    if (intent === 'confirme' || intent === 'dispo' || /^(oui|ouais|ok|correct|c est ca|c est bien)/.test(t)) {
      session.data.dispo_rappel = dispoVal;
      session.etape = 'CLOSING';
      session.crm_action = 'tag_lead_qualifie';
      route = {
        hangup: true,
        qualified: true,
        audioUrl: pickClosing(A, dispoVal),
        crm_action: 'tag_lead_qualifie',
      };
    } else if (intent === 'vente_non' || /(non|pas)/.test(t)) {
      session.etape = 'CAPTURER_DISPO';
      route = { hangup: false, audioUrl: A.redemand_dispo || A.capturer_dispo };
    } else {
      route = { hangup: false, audioUrl: pickConfirmDispo(A, dispoVal) };
    }
  }
}

session.crm_action = route.crm_action || session.crm_action;
sd.lea_qc_sessions[callSid] = session;

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
    variant: session.variant,
    statut: session.crm_action || 'en_cours',
    session,
    event: ev,
  },
}];
