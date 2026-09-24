/**
 * Léa — Ma Réno Facile (rénovation, fr-FR / français de France)
 * Clone fidèle de lea_qc/lib/lea_qc_config.js — MÊME structure, MÊMES étapes,
 * MÊME algo A/B (FNV-1a partagé avec Odoo). Seuls changent : la marque
 * (« Ma Réno Facile »), le positionnement (rénovation), la langue (fr-FR) et
 * le bucket de clips (lea-fr-tts). La divulgation IA reste EXPLICITE.
 * Répliques fixes — MP3 : LEA_FR_STORAGE_BUCKET_URL/{key}.mp3
 */
const REPLIQUES = {
  lea_ouverture:
    'Bonjour, ici Léa, l\'assistante virtuelle automatisée de Ma Réno Facile. ' +
    'Nous accompagnons les propriétaires dans leurs projets de rénovation de leur logement. ' +
    'J\'ai juste deux petites questions, ça prend moins d\'une minute. ' +
    'Êtes-vous bien propriétaire de votre logement ?',

  lea_exit_locataire:
    'Je comprends, dans ce cas nous ne pourrons pas vous aider pour le moment. Je vous souhaite une bonne journée !',

  lea_question_besoin:
    'Parfait ! Pensez-vous plutôt à des travaux de rénovation — par exemple l\'isolation, ' +
    'le chauffage ou la rénovation d\'une pièce —, à faire estimer la valeur de votre bien, ' +
    'ou peut-être les deux ?',

  lea_question_projet:
    'Très bien ! Quels travaux envisagez-vous — cuisine, salle de bains, isolation, ' +
    'chauffage, fenêtres, toiture, ou autre chose ?',

  lea_question_immo:
    'Souhaitez-vous faire estimer la valeur de votre bien, par exemple après vos travaux, ' +
    'dans les prochains mois ?',

  lea_capturer_dispo:
    'Super, c\'est exactement pour cela que nous sommes là ! ' +
    'Un conseiller Ma Réno Facile vous rappellera pour étudier votre projet en détail. ' +
    'Quel est le meilleur moment pour vous — plutôt le matin, l\'après-midi ou en soirée ?',

  lea_closing:
    'Parfait ! Je confirme, nous vous rappellerons au numéro que nous avons dans votre dossier. ' +
    'Merci pour votre temps et excellente journée !',

  lea_sonder_futur:
    'Je comprends, ce n\'est pas forcément pour tout de suite. ' +
    'Avez-vous un projet de rénovation que vous aimeriez réaliser dans les prochains mois ?',

  lea_exit_futur:
    'Pas de souci. Je note votre dossier et nous reviendrons vers vous quand vous serez prêt. Bonne journée !',

  lea_exit_pas_interesse:
    'Très bien, aucun problème ! Si vous changez d\'avis, Ma Réno Facile reste à votre disposition. Bonne journée !',

  lea_exit_dnc:
    'C\'est noté, nous vous retirons de notre liste d\'appel. Bonne journée !',

  lea_objection_entrepreneur:
    'C\'est une très bonne chose ! Nous pouvons tout de même vous proposer un deuxième avis gratuit pour comparer. ' +
    'Puis-je noter vos coordonnées pour que nous restions en contact ?',

  lea_fallback: 'Désolée, je n\'ai pas bien entendu. Pouvez-vous répéter, s\'il vous plaît ?',
  lea_exit_timeout: 'Je vois que vous êtes occupé, nous vous rappellerons à un autre moment. Bonne journée !',
};

/**
 * ════════════════════════════════════════════════════════════════════════
 *  A/B TEST — VARIANTE B (répliques alternatives, voix/IDs identiques)
 * ════════════════════════════════════════════════════════════════════════
 * Même logique que QC : accroche plus chaleureuse/orientée bénéfice (diagnostic
 * gratuit) + qualification reformulée. Seules les clés ci-dessous diffèrent de A.
 */
