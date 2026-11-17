# Trainingsdashboard

Web-GUI op **http://192.168.0.20:8090** die je voortgang naar een hardloopdoel
toont en trainingen naar je Garmin kan schrijven.

Gebouwd 2026-10-25. Doel bij oplevering: NN CPC Loop Den Haag, halve marathon,
zondag 14 maart 2027.

## Wat het doet

- Leest uit **garmin-mcp-taxuspt** (8000): activiteiten, VO2max, trainingsstatus,
  raceprognoses, HR-zones, agenda, en het aanmaken/inplannen van workouts.
- Leest uit **garmin-mcp-endurance** (8001): eigen belastingmodel (TSS, CTL/ATL/TSB,
  ACWR), readiness, HRV/rusthartslag/slaap, drempels.
- Bouwt zelf een periodiseerd plan naar de racedatum (`app/plan.py`).
- Knoppen zetten een sessie of een hele week als gestructureerde workout in
  Garmin Connect en plannen die op de agenda, zodat je horloge hem oppakt.

## Het plan

`app/plan.py` is deterministisch: zelfde doel + zelfde basislijn = zelfde plan.
Uitgangspunten bij prioriteit "gezond finishen":

- Alles aeroob: loopblokken op **128-147 bpm**, onder LT1 (149). Wandelpauzes
  op 95-130 bpm. Die grenzen komen uit de eigen drempels (HRmax 191, LTHR 166).
- Run/walk-verhouding schuift mee op van 2:1 naar 9:1 over het plan.
- Elke 4e week is een herstelweek op 75%.
- De langste duurloop komt nooit boven 85% van de verwachte racetijd.
- Fasen: basis 45%, opbouw 35%, piek 20% van het blok, dan 2 weken taper.

Workouts worden altijd gebouwd met `create_run_interval_workout`, want dat is de
enige builder die **exacte bpm-grenzen** accepteert. Garmins named zones zijn te
grof: Z2 is 115-135 (wandeltempo) en Z3 is 136-152, wat over LT1 heen loopt.

## Doel wijzigen

Knop "Doel wijzigen" in de GUI, of `data/goal.json` aanpassen. Naam, datum,
afstand, trainingen per week en prioriteit zijn instelbaar. Het plan wordt
daarna opnieuw opgebouwd. Werkt dus ook voor een volgend doel.

`start_long_min` (de langste sessie die je nu aankan) wordt automatisch uit je
Garmin-historie gehaald, tenzij je `auto_start_long: false` in goal.json zet.

## Scripts

    bash start.sh     # container (her)starten
    bash rebuild.sh   # image herbouwen na codewijziging

## Belangrijk

- **Lokaal gebouwd image.** "Force update" in de Unraid Docker-tab werkt niet.
- **Garmin Coach kan hiermee conflicteren.** Als er nog een Coach-plan actief is,
  plant dat zelf ook workouts op dezelfde dagen. Zet er één uit.
- **Eerste load duurt ~35 seconden** (Garmin-data ophalen), daarna uit cache.
  Cache is 15 minuten; "Verversen" forceert een nieuwe ophaal.
- **Kaarten** komen uit GPX die taxuspt neerzet in `/mnt/user/appdata/garmin-mcp/gpx`.
  Die map is in beide containers gemount. Bestanden worden pas gedownload als het
  dashboard ze opvraagt.
- **Uploads worden gelogd** in `data/dashboard.db` zodat de GUI weet wat al in
  Garmin staat. Verwijder je een workout in Garmin, dan blijft hij hier als
  geüpload staan tot je die regel uit de tabel `uploads` haalt.
- **Alleen LAN.** Niet via Cloudflare ontsloten. De bearer-tokens van de twee
  MCP-servers staan als env-var in deze container.

## Verificatie bij oplevering

- Beide MCP-servers bereikbaar: 157 en 20 tools.
- Alle 7 databronnen leverden data (activiteiten, belasting, readiness,
  gezondheid, drempels, agenda, prognoses).
- 4 GPS-routes omgezet naar polylines (454-579 punten elk).
- Testupload van de sessie op 2026-11-03 geslaagd: workout 1740134762 staat in de
  Garmin-agenda, met loopblokken op 128-147 bpm en herstel op 95-130 bpm.

## Op je telefoon: https://dash.veldhuizen.us

Sinds 2026-10-25 loopt het dashboard ook via de Cloudflare-tunnel, met een eigen
inlog ervoor.

### Inlog

Het dashboard had geen enkele authenticatie; publiek zetten zonder slot zou
betekenen dat iedereen je gezondheidsdata kan lezen en workouts naar je Garmin
kan pushen. Daarom zit er nu een login in de app zelf (`app/auth.py`):

- Wachtwoord staat in `.env` (mode 0600) en in de Unraid-template, gemaskeerd.
- Sessiecookie is HttpOnly, SameSite=Lax, en blijft **60 dagen** staan - je
  telefoon vraagt dus niet elke keer opnieuw. Aanpasbaar met `DASH_SESSION_DAYS`.
