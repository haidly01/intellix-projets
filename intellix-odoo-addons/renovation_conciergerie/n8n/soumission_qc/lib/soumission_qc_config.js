/**

 * Émilie — SoumissionEntrepreneurs.com (Québec fr-CA)

 * Répliques fixes — pré-générer en MP3 : STORAGE_BUCKET_URL/{key}.mp3

 */

const REPLIQUES = {

  emilie_ouverture:

    'Bonjour ! Ici Émilie de SoumissionEntrepreneurs.com. ' +

    'On aide les propriétaires du Québec à trouver les meilleurs entrepreneurs pour leurs projets, ' +

    'et à obtenir plusieurs soumissions gratuitement. ' +

    'J\'ai juste deux petites questions pour vous — ça prend moins d\'une minute. ' +

    'Est-ce que vous êtes propriétaire de votre maison ?',



  emilie_exit_locataire:

    'Je comprends, dans ce cas je ne peux pas vous aider pour l\'instant. Bonne journée !',



  emilie_question_projet:

    'Excellent ! Est-ce que vous avez un projet de rénovation en tête pour votre maison cette année — ' +

    'que ce soit la cuisine, la salle de bain, la toiture, les fenêtres, le sous-sol, ou même un agrandissement ?',



  emilie_capturer_dispo:

    'Super, c\'est exactement pour ça qu\'on est là ! On peut vous mettre en contact avec des entrepreneurs vérifiés ' +

    'de votre région et vous obtenir jusqu\'à trois soumissions gratuitement. ' +

    'Un de nos conseillers va vous rappeler pour discuter de votre projet en détail. ' +

    'C\'est quoi le meilleur moment pour vous rejoindre — plutôt le matin, l\'après-midi, ou le soir ?',



  emilie_closing:

    'Parfait ! Je confirme — on vous rappelle au numéro qu\'on a en dossier. ' +

    'Votre projet sera pris en charge par un conseiller qui connaît bien les entrepreneurs de votre région. ' +

    'Bonne journée et à bientôt !',



  emilie_sonder_futur:

    'Je comprends, pas nécessairement là maintenant. ' +

    'Est-ce qu\'il y a quelque chose que vous pensez faire sur votre maison dans les prochains mois — même quelque chose de petit ?',



  emilie_exit_futur:

    'Pas de problème du tout. Je vais noter votre dossier et on reviendra vers vous quand vous serez prêt. ' +

    'Si jamais un besoin se présente, SoumissionEntrepreneurs.com est là pour vous. Bonne journée !',



  emilie_exit_pas_interesse:

    'Aucun problème ! Si vous changez d\'idée pour un projet futur, SoumissionEntrepreneurs.com est toujours disponible. Bonne journée !',



  emilie_exit_dnc:

    'C\'est noté, on vous retire de notre liste. Bonne journée !',



  emilie_objection_entrepreneur:

    'C\'est parfait ! Notre service peut quand même vous être utile pour avoir un deuxième avis sur le prix ' +

    'ou pour votre prochain projet. Est-ce que je peux noter vos coordonnées pour qu\'on reste en contact ?',



  emilie_fallback: 'Désolée, je n\'ai pas bien entendu. Pouvez-vous répéter s\'il vous plaît ?',

  emilie_exit_timeout: 'Je vois que vous êtes occupé — on vous rappellera une autre fois. Bonne journée !',

};



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

  const bucket = ($env.STORAGE_BUCKET_URL || '').replace(/\/$/, '');

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


