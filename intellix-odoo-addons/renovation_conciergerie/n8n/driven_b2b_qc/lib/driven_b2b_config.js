/**
 * Alex — Qualification Driven B2B PME QC (fr-CA)
 * Répliques fixes — MP3 : DRIVEN_STORAGE_BUCKET_URL/{key}.mp3
 */
const REPLIQUES = {
  alex_ouverture:
    'Bonjour, c\'est Alex de Agence Doorway. Je vous appelle parce que votre entreprise ' +
    'pourrait être admissible à du financement entre 10 000$ et 500 000$ en moins de 24 heures. ' +
    'Est-ce que c\'est quelque chose qui vous intéresse ?',

  alex_q1_anciennete:
    'Votre entreprise est en activité depuis combien de temps ?',

  alex_q2_revenus:
    'Est-ce que votre entreprise génère au moins 100 000$ de revenus annuels ?',

  alex_q3_compte:
    'Avez-vous un compte bancaire au nom de votre entreprise ?',

  alex_closing_prequal:
    'Parfait, vous êtes préqualifié. Je vous envoie tout de suite un lien sécurisé — ' +
    'ça prend 10 minutes, c\'est gratuit et sans impact sur votre crédit. Prêt ?',

  alex_no_compte:
    'On peut quand même vous envoyer l\'information, ça ne prend que 10 minutes à ouvrir.',

  alex_exit_anciennete:
    'Malheureusement le minimum requis est 6 mois. Bonne continuation.',

  alex_exit_revenus:
    'Je comprends. Pour l\'instant nos critères exigent au moins 100 000$ de revenus annuels. ' +
    'Bonne continuation !',

  alex_exit_pas_interesse:
    'Aucun problème ! Si vous changez d\'idée, Agence Doorway reste disponible. Bonne journée !',

  alex_exit_dnc:
    'C\'est noté, on vous retire de notre liste. Bonne journée !',

  alex_fallback:
    'Désolé, je n\'ai pas bien entendu. Pouvez-vous répéter s\'il vous plaît ?',

  alex_exit_timeout:
    'Je vois que vous êtes occupé — on pourra vous rappeler une autre fois. Bonne journée !',
};

const CLIP_KEYS = {
  ouverture: 'alex_ouverture',
  q1_anciennete: 'alex_q1_anciennete',
  q2_revenus: 'alex_q2_revenus',
  q3_compte: 'alex_q3_compte',
  closing_prequal: 'alex_closing_prequal',
  no_compte: 'alex_no_compte',
  exit_anciennete: 'alex_exit_anciennete',
  exit_revenus: 'alex_exit_revenus',
  exit_pi: 'alex_exit_pas_interesse',
  exit_dnc: 'alex_exit_dnc',
  fallback: 'alex_fallback',
  timeout: 'alex_exit_timeout',
};

function buildClips() {
  const out = {};
  for (const logical in CLIP_KEYS) {
    out[logical] = audioUrl(CLIP_KEYS[logical]);
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
  const bucket = ($env.DRIVEN_STORAGE_BUCKET_URL || 'https://intellixcrm.com/driven-b2b-tts').replace(/\/$/, '');
  return bucket ? `${bucket}/${key}.mp3` : '';
}

function computeCost(durationSec, amdResult) {
  const amd = (amdResult || '').toLowerCase();
  if (['machine', 'not_sure', 'fax'].includes(amd)) {
    return { cost: 0, billed: false, reason: 'AMD_DETECTED' };
  }
  const sec = Math.max(0, parseInt(durationSec, 10) || 0);
  if (!sec) return { cost: 0, billed: false, reason: 'ZERO_DURATION' };
  const rate = parseFloat($env.DRIVEN_QC_RATE_PER_MIN || '0.25') / 60;
  return { cost: Math.round(sec * rate * 10000) / 10000, billed: true, duration: sec };
}

const DRIVEN_SMS_LINK = 'driven.ca/partners/agence-doorway';

function drivenSmsBody(prenom, variant) {
  const name = (prenom || 'Bonjour').trim();
  if (variant === 'j2') {
    return `Bonjour ${name}, avez-vous eu la chance de vérifier votre préqualification Driven ? driven.ca/partners/agence-doorway`;
  }
  if (variant === 'j5') {
    return `Bonjour ${name}, dernière relance — des PME comme la vôtre ont obtenu 50K$-200K$ en 24h. driven.ca/partners/agence-doorway`;
  }
  return (
    `Bonjour ${name}, voici votre lien de préqualification Driven : ` +
    `${DRIVEN_SMS_LINK} — 10 min, gratuit, sans impact crédit.`
  );
}
