#!/usr/bin/env bash
# Contrôle automatique de la plateforme OPCA v2. LECTURE SEULE : ne modifie ni base, ni conteneur.
# Code retour : 0 = tout OK, 1 = au moins un WARN, 2 = au moins un FAIL
set -u
VARS="${OPCA_VARS:-$HOME/projet/v2/vars.sh}"
DIR="${OPCA_CHECK_DIR:-$HOME/projet/v2/checks}"
SCHED="${OPCA_SCHED:-opca_airflow-airflow-scheduler-1}"
DAG="${OPCA_DAG:-opca_pipeline_horaire_v2}"
PGC="${OPCA_PG_CONTAINER:-opca_pg_v2}"
NEW_CONT="${OPCA_NEW_CONTAINERS:-opca_pg_v2 opca_api_v2 opca_dashboard_v2 opca_grafana_v2 opca_airflow-airflow-scheduler-1 opca_airflow-airflow-webserver-1}"
OLD_CONT="${OPCA_OLD_CONTAINERS:-opca_airflow-airflow-postgres-1}"
ALLOWED_USERS="${OPCA_ALLOWED_USERS:-opca_app grafana_ro opca_admin}"
URLS="${OPCA_URLS:-http://127.0.0.1:8003/docs http://127.0.0.1:8503 http://127.0.0.1:3001/api/health}"
BKP_DIR="${OPCA_BACKUP_DIR:-$HOME/projet/backups/opca_v2}"
FRESH_WARN=75; FRESH_FAIL=130      # minutes depuis la dernière bougie (collecte horaire)
GAP_WARN=10;   GAP_FAIL=70         # écart max entre deux bougies sur 48 h (minutes)
ROWS_WARN=270; ROWS_FAIL=240       # bougies sur 24 h (attendu ~288 moins la collecte en attente)
PARITY_WARN=24                     # écart de lignes toléré avec l'ancienne base

mkdir -p "$DIR"; LOG="$DIR/check.log"
NOK=0; NWARN=0; NFAIL=0
say(){ echo "$*"; }
ok(){ NOK=$((NOK+1)); say "[OK]   $*"; }
warn(){ NWARN=$((NWARN+1)); say "[WARN] $*"; }
fail(){ NFAIL=$((NFAIL+1)); say "[FAIL] $*"; }
isnum(){ case "${1:-}" in ''|*[!0-9]*) return 1;; *) return 0;; esac; }
chk_max(){ local v=$1 w=$2 f=$3; shift 3
  if ! isnum "$v"; then fail "$* (valeur illisible)"; return; fi
  if [ "$v" -ge "$f" ]; then fail "$*"; elif [ "$v" -ge "$w" ]; then warn "$*"; else ok "$*"; fi; }
chk_min(){ local v=$1 w=$2 f=$3; shift 3
  if ! isnum "$v"; then fail "$* (valeur illisible)"; return; fi
  if [ "$v" -lt "$f" ]; then fail "$*"; elif [ "$v" -lt "$w" ]; then warn "$*"; else ok "$*"; fi; }

say "===== Contrôle OPCA $(date -u '+%Y-%m-%d %H:%M:%S') UTC ====="
# shellcheck disable=SC1090
source "$VARS" 2>/dev/null || { fail "impossible de charger $VARS"; exit 2; }

say "--- Conteneurs v2 ---"
for c in $NEW_CONT; do
  st=$(docker inspect -f '{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{end}}' "$c" 2>/dev/null | xargs)
  case "$st" in
    "running"|"running healthy") ok "$c : $st";;
    "") fail "$c : introuvable";;
    *) fail "$c : $st";;
  esac
done
say "--- Existant (ne doit pas avoir bougé) ---"
for c in $OLD_CONT; do
  st=$(docker inspect -f '{{.State.Status}}' "$c" 2>/dev/null | xargs)
  [ "$st" = "running" ] && ok "$c : running" || warn "$c : ${st:-introuvable}"
done

say "--- DAG $DAG ---"
RUNS=$(docker exec "$SCHED" airflow dags list-runs -d "$DAG" 2>/dev/null | awk -F'|' 'NR>2 {gsub(/ /,"",$3); if ($3!="") print $3}' | head -12)
if [ -z "$RUNS" ]; then fail "aucune exécution lisible du DAG"; else
  N=$(echo "$RUNS" | wc -l); NF=$(echo "$RUNS" | grep -c failed || true); LAST=$(echo "$RUNS" | head -1)
  [ "$NF" -eq 0 ] && ok "$N dernières exécutions sans échec (dernière : $LAST)" || fail "$NF échec(s) sur les $N dernières exécutions"
fi

say "--- Base de données ---"
if [ "$(newsql "select 1" 2>/dev/null | tr -d '[:space:]')" != "1" ]; then
  fail "nouvelle base injoignable"