- Na 8 foute pogingen per IP volgt 15 minuten blokkade. Achter Cloudflare wordt
  `CF-Connecting-IP` gebruikt, niet het Cloudflare-adres zelf.
- Alle `/api/*` routes geven 401 zonder sessie; `/` leidt naar `/login`.
- Wachtwoord wijzigen: pas `.env` aan en `bash start.sh`.
- `DASH_SECRET` ondertekent de cookies. Wijzig je die, dan logt iedereen uit.

**Niet** gekozen voor Cloudflare Access: het API-token kan de Zero Trust
organisatie-instellingen niet lezen (`Authentication error` op
`/access/organizations`), dus ik kon niet vaststellen of Zero Trust al is
ingericht. Een half-geconfigureerde Access-app die je buitensluit is slechter dan
geen. Je kunt Access er later alsnog voor zetten via het Cloudflare-dashboard;
dat werkt prima naast de app-login en levert dan twee onafhankelijke sloten.

### Let op

- `SESSION_COOKIE_SECURE` staat op 0, zodat de login ook over http op je LAN
  werkt (`http://192.168.0.20:8090`). Gevolg: op de LAN gaat de cookie onversleuteld
  over de lijn. Zet `DASH_COOKIE_SECURE=1` als je alleen nog via https wilt.
- Ontsloten met `cf-expose.sh`, dezelfde logica als cf-tunnel-manager. De route
  is dus ook zichtbaar en te verwijderen in die UI.

### Verificatie van de ontsluiting

Alles getest via Cloudflare, niet alleen lokaal:
`/` geeft 302 naar login, `/api/state` geeft 401 zonder sessie, inloggen geeft
302 met cookie, en daarna leverde `/api/state` de data. Statics 200.

## Opgelost 2026-10-25: lege pagina

Symptoom: "Kon data niet laden: Chart is not defined", niets te zien.

Oorzaak: `index.html` verwees naar `Chart.js/4.4.6/chart.umd.min.js` op cdnjs.
Die **versie** bestaat daar niet (404) - de bestandsnaam was goed, 4.5.1 wel.
De bibliotheek werd dus nooit geladen en `new Chart(...)` gooide een
ReferenceError, die in de ene try/catch om de hele render viel. Gevolg: de
pagina bleef achter de laad-overlay staan.

Drie dingen gewijzigd zodat dit niet herhaalt:

1. Versie naar 4.5.1 (bestaan van elk CDN-bestand nu geverifieerd).
2. `render()` tekent elk onderdeel in zijn eigen try/catch en zet wat faalt in een
   melding bovenaan. Eén kapotte grafiek sloopt niet meer de hele pagina.
   `$('#main').hidden = false` gebeurt nu *voor* het tekenen.
3. `mkChart()` valt netjes terug op een melding als Chart.js ontbreekt, in plaats
   van te crashen.

Daarnaast hangen de statics nu een `?v=<mtime>` mee, zodat een browser na een
update nooit een oude `app.js` uit zijn cache blijft gebruiken.

`check.sh` test dit nu expliciet: het haalt de pagina op en controleert dat
**elk** bestand waar de HTML naar verwijst HTTP 200 geeft, extern en intern. Die
check ontbrak, en daarom kwam dit pas bij jou aan het licht.

    bash check.sh                              # lokaal
    bash check.sh https://dash.veldhuizen.us   # via Cloudflare

## Opgelost 2026-10-25 (2): overlay bleef hangen

Symptoom: alleen "Data ophalen uit Garmin..." te zien, geen foutmelding.

Dat de tekst *onveranderd* bleef was de aanwijzing: elke fout in `load()` zou die
tekst hebben vervangen. Dus de code liep goed, maar de laag-overlay ging nooit weg.

Oorzaak: CSS-cascade. Een author-stylesheet verslaat altijd de UA-stylesheet,
ongeacht specificiteit. Deze twee regels

    .loading{ ... display:grid ... }
    main{ ... display:flex ... }

overruleden dus de ingebouwde browserregel `[hidden]{display:none}`. Daardoor had
`element.hidden = true` geen enkel effect: de overlay bleef over de pagina liggen,
met het dashboard er volledig gerenderd onder. Dezelfde fout zat op `<main>`.

Twee lagen fix:

1. `[hidden]{display:none!important}` bovenaan `style.css`, direct na de reset.
   Dit is de juiste fix en geldt voor elk element met het hidden-attribuut.
2. Een `show(el, on, mode)` helper in `app.js` die zowel het attribuut als
   `style.display` zet, zodat tonen en verbergen niet meer van de CSS afhangt.

### Les voor volgende keer

Beide storingen (eerst Chart.js 404, toen deze) zaten in de **rendering**, niet in
de data of de endpoints. `check.sh` test HTTP-statussen en of elk bestand bestaat,
maar kan niet zien of er daadwerkelijk iets op het scherm komt. Zonder browser is
dat hier niet te verifieren. Bij een volgende wijziging aan de GUI is het sneller
om de pagina zelf te openen en de console te lezen dan om dit server-side te
proberen vast te stellen.

## Opgelost 2026-10-25 (3): kaart vroeg om een API-key

Symptoom: de kaart toonde een melding dat er een API-key nodig is.

