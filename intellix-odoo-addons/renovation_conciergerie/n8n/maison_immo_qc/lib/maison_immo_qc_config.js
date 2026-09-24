/**

 * Sophie — MaisonRecherchee.com (Québec fr-CA)

 */

const REPLIQUES = {

  sophie_ouverture:

    'Bonjour ! Ici Sophie de MaisonRecherchee.com. ' +

    'On aide les propriétaires du Québec à vendre leur maison rapidement et au meilleur prix, ' +

    'grâce à notre réseau de courtiers partenaires. ' +

    'J\'ai juste une question simple pour vous. ' +

    'Est-ce que vous envisagez de vendre votre propriété dans les prochains mois ?',



  sophie_timeline_chaud:

    'Parfait, le marché est actif en ce moment dans votre région. ' +

    'Un de nos conseillers peut vous faire une évaluation gratuite de votre propriété ' +

    'et vous expliquer comment maximiser votre prix de vente. ' +

    'C\'est quoi le meilleur moment pour qu\'il vous rappelle — matin, après-midi ou soir ?',



  sophie_timeline_tiede:

    'C\'est bien de s\'y préparer à l\'avance ! On peut commencer dès maintenant à préparer votre dossier ' +

    'pour que vous soyez prêt quand le moment vient. Un conseiller peut vous rappeler pour commencer la démarche sans pression. ' +

    'Quel moment vous convient le mieux ?',



  sophie_sonder_futur:

    'Je comprends. Est-ce qu\'il y a une possibilité que vous vendiez d\'ici les deux prochaines années — ' +

    'peut-être pour un projet de retraite, un déménagement, ou autre ?',



  sophie_futur_liste:

    'Dans ce cas on peut vous inscrire sur notre liste de suivi. Un conseiller vous contactera quand ce sera le bon moment pour vous. ' +

    'Est-ce que je peux noter vos coordonnées ?',



  sophie_closing:

    'Parfait ! Je confirme votre numéro — c\'est bien celui qu\'on a en dossier. ' +

    'Un conseiller de MaisonRecherchee.com vous rappellera au moment choisi. ' +

    'C\'est entièrement gratuit et sans engagement. Bonne journée et à bientôt !',



  sophie_exit_courtier:

    'Très bien ! Dans ce cas on ne veut surtout pas interférer avec votre relation actuelle. ' +

    'Si jamais vous avez besoin d\'un deuxième avis ou que la situation change, on est là. Bonne chance avec votre vente !',



  sophie_exit_pi:

    'Aucun problème ! Si vous changez d\'idée, MaisonRecherchee.com est toujours disponible. Bonne journée !',



  sophie_exit_dnc: 'C\'est noté, on vous retire de notre liste. Bonne journée !',

  sophie_fallback: 'Désolée, je n\'ai pas bien entendu. Pouvez-vous répéter s\'il vous plaît ?',

  sophie_exit_timeout: 'Je vois que vous êtes occupé — on vous rappellera une autre fois. Bonne journée !',

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


