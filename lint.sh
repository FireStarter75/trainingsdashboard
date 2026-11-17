#!/bin/bash
# Statische controles op de frontend, vóór een rebuild.
# node --check vindt alleen syntaxfouten; deze twee vangen wat daar doorheen glipt:
#   - DOM-ids die het JS opzoekt maar die niet in de HTML staan
#   - functies en constanten die worden aangeroepen maar nergens gedefinieerd zijn
#     (een ReferenceError die pas bij gebruik opduikt, niet bij het laden)
set -e
cd /mnt/user/appdata/garmin-dashboard
fail=0
echo "=== syntax ==="
docker run --rm -v "$PWD/app:/w" --entrypoint node garmin-mcp-endurance:latest --check /w/static/app.js \
  && echo "  app.js OK" || fail=1
docker run --rm -v "$PWD/app:/w" --entrypoint node garmin-mcp-endurance:latest --check /w/static/coach.js \
  && echo "  coach.js OK" || fail=1
docker run --rm -v "$PWD/app:/w" --entrypoint python garmin-mcp-taxuspt:latest \
  -m py_compile /w/app.py /w/plan.py /w/store.py /w/adapt.py /w/auth.py /w/mcp_client.py /w/scheduler.py /w/coach.py \
  && echo "  python OK" || fail=1
echo "=== DOM-ids ==="
docker run --rm -v "$PWD/app:/w" -v "$PWD:/s" --entrypoint python garmin-mcp-taxuspt:latest /s/tools-idcheck.py || fail=1
echo "=== niet-gedefinieerde namen ==="
docker run --rm -v "$PWD/app:/w" -v "$PWD:/s" --entrypoint python garmin-mcp-taxuspt:latest /s/tools-jscheck.py || fail=1
[ "$fail" = "0" ] && echo "=== alles schoon ===" || { echo "=== PROBLEMEN GEVONDEN ==="; exit 1; }
