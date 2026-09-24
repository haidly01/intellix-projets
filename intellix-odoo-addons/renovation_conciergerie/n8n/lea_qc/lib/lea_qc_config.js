/**
 * Léa — Soumission Entrepreneurs (rénovation + immobilier, fr-CA)
 * Répliques fixes — MP3 : STORAGE_BUCKET_URL/{key}.mp3
 */
const REPLIQUES = {
  lea_ouverture:
    'Bonjour, ici Léa, l\'assistante virtuelle automatisée de Soumission Entrepreneurs. ' +
    'On accompagne les propriétaires pour leurs projets de rénovation ' +
    'et aussi pour la vente de leur propriété. ' +
    'J\'ai juste deux petites questions — ça prend moins d\'une minute. ' +
    'Est-ce que vous êtes propriétaire de votre maison ?',

  lea_exit_locataire:
    'Je comprends, dans ce cas je ne peux pas vous aider pour l\'instant. Bonne journée !',

  lea_exit_locataire_info:
    'Je comprends ! Dans ce cas, c\'est votre propriétaire qui pourrait bénéficier des subventions ' +
    'et des rénovations. Si vous voulez, on peut lui envoyer l\'information directement — ' +
    'ça pourrait améliorer votre logement. Bonne journée !',

  lea_question_besoin:
    'Parfait ! Est-ce que vous pensez plutôt à des travaux de rénovation, ' +
    'à vendre votre propriété, ou peut-être les deux ?',

  lea_question_projet:
    'Excellent ! Quels travaux envisagez-vous — cuisine, salle de bain, toiture, ' +
    'fenêtres, sous-sol, agrandissement ou autre chose ?',

  lea_question_immo:
    'Est-ce que vous envisagez de vendre votre propriété dans les prochains mois, ' +
    'disons dans les 12 à 24 prochains mois ?',

  lea_capturer_dispo:
    'Parfait ! Un conseiller de Soumission Entrepreneurs va vous rappeler pour discuter de votre projet. ' +
    'À quel moment préférez-vous qu\'on vous contacte — le matin, l\'après-midi ou le soir ?',

  lea_redemand_dispo:
    'À quel moment préférez-vous qu\'on vous contacte — le matin, l\'après-midi ou le soir ?',

  lea_closing:
    'Parfait ! Un conseiller vous rappelle au numéro qu\'on a en dossier, comme convenu. ' +
    'Merci et bonne journée !',

  lea_closing_matin:
    'Parfait ! Un conseiller de Soumission Entrepreneurs vous rappellera le matin, ' +
    'au numéro qu\'on a en dossier. Merci et bonne journée !',

  lea_closing_apres_midi:
    'Parfait ! Un conseiller de Soumission Entrepreneurs vous rappellera en après-midi, ' +
    'au numéro qu\'on a en dossier. Merci et bonne journée !',

  lea_closing_soir:
    'Parfait ! Un conseiller de Soumission Entrepreneurs vous rappellera en soirée, ' +
    'au numéro qu\'on a en dossier. Merci et bonne journée !',

  lea_confirm_matin: 'Donc le matin, c\'est bien ça ?',
  lea_confirm_apres_midi: 'Donc l\'après-midi, c\'est bien ça ?',
  lea_confirm_soir: 'Donc le soir, c\'est bien ça ?',

  lea_sonder_futur:
    'Je comprends, pas nécessairement là maintenant. Beaucoup de propriétaires commencent par une ' +
    'évaluation gratuite pour voir à quelles subventions ils ont droit, avant même de décider quoi faire. ' +
    'Est-ce qu\'il y a quelque chose dans la maison qui vous préoccupe — l\'isolation, le chauffage, les fenêtres ?',

  lea_exit_futur:
    'Pas de problème. Je note votre dossier et on pourra revenir vers vous quand vous serez prêt. Bonne journée !',

  lea_exit_pas_interesse:
    'Aucun problème ! Si vous changez d\'idée, Soumission Entrepreneurs reste disponible. Bonne journée !',

  lea_exit_pas_temps:
    'Je comprends, vous êtes pris. On vous rappellera une autre fois. Bonne journée !',

  lea_exit_pas_temps_v2:
    'Je comprends, la vie est bien remplie ! Notre service ne vous demande presque aucun temps — ' +
    'on s\'occupe de tout en arrière-plan. Est-ce qu\'on pourrait fixer un moment plus tranquille, ' +
    'peut-être en soirée ou la fin de semaine ? Sinon je note et on vous rappelle une autre fois. Bonne journée !',

  lea_objection_pas_interesse_soft:
    'Je comprends, et je respecte ça ! Juste une question rapide — est-ce que c\'est parce que vous ' +
    'n\'avez pas de projet prévu, ou parce que vous ne connaissez pas encore notre service ? ' +
    'Beaucoup de propriétaires ne savent pas qu\'on aide à accéder à des subventions jusqu\'à dix mille dollars — ' +
    'sans frais et sans engagement.',

  lea_qui_etes_vous:
    'Bonne question ! Je m\'appelle Léa, de Soumission Entrepreneurs — une plateforme québécoise qui met ' +
    'en lien les propriétaires avec des entrepreneurs certifiés R-B-Q, et qui aide à accéder aux subventions ' +
    'gouvernementales. Notre service est cent pour cent gratuit et sans engagement.',

  lea_arnaque_sms_info:
    'Je comprends votre méfiance — c\'est normal avec tous les appels frauduleux. Soumission Entrepreneurs ' +
    'est vérifiable en ligne, on ne demande aucun paiement ni carte de crédit. Si vous préférez, je peux ' +
    'vous envoyer un texto avec notre site pour vérifier à votre rythme. Bonne journée !',

  lea_rappeler_plus_tard:
    'Pas de problème ! Pour vous rappeler au bon moment — est-ce que c\'est plutôt dans un mois, ' +
    'trois mois, ou au printemps prochain ? Je note dans notre système. Bonne journée !',

  lea_exit_dnc:
    'C\'est noté, on vous retire de notre liste. Bonne journée !',

  lea_objection_entrepreneur:
    'C\'est parfait d\'avoir un entrepreneur de confiance ! On est complémentaires — on vous aide à ' +
    'maximiser les subventions gouvernementales pour vos projets. Est-ce que votre entrepreneur vous a ' +
    'parlé de Rénoclimat ou LogisVert ? On peut quand même noter vos coordonnées pour rester en contact.',

  lea_fallback: 'Désolée, je n\'ai pas bien entendu. Pouvez-vous répéter s\'il vous plaît ?',
  lea_exit_timeout: 'Je vois que vous êtes occupé — on vous rappellera une autre fois. Bonne journée !',
};

