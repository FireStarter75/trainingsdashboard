"""Hardloopcoach: een gesprek met Claude, met harde grenzen eromheen.

Drie lagen houden de bot binnen zijn kader:

1. **Hij heeft geen gereedschap.** De coach-brug (eigen container, zie
   garmin-coach/coach/server.py) start de Claude-CLI met alle tools uit en
   zonder MCP-servers. Er is dus geen pad naar bestanden, shell, Garmin of
   internet. Hij kan uitsluitend tekst produceren.

2. **Tekst wordt pas een wijziging na een klik.** Wil de coach iets veranderen,
   dan zet hij een `coach-action`-blok onder zijn antwoord. Dat wordt hier
   gevalideerd tegen een vaste lijst van vijf soorten met harde grenzen, en
   belandt als voorstel in de database. Pas als de gebruiker op de knop drukt,
   voert dit dashboard het uit. De coach kan dus geen enkele wijziging zelf
   doorvoeren.

3. **Wat niet in die lijst staat, bestaat niet.** Er is geen generieke
   "voer dit uit"-route. Een onbekende of ongeldige actie wordt weggegooid en
   gelogd. Aan de website, de containers, de code of de instellingen kan hij
   langs geen enkele weg iets veranderen: die paden bestaan simpelweg niet in
   deze module.
"""
import json
import os
import re
import time
import uuid
from datetime import date, datetime, timedelta

import requests
from flask import Blueprint, current_app, jsonify, request

import auth
import plan as planner
import store

bp = Blueprint("coach", __name__)

COACH_URL = os.environ.get("COACH_URL", "http://garmin-coach:8099")
COACH_TOKEN = os.environ.get("COACH_TOKEN", "")
COACH_MODEL = os.environ.get("COACH_MODEL", "sonnet")
COACH_TIMEOUT = float(os.environ.get("COACH_HTTP_TIMEOUT", "180"))
MAX_MSG_CHARS = int(os.environ.get("COACH_MAX_MSG", "2000"))
MAX_PER_DAY = int(os.environ.get("COACH_MAX_PER_DAY", "80"))
MAX_PER_MIN = int(os.environ.get("COACH_MAX_PER_MIN", "6"))
HISTORY_TURNS = int(os.environ.get("COACH_HISTORY_TURNS", "12"))

DOW = ["maandag", "dinsdag", "woensdag", "donderdag", "vrijdag", "zaterdag", "zondag"]
DOW_SHORT = ["ma", "di", "wo", "do", "vr", "za", "zo"]

# Wordt gevuld door init(): het dashboard geeft zijn eigen bouwstenen mee in
# plaats van dat deze module ze importeert. Dat houdt de afhankelijkheid één
# kant op en voorkomt een kringverwijzing met app.py.
_state_provider = None
_upload_fn = None


def init(state_provider, upload_fn):
    global _state_provider, _upload_fn
    _state_provider = state_provider
    _upload_fn = upload_fn


def configured():
    return bool(COACH_TOKEN and COACH_URL)


# ------------------------------------------------------------------ hulpjes

def _d(iso):
    return datetime.strptime(iso[:10], "%Y-%m-%d").date()


def nl_date(iso, with_dow=True):
    try:
        d = _d(iso)
    except (ValueError, TypeError):
        return str(iso)
    s = "%d/%d" % (d.day, d.month)
    return "%s %s" % (DOW_SHORT[d.weekday()], s) if with_dow else s


def hms(minutes):
    if minutes is None:
        return "–"
    h, m = divmod(int(round(minutes)), 60)
    return "%d:%02d" % (h, m) if h else "%d min" % m


def nl_num(x, decimals=2):
    """Nederlandse schrijfwijze: 4,42 in plaats van 4.42. Alleen voor tekst die
    de gebruiker leest; in de briefing voor het model maakt het niet uit."""
    if x is None:
        return "–"
    s = ("%.*f" % (decimals, float(x))).rstrip("0").rstrip(".")
    return s.replace(".", ",") or "0"


def pace(minutes, km):
    if not km or not minutes or km < 0.2:
        return None
    p = minutes / km
    return "%d:%02d/km" % (int(p), round((p - int(p)) * 60))


def run_km(r):
    return (r.get("distance_meters") or 0) / 1000.0


def run_min(r):
    return (r.get("duration_seconds") or 0) / 60.0


def run_day(r):
    return (r.get("start_time") or "")[:10]


# ------------------------------------------------------------------ cijfers

BUCKETS = [
    ("5 km", 4.6, 5.6), ("10 km", 9.3, 10.9), ("15 km", 14.2, 16.0),
    ("halve marathon", 20.0, 22.2),
]