Oorzaak: de tegels kwamen van `basemaps.cartocdn.com` (CARTO dark_all). CARTO
vereist daar inmiddels registratie voor. De tegels gaven keurig HTTP 200 met
content-type image/png, maar het waren tegels van 2,5 kB met die tekst erin in
plaats van kaartdata - vandaar dat geen enkele statuscheck dit ving.

Nu: **OpenStreetMap** (`tile.openstreetmap.org`), geen key nodig. Geverifieerd
met de tegel die het loopgebied Leidschendam-Voorburg dekt: 39 kB, echte
kaartdata.

OSM-tegels zijn licht, dus ze worden donker gemaakt met een CSS-filter op
`.leaflet-tile-pane`. Alleen die pane, zodat de routelijnen (overlay-pane) hun
eigen kleur houden. Verder zijn de popups, zoomknoppen en attributie in de
donkere stijl getrokken.

Toegevoegd: de kaart luistert nu op `tileerror`. Falen er vier tegels, dan komt
er een melding boven de kaart in plaats van stilzwijgend een lege ondergrond.

Houd je aan de OSM tile usage policy: dit is persoonlijk gebruik met een handvol
tegels, dat valt ruim binnen wat zij toestaan. Zwaarder gebruik vraagt een eigen
tegelserver of een betaalde provider.

## Routes aan- en uitzetten (2026-10-25)

De kaart heeft nu twee manieren om routes te tonen of te verbergen, die elkaar
spiegelen:

1. **Een laagregelaar op de kaart zelf**, rechtsboven, met een vinkje en een
   kleurstreepje per run. Dat is de ingebouwde `L.control.layers` van Leaflet.
2. **De chips onder de kaart**, elk met een vinkje, een kleurstreepje en een
   zoomknop (het pijltjes-icoon) om op die ene route in te zoomen.

Zet je iets aan of uit in de een, dan volgt de ander. Dat loopt via het
`overlayadd`/`overlayremove`-event van de kaart en een gedeelde `setRoute()`.

Verder:

- **Alles aan / Alles uit / Passend maken** in de kop van de kaartsectie.
  "Passend maken" zoomt naar precies de routes die aan staan.
- De keuze wordt onthouden in `localStorage` (sleutel `routesOff`, alleen de
  uitgezette ids), dus na een herlaad staat je selectie er nog. In een
  privevenster faalt dat stil en staat gewoon alles aan.
- Er worden nu 12 runs opgehaald in plaats van 6.

Tegelijk een bug verholpen die hier zat: `loadRoutes()` hing bij elke aanroep een
nieuwe click-listener aan de chiplijst, dus na een "Verversen" vuurde die dubbel.
De listeners staan nu eenmalig op `document`.

## Opgelost 2026-10-25 (4): projectie was circulair

Symptoom: "als je nu zou starten 2:50" tegen "na het hele plan 2:49". Een minuut
winst over twintig weken, wat niet klopt.

Oorzaak: de twee getallen waren hetzelfde getal. `plan.py` leidde de
piekduurloop af uit de geschatte racetijd:

    peak_long = est_race_min * 0.85          # 170 -> 145

en de frontend "projecteerde" de racetijd door diezelfde formule om te keren:

    const projected = peak / 0.85;           # 145 -> 170

Het resultaat was per definitie gelijk aan het vertrekpunt; de ene minuut was
afronding. De projectie bevatte dus geen informatie.

### Het model nu

Riegel (`T2 = T1 * (D2/D1)^k`) op de langste recente run, met twee verschillende
exponenten. Die exponent zegt hoe hard je terugvalt op de langere afstand, en
daar zit precies de winst van een uithoudingsblok:

| | exponent | snelheidswinst | halve marathon |
|---|---|---|---|
| Nu, ongetraind | 1.15 | - | 3:03 |
| Na het plan | 1.06 | 5% | 2:31 (band 2:26 - 2:36) |

Verwachte winst dus ~32 minuten, en die komt bijna volledig uit minder terugval
over de afstand, niet uit harder lopen. Dat wordt in de GUI ook zo benoemd,
samen met de bandbreedte, zodat het niet als een belofte leest.

De **piekduurloop hangt nu aan de projectie** (85% van 2:31 = 129 min) in plaats
van aan de huidige stand (was 145 min). Je bouwt op naar de race die je straks
loopt, niet naar de race die je nu zou lopen. Omdat de projectie onafhankelijk
wordt berekend, is de cirkel daarmee doorbroken.

De duurloopgrafiek toont nu beide referentielijnen: de verwachte racetijd na het
plan (doorgetrokken streepjes) en wat je nu zou lopen (vage streepjes).

## ACWR-bewaking in de planopbouw (2026-10-25)

Het plan stuurde eerst op een vuistregel (~6% groei per week, elke vierde week
herstel). Nu rekent het expliciet met de **acute:chronische belastingverhouding**:
de belasting van deze week gedeeld door het gemiddelde van de vier weken ervoor.
Drempels gelijkgehouden aan die van de endurance-server: waarschuwing 1,3,
hoog risico 1,5, te weinig prikkel onder 0,8.