/**
 * ════════════════════════════════════════════════════════════════════════
 *  A/B TEST — VARIANTE B (répliques alternatives, voix/IDs identiques)
 * ════════════════════════════════════════════════════════════════════════
 * Hypothèse B : une accroche plus chaleureuse/orientée bénéfice + une
 * qualification reformulée (moins de friction, cadrage « évaluation gratuite »)
 * augmentent le TAUX DE QUALIFICATION à coût/minute ≈ identique (mêmes étapes,
 * même nombre de tours, même voix ElevenLabs).
 *
 * Seules les clés ci-dessous diffèrent de la variante A. Toutes les autres
 * répliques (exits, fallback, dnc, timeout) sont RÉUTILISÉES depuis A pour que
 * la variante B reste un sur-ensemble additif et clairement isolé.
 */
const REPLIQUES_B = {
  lea_ouverture_b:
    'Bonjour, ici Léa, l\'assistante virtuelle automatisée de Soumission Entrepreneurs. ' +
    'Bonne nouvelle pour les propriétaires : on aide à faire estimer ' +
    'gratuitement la valeur de votre maison. Ça prend trente secondes — ' +
    'êtes-vous bien propriétaire de votre maison ?',

  lea_question_besoin_b:
    'Super, merci ! Pour bien vous orienter : est-ce que ce qui vous ' +
    'intéresserait le plus en ce moment, ce serait de connaître la valeur ' +
    'de revente de votre maison, de réaliser des rénovations, ou un peu ' +
    'les deux ?',

  lea_question_projet_b:
    'Bon choix ! Concrètement, quel projet vous trotte dans la tête — ' +
    'la cuisine, la salle de bain, la toiture, les fenêtres, le sous-sol, ' +
    'un agrandissement, ou autre chose ?',

  lea_question_immo_b:
    'Parfait. Et juste pour savoir comment on peut vous aider : est-ce que ' +
    'vendre votre propriété, c\'est quelque chose que vous envisagez d\'ici ' +
    'un an ou deux, même sans être pressé ?',

  lea_capturer_dispo_b:
    'Excellent, c\'est exactement notre spécialité ! Un conseiller va vous rappeler avec une ' +
    'évaluation gratuite pour votre projet. À quel moment préférez-vous qu\'on vous contacte — ' +
    'le matin, l\'après-midi ou le soir ?',

  lea_redemand_dispo_b:
    'À quel moment préférez-vous qu\'on vous contacte — le matin, l\'après-midi ou le soir ?',

  lea_closing_b:
    'Parfait, c\'est noté ! Votre conseiller vous rappelle au numéro qu\'on a au dossier, ' +
    'comme convenu. Merci beaucoup et excellente journée !',

  lea_closing_matin_b:
    'Parfait, c\'est noté ! Votre conseiller vous rappellera le matin, au numéro qu\'on a au dossier. ' +
    'Merci beaucoup et excellente journée !',

  lea_closing_apres_midi_b:
    'Parfait, c\'est noté ! Votre conseiller vous rappellera en après-midi, au numéro qu\'on a au dossier. ' +
    'Merci beaucoup et excellente journée !',

  lea_closing_soir_b:
    'Parfait, c\'est noté ! Votre conseiller vous rappellera en soirée, au numéro qu\'on a au dossier. ' +
    'Merci beaucoup et excellente journée !',

  lea_sonder_futur_b:
    'Aucun souci, rien d\'urgent ! Juste pour le futur : y a-t-il un petit ' +
    'projet sur votre maison — rénovation ou même une vente éventuelle — que ' +
    'vous aimeriez garder dans un coin de votre tête pour plus tard ?',

  lea_objection_entrepreneur_b:
    'C\'est une excellente chose d\'avoir déjà quelqu\'un ! On peut quand même ' +
    'vous offrir un deuxième avis gratuit, souvent ça aide à comparer. Est-ce ' +
    'que je peux noter vos coordonnées pour rester en contact ?',
};