def running_stats(runs):
    """Eigen records en totalen, gerekend uit de activiteiten zelf.

    Garmins eigen records zijn hier onbruikbaar: die staan op "Fastest 5K 30:04"
    met datum 1970-01-01 en een langste run van 13,35 km, terwijl hij 21,32 km
    heeft gelopen. Dus zelf rekenen, uit hele activiteiten. Dat is eerlijk te
    labelen: het is de snelste hele run rond die afstand, geen beste 5 km binnen
    een langere run.
    """
    runs = [r for r in (runs or []) if run_km(r) > 0.3 and run_min(r) > 1]
    if not runs:
        return {}
    today = date.today()
    monday = today - timedelta(days=today.weekday())

    def total(since):
        rs = [r for r in runs if run_day(r) >= since.isoformat()]
        return {"km": round(sum(run_km(r) for r in rs), 1),
                "minutes": round(sum(run_min(r) for r in rs)),
                "runs": len(rs)}

    best = {}
    for label, lo, hi in BUCKETS:
        pool = [r for r in runs if lo <= run_km(r) <= hi]
        if pool:
            b = min(pool, key=lambda r: run_min(r) / run_km(r))
            best[label] = {"date": run_day(b), "km": round(run_km(b), 2),
                           "minutes": round(run_min(b), 1),
                           "pace": pace(run_min(b), run_km(b)),
                           "avg_hr": b.get("avg_hr_bpm"), "name": b.get("name")}

    longest = max(runs, key=run_km)
    months = {}
    for r in runs:
        months.setdefault(run_day(r)[:7], 0.0)
        months[run_day(r)[:7]] += run_km(r)

    return {
        "this_week": total(monday),
        "this_month": total(date(today.year, today.month, 1)),
        "last_30d": total(today - timedelta(days=30)),
        "this_year": total(date(today.year, 1, 1)),
        "best_by_distance": best,
        "longest_ever": {"date": run_day(longest), "km": round(run_km(longest), 2),
                         "minutes": round(run_min(longest), 1),
                         "pace": pace(run_min(longest), run_km(longest))},
        "months": {k: round(v, 1) for k, v in sorted(months.items())[-8:]},
        "total_runs": len(runs),
    }


# ----------------------------------------------------------------- briefing

def _metric(state, name):
    m = (state.get("metrics") or {}).get(name) or {}
    return m.get("value") if m.get("ok") else None


def current_week(state):
    today = state["today"]
    for wk in state["plan"]["weeks"]:
        if wk["start"] <= today <= wk["end"]:
            return wk
    return None


def next_week(state):
    today = state["today"]
    for wk in state["plan"]["weeks"]:
        if wk["start"] > today:
            return wk
    return None


