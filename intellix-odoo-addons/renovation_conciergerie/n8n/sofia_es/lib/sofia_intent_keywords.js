/**
 * Classification rapide par mots-clés (évite appel LLM + corrige propietario/propriétaire).
 * Retourne null si pas de match → fallback Deepgram + Claude.
 */
function normTranscript(t) {
  return (t || '')
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^\w\s]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function extractPostalCode(t) {
  const nums = t.match(/\d{2,5}/g);
  if (nums && nums.length) {
    const joined = nums.join('');
    if (joined.length >= 4 && joined.length <= 6) return joined;
  }
  const compact = t.replace(/\D/g, '');
  if (compact.length >= 4 && compact.length <= 6) return compact;
  return '';
}

function fastClassifyIntent(etape, transcript) {
  const t = normTranscript(transcript);
  if (!t) return null;

  const ownerWord =
    /\bpropiet/i.test(t) ||
    /\b(propietari[oa]|propietario|propietaria|titular|dueno|duena|duno|duna)\b/.test(t) ||
    /\bsoy\s+(el\s+)?(propietari[oa]|dueno|duena|titular)\b/.test(t) ||
    /\b(es mi casa|es mia|es mio|casa propia|de mi propiedad|figura como titular)\b/.test(t);
  const affirm =
    /^(si|sí|aja|ajá|claro|exacto|correcto|vale|ok|por supuesto)\b/.test(t) ||
    /\b(si|sí|aja|ajá|claro|exacto|correcto|por supuesto|soy|somos|bien)\b/.test(t);
  const denyExplicit =
    /\b(no soy|no lo soy|no somos|inquilino|arrendatari[oa]|alquil|rento|no es mio|no es mia|no es de mi)\b/.test(t);
  const denyBare = /^(no|nop)\s*$/i.test(t);
  const deny = denyExplicit || denyBare;
  const unsure =
    /\b(no se|no lo se|no estoy segur[oa]|quizas|tal vez|creo que|a lo mejor)\b/.test(t);

  if (etape === 'ouverture' || etape === 'Q1_clarif') {
    if (denyExplicit && !ownerWord) return { intent: 'non' };
    if (denyBare && !ownerWord && !affirm && t.length <= 6) return { intent: 'non' };
    if (ownerWord || (affirm && !deny)) return { intent: 'oui' };
    if (unsure) return { intent: 'incertain' };
    if (/\b(no me interesa|no gracias|dejeme|no quiero|no moleste)\b/.test(t)) {
      return { intent: 'pas_interesse' };
    }
    if (/\b(no llame|no llamen|retiren|baja|no me llamen)\b/.test(t)) {
      return { intent: 'do_not_call' };
    }
    if (affirm) return { intent: 'oui' };
  }

  if (['Q2', 'Q2_appt', 'Q5', 'Q5_non'].includes(etape)) {
    if (affirm && !deny) return { intent: 'oui' };
    if (deny) return { intent: 'non' };
  }

  if (etape === 'Q3') {
    if (/\b(no se|no lo se|no recuerdo|no me acuerdo|no sabria|no lo tengo)\b/.test(t)) {
      return { intent: 'inconnu' };
    }
    const cp = extractPostalCode(t);
    if (cp) return { intent: 'ok', valeur: cp };
  }

  if (etape === 'Q4' || etape === 'Q4_non') {
    const heat = t.match(/\b(gas|gasoleo|gasoil|electricidad|electrico|fuel|propano|pellet|lenia)\b/);
    if (heat) return { intent: 'ok', valeur: heat[1] };
    if (affirm && !deny) return { intent: 'ok', valeur: t };
    if (deny) return { intent: 'inconnu' };
  }

  if (etape === 'collect_tel') {
    if (/\b(este|mismo|ese|confirmo|si|sí|vale|correcto)\b/.test(t) && !deny) {
      return { intent: 'confirme' };
    }
    if (/\d{6,}/.test(t)) return { intent: 'nouveau', valeur: t.replace(/\D/g, '') };
  }

  return null;
}