### Belasting

Per sessie: minuten x een wegingsfactor (`LOAD_WEIGHTS`): rustig 1,0, duurloop
1,15, versnellingen 1,1, drempel 1,5. **Krachttraining telt niet mee** - de
ACWR-drempels komen uit looponderzoek, en peesbelasting van squats laat zich
niet in loopminuten uitdrukken.

### Twee regimes

Bij een chronische belasting van bijna nul is ACWR betekenisloos: wie terugkomt
van maanden niets heeft per definitie een enorme ratio, hoe voorzichtig hij ook
begint. Daarom:

- **opwarmen** (chronisch onder 60 loopmin/week): sturen op absolute weekgroei,
  maximaal +22% ten opzichte van de zwaarste van de laatste drie weken.
- **normaal**: sturen op ACWR, plafond instelbaar via `acwr_cap` in goal.json.

De weeksprong wordt bewust afgezet tegen de **zwaarste van de laatste drie
weken**, niet tegen de vorige week. Anders straft de regel het terugkeren na een
herstelweek af: daarna is +33% nodig om de lijn op te pakken, terwijl dat volume
al bewezen haalbaar was. Dat is precies wat het plan eerst kapot maakte.

### Hoe het afremt

Een week die over het plafond gaat wordt **opnieuw opgebouwd** met een kortere
duurloop, niet achteraf verkleind. Dat laatste liet de omschrijvingen scheeflopen
("96 min" boven een tekst die 120 minuten beschreef). Alles schaalt mee met de
duurloop, inclusief de drempelsessie - zonder die koppeling bleef een blok van
65 minuten zware arbeid staan terwijl de rest werd afgeremd, en schoot de ratio
er alsnog overheen.

### Wat het kost

Het plafond bepaalt direct hoeveel volume haalbaar is vanaf dit vertrekpunt:

| acwr_cap | piek per week | langste duurloop | weken boven 1,3 |
|---|---|---|---|
| 1,20 | 167 min (~25 km) | 1:24 | 0 |
| 1,25 | 182 min (~28 km) | 1:24 | 0 |
| **1,30 (in gebruik)** | **211 min (~32 km)** | **1:37** | 4 |
| 1,35 | 237 min (~36 km) | 1:55 | 7 |

Aan te passen met `acwr_cap` in `data/goal.json`, of via de API.

In het dashboard staat een grafiek met de geplande ratio per week, de drie
drempellijnen, en de werkelijke ratio uit de endurance-server. Opwarmweken
staan er gestippeld in, met het label erbij dat de ratio daar niets zegt.

## Adaptief plan (2026-10-25)

Het plan stelt zichzelf elke maandagochtend bij op basis van wat er werkelijk is
gebeurd en hoe het herstel ervoor staat.

### Eerst een bug die dit zou breken

De startdatum werd elke keer berekend als "komende maandag". Volgende week zou
het plan dus stilzwijgend een week opschuiven en week 1 verdwijnen. `start_date`
staat nu vast in `goal.json` (2026-10-26).

### Wat er wordt gewogen

Uit Garmin, via de twee MCP-servers:

| Signaal | Drempel | Gevolg |
|---|---|---|
| ACWR | >= 1,5 | x0,70 en kwaliteitssessie eruit |
| ACWR | >= 1,3 | x0,85 |
| ACWR | < 0,8 | x1,05 (ruimte voor meer) |
| Vorm (TSB) | <= -25 | x0,80 en kwaliteitssessie eruit |
| Garmin readiness | REST | x0,70 en kwaliteitssessie eruit |
| Garmin readiness | MODIFY | x0,88 |
| HRV onder basislijn | >= 3 van 7 dagen | x0,85 en kwaliteitssessie eruit |
| Rusthartslag | >= +5 bpm boven basislijn | x0,85 |
| Slaap | < 6 u gemiddeld over 7 dagen | x0,88 |
| Gedaan vs gepland (4 wk) | < 60% | x0,85, niet terugspringen naar de curve |
| Alles groen en >95% gedaan | - | x1,05 |

**De uitkomst is de laagste factor, niet het product.** Vier matige signalen
mogen niet tot een halvering leiden; het zwaarste signaal bepaalt. Ondergrens
0,60 en bovengrens 1,08: ook een slechte week blijft een trainingsweek, en
volledig stilleggen hoort een menselijk besluit te zijn.

Tijdens de opwarmfase (chronische belasting onder 60 loopmin/week) wordt het
ACWR-signaal genegeerd, omdat de ratio daar niets zegt.

### Volgorde

1. Bijstelling toepassen op de komende week (duurloop schalen, eventueel de
   kwaliteitssessie schrappen) en de week opnieuw opbouwen.
2. Daarna pas de ACWR-bewaking. Die kan alleen verder verlagen, nooit een
   verlichting ongedaan maken.

### De planner

`scheduler.py` draait in precies een gunicorn-worker, afgedwongen met een
bestandsvergrendeling (`/data/scheduler.lock`) - anders zou de taak dubbel
draaien. Hij controleert elke 20 minuten of het maandag na 05:00 is en of er
voor deze week al een besluit ligt.