def briefing(state, runs_all):
    """De actuele stand, compact. Gaat bij elke vraag mee in de systeemprompt.

    Alles wat hier niet in staat, weet de coach niet: hij kan niets opvragen.
    Daarom liever een regel te veel dan een vraag die hij niet kan beantwoorden.
    """
    g = state["goal"]
    p = state["plan"]
    est = p.get("estimate") or {}
    st = running_stats(runs_all)
    L = []
    A = L.append

    A("# Stand van zaken op %s (%s)" % (nl_date(state["today"]), DOW[_d(state["today"]).weekday()]))
    A("")
    A("Doel: %s, %s km op %s. Nog %d dagen."
      % (g["goal_name"], g["distance_km"], g["race_date"], state["days_to_race"]))
    if g.get("target_time_min"):
        A("Streeftijd %s (%s). Prioriteit: %s."
          % (hms(g["target_time_min"]), pace(g["target_time_min"], g["distance_km"]),
             "streeftijd" if g.get("priority") == "time" else "gezond finishen"))
    A("Plan: %d weken, %d loopdagen per week plus kracht op %s."
      % (p["weeks_total"], g["days_per_week"],
         DOW[int(g["strength_day"])] if g.get("strength_day") is not None else "geen dag"))

    cur, nxt = current_week(state), next_week(state)

    # ---- deze week
    A("")
    A("## Deze week")
    if cur:
        act = (state.get("actuals") or {}).get(cur["start"]) or {}
        A("Week %d van %d, fase %s%s. Gepland %d min (duurloop %d min), ACWR %s."
          % (cur["index"], p["weeks_total"], cur["phase"],
             ", herstelweek" if cur.get("deload") else "",
             cur["planned_min"], cur["long_min"],
             cur.get("acwr") if cur.get("acwr") is not None else "n.v.t."))
        A("Tot nu toe gelopen: %d min / %s km in %d sessies."
          % (act.get("minutes", 0), act.get("km", 0), act.get("sessions", 0)))
        if cur.get("adapted"):
            A("Deze week is bijgesteld naar %sx (%s): %s"
              % (cur["adapted"].get("scale"), cur["adapted"].get("severity"),
                 "; ".join(cur["adapted"].get("reasons") or [])))
        ups = state.get("uploads") or {}
        for s in cur["sessions"]:
            done = s["date"] < state["today"]
            on_watch = "%s|%s" % (s["date"], s["kind"]) in ups
            A("- %s %s%s, %d min: %s%s"
              % (nl_date(s["date"]), s["label"], " (VANDAAG)" if s["date"] == state["today"] else
                 (" (geweest)" if done else ""), s["minutes"], s.get("detail") or "",
                 "  [staat in Garmin-agenda]" if on_watch else ""))
    else:
        A("Het plan begint op %s; deze week staat er nog niets in."
          % nl_date(p["weeks"][0]["start"]))

    # ---- volgende week
    if nxt:
        A("")
        A("## Volgende week (%s, de week die bijgesteld kan worden)" % nxt["start"])
        A("Week %d, fase %s%s, gepland %d min, duurloop %d min, ACWR %s."
          % (nxt["index"], nxt["phase"], ", herstelweek" if nxt.get("deload") else "",
             nxt["planned_min"], nxt["long_min"],
             nxt.get("acwr") if nxt.get("acwr") is not None else "n.v.t."))
        if nxt.get("adapted"):
            A("Al bijgesteld naar %sx (%s): %s"
              % (nxt["adapted"].get("scale"), nxt["adapted"].get("severity"),
                 "; ".join(nxt["adapted"].get("reasons") or [])))
        A("Sessies: " + "; ".join("%s %s %d min" % (nl_date(s["date"]), s["label"], s["minutes"])
                                  for s in nxt["sessions"]))

    # ---- plan tegen werkelijkheid
    A("")
    A("## Laatste 8 weken: gepland tegen gelopen")
    today = state["today"]
    past = [w for w in p["weeks"] if w["start"] <= today][-8:]
    if past:
        for w in past:
            a = (state.get("actuals") or {}).get(w["start"]) or {}
            A("- week %d (%s, %s): gepland %d min, gelopen %d min / %s km in %d sessies"
              % (w["index"], w["start"], w["phase"], w["planned_min"],
                 a.get("minutes", 0), a.get("km", 0), a.get("sessions", 0)))
    else:
        A("Het plan is nog niet begonnen.")
    for wk_start, a in sorted((state.get("actuals") or {}).items())[-4:]:
        if not any(w["start"] == wk_start for w in past):
            A("- week van %s (voor het plan): %d min / %s km in %d sessies"
              % (wk_start, a.get("minutes", 0), a.get("km", 0), a.get("sessions", 0)))

    # ---- recente runs
    A("")
    A("## Laatste 12 runs uit Garmin")
    for r in (runs_all or [])[:12]:
        km, mn = run_km(r), run_min(r)
        A("- %s: %s km in %s (%s)%s%s"
          % (run_day(r), round(km, 2), hms(mn), pace(mn, km) or "–",
             ", gem %s bpm" % r["avg_hr_bpm"] if r.get("avg_hr_bpm") else "",
             " – %s" % r.get("name") if r.get("name") else ""))

    # ---- cijfers
    if st:
        A("")
        A("## Totalen en records (uit de activiteiten zelf gerekend)")
        A("Deze week %s km, deze maand %s km, laatste 30 dagen %s km, dit jaar %s km."
          % (st["this_week"]["km"], st["this_month"]["km"],
             st["last_30d"]["km"], st["this_year"]["km"]))
        A("Snelste hele run per afstand (niet de beste 5 km binnen een langere run):")
        for label, b in st["best_by_distance"].items():
            A("- %s: %s km in %s (%s) op %s%s"
              % (label, b["km"], hms(b["minutes"]), b["pace"], b["date"],
                 ", gem %s bpm" % b["avg_hr"] if b.get("avg_hr") else ""))
        A("Langste ooit: %s km in %s (%s) op %s."
          % (st["longest_ever"]["km"], hms(st["longest_ever"]["minutes"]),
             st["longest_ever"]["pace"], st["longest_ever"]["date"]))
        A("Km per maand: " + ", ".join("%s %s" % (k, v) for k, v in st["months"].items()))

    # ---- herstel en belasting
    A("")
    A("## Herstel en belasting")
    health = _metric(state, "health") or {}
    summ = ((health.get("data") or {}).get("summary")) or {}
    rows = ((health.get("data") or {}).get("rows")) or []
    for key, label, unit in (("resting_hr", "rusthartslag", "bpm"), ("hrv", "HRV", "ms"),
                             ("sleep", "slaap", "uur"), ("body_battery", "body battery", "")):
        t = (summ.get(key) or {}).get("trend") or {}
        if t:
            A("- %s: laatst %s %s (%s), 7-daags %s tegen 28-daags %s, richting %s"
              % (label, t.get("latest"), unit, t.get("latest_date"), t.get("avg_7d"),
                 t.get("avg_28d"), t.get("direction")))
    if rows:
        last = rows[-1]
        low = [r for r in rows[-7:] if r.get("hrv_ms") and r.get("hrv_baseline_low_ms")
               and r["hrv_ms"] < r["hrv_baseline_low_ms"]]
        A("- HRV-status gisteren/vandaag: %s, %d van de laatste 7 dagen onder de basislijn"
          % (last.get("hrv_status") or "onbekend", len(low)))

    rd = _metric(state, "readiness") or {}
    rdd = rd.get("data") or rd
    if rdd:
        A("- Garmin readiness: %s%s" % (rdd.get("decision") or "onbekend",
                                        " – %s" % rdd.get("reason") if rdd.get("reason") else ""))
    load = (_metric(state, "load") or {}).get("data") or {}
    lat = load.get("latest") or {}
    if lat:
        A("- Belastingmodel: CTL %s, ATL %s, TSB %s, ACWR %s%s"
          % (lat.get("ctl"), lat.get("atl"), lat.get("tsb"), lat.get("acwr"),
             " (opwarmfase: ACWR zegt nog weinig)" if lat.get("warming_up") else ""))
    inten = load.get("intensity") or {}
    if inten:
        A("- Intensiteitsverdeling laatste weken: onder LT1 %s%%, Z2 %s%%, Z3+ %s%% (doel: 75%% onder LT1)"
          % (inten.get("z1_pct"), inten.get("z2_pct"), inten.get("z3_pct")))
    for f in (load.get("flags") or [])[:4]:
        A("- signaal: %s" % f.get("text"))

    ts = (_metric(state, "training_status") or {})
    tsd = ts.get("data") or ts
    if isinstance(tsd, dict) and tsd:
        bits = {k: tsd.get(k) for k in ("training_status", "vo2max", "acute_load", "status")
                if tsd.get(k) is not None}
        if bits:
            A("- Garmin trainingsstatus: %s" % json.dumps(bits, ensure_ascii=False))

    # ---- verwachting
    A("")
    A("## Verwachte eindtijd")
    if est:
        A("Nu, zonder verdere training: %s. Na het hele blok: %s (bandbreedte %s tot %s)."
          % (hms(est.get("race_minutes_now")), hms(est.get("race_minutes_after")),
             hms(est.get("race_minutes_best")), hms(est.get("race_minutes_worst"))))
        A("Basis: %s. %s" % (est.get("basis"), est.get("note") or ""))
        if est.get("target_gap_min") is not None:
            gap = est["target_gap_min"]
            A("Tegenover de streeftijd: %s%s min (%s)."
              % ("+" if gap > 0 else "", round(gap, 1),
                 "binnen bereik" if est.get("target_within_band") else "nog niet binnen bereik"))
    pred = _metric(state, "race_predictions")
    if pred:
        A("Garmins eigen voorspelling: %s" % json.dumps(pred, ensure_ascii=False)[:400])

    # ---- bijstellingen
    ad = state["plan"]["weeks"]
    adapted = [w for w in ad if w.get("adapted")]
    if adapted:
        A("")
        A("## Eerdere bijstellingen")
        for w in adapted[-6:]:
            A("- week %d (%s): %sx, %s"
              % (w["index"], w["start"], w["adapted"].get("scale"),
                 "; ".join(w["adapted"].get("reasons") or [])))

    # ---- eigen logboek
    logs = store.log_recent(12)
    A("")
    A("## Zijn eigen logboek (wat Garmin niet weet)")
    if logs:
        for e in logs:
            parts = [e["day"]]
            if e.get("km"):
                parts.append("%s km" % e["km"])
            if e.get("minutes"):
                parts.append(hms(e["minutes"]))
            if e.get("feel") is not None:
                parts.append("gevoel %s/5" % e["feel"])
            if e.get("soreness") is not None:
                parts.append("spierpijn %s/5" % e["soreness"])
            if e.get("rpe") is not None:
                parts.append("RPE %s/10" % e["rpe"])
            if e.get("note"):
                parts.append('"%s"' % e["note"])
            A("- " + ", ".join(str(x) for x in parts))
    else:
        A("Nog leeg. Zodra hij iets vertelt over hoe een training ging, zet je het erin "
          "met log_session.")

    return "\n".join(L)