// Catalogue complet (A + B) — utilisé seulement à titre de référence/doc.
const REPLIQUES_ALL = Object.assign({}, REPLIQUES, REPLIQUES_B);

// Mapping clé LOGIQUE → clé clip pour chaque variante.
// La variante A est la production actuelle, octet pour octet identique.
const LEA_LOGICAL_KEYS = {
  ouverture: 'lea_ouverture',
  question_besoin: 'lea_question_besoin',
  question_projet: 'lea_question_projet',
  question_immo: 'lea_question_immo',
  capturer_dispo: 'lea_capturer_dispo',
  redemand_dispo: 'lea_redemand_dispo',
  closing: 'lea_closing',
  closing_matin: 'lea_closing_matin',
  closing_apres_midi: 'lea_closing_apres_midi',
  closing_soir: 'lea_closing_soir',
  confirm_matin: 'lea_confirm_matin',
  confirm_apres_midi: 'lea_confirm_apres_midi',
  confirm_soir: 'lea_confirm_soir',
  sonder_futur: 'lea_sonder_futur',
  exit_loc: 'lea_exit_locataire_info',
  exit_futur: 'lea_exit_futur',
  exit_pi: 'lea_exit_pas_interesse',
  exit_pas_temps: 'lea_exit_pas_temps_v2',
  exit_dnc: 'lea_exit_dnc',
  objection: 'lea_objection_entrepreneur',
  objection_pi_soft: 'lea_objection_pas_interesse_soft',
  qui_etes_vous: 'lea_qui_etes_vous',
  arnaque_sms: 'lea_arnaque_sms_info',
  rappeler_plus_tard: 'lea_rappeler_plus_tard',
  fallback: 'lea_fallback',
  timeout: 'lea_exit_timeout',
};