Te sturen met omgevingsvariabelen: `ADAPT_ENABLED` (1/0), `ADAPT_WEEKDAY`
(0 = maandag) en `ADAPT_HOUR`.

Omdat threadnamen in gunicorn niet uitleesbaar zijn, schrijft de planner een
**hartslag** naar de cache. Die staat in `/api/adaptations` en bovenaan het
paneel in de GUI, zodat zichtbaar is dat hij leeft in plaats van aangenomen.

### Handmatig

Knop "Nu opnieuw beoordelen" in het dashboard, of:

    curl -s -X POST -b <sessiecookie> http://192.168.0.20:8090/api/adapt

Elk besluit wordt bewaard in de tabel `adaptations` met de redenen en de
gemeten signalen, zodat terug te zien is waarom een week anders liep.

## Opgelost 2026-10-25 (5): dinsdagen stonden tien weken stil

Symptoom: elke dinsdag 25 minuten, week 1 tot en met 10.

Oorzaak: de rustige run werd berekend als `max(25, duurloop * 0,5)`. Zolang de
duurloop onder de 50 minuten bleef won die ondergrens, dus de helft van het plan
had een identieke dinsdag. Geen ontwerpkeuze maar een artefact.

Twee gevolgen, waarvan het tweede het ernstigst:

1. De rustige runs droegen tien weken niets bij aan de opbouw.
2. Daardoor kwam **alle** volumegroei op de duurloop terecht: week 1 29 min naar
   week 17 97 min, ruim drie keer zoveel. Een duurloop die als enige groeit is
   een bekend blessurepatroon.

Nu: `max(20, min(duurloop * 0,6, 75))`. De rustige run groeit mee van 20 naar
58 minuten. Alleen week 1 tot en met 4 staat vlak op de ondergrens, wat tijdens
de gewenningsperiode juist gewenst is.

Na de wijziging: aandeel duurloop gemiddeld 43% van het weekvolume (was tot 46%
en structureel stijgend), piek 219 loopmin (~34 km), ACWR maximaal 1,31 met nog
een week op de grens. Bij drie loopdagen blijft een aandeel van ruim 40% normaal;
met vier dagen zou dat vanzelf dalen.

## Variatie in de loopsessies (2026-10-25)

Daarvoor was de donderdag altijd hetzelfde drempelblok. Een gebalanceerd
halve-marathonschema bevat duurloop, tempoloop, interval en herstelruns, maar
met **drie loopdagen** passen die niet allemaal in een week. Daarom rouleert de
kwaliteitssessie over de weken in plaats van ze te stapelen.

### Rotatie per fase

| Fase | Volgorde |
|---|---|
| basis | versnellingen, heuvels, versnellingen, heuvels |
| opbouw | drempel, tempo, heuvels, drempel, interval, tempo |
| piek | drempel, tempo, interval, tempo |
| taper | tempo, interval (beide kort) |

Uitkomst over het hele plan: 3x drempel, 3x tempoloop, 3x interval, 2x heuvels,
2x versnellingen. Op herstelweken vervalt de kwaliteitssessie en staan er twee
rustige runs.

De zondagse duurloop varieert zelf ook: vanaf de tweede helft van de opbouw
komt er een blok op wedstrijdtempo achterin, op vermoeide benen.

### Nieuwe sessietypen

- **Tempoloop** - aaneengesloten blok op 150-160 bpm (wedstrijdtempo-gevoel),
  15 tot 30 minuten afhankelijk van de fase.
- **Intervaltraining** - 5-6 x 3 min op 172-182 bpm met 2 min dribbelen.
  In de taper teruggebracht naar 4 x 2 min.
- **Heuvelherhalingen** - 6-9 x 1 min stevig omhoog. Minder impact dan vlakke
  intervallen bij vergelijkbare prikkel, wat bij een terugkerende loper telt.
  Zijn recente runs hebben 15-18 hoogtemeters per km, dus er is een klim in de
  buurt; een brug of viaduct volstaat.

### Twee dingen die dit blootlegde

1. **Vaste warming-up woog te zwaar in kleine weken.** 12 min inlopen + 8 min
   uitlopen maakte in een basisweek met een duurloop van 26 minuten de
   kwaliteitssessie langer dan de duurloop zelf. In- en uitlopen schalen nu mee
   met de weekomvang (`_warm_cool`), met een ondergrens van 6 en 5 minuten.
2. **Taper kreeg een volwaardige intervaltraining**, zeven dagen voor de race.
   Intervallen in de taper zijn nu 4 x 2 min in plaats van 6 x 3 min.

## Planoverzicht herbouwd (2026-10-25)

De tabel onderaan toonde per week alleen naam en duur van de sessies, in een
platte regel. Zes dingen ontbraken of klopten niet:

1. Kolom **Run:walk** stond twintig rijen leeg - die hoort bij het oude
   run/walk-plan, niet bij een tijdsgericht schema.
2. Geen **sessiedetails**: je zag "Drempelblok 50 min" maar niet wat dat inhield.
3. **ACWR, belasting en chronische belasting** werden wel berekend maar nergens
   getoond.