const REPLIQUES_B = {
  lea_ouverture_b:
    'Bonjour, ici Léa, l\'assistante virtuelle automatisée de Ma Réno Facile. ' +
    'Bonne nouvelle pour les propriétaires : nous aidons à organiser vos travaux ' +
    'de rénovation avec un diagnostic gratuit. Ça prend trente secondes — ' +
    'êtes-vous bien propriétaire de votre logement ?',

  lea_question_besoin_b:
    'Super, merci ! Pour bien vous orienter : ce qui vous intéresserait le plus ' +
    'en ce moment, ce serait plutôt des travaux de rénovation, connaître la valeur ' +
    'de votre bien, ou un peu les deux ?',

  lea_question_projet_b:
    'Très bon choix ! Concrètement, quel projet avez-vous en tête — la cuisine, ' +
    'la salle de bains, l\'isolation, le chauffage, les fenêtres, la toiture, ou autre chose ?',

  lea_question_immo_b:
    'Parfait. Et juste pour savoir comment vous aider au mieux : faire estimer la ' +
    'valeur de votre bien, c\'est quelque chose que vous envisagez d\'ici un an ou deux, ' +
    'même sans être pressé ?',

  lea_capturer_dispo_b:
    'Excellent, c\'est tout à fait notre spécialité ! Un conseiller Ma Réno Facile ' +
    'vous rappellera avec un diagnostic gratuit et des idées concrètes pour votre projet. ' +
    'Pour qu\'il tombe au bon moment, préférez-vous plutôt le matin, l\'après-midi ou la soirée ?',

  lea_closing_b:
    'Parfait, c\'est noté ! Votre conseiller Ma Réno Facile vous rappellera au numéro ' +
    'de votre dossier, au moment que vous avez choisi. Merci beaucoup et très belle journée !',

  lea_sonder_futur_b:
    'Aucun souci, rien d\'urgent ! Juste pour l\'avenir : y a-t-il un projet de rénovation ' +
    'sur votre logement que vous aimeriez garder en tête pour plus tard ?',

  lea_objection_entrepreneur_b:
    'C\'est une excellente chose d\'avoir déjà quelqu\'un ! Nous pouvons tout de même ' +
    'vous offrir un deuxième avis gratuit, souvent ça aide à comparer. Puis-je noter ' +
    'vos coordonnées pour rester en contact ?',
};

const REPLIQUES_ALL = Object.assign({}, REPLIQUES, REPLIQUES_B);

// Mapping clé LOGIQUE → clé clip (identique à QC — structure préservée).
const LEA_LOGICAL_KEYS = {
  ouverture: 'lea_ouverture',
  question_besoin: 'lea_question_besoin',
  question_projet: 'lea_question_projet',
  question_immo: 'lea_question_immo',
  capturer_dispo: 'lea_capturer_dispo',
  closing: 'lea_closing',
  sonder_futur: 'lea_sonder_futur',
  exit_loc: 'lea_exit_locataire',
  exit_futur: 'lea_exit_futur',
  exit_pi: 'lea_exit_pas_interesse',
  exit_dnc: 'lea_exit_dnc',
  objection: 'lea_objection_entrepreneur',
  fallback: 'lea_fallback',
  timeout: 'lea_exit_timeout',
};

const LEA_VARIANT_B_KEYS = {
  ouverture: 'lea_ouverture_b',
  question_besoin: 'lea_question_besoin_b',
  question_projet: 'lea_question_projet_b',
  question_immo: 'lea_question_immo_b',
  capturer_dispo: 'lea_capturer_dispo_b',
  closing: 'lea_closing_b',
  sonder_futur: 'lea_sonder_futur_b',
  objection: 'lea_objection_entrepreneur_b',
};

/**
 * Assignation 50/50 déterministe — FNV-1a 32 bits, MÊME algo que QC/Odoo.
 * NE JAMAIS modifier d'un seul côté.
 */
function leaVariant(callSid) {
  const s = String(callSid || '');
  let h = 0x811c9dc5;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  return ((h >>> 0) % 2) === 0 ? 'A' : 'B';
}

function buildClips(variant) {
  const out = {};
  for (const logical in LEA_LOGICAL_KEYS) {
    const key =
      variant === 'B' && LEA_VARIANT_B_KEYS[logical]
        ? LEA_VARIANT_B_KEYS[logical]
        : LEA_LOGICAL_KEYS[logical];
    out[logical] = audioUrl(key);
  }
  return out;
}

// Deepgram en fr-FR pour la France (la voie QC reste fr-CA, intouchée).
const DEEPGRAM_CONFIG = {
  model: 'nova-2',
  language: 'fr-FR',
  endpointing: 300,
  utterance_end_ms: 700,
  interim_results: true,
  smart_format: true,
  punctuate: true,
  encoding: 'mulaw',
  sample_rate: 8000,
};

function audioUrl(key) {
  // Bucket DÉDIÉ France (séparé de lea-qc-tts). Surchargeable via
  // LEA_FR_STORAGE_BUCKET_URL. NE PAS pointer vers lea-qc-tts (clips fr-CA).
  const bucket = ($env.LEA_FR_STORAGE_BUCKET_URL || 'https://intellixcrm.com/lea-fr-tts').replace(/\/$/, '');
  return bucket ? `${bucket}/${key}.mp3` : '';
}

function computeCost(durationSec, amdResult) {
  const amd = (amdResult || '').toLowerCase();
  if (['machine', 'not_sure', 'fax'].includes(amd)) {
    return { cost: 0, billed: false, reason: 'AMD_DETECTED' };
  }
  const sec = Math.max(0, parseInt(durationSec, 10) || 0);
  if (!sec) return { cost: 0, billed: false, reason: 'ZERO_DURATION' };
  const rate = parseFloat($env.LEA_FR_RATE_PER_MIN || '0.008') / 60; // Africa-Con FR
  return { cost: Math.round(sec * rate * 10000) / 10000, billed: true, duration: sec };
}
