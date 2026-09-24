/**
 * Minutes jusqu'au prochain créneau d'ouverture (appel matin).
 * Timezone: America/Toronto — jours ouvrés lun–sam.
 */
function torontoNow() {
  return new Date(new Date().toLocaleString('en-US', { timeZone: 'America/Toronto' }));
}

/** Prochain appel matin à openHour (défaut 9h) sur un jour ouvré (lun–sam). */
function minutesUntilNextMorningOpen(openHour = 9) {
  const now = torontoNow();
  const target = new Date(now);
  target.setSeconds(0, 0);

  const day = now.getDay(); // 0=dim, 6=sam
  const hour = now.getHours();

  const isBusinessDay = (d) => d >= 1 && d <= 6;

  if (isBusinessDay(day) && hour < openHour) {
    target.setHours(openHour, 0, 0, 0);
  } else {
    let cursor = new Date(now);
    cursor.setDate(cursor.getDate() + 1);
    cursor.setHours(openHour, 0, 0, 0);
    while (!isBusinessDay(cursor.getDay())) {
      cursor.setDate(cursor.getDate() + 1);
    }
    target.setTime(cursor.getTime());
  }

  let diff = Math.round((target - now) / 60000);
  return diff < 1 ? 1 : diff;
}

module.exports = { torontoNow, minutesUntilNextMorningOpen };
