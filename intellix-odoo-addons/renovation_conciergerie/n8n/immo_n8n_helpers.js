/**
 * Snippets à coller dans les nodes Code n8n (Immo Meta relances).
 * Timezone: America/Toronto
 */

function normalizePhone(phone) {
  if (!phone) return '';
  const d = String(phone).replace(/\D/g, '');
  if (d.length === 10) return '+1' + d;
  if (d.length === 11 && d.startsWith('1')) return '+' + d;
  if (String(phone).trim().startsWith('+')) return '+' + d;
  return d ? '+1' + d : '';
}

function torontoNow() {
  return new Date(new Date().toLocaleString('en-US', { timeZone: 'America/Toronto' }));
}

/** Minutes jusqu'à J+dayOffset à hour:minute (heure locale Toronto). */
function minutesUntilToronto(dayOffset, hour, minute = 0) {
  const now = torontoNow();
  const target = new Date(now);
  target.setDate(target.getDate() + dayOffset);
  target.setHours(hour, minute, 0, 0);
  let diff = Math.round((target - now) / 60000);
  if (diff < 1) diff = 1;
  return diff;
}

const MESSAGES = {
  sms_j0_30min:
    "Bonjour {{first_name}}! 👋\n\nJe viens d'essayer de vous joindre concernant votre évaluation marchande gratuite.\n\nRépondez simplement OUI ici et je vous rappelle dans les prochaines minutes!\n\n— Sophie, Maison Recherchée.",
  wa_j0_4h:
    "Bonjour {{first_name}} 😊\n\nVotre demande d'évaluation marchande est bien reçue!\n\nQuel est le meilleur moment pour vous appeler cette semaine?\n\n☐ Matin (8h-12h)\n☐ Après-midi (12h-17h)\n☐ Soir (17h-20h)\n\n— Sophie, Maison Recherchée.",
  sms_j1:
    "Bonjour {{first_name}}!\n\n💡 Les propriétés dans votre secteur se vendent en moyenne en {{market_days}} jours.\n\nVotre évaluation gratuite vous donne une fourchette précise.\n\nDisponible pour un appel rapide aujourd'hui?\n\n— Agence Doorway",
  wa_j3:
    "Bonjour {{first_name}} 🏡\n\nCette semaine, on a aidé des propriétaires du secteur {{neighborhood}}.\n\n✅ Évaluation en 24h\n✅ Ventes comparables\n✅ Estimation nette\n\nGratuit et sans engagement. On fixe ça cette semaine?",
  sms_j5:
    "Bonjour {{first_name}},\n\nLe marché {{season}} est actif dans votre secteur.\n\nOn a de la disponibilité cette semaine pour votre évaluation.\n\n— Sophie, Maison Recherchée. 📞",
  wa_j7:
    "Bonjour {{first_name}},\n\nDernier message 😊 — votre dossier d'évaluation expire dans 48h. Répondez OUI pour le garder actif.\n\n— Sophie, Maison Recherchée.",
  sms_j14:
    "Bonjour {{first_name}} 👋\n\nNotre rapport de marché {{season}} pour votre secteur est prêt.\n\nRépondez OUI 📊 — Maison Recherchée.",
  sms_j30:
    "Bonjour {{first_name}},\n\nVotre dossier sera archivé cette semaine. Écrivez RÉACTIVER pour reprendre.\n\n— Équipe Maison Recherchée. 🏡",
};

function fillTemplate(key, vars) {
  let tpl = MESSAGES[key] || '';
  return tpl.replace(/\{\{(\w+)\}\}/g, (_, k) => vars[k] ?? '');
}

module.exports = {
  normalizePhone,
  torontoNow,
  minutesUntilToronto,
  fillTemplate,
  MESSAGES,
};