4. **Afgeremde en bijgestelde weken** waren onzichtbaar.
5. Geen **uploadstatus per sessie**, alleen een knop voor de hele week.
6. Krachttraining stond in de lijst maar telt niet mee in het weektotaal, zonder
   dat dat ergens stond.

Nu: kolommen Wk, Vanaf, Fase, Duurloop, Loopvolume, Gelopen, **ACWR**, Sessies
(als gekleurde labels per type) en **Status** (herstelweek / afgeremd / bijgesteld,
met de reden in de tooltip).

Elke week is **uitklapbaar** met het driehoekje links, of allemaal tegelijk met
de knop in de kop. Uitgeklapt staat per sessie de volledige opbouw, de
hartslagband, bij krachttraining de oefeningen met sets en herhalingen, de
toelichting, en een eigen "Naar Garmin"-knop met de status erbij.

De ACWR-cel is gekleurd (groen binnen de band, oranje te laag, rood boven 1,3)
en grijs tijdens de opwarmfase, waar de ratio weinig zegt. De tooltip toont de
onderliggende belasting en de chronische belasting.

Weken die al voorbij zijn en waarin niets is gelopen tonen een rode 0 in plaats
van een streepje, zodat een gemiste week opvalt.

## Opgelost 2026-10-25 (6): "ROUTES is not defined"

Symptoom: de kaart gaf "Routes laden mislukte: ROUTES is not defined".

Oorzaak: bij het herbouwen van het planoverzicht verving ik alles tussen
`function renderPlanTable()` en `async function loadRoutes()`. Daartussen
stonden de route-hulpfuncties - `ROUTE_COLORS`, `ROUTES`, `layerControl`,
`routePrefs`, `saveRoutePrefs`, `isOn`, `setRoute`, `visibleRoutes`,
`updateRouteCount` en `fitVisible`. Die zijn daarmee stilzwijgend gewist,
terwijl `loadRoutes` ze bleef aanroepen.

`node --check` zag dat niet: een ontbrekende functie is geen syntaxfout maar een
ReferenceError die pas bij gebruik opduikt.

### lint.sh

Daarom staan de statische controles nu in `lint.sh`, te draaien **voor** een
rebuild:

    bash lint.sh

Drie lagen:

1. Syntaxcheck op app.js en alle Python-bestanden.
2. **DOM-ids**: elke id die het JS opzoekt moet in de HTML bestaan.
3. **Niet-gedefinieerde namen**: elke aangeroepen functie en elke
   SCHREEUWCONSTANTE moet ergens gedefinieerd zijn (`tools-jscheck.py`).

Die derde is geverifieerd tegen het echte geval: met `setRoute` verwijderd
meldt hij "AANGEROEPEN MAAR NIET GEDEFINIEERD: setRoute", terwijl
`node --check` geen enkel probleem ziet.

De checker haalt eerst commentaar, strings en **regex-literals** uit de bron.
Dat laatste bleek nodig: `/^(GO|MODIFY|REST):/` leverde anders valse meldingen
over niet-bestaande constanten.

## Literatuurtoets en herziening (2026-10-25)

Het plan is tegen de onderzoeksliteratuur gelegd. Vijf dingen bleken niet te
kloppen, een daarvan fundamenteel.

### De belangrijkste bevinding zit in zijn eigen racedata

Splits van de CPC Loop 2025 (2:08):

| | tempo | HR |
|---|---|---|
| km 1-5 | 5:26/km | 153 |
| km 6-10 | 5:47/km | 175 |
| km 11-15 | 6:19/km | 176 |
| km 16-eind | 6:24/km | 178 |

Eerste helft 5:38/km, tweede helft 6:24/km: **46 seconden per km langzamer**.
Bij gelijkmatig doorlopen van het eerste-helft-tempo was de tijd exact 2:00:00
geweest. Het doel is dus geen ambitie maar een tempo dat hij elf kilometer lang
al heeft gelopen. De beperking is vermoeidheidsbestendigheid, niet snelheid.

Ondersteund door de VO2max-historie: 45,5 in maart 2025, 46,4 op 18 oktober 2026.
Na zestien maanden niets lopen is de aerobe motor er nog; wat weg is, is
weefseltolerantie en specifieke duurkracht.

### Wat is gewijzigd

1. **Duurloop-sprongbegrenzing toegevoegd** (max 115% van de langste duurloop
   van de vier weken ervoor). Hiervoor is de evidentie sterker dan voor ACWR:
   een sprong van 30%+ geeft een gemeten toename van het blessurerisico.
   Het plan had twee weken met een sprong boven 130%; nu nul.
2. **ACWR-plafond van 1,30 naar 1,40.** De meta-analyse concludeert dat ACWR
   geen zelfstandig voorspellend instrument is en niet via universele drempels
   moet worden gelezen, en dat de ratio juist onbetrouwbaar wordt bij lage
   chronische belasting. Nu de beter onderbouwde sprongregel erin zit, kostte
   het strakke plafond echte training: de piekduurloop bleef op 95 minuten
   steken, terwijl zijn faalpunt juist de tweede racehelft is. Nu 106 minuten.
