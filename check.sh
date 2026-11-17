#!/bin/bash
# Controleert of het dashboard werkt EN of elk bestand dat de pagina opvraagt bestaat.
# Die laatste check ontbrak eerst, waardoor een 404 op Chart.js een lege pagina gaf.
BASE=/mnt/user/appdata/garmin-dashboard
source "$BASE/.env"
HOST=${1:-http://127.0.0.1:8090}
CK=$(mktemp)
trap 'rm -f "$CK" "$CK.html"' EXIT

echo "=== container ==="
docker ps --filter name=garmin-dashboard --format '  {{.Names}}  {{.Status}}'

echo "=== login ==="
code=$(curl -4 -s -o /dev/null -w '%{http_code}' -m 25 "$HOST/")
[ "$code" = "302" ] && echo "  OK   / vraagt login (302)" || echo "  LET OP  / gaf $code, verwacht 302"
code=$(curl -4 -s -o /dev/null -w '%{http_code}' -m 25 "$HOST/api/state")
[ "$code" = "401" ] && echo "  OK   /api/state weigert zonder sessie (401)" || echo "  LET OP  /api/state gaf $code, verwacht 401"
curl -4 -s -m 25 -c "$CK" -o /dev/null -X POST "$HOST/login" -d "password=$DASH_PASSWORD&next=/"
code=$(curl -4 -s -o /dev/null -w '%{http_code}' -m 25 -b "$CK" "$HOST/")
[ "$code" = "200" ] && echo "  OK   inloggen werkt" || echo "  FOUT inloggen gaf $code"

echo "=== data ==="
curl -4 -s -m 180 -b "$CK" "$HOST/api/state" \
  | jq -r '"  dagen tot race: \(.days_to_race)  |  weken: \(.plan.weeks_total)",
           (.metrics | to_entries[] | if .value.ok then "  OK   \(.key)" else "  FOUT \(.key): \(.value.error[0:70])" end)' \
  2>/dev/null || echo "  FOUT kon /api/state niet lezen"

echo "=== elk bestand dat de pagina opvraagt ==="
curl -4 -s -m 25 -b "$CK" "$HOST/" > "$CK.html"
# preconnect/dns-prefetch zijn verbindingshints, geen bestanden: een bare origin
# hoort 404 te geven en dat is geen fout.
grep -oE '<link[^>]+>|<script[^>]+>' "$CK.html" | grep -v 'rel="\(preconnect\|dns-prefetch\)"'   | grep -oE '(src|href)="[^"]+"' | sed 's/^[a-z]*="//;s/"$//' | sort -u | while read -r u; do
  case "$u" in
    http*) full="$u" ;;
    /static/*) full="$HOST$u" ;;
    *) continue ;;
  esac
  code=$(curl -4 -s -o /dev/null -w '%{http_code}' -m 25 -b "$CK" "$full")
  [ "$code" = "200" ] && echo "  OK   $u" || echo "  FOUT HTTP $code  $u"
done

echo "=== coach ==="
docker ps --filter name=garmin-coach --format '  {{.Names}}  {{.Status}}'
# Structurele grens: de CLI mag geen enkele tool hebben. Staat die vlag er niet
# meer, dan is de bot niet langer begrensd en moet dat opvallen.
for flag in '"--tools", ""' '"--safe-mode"' '"--strict-mcp-config"' '"--permission-prompts", "none"'; do
  if docker exec garmin-coach grep -qF "$flag" /app/server.py 2>/dev/null; then
    echo "  OK   grens aanwezig: $flag"
  else
    echo "  FOUT grens ONTBREEKT: $flag"
  fi
done
curl -4 -s -m 90 -b "$CK" "$HOST/api/chat/health" \
  | jq -r 'if .ok then "  OK   brug bereikbaar, CLI \(.bridge.cli), inloggegevens \(.bridge.credentials_present)"
           else "  FOUT brug: \(.error // .bridge.error)" end' 2>/dev/null \
  || echo "  FOUT kon /api/chat/health niet lezen"
curl -4 -s -m 200 -b "$CK" "$HOST/api/chat/opening" \
  | jq -r 'if .enabled then "  OK   opening: \(.text[0:70])…" else "  FOUT coach staat uit: \(.reason)" end' 2>/dev/null \
  || echo "  FOUT kon /api/chat/opening niet lezen"
for id in coachFab coachPanel coachLog coachInput rnFab rnStage; do
  grep -q "id=\"$id\"\|class=\"rn $id\"" "$CK.html" && echo "  OK   $id staat in de pagina" \
    || echo "  FOUT $id ontbreekt in de pagina"
done
