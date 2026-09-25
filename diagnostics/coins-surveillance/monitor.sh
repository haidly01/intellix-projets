#!/usr/bin/env bash
# Surveillance LECTURE SEULE — disparition des lieux Coins Marocain (ids 19, 24, 28).
# Compatible bash 3.2 (macOS). Uniquement : curl GET (+ -D pour lire les en-têtes),
# et un SELECT psql en transaction read-only via ssh. Aucune écriture distante.
#
# Lancer (48 h, toutes les 10 min, Mac maintenu éveillé) :
#   bash diagnostics/coins-surveillance/monitor.sh start
# Un seul passage (test / empreinte) :
#   bash diagnostics/coins-surveillance/monitor.sh once
# Arrêter :
#   bash diagnostics/coins-surveillance/monitor.sh stop
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
LOG="$HERE/log.csv"
CAP="$HERE/captures"
STATE="$HERE/.last_presence"
PIDF="$HERE/monitor.pid"
INTERVAL="${INTERVAL:-600}"          # 10 min
DURATION="${DURATION:-172800}"       # 48 h
DB="${DB:-intellixcrm}"
SITE="https://coinsmarocain.com"
# Origines comparées par GET direct (Host: coinsmarocain.com, sans passer par Cloudflare).
# Format "nom=ip[:port]" séparé par des espaces. Ajouter la copie de secours si elle a
# sa propre IP/port, ex. : ORIGINS="canada=173.209.51.190 france=187.124.50.69 secours=173.209.51.190:8443"
ORIGINS="${ORIGINS:-canada=173.209.51.190 france=187.124.50.69}"
URLS="listing=/villas-riads-marrakech.html
asrari=/lieux/riad-asrari-medina-marrakech.html
ysabella=/lieux/riad-medina-marrakech-la-casa-ysabella.html
nougat=/lieux/chateau-nougat.html
api=/api/coins-marocain/proprietes.json"
UA="coins-surveillance/1.0 (lecture seule)"
mkdir -p "$CAP"

sha() { shasum -a 256 "$1" 2>/dev/null | cut -c1-16; }
hdr() { grep -i "^$2:" "$1" 2>/dev/null | tail -1 | cut -d: -f2- | tr -d '\r,' | sed 's/^ *//'; }
has() { grep -qiE "$2" "$1" 2>/dev/null && echo OUI || echo NON; }
# Masque jetons portail, paramètres token=, valeurs de cookies.
mask() {
  sed -E -e 's#(/partenaire/)[A-Za-z0-9_-]{12,}#\1***MASQUE***#g' \
         -e 's#([?&](token|access_token|key)=)[^&"'"'"' ]+#\1***MASQUE***#g' \
         -e 's#^([Ss]et-[Cc]ookie: *[^=]+=)[^;]*#\1***MASQUE***#' "$1"
}

db_state() {
  ssh -o BatchMode=yes -o ConnectTimeout=15 intellix-canada \
    "sudo -u postgres env PGOPTIONS='-c default_transaction_read_only=on' psql -X -At -F: -d $DB -c \
     \"SELECT id, state, onboarding_status, active FROM coins_property WHERE id IN (19,24,28) ORDER BY id\"" \
    2>/dev/null | tr '\n' ' ' | sed 's/ $//'
}