3. **Taper verdiept** van -21%/-39% naar -30%/-51%. De meta-analyse wijst op
   41-60% volumereductie met behoud van intensiteit; dat laatste was al goed.
4. **Rotatie verschoven naar drempel en wedstrijdtempo** (3x drempel, 4x tempo,
   2x interval) in plaats van intervalzwaar. VO2max-werk levert bij hem het
   minst op: de top is er al.
5. **Krachttraining in de basisfase van 2 naar 3 sets.** Krachttraining is het
   best onderbouwde blessurepreventiemiddel (ongeveer halvering van
   overbelastingsblessures) en verbetert de loopeconomie 2-8%, maar dat effect
   komt van zwaar werk en van programma's van 10-14 weken.

### Wat na toetsing overeind bleef

- **Drie loopdagen.** Het FIRST/Furman-onderzoek liet zien dat drie
  kwaliteitsruns per week halve-marathonprestaties evenaren of verbeteren ten
  opzichte van vijf tot zes dagen, met lagere blessurecijfers.
- **Duurloop als 43% van het weekvolume.** De gangbare richtlijn van 20-30%
  gaat uit van vijf tot zes loopdagen; bij drie dagen zit 40-45% ook in de
  FIRST-plannen. Dit is geen fout.
- **Twee weken taper**, hartslagbanden onder LT1 voor rustige runs, en het
  blok op wedstrijdtempo achterin de duurloop - dat laatste traint precies
  waar zijn race uiteenviel.

## Vormgeving (2026-10-25)

De interface heet nu **dash** en is opnieuw opgemaakt. Discipline daarbij: alle
95 bestaande klassenamen zijn ongewijzigd gebleven, zodat de opmaak los staat
van de werking en een stijlwijziging nooit de functionaliteit kan breken. Er is
vooraf geinventariseerd welke klassen in HTML en JS worden gebruikt.

Wat er veranderd is:

- **Inter** als lettertype, met tabulaire cijfers waar getallen onder elkaar
  staan. Vooraf geverifieerd dat de Google Fonts-URL en de onderliggende
  woff2-bestanden daadwerkelijk bestaan - dezelfde les als bij Chart.js.
- **Vier dieptelagen** in plaats van twee, plus twee zachte lichtbronnen in de
  achtergrond. Dat geeft kaarten reliëf zonder harde randen.
- **Hero**: de racenaam staat nu boven de countdown in plaats van in de kop,
  het aantal dagen is een groot verloopcijfer, en de voortgangsbalk gloeit mee.
  De kop houdt alleen het woordmerk met een punt in de accentkleur.
- **Labels per sessietype** hebben elk een eigen kleur: duurloop paars, rustig
  blauw, tempo en drempel oranje, interval rood, heuvels groen, kracht groen.
  Zo is een trainingsweek in één oogopslag te lezen.
- **Grafieken** in dezelfde taal: Inter, zachtere rasterlijnen, donkere tooltips
  met afgeronde hoeken.
- **Leaflet** volledig in de donkere stijl, inclusief de laagregelaar en popups.
- Hover- en focusstaten overal, en `prefers-reduced-motion` wordt gerespecteerd.
- Mobiel: twee breekpunten (760 en 620 px), de tabel scrollt binnen zijn kaart.

### check.sh aangepast

De controle op externe bestanden sloeg aan op `rel="preconnect"`-regels. Die
wijzen naar een bare origin, die hoort 404 te geven - het zijn
verbindingshints, geen bestanden. Die worden nu overgeslagen.

## De coach: chatbot in het dashboard (2026-10-25)

Rechtsonder staat een hardlopertje. Klik erop en je praat met een coach die je
plan, je Garmin-data en je eigen logboek kent, en die voorstellen kan doen om je
schema bij te stellen. Hij vraagt uit zichzelf of hij kan helpen: bij het openen
zegt hij wat er nu speelt (een run die nog niet besproken is, de training van
vandaag, een HRV die al dagen laag staat) en daarna staat er een wolkje bij de
knop, één keer per dag.

### Wat hij kan

- **Trainingen loggen.** "10 km gelopen in 50 minuten, ging lekker" wordt een
  regel in je eigen logboek, met gevoel, spierpijn en RPE als je die noemt. Dat
  is precies wat Garmin niet weet, en het gaat mee in elk volgend gesprek.
- **Vragen over je data.** Hoeveel km deze maand, wat was je snelste run rond
  5 km, hoe staat je herstel ervoor, lig je op schema voor 2:00.
- **Je schema bijstellen.** Hij kan een week die nog niet begonnen is lichter of
  zwaarder maken (factor 0,60 tot 1,10), de kwaliteitssessie laten vervallen,
  een eerdere bijstelling terugdraaien, een instelling van het doel wijzigen of
  de week in je Garmin-agenda zetten.
- **Advies over herstel, pacing en blessures**, op basis van je eigen cijfers en
  van wat we over jouw lopen hebben uitgezocht.

### De grenzen, in drie lagen

De bot kan niets aan deze website, de containers of je data veranderen. Dat is
niet alleen een instructie in zijn prompt; het zit in de bouw.