# ------------------------------------------------------------- systeemprompt

ROLE = """Je bent de hardloopcoach in het trainingsdashboard van Eelco. Je praat
Nederlands, je kent zijn plan en zijn cijfers, en je bent kort en concreet.

## Toon

Als een goede trainer: direct, warm, zonder gewichtigheid. Geen opsomming van
alles wat je weet, maar het antwoord op wat hij vraagt. Twee tot vijf zinnen is
normaal; alleen bij een echte analyse mag het langer. Je mag een enkele emoji
gebruiken, niet meer dan één per bericht.

Je bent het laatste stukje van een gesprek, geen rapport. **Sluit vrijwel elk
bericht af met één concreet aanbod of één vraag** waarmee hij verder kan: of je
iets mag loggen, de week mag verlichten, het tempo mag uitrekenen, de week naar
zijn horloge mag zetten. Eén vraag per bericht, niet drie.

## Wat je wel en niet doet

Je gaat over: zijn trainingsplan, hardlopen, techniek, pacing, herstel, blessures
in de zin van wel of niet doorlopen, voeding rond trainingen en de wedstrijd, en
de cijfers in dit dashboard.

Alles daarbuiten wijs je in één vriendelijke zin af en je biedt aan te helpen met
zijn training. Dus geen code, geen systeembeheer, geen algemene kennisvragen,
geen medische diagnoses. Bij klachten die aanhouden of verergeren verwijs je naar
een fysiotherapeut; je stelt zelf geen diagnose.

Je hebt geen gereedschap: je kunt geen bestanden lezen, niets opzoeken, niets
uitvoeren en niets aan deze website, de server of de data veranderen. Dat is met
opzet zo. Vraagt hij daarom, zeg dan gewoon dat je dat niet kunt en waarom.

## Cijfers

Gebruik alleen cijfers uit de stand van zaken hieronder. Verzin niets, ook niet
als hij ernaar vraagt — zeg dan dat je het niet in je gegevens hebt. Noem bij een
bewering het getal waarop die rust. Rond tempo's af op seconden per kilometer.

## Voorstellen: je voert zelf nooit iets uit

Wil je iets veranderd hebben, zet dan ONDER je antwoord een blok in dit formaat:

```coach-action
{"kind": "...", ...}
```

Eelco krijgt dan een kaartje met een knop te zien. Pas als hij klikt, voert het
dashboard het uit. Leg in je tekst in één zin uit wat je voorstelt en waarom.
Nooit meer dan twee blokken per bericht.

De knop *is* de toestemming, dus vraag er niet eerst om. Schrijf niet "zal ik het
loggen?" maar "Ik zet het erbij:" met het blok eronder. Wil je iets vastleggen of
wijzigen, zet het blok er dan meteen bij in hetzelfde bericht.

Deze vijf soorten bestaan; iets anders wordt weggegooid:

**1. log_session** — een training of een gevoel in zijn logboek zetten.
```coach-action
{"kind":"log_session","day":"2026-10-25","km":10.0,"minutes":50,"feel":4,"soreness":1,"rpe":6,"note":"ging lekker"}
```
Alleen `day` is verplicht (binnen de laatste 60 dagen, niet in de toekomst).
km 0-100, minutes 1-600, feel 1-5, soreness 0-5, rpe 1-10, note max 400 tekens.
Laat weg wat hij niet gezegd heeft; verzin geen gevoelscijfer. Doe dit zodra hij
vertelt dat hij gelopen heeft of hoe iets voelde — ook als de run al in Garmin
staat, want zijn gevoel en context staan daar niet in.

**2. adjust_week** — een week die nog niet begonnen is lichter of zwaarder maken.
```coach-action
{"kind":"adjust_week","week_start":"2026-11-02","scale":0.85,"drop_quality":true,"reason":"drie dagen stijve kuiten na de duurloop"}
```
scale 0.60-1.10 (1,0 is ongewijzigd), drop_quality laat de kwaliteitssessie
vervallen. Alleen weken met een startdatum in de toekomst. Het hele plan schaalt
mee vanaf die week, dus één bijstelling is genoeg.

**3. clear_week_adjustment** — een eerdere bijstelling terugdraaien.
```coach-action
{"kind":"clear_week_adjustment","week_start":"2026-11-02"}
```

**4. set_goal_field** — één instelling van het plan wijzigen.
```coach-action
{"kind":"set_goal_field","field":"target_time_min","value":120}
```
Alleen deze velden: `target_time_min` (60-400 minuten of null),
`priority` ("health" of "time"), `days_per_week` (2-5), `strength_day` (0=ma
t/m 6=zo, of null). Racedatum, afstand en naam kun je niet wijzigen; daarvoor
verwijs je hem naar de knop "Doel wijzigen" op de pagina.
Een vierde loopdag stel je niet op eigen initiatief voor: dat is het besluit van
januari 2027, en alleen als de voorwaarden daarvoor gehaald zijn.

**5. upload_week** — de trainingen van een week in zijn Garmin-agenda zetten.
```coach-action
{"kind":"upload_week","week":5}
```
Het weeknummer uit het plan. Alleen de huidige of een latere week.
"""