one_pass() {
  local ts_utc ts_mar tmp db line key path body head code
  ts_utc="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  ts_mar="$(TZ=Africa/Casablanca date +%Y-%m-%dT%H:%M:%S%z)"
  tmp="$(mktemp -d)"
  db="$(db_state)"; [ -z "$db" ] && db="ERREUR_SSH_OU_SQL"
  [ -f "$LOG" ] || echo "utc,marrakech,page,http,cf_cache_status,age,cf_ray,last_modified,etag,server,origine,asrari,ysabella,nougat,sha256_16,db_19_24_28" > "$LOG"
  echo "$URLS" | while IFS='=' read -r key path; do
    [ -n "$key" ] || continue
    body="$tmp/$key.pub.body"; head="$tmp/$key.pub.head"
    code="$(curl -sS -L --max-time 30 -A "$UA" -D "$head" -o "$body" -w '%{http_code}' "$SITE$path" 2>/dev/null)"
    # Empreinte : même corps que quelle origine (GET direct, sans Cloudflare) ?
    origin=""
    for o in $ORIGINS; do
      oname="${o%%=*}"; oaddr="${o#*=}"; oip="${oaddr%%:*}"; oport="443"
      [ "$oaddr" != "$oip" ] && oport="${oaddr#*:}"
      ob="$tmp/$key.$oname.body"
      curl -sS -k --max-time 30 -A "$UA" --resolve "coinsmarocain.com:$oport:$oip" \
        -o "$ob" "https://coinsmarocain.com:$oport$path" 2>/dev/null
      [ -s "$ob" ] && [ "$(sha "$ob")" = "$(sha "$body")" ] && origin="${origin:+$origin+}$oname"
    done
    [ -z "$origin" ] && origin="aucune_egale"
    if [ "$code" = "000" ] || [ ! -s "$body" ]; then a=ERR; y=ERR; n=ERR   # panne réseau : pas une disparition
    else a="$(has "$body" asrari)"; y="$(has "$body" ysabella)"; n="$(has "$body" nougat)"; fi
    line="$ts_utc,$ts_mar,$key,$code,$(hdr "$head" cf-cache-status),$(hdr "$head" age),$(hdr "$head" cf-ray),\"$(hdr "$head" last-modified)\",$(hdr "$head" etag),$(hdr "$head" server),$origin,$a,$y,$n,$(sha "$body"),\"$db\""
    echo "$line" >> "$LOG"
    # Capture si la présence d'un lieu change pour cette page.
    now="$key:$a$y$n"
    prev="$(grep "^$key:" "$STATE" 2>/dev/null)"
    [ "$a" = ERR ] && continue
    if [ -n "$prev" ] && [ "$prev" != "$now" ]; then
      stamp="$(date -u +%Y%m%dT%H%M%SZ)_$key"
      mask "$body" > "$CAP/$stamp.html"
      mask "$head" > "$CAP/$stamp.headers.txt"
      for o in $ORIGINS; do oname="${o%%=*}"; [ -s "$tmp/$key.$oname.body" ] && mask "$tmp/$key.$oname.body" > "$CAP/$stamp.origine_$oname.html"; done
      { echo "precedent=$prev actuel=$now"; echo "db=$db"; echo "$line"; } > "$CAP/$stamp.resume.txt"
      echo "!! CHANGEMENT $key : $prev -> $now (capture $CAP/$stamp.*)"
    fi
    { grep -v "^$key:" "$STATE" 2>/dev/null; echo "$now"; } > "$STATE.tmp" && mv "$STATE.tmp" "$STATE"
  done
  rm -rf "$tmp"
}

case "${1:-once}" in
  once) one_pass; tail -n 6 "$LOG" ;;
  start)
    if [ -f "$PIDF" ] && kill -0 "$(cat "$PIDF")" 2>/dev/null; then echo "déjà lancé (pid $(cat "$PIDF"))"; exit 1; fi
    nohup bash "$0" loop > "$HERE/monitor.out" 2>&1 &
    echo $! > "$PIDF"; echo "lancé pid $(cat "$PIDF") — log : $LOG" ;;
  loop)
    caffeinate -i -w $$ >/dev/null 2>&1 &   # garde le Mac éveillé tant que la boucle vit
    end=$(( $(date +%s) + DURATION ))
    while [ "$(date +%s)" -lt "$end" ]; do one_pass; sleep "$INTERVAL"; done
    rm -f "$PIDF" ;;
  stop)
    if [ -f "$PIDF" ]; then pkill -P "$(cat "$PIDF")" 2>/dev/null; kill "$(cat "$PIDF")" 2>/dev/null; rm -f "$PIDF"; echo "arrêté"; else echo "pas de surveillance en cours"; fi ;;
  *) echo "usage: $0 once|start|stop" ;;
esac