**1. Hij heeft geen gereedschap.** De Vibe CLI draait headless (`-p`) in een
eigen container: in headless-modus is geen enkele goedkeuring mogelijk, dus
wordt élke tool-aanroep door het goedkeuringsbeleid geweigerd in plaats van
uitgevoerd (getest met vijandige schrijf-, shell- en netwerkpogingen: nul
bijeffecten). Daarnaast: `--system-prompt-file` vervangt de systeemprompt van
Vibe volledig door de briefing, `--max-turns 1` houdt het bij één vraag-antwoord,
`--max-price` zet een kostenplafond, en de eigen `VIBE_HOME` is een lege,
gesloten configuratie (geen skills, agents, plugins of MCP-servers, dus hij kan
ook via die weg niet naar Garmin schrijven; session-logging staat uit). Zijn
werkmap is een lege `/work` buiten elke vertrouwde map. Hij kan dus
uitsluitend tekst produceren. `check.sh` controleert of die vangrails er nog
staan en of er geen goedkeuringsomzeiling in de brug zit.

**2. Hij ziet het dashboard niet.** De container `garmin-coach` heeft geen enkele
mount van de dashboardcode of -data. Hij krijgt tekst binnen en geeft tekst
terug. Hij hangt niet aan het LAN en niet aan Cloudflare: hij zit op het
docker-netwerk `garmin-net` en is alleen bereikbaar voor het dashboard, met een
token uit `/mnt/user/appdata/garmin-coach/.env`.

**3. Een wijziging vraagt altijd jouw klik.** Wil de coach iets veranderen, dan
zet hij een `coach-action`-blok onder zijn antwoord. Dat wordt in `coach.py`
gevalideerd tegen een vaste lijst van vijf soorten met harde grenzen, en
verschijnt als kaartje met een knop. Pas als je op "Doorvoeren" drukt, voert het
dashboard het uit - en het valideert dan opnieuw, want tussen voorstel en klik
kan de week begonnen zijn. Wat niet door die poort komt, wordt weggegooid en
gelogd.

Wat hij daardoor niet kan, ook niet als je het hem vraagt: de racedatum, de
afstand of de naam van je doel wijzigen (dat doe je zelf via "Doel wijzigen"),
een week in het verleden aanpassen, een week meer dan 10% zwaarder maken,
activiteiten in Garmin verwijderen, of wat dan ook aan de code, de instellingen
of de server. Getest met vijandige voorstellen: 16 van de 17 geweigerd, de 17e
(een notitie van 5000 tekens) afgekapt op 400.

### Waar het staat

| Bestand | Wat |
|---|---|
| `app/coach.py` | briefing, protocol, validatie, uitvoeren, de endpoints |
| `app/coach_knowledge.md` | vaste kennis over deze loper en dit plan |
| `app/static/coach.js` | chat in de browser, voorstelkaartjes |
| `app/static/coach.css` | paneel en de animaties van het poppetje |
| `/mnt/user/appdata/garmin-coach/` | de brug: eigen container, eigen `.env`, Vibe CLI uit het image |

Het poppetje is één SVG in `index.html` (een Jinja-macro, twee keer neergezet).
Alle beweging hangt aan de variabele `--rn-speed`, zodat hetzelfde figuurtje kan
joggen (rust), sprinten (denkt na) en bijpraten (antwoordt) zonder tweede
tekening. Bij `prefers-reduced-motion` staat alles stil.

### Kosten en snelheid

Een vraag kost ongeveer 4 tot 8 seconden en een paar cent aan tokens, via je
Mistral API-key (de key in `garmin-coach/.env`). Elk
gesprek krijgt de volledige briefing mee, dus de kosten zitten in de invoer.
Limieten: 6 berichten per minuut, 80 per dag, 2000 tekens per bericht, en per
vraag een kostenplafond (`COACH_MAX_BUDGET_USD`).

### Onderhoud

- **Kennis bijwerken:** `app/coach_knowledge.md` aanpassen en `bash rebuild.sh`.
  Dat is de plek voor alles wat je wilt dat hij blijvend weet.
- **CLI bijwerken:** in `garmin-coach/requirements.txt` de versie van
  `mistral-vibe` ophogen en `bash rebuild.sh` (de CLI zit in het image,
  bewust: een nieuwe versie komt niet stiekem mee met een herstart).
- **Coach uit:** `COACH_TOKEN` leeghalen in `start.sh` van het dashboard. Dan
  verdwijnt de knop en blijft de rest van het dashboard gewoon werken.
- **Start:** eerst `bash /mnt/user/appdata/garmin-coach/start.sh`, dan
  `bash start.sh` hier. Beide maken `garmin-net` aan als die nog niet bestaat.

### Samenloop met de automatische bijstelling

Verlicht de coach een week omdat jij iets vertelt wat niet in de data staat, dan
mag de wekelijkse automatische beoordeling dat niet ongedaan maken. Zelfde regel
als binnen `adapt.decide`: de laagste factor wint. De redenen van allebei blijven
staan, en je ziet in de kaart "Automatische bijstelling" wat er is gebeurd.
