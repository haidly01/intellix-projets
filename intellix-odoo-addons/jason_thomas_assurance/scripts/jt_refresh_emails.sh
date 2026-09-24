#!/usr/bin/env bash
# Ré-extraction AGO/Inalco (avec emails) + upload dev + backfill CRM + accès portail
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
IA="$ROOT/../iaexcellence_extract"
IN="$ROOT/../inalco_extract"
PROFILE="${JT_BROWSER_PROFILE:-$ROOT/.browser_profile/account_2}"
DEV="${JT_DEV_HOST:-intellix-dev}"
REMOTE_SCRIPTS="/odoo/custom/addons/jason_thomas_assurance/scripts"

echo "=== 1. Ré-extraction AGO (Chrome / profil Playwright) ==="
if [[ -x "$IA/.venv/bin/python3" ]]; then
  "$IA/.venv/bin/python3" "$ROOT/jason_thomas_assurance/scripts/jt_fetch_emails_playwright.py" \
    --profile "$PROFILE" --out "$IA/output" || echo "AGO: session requise — ouvrez Assure&Go dans le profil $PROFILE"
else
  echo "Skip AGO: venv iaexcellence_extract absent"
fi

echo "=== 2. Upload CSV vers $DEV ==="
scp "$IA/output/clients.csv" "$DEV:$REMOTE_SCRIPTS/ago_clients.csv"
scp "$IA/output/polices.csv" "$DEV:$REMOTE_SCRIPTS/ago_polices.csv"
scp "$IN/output/clients.csv" "$DEV:$REMOTE_SCRIPTS/inalco_clients.csv"
scp "$IN/output/polices.csv" "$DEV:$REMOTE_SCRIPTS/inalco_polices.csv"
scp "$ROOT/assomption_extract/output/compte2/polices.csv" "$DEV:$REMOTE_SCRIPTS/compte2_polices.csv" 2>/dev/null || true

echo "=== 3. Backfill emails + accès portail ==="
ssh "$DEV" "sudo -u odoo python3 $REMOTE_SCRIPTS/backfill_emails.py --config /etc/odoo-server.conf --db intellixcrm"
ssh "$DEV" "sudo -u odoo /usr/bin/python3 /odoo/odoo-server/odoo-bin shell -c /etc/odoo-server.conf -d intellixcrm --no-http <<'PY'
created = env['jt.portal.access'].create_access_for_all_clients()
env.cr.commit()
with_email = env['jt.client'].search_count([('email','!=',False)])
access = env['jt.portal.access'].search_count([])
print('clients_with_email', with_email, 'portal_access', access, 'new_access', created)
PY"

echo "=== Terminé ==="
