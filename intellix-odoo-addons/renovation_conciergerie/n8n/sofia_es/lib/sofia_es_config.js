/**
 * Répliques fixes Sofia Espagne — pré-générer en MP3 avant campagne.
 * Bucket public : $env.STORAGE_BUCKET_URL/{replica_key}.mp3
 */
const REPLIQUES_FIXES = {
  sofia_ouverture:
    'Hola, buenos días. Le llamo de parte del Centro de Ayudas para la Renovación Energética. ' +
    'Me pongo en contacto con usted porque su vivienda podría ser elegible para una subvención ' +
    'destinada a mejorar el aislamiento de su hogar. La verificación es completamente gratuita ' +
    'y solo le tomará un momento. ¿Es usted el propietario o la propietaria de la vivienda?',

  sofia_propietario_si:
    'Perfecto, muchas gracias. ¿Se trata de una vivienda unifamiliar — una casa individual — ' +
    'o de un piso en un bloque de apartamentos?',

  sofia_no_propietario:
    'Entiendo, no hay ningún problema. En ese caso, la ayuda debería tramitarse a través del propietario. ' +
    'Muchas gracias por su tiempo y que tenga un buen día.',

  sofia_q2_unifamiliar:
    'Estupendo. ¿Podría indicarme el código postal de su vivienda para verificar si está dentro de la zona cubierta?',

  sofia_q2_piso:
    'Entendido. Las ayudas para comunidades de propietarios tienen un proceso diferente. ' +
    '¿Le interesaría que un asesor de nuestra parte le contactara para explicarle las opciones disponibles para su caso?',

  sofia_sin_codigo_postal:
    'No se preocupe en absoluto. Un supervisor de nuestro equipo le llamará en breve para tomar nota ' +
    'de todos sus datos y verificar su elegibilidad con calma. ' +
    '¿A qué nombre está registrada la vivienda para que podamos identificar su expediente?',

  sofia_cierre_positivo:
    'Perfecto, muchas gracias por su tiempo. Un asesor especializado se pondrá en contacto con usted en las próximas horas ' +
    'para explicarle en detalle las ayudas disponibles y los próximos pasos. Que tenga un excelente día.',

  sofia_cierre_negativo:
    'De acuerdo, le entiendo perfectamente. Si en algún momento cambia de opinión o tiene alguna pregunta, ' +
    'no dude en contactarnos. Que tenga un buen día.',

  sofia_repondeur:
    'Hola, le llamamos del Centro de Ayudas para la Renovación Energética. ' +
    'Su vivienda podría ser elegible para una subvención de mejora del aislamiento. ' +
    'Le devolveremos la llamada en breve. Gracias.',

  sofia_no_entiendo:
    'Disculpe, no le he escuchado bien. ¿Podría repetirlo por favor?',

  sofia_muy_ocupado:
    'Por supuesto, le entiendo completamente. ¿Cuándo sería un mejor momento para volver a llamarle?',
};

const STATES = {
  INTRO: 'intro',
  Q1_PROPIETARIO: 'q1_propietario',
  Q2_TIPO: 'q2_tipo',
  Q3_CP: 'q3_codigo_postal',
  Q3_SIN_CP: 'q3_sin_cp',
  Q4_DISPONIBLE: 'q4_disponible',
  CIERRE_POSITIVO: 'cierre_positivo',
  CIERRE_NEGATIVO: 'cierre_negativo',
  NO_CONTESTA: 'no_contesta',
};

const DEEPGRAM_CONFIG = {
  model: 'nova-2',
  language: 'es',
  endpointing: 300,
  utterance_end_ms: 1000,
  interim_results: true,
  smart_format: true,
  punctuate: true,
  encoding: 'mulaw',
  sample_rate: 8000,
};

function audioUrl(replicaKey) {
  const bucket = ($env.STORAGE_BUCKET_URL || '').replace(/\/$/, '');
  return bucket ? `${bucket}/${replicaKey}.mp3` : '';
}

function calculateCost(durationSec, amdResult) {
  const amd = (amdResult || '').toLowerCase();
  if (['machine', 'not_sure', 'fax'].includes(amd)) {
    return { cost: 0, billed: false, reason: 'AMD_DETECTED' };
  }
  const sec = Math.max(0, parseInt(durationSec, 10) || 0);
  if (!sec) return { cost: 0, billed: false, reason: 'ZERO_DURATION' };
  const cost = Math.round((sec * 0.22 / 60) * 10000) / 10000;
  return { cost, billed: true, duration: sec, reason: 'HUMAN_CALL' };
}

module.exports = {
  REPLIQUES_FIXES,
  STATES,
  DEEPGRAM_CONFIG,
  audioUrl,
  calculateCost,
};