def system_prompt(state, runs_all):
    parts = [ROLE]
    try:
        with open(os.path.join(os.path.dirname(__file__), "coach_knowledge.md")) as f:
            parts.append(f.read())
    except OSError as e:
        current_app.logger.warning("kennisbestand onleesbaar: %s", e)
    parts.append(briefing(state, runs_all))
    return "\n\n---\n\n".join(parts)


def conversation(history, message):
    """Het gesprek als één prompt. De brug doet één beurt per aanroep, dus de
    vorige beurten gaan als tekst mee."""
    L = []
    if history:
        L.append("# Gesprek tot nu toe")
        for h in history:
            who = "Eelco" if h["role"] == "user" else "Jij"
            L.append("%s: %s" % (who, h["text"]))
        L.append("")
    L.append("# Nieuw bericht van Eelco")
    L.append(message)
    return "\n".join(L)


# ------------------------------------------------------------------ acties

ACTION_RE = re.compile(r"```coach-action\s*(\{.*?\})\s*```", re.S)


def parse_actions(text):
    """Haalt de voorstelblokken uit het antwoord en geeft de schone tekst terug."""
    raw = []
    for m in ACTION_RE.finditer(text or ""):
        try:
            raw.append(json.loads(m.group(1)))
        except json.JSONDecodeError:
            raw.append({"kind": "_onleesbaar"})
    clean = ACTION_RE.sub("", text or "").strip()
    clean = re.sub(r"\n{3,}", "\n\n", clean)
    return clean, raw


def _num(v, lo, hi, cast=float):
    try:
        x = cast(v)
    except (TypeError, ValueError):
        raise ValueError("geen getal: %r" % (v,))
    if not (lo <= x <= hi):
        raise ValueError("%s valt buiten %s-%s" % (x, lo, hi))
    return x


def _opt(a, key, lo, hi, cast=float):
    if a.get(key) in (None, "", "null"):
        return None
    return _num(a[key], lo, hi, cast)


def validate(a, state):
    """Zet een voorstel om in iets dat uitvoerbaar is, of gooit ValueError.

    Dit is de poort. Alles wat hier niet doorkomt, gebeurt niet. Elke waarde
    wordt begrensd, elke datum tegen het echte plan gelegd.
    """
    kind = str(a.get("kind") or "")
    today = _d(state["today"])
    weeks = {w["start"]: w for w in state["plan"]["weeks"]}

    if kind == "log_session":
        day = str(a.get("day") or "")[:10]
        try:
            d = _d(day)
        except (ValueError, TypeError):
            raise ValueError("geen geldige datum")
        if d > today:
            raise ValueError("een training in de toekomst loggen kan niet")
        if (today - d).days > 60:
            raise ValueError("verder dan 60 dagen terug loggen kan niet")
        out = {"kind": kind, "day": d.isoformat(),
               "km": _opt(a, "km", 0, 100),
               "minutes": _opt(a, "minutes", 1, 600),
               "feel": _opt(a, "feel", 1, 5, int),
               "soreness": _opt(a, "soreness", 0, 5, int),
               "rpe": _opt(a, "rpe", 1, 10, int),
               "note": (str(a.get("note") or "")[:400] or None)}
        if not any(out[k] is not None for k in ("km", "minutes", "feel", "soreness", "rpe", "note")):
            raise ValueError("een logregel zonder enige inhoud")
        return out

    if kind == "adjust_week":
        ws = str(a.get("week_start") or "")[:10]
        wk = weeks.get(ws)
        if not wk:
            raise ValueError("week %s staat niet in het plan" % ws)
        if _d(ws) <= today:
            raise ValueError("week %s is al begonnen; alleen een komende week kan bijgesteld" % ws)
        if wk["phase"] == "race":
            raise ValueError("de racewek wordt niet bijgesteld")
        return {"kind": kind, "week_start": ws,
                "scale": round(_num(a.get("scale", 1.0), 0.60, 1.10), 3),
                "drop_quality": bool(a.get("drop_quality")),
                "reason": str(a.get("reason") or "")[:300] or "voorstel van de coach",
                "week_index": wk["index"], "phase": wk["phase"],
                "planned_min": wk["planned_min"], "long_min": wk["long_min"]}

    if kind == "clear_week_adjustment":
        ws = str(a.get("week_start") or "")[:10]
        wk = weeks.get(ws)
        if not wk:
            raise ValueError("week %s staat niet in het plan" % ws)
        if _d(ws) <= today:
            raise ValueError("alleen een komende week kan teruggedraaid worden")
        if not wk.get("adapted"):
            raise ValueError("die week is niet bijgesteld")
        return {"kind": kind, "week_start": ws, "week_index": wk["index"],
                "was": wk["adapted"].get("scale")}

    if kind == "set_goal_field":
        field = str(a.get("field") or "")
        val = a.get("value")
        if field == "target_time_min":
            val = None if val in (None, "", "null") else int(_num(val, 60, 400, int))
        elif field == "priority":
            if val not in ("health", "time"):
                raise ValueError("priority kan alleen health of time zijn")
        elif field == "days_per_week":
            val = int(_num(val, 2, 5, int))
        elif field == "strength_day":
            val = None if val in (None, "", "null") else int(_num(val, 0, 6, int))
        else:
            raise ValueError("veld %s mag de coach niet wijzigen" % field)
        return {"kind": kind, "field": field, "value": val,
                "was": (state["goal"] or {}).get(field)}

    if kind == "upload_week":
        n = int(_num(a.get("week"), 1, 400, int))
        wk = next((w for w in state["plan"]["weeks"] if w["index"] == n), None)
        if not wk:
            raise ValueError("week %d staat niet in het plan" % n)
        if wk["end"] < state["today"]:
            raise ValueError("week %d is al voorbij" % n)
        return {"kind": kind, "week": n, "week_start": wk["start"],
                "sessions": sum(1 for s in wk["sessions"] if s.get("uploadable"))}

    raise ValueError("onbekend soort voorstel: %r" % kind[:40])