else
  ok "nouvelle base joignable"
  while IFS='|' read -r s age; do [ -z "$s" ] && continue
    chk_max "$age" $FRESH_WARN $FRESH_FAIL "série $s : dernière bougie il y a ${age} min"
  done < <(newsql "select instrument_id||'/'||plateforme_id, round(extract(epoch from ((now() at time zone 'utc') - max(date_heure)))/60)::int from serie_prix group by instrument_id, plateforme_id order by 1")
  while IFS='|' read -r s gap; do [ -z "$s" ] && continue
    chk_max "${gap:-0}" $GAP_WARN $GAP_FAIL "série $s : plus grand écart sur 48 h = ${gap:-0} min"
  done < <(newsql "select instrument_id||'/'||plateforme_id, round(max(extract(epoch from ecart))/60)::int from (select instrument_id, plateforme_id, date_heure - lag(date_heure) over (partition by instrument_id, plateforme_id order by date_heure) as ecart from serie_prix where date_heure > (now() at time zone 'utc') - interval '48 hours') t group by instrument_id, plateforme_id order by 1")
  while IFS='|' read -r s n; do [ -z "$s" ] && continue
    chk_min "$n" $ROWS_WARN $ROWS_FAIL "série $s : $n bougies sur 24 h"
  done < <(newsql "select instrument_id||'/'||plateforme_id, count(*) from serie_prix where date_heure > (now() at time zone 'utc') - interval '24 hours' group by instrument_id, plateforme_id order by 1")
  D=$(newsql "select count(*) - count(distinct (instrument_id, plateforme_id, date_heure, pas_temps)) from serie_prix" | tr -d '[:space:]')
  [ "$D" = "0" ] && ok "aucun doublon dans serie_prix" || fail "doublons dans serie_prix : ${D:-?}"
  IFS='|' read -r page pdup < <(newsql "select round(extract(epoch from ((now() at time zone 'utc') - max(date_heure)))/60)::int, count(*) - count(distinct date_heure) from prediction_modele where horizon_prediction <> '1 pas de temps'")
  chk_max "$page" $FRESH_WARN $FRESH_FAIL "prédictions : dernière il y a ${page} min"
  [ "${pdup:-x}" = "0" ] && ok "aucun doublon de date dans prediction_modele" || fail "doublons dans prediction_modele : ${pdup:-?}"
  if [ "${OPCA_PARITY:-0}" = 1 ] && type oldsql >/dev/null 2>&1; then
    declare -A OLDN; Q="select instrument_id||'/'||plateforme_id, count(*) from serie_prix group by 1 order by 1"
    while IFS='|' read -r s n; do [ -n "$s" ] && OLDN[$s]=$n; done < <(oldsql "$Q")
    while IFS='|' read -r s n; do [ -z "$s" ] && continue
      o=${OLDN[$s]:-0}; d=$(( n > o ? n - o : o - n ))
      [ "$d" -le $PARITY_WARN ] && ok "parité ancienne/nouvelle base, série $s : écart $d" || warn "parité ancienne/nouvelle base, série $s : écart $d lignes"
    done < <(newsql "$Q")
  fi
  say "--- Connexions à la nouvelle base (24 h) ---"
  BAD=""
  for u in $(docker logs --since 24h "$PGC" 2>&1 | grep "connection authorized" | grep -oE "user=[^ ]+" | sort -u | cut -d= -f2); do
    case " $ALLOWED_USERS " in *" $u "*) ;; *) BAD="$BAD $u";; esac
  done
  [ -z "$BAD" ] && ok "seuls les comptes attendus se sont connectés" || fail "comptes inattendus connectés :$BAD"
fi

say "--- Services HTTP ---"
for u in $URLS; do
  c=$(curl -s -o /dev/null -w '%{http_code}' --max-time 8 "$u" 2>/dev/null)
  [ "$c" = "200" ] && ok "$u : 200" || fail "$u : ${c:-000}"
done

say "--- Ressources ---"
chk_min "$(free -m | awk '/^Mem:/ {print $7}')" 1024 512 "mémoire disponible : $(free -m | awk '/^Mem:/ {print $7}') Mo"
U=$(df --output=pcent / | tail -1 | tr -dc '0-9')
chk_max "$U" 85 95 "disque / utilisé à ${U} %"
if [ -n "$(find "$BKP_DIR" -name '*.dump' -mmin -1560 2>/dev/null | head -1)" ]; then ok "sauvegarde de la nouvelle base < 26 h"
else warn "aucune sauvegarde de la nouvelle base < 26 h (dans $BKP_DIR)"; fi

say "===== Résumé : $NOK OK, $NWARN WARN, $NFAIL FAIL ====="
echo "$(date -u '+%F %T') UTC  OK=$NOK WARN=$NWARN FAIL=$NFAIL" > "$DIR/last_status.txt"
[ -n "${OPCA_ALERT_CMD:-}" ] && [ "$NFAIL" -gt 0 ] && eval "$OPCA_ALERT_CMD" || true
[ "$NFAIL" -gt 0 ] && exit 2; [ "$NWARN" -gt 0 ] && exit 1; exit 0
