#!/bin/bash
# Zet de TESTOMGEVING van het dashboard achter de Cloudflare-tunnel op
# https://dash.veldhuizen.us/test (pad-routering naar de test-container op
# poort 8091; productie op / blijft gewoon bij poort 8090).
#
# Aanroepen zoals cf-expose.sh; leest hetzelfde env-bestand.
set -euo pipefail
set -a; source /mnt/user/appdata/cf-tunnel-manager/.env; set +a
API=https://api.cloudflare.com/client/v4
H="Authorization: Bearer $CF_API_TOKEN"
HOST="dash.$BASE_DOMAIN"
SUB=${1:-test}
PATH_PREFIX="/${SUB}"
SVC="http://192.168.0.20:8091"
TARGET="$CF_TUNNEL_ID.cfargotunnel.com"

cfg=$(curl -sf -H "$H" "$API/accounts/$CF_ACCOUNT_ID/cfd_tunnel/$CF_TUNNEL_ID/configurations" --max-time 20 | jq '.result.config')
cfg=$(printf '%s' "$cfg" | jq --arg h "$HOST" --arg p "${PATH_PREFIX}*" --arg s "$SVC" '
  # oude regel voor dit pad weg, nieuwe vooraan (voor de gewone hostname-regel)
  .ingress = ([ .ingress[] | select((.hostname // "") != $h or (.path // "") != $p) ]
            | [ { hostname: $h, path: $p, service: $s } ] + .)')
# de regel voor dit pad moet vóór de catch-all én vóór de hostname-zonder-path
cfg=$(printf '%s' "$cfg" | jq --arg h "$HOST" --arg p "${PATH_PREFIX}*" '
  .ingress = ([ .ingress[] | select((.hostname // "") == $h and (.path // "") == $p) ] +
              [ .ingress[] | select((.hostname // "") != $h or (.path // "") != $p) ]) ')

echo "=== ingress ==="
printf '%s' "$cfg" | jq -r '.ingress[] | "  \(.hostname // "(catch-all)")\(.path // "")  ->  \(.service)"'

printf '%s' "$cfg" | jq '{config: .}' | curl -sf -X PUT -H "$H" -H "Content-Type: application/json" \
  "$API/accounts/$CF_ACCOUNT_ID/cfd_tunnel/$CF_TUNNEL_ID/configurations" --data @- --max-time 20 \
  | jq -r '"  tunnel bijgewerkt: \(.success)"'

echo "  -> https://$HOST$PATH_PREFIX"