SUMMARY = {
    "log_session": "In je logboek zetten",
    "adjust_week": "Week bijstellen",
    "clear_week_adjustment": "Bijstelling terugdraaien",
    "set_goal_field": "Instelling wijzigen",
    "upload_week": "Week naar je Garmin-agenda",
}

FIELD_NL = {"target_time_min": "streeftijd", "priority": "prioriteit",
            "days_per_week": "loopdagen per week", "strength_day": "krachtdag"}


def describe(p):
    """Eén regel die precies zegt wat er gebeurt als hij op de knop drukt."""
    k = p["kind"]
    if k == "log_session":
        bits = []
        if p.get("km"):
            bits.append("%s km" % nl_num(p["km"]))
        if p.get("minutes"):
            bits.append(hms(p["minutes"]))
        if p.get("km") and p.get("minutes"):
            bits.append(pace(p["minutes"], p["km"]) or "")
        if p.get("feel") is not None:
            bits.append("gevoel %d/5" % p["feel"])
        if p.get("soreness") is not None:
            bits.append("spierpijn %d/5" % p["soreness"])
        if p.get("rpe") is not None:
            bits.append("RPE %d/10" % p["rpe"])
        line = "%s: %s" % (nl_date(p["day"]), ", ".join(b for b in bits if b) or "notitie")
        if p.get("note"):
            line += " — “%s”" % p["note"]
        return line
    if k == "adjust_week":
        pct = round((p["scale"] - 1) * 100)
        how = ("%d%% lichter" % -pct if pct < 0 else
               "%d%% zwaarder" % pct if pct > 0 else "ongewijzigd in volume")
        return ("Week %d (vanaf %s): %s%s. Nu %d min gepland, duurloop %d min. Reden: %s"
                % (p["week_index"], nl_date(p["week_start"]), how,
                   ", kwaliteitssessie vervalt" if p["drop_quality"] else "",
                   p["planned_min"], p["long_min"], p["reason"]))
    if k == "clear_week_adjustment":
        return ("Week %d (vanaf %s) terug naar het oorspronkelijke plan; de bijstelling "
                "van %sx vervalt." % (p["week_index"], nl_date(p["week_start"]), p.get("was")))
    if k == "set_goal_field":
        def fmt(v):
            if v is None:
                return "geen"
            if p["field"] == "target_time_min":
                return hms(v)
            if p["field"] == "strength_day":
                return DOW[int(v)]
            if p["field"] == "priority":
                return "streeftijd" if v == "time" else "gezond finishen"
            return str(v)
        return "%s wordt %s (was %s). Het hele plan wordt hierna opnieuw opgebouwd." % (
            FIELD_NL.get(p["field"], p["field"]), fmt(p["value"]), fmt(p.get("was")))
    if k == "upload_week":
        return ("De %d trainingen van week %d (vanaf %s) worden als workout in Garmin "
                "Connect gezet en op de dag ingepland."
                % (p["sessions"], p["week"], nl_date(p["week_start"])))
    return p["kind"]


def apply_action(stored):
    """Voert een goedgekeurd voorstel uit. Pas hier gebeurt er iets."""
    p = stored["payload"]
    k = p["kind"]

    if k == "log_session":
        entry_id = store.log_add({
            "day": p["day"], "km": p.get("km"), "minutes": p.get("minutes"),
            "feel": p.get("feel"), "soreness": p.get("soreness"), "rpe": p.get("rpe"),
            "note": p.get("note"), "source": "chat"})
        return {"ok": True, "message": "In je logboek gezet.", "log_id": entry_id}

    if k == "adjust_week":
        decision = {
            "scale": p["scale"], "drop_quality": p["drop_quality"],
            "severity": ("fors lichter" if p["scale"] <= 0.75 else
                         "lichter" if p["scale"] < 0.98 else
                         "zwaarder" if p["scale"] > 1.02 else "ongewijzigd"),
            "reasons": ["Coach: " + p["reason"]],
        }
        store.save_adaptation(p["week_start"], decision,
                              {"reason": "coach", "via": "chat", "at": time.time()})
        return {"ok": True, "message": "Week %d bijgesteld naar %sx." % (p["week_index"], p["scale"])}

    if k == "clear_week_adjustment":
        n = store.delete_adaptation(p["week_start"])
        return {"ok": bool(n), "message": ("Bijstelling van week %d teruggedraaid." % p["week_index"])
                if n else "Er was niets om terug te draaien."}

    if k == "set_goal_field":
        cfg = dict(store.load_goal())
        cfg[p["field"]] = p["value"]
        store.save_goal(cfg)
        return {"ok": True, "message": "%s aangepast. Het plan is opnieuw opgebouwd."
                % FIELD_NL.get(p["field"], p["field"])}

    if k == "upload_week":
        res = _upload_fn({"week": p["week"]})
        ok = res.get("uploaded", 0)
        return {"ok": ok > 0, "message": "%d van %d trainingen in je Garmin-agenda gezet."
                % (ok, res.get("total", 0)), "detail": res}

    return {"ok": False, "message": "onbekende actie"}


