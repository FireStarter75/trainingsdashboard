#!/bin/bash
# Start het trainingsdashboard.
set -e
BASE=/mnt/user/appdata/garmin-dashboard
source /mnt/user/appdata/garmin-mcp/.env
source "$BASE/.env"
# Token van de coach-brug; die container staat in /mnt/user/appdata/garmin-coach.
source /mnt/user/appdata/garmin-coach/.env

# Eigen netwerk, zodat het dashboard de coach op naam kan vinden zonder dat die
# aan het LAN hangt.
docker network inspect garmin-net >/dev/null 2>&1 || docker network create garmin-net

docker rm -f garmin-dashboard 2>/dev/null || true

docker run -d --name garmin-dashboard \
  --restart unless-stopped \
  --network garmin-net \
  -p 8090:8080 \
  -e TZ=Europe/Amsterdam \
  -e DASH_DATA_DIR=/data \
  -e GPX_DIR=/gpx \
  -e CACHE_TTL=900 \
  -e DASH_PASSWORD="$DASH_PASSWORD" \
  -e DASH_SECRET="$DASH_SECRET" \
  -e DASH_SESSION_DAYS=60 \
  -e MCP_TAXUSPT_URL=http://192.168.0.20:8000/mcp \
  -e MCP_TAXUSPT_TOKEN="$GARMIN_MCP_HTTP_TOKEN_TAXUSPT" \
  -e MCP_ENDURANCE_URL=http://192.168.0.20:8001/mcp \
  -e MCP_ENDURANCE_TOKEN="$GARMIN_MCP_HTTP_TOKEN_ENDURANCE" \
  -e COACH_URL=http://garmin-coach:8099 \
  -e COACH_TOKEN="$COACH_TOKEN" \
  -e COACH_MODEL=sonnet \
  -v "$BASE/data:/data" \
  -v /mnt/user/appdata/garmin-mcp/gpx:/gpx:ro \
  garmin-dashboard:latest

sleep 3
docker ps --filter name=garmin-dashboard --format '{{.Names}}  {{.Status}}  {{.Ports}}'
