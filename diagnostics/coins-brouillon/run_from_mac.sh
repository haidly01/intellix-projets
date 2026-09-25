#!/usr/bin/env bash
# Enquête « lieux Coins Marocain qui repassent en brouillon » — LECTURE SEULE.
# À lancer depuis le Mac (clés dans ~/.ssh/config) :
#   bash diagnostics/coins-brouillon/run_from_mac.sh
# Résultats dans diagnostics/coins-brouillon/out/ (à me renvoyer).
# BatchMode=yes : si une clé demande une passphrase, ssh échoue au lieu d'attendre.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="$HERE/out"; mkdir -p "$OUT"
SSH="ssh -o BatchMode=yes -o ConnectTimeout=15"
DB="${DB:-intellixcrm}"

for host in intellix-canada intellix-france; do
  if ! $SSH "$host" true 2>"$OUT/$host.ssh_err"; then
    echo "!! $host : connexion refusée (passphrase ou clé ?) — voir $OUT/$host.ssh_err"
  fi
done

echo "== Canada : requêtes SQL (transaction lecture seule)"
$SSH intellix-canada \
  "sudo -u postgres env PGOPTIONS='-c default_transaction_read_only=on' psql -X -d $DB -f -" \
  < "$HERE/01_canada_lieux.sql" > "$OUT/canada_sql.txt" 2>&1

echo "== Canada + doorway-vps : crontabs, timers, n8n, logs"
for host in intellix-canada intellix-france; do
  $SSH "$host" 'bash -s' > "$OUT/${host}_systeme.txt" 2>&1 <<'EOF'
echo "### host: $(hostname) — $(date -Is)"
echo "### crontab root";  sudo crontab -l 2>&1
for u in odoo www-data ubuntu n8n; do echo "### crontab $u"; sudo crontab -l -u "$u" 2>&1; done
echo "### /etc/crontab + /etc/cron.d";  sudo cat /etc/crontab 2>&1; sudo grep -Hv '^\s*#' /etc/cron.d/* 2>/dev/null
echo "### /etc/cron.{hourly,daily}"; ls -la /etc/cron.hourly /etc/cron.daily 2>&1
echo "### systemd timers"; systemctl list-timers --all --no-pager 2>&1
echo "### scripts qui parlent à Odoo (xmlrpc/jsonrpc/coins.property)"
sudo grep -rIlE "coins\.property|onboarding_status|xmlrpc|execute_kw|/jsonrpc" \
  /root /opt /home /var/www /srv /usr/local/bin /etc/cron.d 2>/dev/null \
  | grep -vE "/(node_modules|\.git|site-packages|dist-packages|odoo-server/odoo|odoo/addons)/" | head -100
echo "### n8n (docker ou service)"
sudo docker ps --format '{{.Names}} {{.Image}} {{.Status}}' 2>&1 | grep -i n8n
systemctl status n8n --no-pager 2>&1 | head -5
echo "### Odoo : crons en base et état (instance locale éventuelle)"
sudo -u postgres env PGOPTIONS='-c default_transaction_read_only=on' psql -X -Atc \
  "select datname from pg_database where not datistemplate" 2>&1
EOF
done

echo "== Canada : logs Odoo (écritures RPC et portail sur coins.property, 7 jours)"
$SSH intellix-canada 'bash -s' > "$OUT/canada_logs.txt" 2>&1 <<'EOF'
for f in /var/log/odoo/*.log /var/log/odoo/*.log.1; do
  [ -f "$f" ] || continue
  echo "### $f"
  sudo grep -nE "coins\.property|/partenaire/|/xmlrpc|/jsonrpc|/web/dataset/call_kw/coins\.property" "$f" \
    | grep -vE "GET /api/coins-marocain/photos" | tail -400
done
sudo zgrep -hE "POST /partenaire/" /var/log/odoo/*.gz 2>/dev/null | tail -100
EOF

echo "== doorway-vps : ces lieux existent-ils sur l'ancienne base ? + crons Odoo désactivés ?"
$SSH intellix-france 'bash -s' > "$OUT/france_odoo.txt" 2>&1 <<'EOF'
for db in $(sudo -u postgres psql -X -Atc "select datname from pg_database where not datistemplate and datname not in ('postgres')"); do
  echo "### base $db"
  sudo -u postgres env PGOPTIONS='-c default_transaction_read_only=on' psql -X -d "$db" -c \
   "select id,name,active,state,onboarding_status,write_date from coins_property
     where lower(name) ~ '(asrari|ysabella|nougat)' order by id" 2>&1 | head -30
  sudo -u postgres env PGOPTIONS='-c default_transaction_read_only=on' psql -X -d "$db" -c \
   "select c.id,c.cron_name,c.active,c.nextcall,c.lastcall from ir_cron c where c.active order by c.nextcall" 2>&1 | head -60
done
systemctl is-active odoo odoo-server 2>&1
EOF

echo "Terminé. Fichiers : $OUT"
ls -la "$OUT"