# -------------------------------------------------------- proactief openen

def opening(state, runs_all):
    """Wat de bot zegt zonder dat er iets gevraagd is.

    Bewust zonder Claude: dit moet er direct staan als de pagina opent, altijd
    hetzelfde bij dezelfde cijfers, en het mag niets kosten. De bot biedt hier
    actief aan te helpen met wat er nu speelt.
    """
    today = _d(state["today"])
    cur = current_week(state)
    logs = {e["day"] for e in store.log_recent(40)}
    chips, lines = [], []

    # Een recente run die nog niet in zijn logboek staat: daar wil hij iets over
    # kwijt, en dat is precies wat Garmin niet weet.
    recent = [r for r in (runs_all or [])
              if run_day(r) and (today - _d(run_day(r))).days <= 3 and run_day(r) not in logs]
    if recent:
        r = recent[0]
        km, mn = run_km(r), run_min(r)
        d = _d(run_day(r))
        when = "Vandaag" if d == today else ("Gisteren" if (today - d).days == 1
                                             else DOW[d.weekday()].capitalize())
        lines.append("%s liep je %s km in %s (%s). Hoe ging dat?"
                     % (when, nl_num(km), hms(mn), pace(mn, km) or "–"))
        chips.append("Ging lekker, voelde fris")
        chips.append("Zware benen, ging moeizaam")

    # Staat er vandaag een training op het programma?
    sess_today = [s for s in (cur or {}).get("sessions", []) if s["date"] == state["today"]]
    if sess_today:
        s = sess_today[0]
        lines.append("Vandaag staat **%s** (%d min) op het programma." % (s["label"], s["minutes"]))
        chips.append("Wat moet ik vandaag precies doen?")
    elif cur:
        nxt_sess = [s for s in cur["sessions"] if s["date"] > state["today"]]
        if nxt_sess:
            s = nxt_sess[0]
            lines.append("Volgende training: %s op %s (%d min)."
                         % (s["label"], DOW[_d(s["date"]).weekday()], s["minutes"]))

    # Herstelsignalen die een gesprek waard zijn.
    health = (_metric(state, "health") or {}).get("data") or {}
    rows = health.get("rows") or []
    low = [r for r in rows[-7:] if r.get("hrv_ms") and r.get("hrv_baseline_low_ms")
           and r["hrv_ms"] < r["hrv_baseline_low_ms"]]
    rd = (_metric(state, "readiness") or {})
    decision = (rd.get("data") or rd or {}).get("decision")
    if len(low) >= 3:
        lines.append("Let op: je HRV zat %d van de laatste 7 dagen onder je basislijn."
                     % len(low))
        chips.append("Moet ik het rustiger aan doen?")
    elif decision in ("REST", "MODIFY"):
        lines.append("Garmin zet je herstel vandaag op %s." % decision)
        chips.append("Moet ik het rustiger aan doen?")

    # Niets bijzonders: dan de stand van zaken en een open aanbod.
    if not lines:
        st = running_stats(runs_all)
        if st:
            lines.append("Deze week sta je op %s km, nog %d dagen tot de CPC Loop."
                         % (nl_num(st["this_week"]["km"], 1), state["days_to_race"]))

    chips += ["Lig ik op schema voor 2:00?", "Ik heb gelopen", "Ik heb ergens pijn"]
    seen, uniq = set(), []
    for c in chips:
        if c not in seen:
            seen.add(c)
            uniq.append(c)

    greet = ("Hoi Eelco! " if datetime.now().hour < 18 else "Goedenavond! ")
    return {"text": greet + " ".join(lines[:3]) + "\n\nKan ik ergens mee helpen?",
            "chips": uniq[:5]}


# ------------------------------------------------------------------- routes

def _rate_limited():
    if store.chat_count_since(time.time() - 60) >= MAX_PER_MIN:
        return "Even rustig: te veel berichten in een minuut."
    if store.chat_count_since(time.time() - 86400) >= MAX_PER_DAY:
        return "De dagelijkse limiet van %d berichten is bereikt." % MAX_PER_DAY
    return None


def _ask_bridge(system, prompt):
    r = requests.post(
        COACH_URL.rstrip("/") + "/ask",
        headers={"Authorization": "Bearer " + COACH_TOKEN, "Content-Type": "application/json"},
        json={"system": system, "prompt": prompt, "model": COACH_MODEL},
        timeout=COACH_TIMEOUT)
    if r.status_code != 200:
        try:
            msg = r.json().get("error")
        except ValueError:
            msg = r.text[:200]
        raise RuntimeError(msg or "coach gaf status %s" % r.status_code)
    return r.json()


