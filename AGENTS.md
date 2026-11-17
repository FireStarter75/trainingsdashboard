# Trainingsdashboard — dash.veldhuizen.us

Web-GUI (Flask, Python 3.12), draait als Docker-container `garmin-dashboard`
op Unraid, poort 8090, via Cloudflare bereikbaar als
<https://dash.veldhuizen.us>). Leest twee garmin-mcp-servers uit (8000
taxuspt, 8001 endurance), bouwt een periodiseerd loopplan naar de racedatum,
en schrijft workouts terug naar Garmin Connect. Doel en stand van zaken staan
uitgebreid in `README.md` — lees dat eerst bij inhoudelijke vragen.

## Commands

    bash start.sh      # container (her)starten (maakt garmin-net aan)
    bash rebuild.sh    # image herbouwen na codewijzigingen, daarna start.sh
    bash check.sh [url]   # rooktest: login, data, statische bestanden, coach
    bash lint.sh       # lint

De container wordt lokaal gebouwd; "Force update" in de Unraid-tab doet
niets. Na een wijziging: `rebuild.sh`, daarna `check.sh
https://dash.veldhuizen.us`.

## Vaste regels

- **`data/` is levende data** (SQLite `dashboard.db`, `goal.json`) en staat
  niet in git. Schrijf er nooit testwaarden weg; lees ze alleen.
- **`.env` nooit lezen, kopiëren of weergeven** — en nooit in git.
- **`app/plan.py` is deterministisch**: zelfde doel + zelfde basislijn =
  zelfde plan. Breek die eigenschap niet; nieuwe invoer hoort via
  `data/goal.json` of expliciete parameters te lopen.
- Workouts worden altijd gebouwd met `create_run_interval_workout` (enige
  builder met exacte bpm-grenzen). Aerobe grenzen komen uit de eigen
  drempels (HRmax 191, LTHR 166), niet uit Garmins zones.
- Wijzigingen aan het plan of de API gaan gepaard met een update van
  `README.md`; dat is de documentatie van dit systeem.

## De coach (bot)

De coach draait in een aparte container (`garmin-coach`, broncode in
`/mnt/user/appdata/garmin-coach`, niet in deze repo). Het dashboard praat via
HTTP + token met die brug; de brug roept headless de Vibe CLI aan.

**De veiligheidsopzet is niet onderhandelbaar en nooit verzwakken:**

1. De brug draait headless zonder goedkeuringsmogelijkheid: élke
   tool-aanroep wordt door het goedkeuringsbeleid geweigerd. Voeg nooit
   `--auto-approve`/`--yolo`, een allowlist of een mount van dashboardcode of
   -data in de brugcontainer toe.
2. De brug krijgt alleen tekst binnen en geeft tekst terug; alle acties
   (loggen, week bijstellen) voert `app/coach.py` uit, pas na een klik van de
   gebruiker, en valideert tegen een vaste lijst van vijf soorten.
3. `check.sh` controleert die grenzen structureel; houd die checks werkzaam.

Kennis voor de coach hoort in `app/coach_knowledge.md` (wordt ingebouwd bij
`rebuild.sh`), niet in prompts die per sessie verstuurd worden.
