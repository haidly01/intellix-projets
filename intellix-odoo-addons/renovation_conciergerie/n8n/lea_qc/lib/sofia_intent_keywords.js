/**
 * Classification rapide fr-CA — évite appel LLM sur réponses courantes.
 */
function normTranscript(t) {
  return (t || '')
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-z0-9\s]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function fastClassifyIntent(etape, transcript) {
  const t = normTranscript(transcript);
  if (!t) return null;

  const affirm =
    /^(oui|ouais|ouin|yes|ok|correct|exact|c est ca|cest ca|bien sur)\b/.test(t) ||
    /\b(oui|ouais|ouin|bien sur|exactement|correct|c est ca)\b/.test(t);
  const deny =
    /^(non|nan|nope|no)\s*$/.test(t) ||
    /\b(non je|pas proprietaire|pas proprio|locataire|je loue|en location|je suis locataire)\b/.test(t);
  const owner =
    /\b(proprietaire|proprio|a mon nom|c est ma maison|maison est a moi|titulaire)\b/.test(t);
  const tenant = /\b(locataire|je loue|en location|pas proprietaire|pas proprio)\b/.test(t);
  const pasInteresse = /\b(pas interesse|pas interesse|ca m interesse pas|laissez moi|rappelez plus)\b/.test(t);
  const dnc = /\b(ne plus appeler|retirez|retirer|do not call|enlevez mon numero)\b/.test(t);
  const unsure = /\b(je sais pas|sais pas|pas sur|peut etre|je pense)\b/.test(t);

  if (etape === 'ouverture' || etape === 'Q1_clarif') {
    if (tenant || (deny && !owner)) return { intent: 'non' };
    if (owner || affirm) return { intent: 'oui' };
    if (pasInteresse) return { intent: 'pas_interesse' };
    if (dnc) return { intent: 'do_not_call' };
    if (unsure) return { intent: 'incertain' };
  }

  if (etape === 'Q2_age') {
    if (/\b(moins de 10|neuve|recente|moins de dix)\b/.test(t)) return { intent: 'ok', valeur: 'moins_10' };
    if (/\b(10 et 30|dix et trente|entre 10|entre dix)\b/.test(t)) return { intent: 'ok', valeur: '10_30' };
    if (/\b(plus de 30|plus de trente|vieille|ancienne)\b/.test(t)) return { intent: 'ok', valeur: 'plus_30' };
    if (affirm) return { intent: 'ok', valeur: t.slice(0, 40) };
  }

  if (etape === 'Q3_travaux') {
    if (/\b(rien|aucun|pas de travaux|rien pour l instant|ca va bien)\b/.test(t)) return { intent: 'aucun' };
    const trav = t.match(/\b(toiture|fenetre|fenetres|cuisine|salle de bain|sdb|sous sol|patio|thermopompe|isolation)\b/);
    if (trav) return { intent: 'ok', valeur: trav[1] };
    if (affirm && t.length > 8) return { intent: 'ok', valeur: t.slice(0, 60) };
  }

  if (etape === 'Q4_vente') {
    if (affirm && !deny) return { intent: 'oui' };
    if (deny) return { intent: 'non' };
  }

  if (['Q5_pitch', 'Q5_objection'].includes(etape)) {
    if (affirm && !deny) return { intent: 'oui' };
    if (deny || pasInteresse) return { intent: 'non' };
    if (unsure) return { intent: 'incertain' };
  }

  if (etape === 'Q6_preference') {
    if (/\b(avant midi|matin|matinee|am|avant-midi)\b/.test(t)) return { intent: 'ok', valeur: 'avant_midi' };
    if (/\b(apres midi|apres-midi|pm|soir|apres-midi)\b/.test(t)) return { intent: 'ok', valeur: 'apres_midi' };
    if (affirm) return { intent: 'ok', valeur: t.slice(0, 40) };
  }

  if (pasInteresse) return { intent: 'pas_interesse' };
  if (dnc) return { intent: 'do_not_call' };
  return null;
}