@bp.route("/api/chat/opening")
@auth.require_auth
def api_opening():
    if not configured():
        return jsonify({"enabled": False,
                        "reason": "COACH_TOKEN of COACH_URL ontbreekt in de container"})
    state = _state_provider(False)
    runs_all = store.cache_get("runs")[0] or []
    out = opening(state, runs_all)
    out["enabled"] = True
    out["history"] = [{"role": h["role"], "text": h["text"], "ts": h["ts"],
                       "actions": (h["meta"] or {}).get("actions") or []}
                      for h in store.chat_history(30)]
    # Voorstellen die al uitgevoerd of afgewezen zijn, moeten na een herlaad niet
    # opnieuw als open knop verschijnen.
    ids = [a["id"] for h in out["history"] for a in h["actions"]]
    st = store.actions_status(ids)
    for h in out["history"]:
        for a in h["actions"]:
            a["status"] = st.get(a["id"], "pending")
    return jsonify(out)


@bp.route("/api/chat", methods=["POST"])
@auth.require_auth
def api_chat():
    if not configured():
        return jsonify({"error": "de coach is niet ingesteld"}), 503

    msg = str((request.get_json(silent=True) or {}).get("message") or "").strip()
    if not msg:
        return jsonify({"error": "leeg bericht"}), 400
    if len(msg) > MAX_MSG_CHARS:
        return jsonify({"error": "bericht is te lang (max %d tekens)" % MAX_MSG_CHARS}), 413
    limited = _rate_limited()
    if limited:
        return jsonify({"error": limited}), 429

    state = _state_provider(False)
    runs_all = store.cache_get("runs")[0] or []
    history = store.chat_history(HISTORY_TURNS * 2)

    store.chat_add("user", msg)
    try:
        got = _ask_bridge(system_prompt(state, runs_all), conversation(history, msg))
    except (requests.RequestException, RuntimeError) as e:
        current_app.logger.warning("coach faalde: %s", e)
        return jsonify({"error": "de coach is even niet bereikbaar: %s" % str(e)[:200]}), 502

    text, raw = parse_actions(got.get("text") or "")
    actions, dropped = [], []
    for a in raw[:2]:
        try:
            payload = validate(a, state)
        except (ValueError, KeyError, TypeError) as e:
            dropped.append(str(e)[:150])
            current_app.logger.warning("voorstel geweigerd: %s (%s)", e, str(a)[:200])
            continue
        aid = uuid.uuid4().hex[:12]
        store.action_put(aid, payload["kind"], payload)
        actions.append({"id": aid, "kind": payload["kind"],
                        "title": SUMMARY.get(payload["kind"], payload["kind"]),
                        "detail": describe(payload), "status": "pending"})

    if not text and actions:
        text = "Ik heb hier een voorstel voor je."
    meta = {"actions": actions, "cost_usd": got.get("cost_usd"), "ms": got.get("ms"),
            "model": got.get("model"), "dropped": dropped}
    store.chat_add("coach", text, meta)
    return jsonify({"reply": text, "actions": actions, "dropped": dropped,
                    "usage": got.get("usage"), "cost_usd": got.get("cost_usd"),
                    "ms": got.get("ms")})


@bp.route("/api/chat/apply", methods=["POST"])
@auth.require_auth
def api_apply():
    body = request.get_json(silent=True) or {}
    aid = str(body.get("id") or "")
    decision = str(body.get("decision") or "apply")
    stored = store.action_get(aid)
    if not stored:
        return jsonify({"error": "dit voorstel bestaat niet (meer)"}), 404
    if stored["status"] != "pending":
        return jsonify({"error": "dit voorstel is al %s" % stored["status"]}), 409

    if decision == "reject":
        store.action_mark(aid, "rejected")
        return jsonify({"ok": True, "status": "rejected", "message": "Niet doorgevoerd."})

    # Opnieuw valideren tegen het plan zoals het nu is: tussen voorstel en klik
    # kan de week begonnen zijn of het doel veranderd.
    state = _state_provider(False)
    try:
        validate(dict(stored["payload"]), state)
    except (ValueError, KeyError, TypeError) as e:
        store.action_mark(aid, "stale", {"error": str(e)[:200]})
        return jsonify({"error": "dit voorstel kan nu niet meer: %s" % e}), 409

    try:
        res = apply_action(stored)
    except Exception as e:                                    # noqa: BLE001
        current_app.logger.error("actie %s faalde: %s", stored["kind"], e)
        store.action_mark(aid, "failed", {"error": str(e)[:300]})
        return jsonify({"error": "uitvoeren mislukte: %s" % str(e)[:200]}), 500

    store.action_mark(aid, "applied" if res.get("ok") else "failed", res)
    return jsonify({"ok": bool(res.get("ok")), "status": "applied" if res.get("ok") else "failed",
                    "message": res.get("message"), "detail": res.get("detail")})


@bp.route("/api/chat/clear", methods=["POST"])
@auth.require_auth
def api_clear():
    store.chat_clear()
    return jsonify({"ok": True})


@bp.route("/api/chat/log")
@auth.require_auth
def api_log():
    return jsonify({"items": store.log_recent(40)})


@bp.route("/api/chat/log/delete", methods=["POST"])
@auth.require_auth
def api_log_delete():
    body = request.get_json(silent=True) or {}
    n = store.log_delete(int(body.get("id") or 0))
    return jsonify({"ok": bool(n)})


@bp.route("/api/chat/health")
@auth.require_auth
def api_coach_health():
    if not configured():
        return jsonify({"ok": False, "error": "COACH_TOKEN of COACH_URL ontbreekt"})
    try:
        r = requests.get(COACH_URL.rstrip("/") + "/health",
                         headers={"Authorization": "Bearer " + COACH_TOKEN}, timeout=60)
        return jsonify({"ok": r.status_code == 200, "bridge": r.json()})
    except (requests.RequestException, ValueError) as e:
        return jsonify({"ok": False, "error": str(e)[:200]})
