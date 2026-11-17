#!/bin/bash
# Zet het dashboard achter de Cloudflare-tunnel op dash.veldhuizen.us.
# Volgt dezelfde logica als cf-tunnel-manager: ingress-regel (catch-all blijft
# laatste) plus een proxied CNAME.
set -euo pipefail
set -a; source /mnt/user/appdata/cf-tunnel-manager/.env; set +a
API=https://api.cloudflare.com/client/v4
H="Authorization: Bearer $CF_API_TOKEN"
SUB=${1:-dash}
HOST="$SUB.$BASE_DOMAIN"
SVC="http://192.168.0.20:8090"
TARGET="$CF_TUNNEL_ID.cfargotunnel.com"

cfg=$(curl -sf -H "$H" "$API/accounts/$CF_ACCOUNT_ID/cfd_tunnel/$CF_TUNNEL_ID/configurations" --max-time 20 | jq '.result.config')
cfg=$(printf '%s' "$cfg" | jq --arg h "$HOST" --arg s "$SVC" '
  .ingress = ([ .ingress[] | select(has("hostname") and .hostname != $h) ]
            + [ { hostname: $h, service: $s } ]
            + [ .ingress[] | select(has("hostname") | not) ])')

echo "=== ingress ==="
printf '%s' "$cfg" | jq -r '.ingress[] | "  \(.hostname // "(catch-all)")  ->  \(.service)"'

printf '%s' "$cfg" | jq '{config: .}' | curl -sf -X PUT -H "$H" -H "Content-Type: application/json" \
  "$API/accounts/$CF_ACCOUNT_ID/cfd_tunnel/$CF_TUNNEL_ID/configurations" --data @- --max-time 20 \
  | jq -r '"  tunnel bijgewerkt: \(.success)"'

rec=$(curl -sf -H "$H" "$API/zones/$CF_ZONE_ID/dns_records?name=$HOST" --max-time 20 | jq -r '.result[0].id // empty')
body=$(jq -nc --arg n "$HOST" --arg c "$TARGET" '{type:"CNAME",name:$n,content:$c,proxied:true,ttl:1}')
if [ -n "$rec" ]; then
  curl -sf -X PATCH -H "$H" -H "Content-Type: application/json" \
    "$API/zones/$CF_ZONE_ID/dns_records/$rec" --data "$body" --max-time 20 \
    | jq -r '"  DNS \(.result.name) bijgewerkt"'
else
  curl -sf -X POST -H "$H" -H "Content-Type: application/json" \
    "$API/zones/$CF_ZONE_ID/dns_records" --data "$body" --max-time 20 \
    | jq -r '"  DNS \(.result.name) aangemaakt"'
fi
echo "  -> https://$HOST"
