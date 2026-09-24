#!/bin/bash
# Déploie AGI + dialplan + greetings pour agents QC (Émilie + Sophie)
set -euo pipefail

ADDON_ROOT="/odoo/custom/addons/renovation_conciergerie"
SRC_AGI="/var/lib/asterisk/agi-bin/n8n_sofia_es.agi"
SE_AGI="/var/lib/asterisk/agi-bin/n8n_soumission_qc.agi"
MR_AGI="/var/lib/asterisk/agi-bin/n8n_maison_immo_qc.agi"
DIALPLAN_SRC="$ADDON_ROOT/deploy/extensions_qc_ia.conf"
DIALPLAN_DST="/etc/asterisk/extensions_qc_ia.conf"

if [[ ! -f "$SRC_AGI" ]]; then
  echo "AGI source manquant: $SRC_AGI" >&2
  exit 1
fi

cp "$SRC_AGI" "$SE_AGI"
cp "$SRC_AGI" "$MR_AGI"
sed -i 's|sofia-es-demo/vicidial/event|soumission-qc/event|g' "$SE_AGI"
sed -i 's|DWTOISOE|SE_RENOV_QC|g' "$SE_AGI"
sed -i 's|sofia-es-demo-abdallah|sofia-soumission-qc-2026|g' "$SE_AGI"
sed -i 's|sofia-es-tts|soumission-qc-tts|g' "$SE_AGI"

sed -i 's|sofia-es-demo/vicidial/event|maison-immo-qc/event|g' "$MR_AGI"
sed -i 's|DWTOISOE|MR_IMMO_QC|g' "$MR_AGI"
sed -i 's|sofia-es-demo-abdallah|sophie-maison-immo-qc-2026|g' "$MR_AGI"
sed -i 's|sofia-es-tts|maison-immo-qc-tts|g' "$MR_AGI"

chmod +x "$SE_AGI" "$MR_AGI"
chown asterisk:asterisk "$SE_AGI" "$MR_AGI"
cp "$SE_AGI" /usr/share/asterisk/agi-bin/n8n_soumission_qc.agi
cp "$MR_AGI" /usr/share/asterisk/agi-bin/n8n_maison_immo_qc.agi

cp "$DIALPLAN_SRC" "$DIALPLAN_DST"
grep -q 'extensions_qc_ia.conf' /etc/asterisk/extensions.conf \
  || echo '#include extensions_qc_ia.conf' >> /etc/asterisk/extensions.conf

python3 "$ADDON_ROOT/scripts/precache_greetings.py" || echo "WARN: precache greetings failed (clé ElevenLabs?)"

asterisk -rx "dialplan reload"
echo "Deploy QC IA OK — AGI + dialplan 86013/86014"