const LEA_VARIANT_B_KEYS = {
  ouverture: 'lea_ouverture_b',
  question_besoin: 'lea_question_besoin_b',
  question_projet: 'lea_question_projet_b',
  question_immo: 'lea_question_immo_b',
  capturer_dispo: 'lea_capturer_dispo_b',
  redemand_dispo: 'lea_redemand_dispo_b',
  closing: 'lea_closing_b',
  closing_matin: 'lea_closing_matin_b',
  closing_apres_midi: 'lea_closing_apres_midi_b',
  closing_soir: 'lea_closing_soir_b',
  sonder_futur: 'lea_sonder_futur_b',
  objection: 'lea_objection_entrepreneur_b',
};

/**
 * Assignation 50/50 déterministe d'une variante à partir du call_sid.
 *
 * ⚠️ SOURCE DE VÉRITÉ PARTAGÉE avec Odoo
 *    (lea.qc.sample.call.variant_for_sid en Python). Le hash est un FNV-1a
 *    32 bits portable : pas de dépendance crypto/require (indisponible dans
 *    le sandbox du Code node n8n) et parité (bit de poids faible) STRICTEMENT
 *    identique à l'implémentation Python. NE JAMAIS modifier l'algorithme d'un
 *    seul côté — sinon n8n et Odoo assigneraient des bras différents.
 */
function leaVariant(callSid) {
  const forced = String($env.LEA_FORCE_VARIANT || 'B').trim().toUpperCase();
  if (forced === 'A' || forced === 'B') return forced;
  const s = String(callSid || '');
  let h = 0x811c9dc5; // FNV offset basis (2166136261)
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 0x01000193); // FNV prime 16777619 (multiplication 32 bits)
  }
  return ((h >>> 0) % 2) === 0 ? 'A' : 'B';
}

/**
 * Construit la table des URLs de clips pour une variante donnée.
 * Variante B = clips B pour les clés listées, sinon repli sur les clips A.
 */
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

const DEEPGRAM_CONFIG = {
  model: 'nova-2',
  language: 'fr-CA',
  endpointing: 300,
  utterance_end_ms: 700,
  interim_results: true,
  smart_format: true,
  punctuate: true,
  encoding: 'mulaw',
  sample_rate: 8000,
};

function audioUrl(key) {
  // IMPORTANT : le $env.STORAGE_BUCKET_URL GLOBAL de n8n est partagé et pointe
  // vers un AUTRE bucket (soumission-qc-tts) — ce qui renvoyait des URLs de
  // clips Léa introuvables (l'AGI échouait à les jouer -> silence). On force le
  // bucket Léa, surchargeable via LEA_STORAGE_BUCKET_URL si besoin.
  const bucket = ($env.LEA_STORAGE_BUCKET_URL || 'https://intellixcrm.com/lea-qc-tts').replace(/\/$/, '');
  return bucket ? `${bucket}/${key}.mp3` : '';
}

function computeCost(durationSec, amdResult) {
  const amd = (amdResult || '').toLowerCase();
  if (['machine', 'not_sure', 'fax'].includes(amd)) {
    return { cost: 0, billed: false, reason: 'AMD_DETECTED' };
  }
  const sec = Math.max(0, parseInt(durationSec, 10) || 0);
  if (!sec) return { cost: 0, billed: false, reason: 'ZERO_DURATION' };
  const rate = parseFloat($env.SOFIA_QC_RATE_PER_MIN || '0.25') / 60;
  return { cost: Math.round(sec * rate * 10000) / 10000, billed: true, duration: sec };
}
