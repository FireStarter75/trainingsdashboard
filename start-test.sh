#!/bin/bash
# Start de TESTOMGEVING van het trainingsdashboard.
#
# Loopt naast productie (poort 8091 i.p.v. 8090) en hangt onder /test:
# de container krijgt DASH_URL_PREFIX=/test en de Cloudflare-tunnel routeert
# dash.veldhuizen.us/test* hierheen (cf-test-expose.sh).
#
# Eigen data: een kopie van data/, zodat testen nooit in productiedata
# schrijven. Eerste start kopieert; daarna leeft de test-databank eigenwijs.
set -e
BASE=/mnt/user/appdata/garmin-dashboard
source /mnt/user/appdata/garmin-mcp/.env
source "$BASE/.env"
# Token van de coach-brug, zodat de chat ook in de testomgeving werkt.
source /mnt/user/appdata/garmin-coach/.env

if [ ! -f "$BASE/data-test/dashboard.db" ]; then
  mkdir -p "$BASE/data-test"
  cp -a "$BASE/data/." "$BASE/data-test/"
  echo "  test-data gekopieerd van data/ (eenmalig)"
fi

docker network inspect garmin-net >/dev/null 2>&1 || docker network create garmin-net

docker rm -f garmin-dashboard-test 2>/dev/null || true

docker run -d --name garmin-dashboard-test \
  --restart unless-stopped \
  --network garmin-net \
  -p 8091:8080 \
  -e TZ=Europe/Amsterdam \
  -e DASH_DATA_DIR=/data \
  -e GPX_DIR=/gpx \
  -e CACHE_TTL=900 \
  -e DASH_URL_PREFIX=/test \
  -e DASH_PASSWORD="$DASH_PASSWORD" \
  -e DASH_SECRET="$DASH_SECRET" \
  -e DASH_SESSION_DAYS=60 \
  -e MCP_TAXUSPT_URL=http://192.168.0.20:8000/mcp \
  -e MCP_TAXUSPT_TOKEN="$GARMIN_MCP_HTTP_TOKEN_TAXUSPT" \
  -e MCP_ENDURANCE_URL=http://192.168.0.20:8001/mcp \
  -e MCP_ENDURANCE_TOKEN="$GARMIN_MCP_HTTP_TOKEN_ENDURANCE" \
  -e COACH_URL=http://garmin-coach:8099 \
  -e COACH_TOKEN="$COACH_TOKEN" \
  -e COACH_MODEL=mistral-medium-3.5 \
  -v "$BASE/data-test:/data" \
  -v /mnt/user/appdata/garmin-mcp/gpx:/gpx:ro \
  garmin-dashboard:test

sleep 3
docker ps --filter name=garmin-dashboard-test --format '{{.Names}}  {{.Status}}  {{.Ports}}'
