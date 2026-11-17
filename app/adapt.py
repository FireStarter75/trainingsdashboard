"""Wekelijkse aanpassing van de komende trainingsweek.

Het plan is een voornemen; je lichaam heeft het laatste woord. Deze module
leest elke week wat er werkelijk is gebeurd en hoe het herstel ervoor staat, en
stelt de eerstvolgende week bij.

Opzet:
- Elk signaal levert een eigen schaalfactor voor het volume en mag de
  kwaliteitssessie schrappen.
- De uitkomst is de LAAGSTE factor, niet het product. Vier matige signalen
  mogen niet tot een halvering leiden; het zwaarste signaal bepaalt.
- Omhoog bijstellen mag maar mondjesmaat (max +8%) en alleen als alles groen is.
- Elke beslissing bewaart waarom, zodat terug te zien is wat er is gebeurd.
"""
from datetime import date, datetime, timedelta

# Ondergrens: ook een slechte week blijft een week trainen. Volledig stilleggen
# is zelden het goede antwoord en hoort een menselijk besluit te zijn.
MIN_SCALE = 0.60
MAX_SCALE = 1.08


def _f(x, default=None):
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def gather_signals(load_data, readiness_data, health_rows, actuals, upcoming, recent_weeks):
    """Verzamelt de ruwe signalen. Ontbrekende data is geen fout, alleen stilte."""
    s = {"missing": []}

    latest = (load_data or {}).get("latest") or {}
    s["acwr"] = _f(latest.get("acwr"))
    s["tsb"] = _f(latest.get("tsb"))
    s["ctl"] = _f(latest.get("ctl"))
    s["warming_up"] = bool(latest.get("warming_up"))
    if s["acwr"] is None:
        s["missing"].append("belasting")

    rd = readiness_data or {}
    s["readiness"] = rd.get("decision")
    if not s["readiness"]:
        s["missing"].append("readiness")

    rows = sorted(health_rows or [], key=lambda r: r.get("date") or "")
    recent = rows[-7:]
    hrv = [r for r in recent if r.get("hrv_ms")]
    if hrv:
        low = [r for r in hrv if r.get("hrv_baseline_low_ms")
               and r["hrv_ms"] < r["hrv_baseline_low_ms"]]
        s["hrv_days_below_baseline"] = len(low)
        s["hrv_last"] = hrv[-1]["hrv_ms"]
    else:
        s["hrv_days_below_baseline"] = None
        s["missing"].append("hrv")

    rhr = [r["resting_hr_bpm"] for r in rows if r.get("resting_hr_bpm")]
    if len(rhr) >= 8:
        base = sum(rhr[-28:-3]) / max(1, len(rhr[-28:-3]))
        s["rhr_recent"] = sum(rhr[-3:]) / 3.0
        s["rhr_baseline"] = base
        s["rhr_delta"] = s["rhr_recent"] - base
    else:
        s["rhr_delta"] = None
        s["missing"].append("rusthartslag")

    sleep = [r["sleep_h"] for r in rows[-7:] if r.get("sleep_h")]
    s["sleep_avg_7d"] = round(sum(sleep) / len(sleep), 2) if sleep else None

    # Hoeveel van het plan is de afgelopen vier weken echt gedaan?
    done = planned = 0.0
    for wk in recent_weeks:
        a = (actuals or {}).get(wk["start"])
        done += (a or {}).get("minutes", 0)
        planned += wk.get("planned_min", 0)
    s["compliance"] = round(done / planned, 3) if planned > 0 else None
    s["done_4w_min"] = round(done)
    s["planned_4w_min"] = round(planned)
    s["upcoming"] = upcoming["start"] if upcoming else None
    return s


def decide(s):
    """Weegt de signalen en geeft een besluit voor de komende week."""
    votes = []     # (factor, reden, drop_quality)

    acwr = s.get("acwr")
    if acwr is not None and not s.get("warming_up"):
        if acwr >= 1.5:
            votes.append((0.70, "ACWR %.2f: je belasting is te snel opgelopen" % acwr, True))
        elif acwr >= 1.3:
            votes.append((0.85, "ACWR %.2f: net boven de waarschuwingsgrens" % acwr, False))
        elif acwr < 0.8:
            votes.append((1.05, "ACWR %.2f: er zit ruimte voor meer prikkel" % acwr, False))

    tsb = s.get("tsb")
    if tsb is not None and tsb <= -25:
        votes.append((0.80, "Vorm %.0f: flink vermoeid" % tsb, True))

    rd = s.get("readiness")
    if rd == "REST":
        votes.append((0.70, "Garmin readiness staat op REST", True))
    elif rd == "MODIFY":
        votes.append((0.88, "Garmin readiness staat op MODIFY", False))

    hrv_low = s.get("hrv_days_below_baseline")
    if hrv_low is not None and hrv_low >= 3:
        votes.append((0.85, "HRV %d van de 7 dagen onder je basislijn" % hrv_low, True))

    rhr_d = s.get("rhr_delta")
    if rhr_d is not None and rhr_d >= 5:
        votes.append((0.85, "Rusthartslag %.0f bpm boven je basislijn" % rhr_d, False))

    comp = s.get("compliance")
    if comp is not None:
        if comp < 0.6:
            votes.append((0.85, "Maar %d%% van het plan gedaan: niet terugspringen naar de curve"
                          % round(comp * 100), False))
        elif comp > 0.95 and not votes:
            votes.append((1.05, "Plan volledig gevolgd en alle signalen groen", False))

    sleep = s.get("sleep_avg_7d")
    if sleep is not None and sleep < 6.0:
        votes.append((0.88, "Gemiddeld %.1f uur slaap deze week" % sleep, False))

    if not votes:
        return {"scale": 1.0, "drop_quality": False, "severity": "ongewijzigd",
                "reasons": ["Alle signalen binnen de bandbreedte."], "votes": []}

    # Laagste factor wint; alleen omhoog als geen enkel signaal omlaag wijst.
    down = [v for v in votes if v[0] < 1.0]
    if down:
        scale = min(v[0] for v in down)
        drop = any(v[2] for v in down)
    else:
        scale = min(MAX_SCALE, max(v[0] for v in votes))
        drop = False

    scale = max(MIN_SCALE, min(MAX_SCALE, scale))
    severity = ("fors lichter" if scale <= 0.75 else
                "lichter" if scale < 0.98 else
                "zwaarder" if scale > 1.02 else "ongewijzigd")
    return {"scale": round(scale, 3), "drop_quality": drop, "severity": severity,
            "reasons": [v[1] for v in votes], "votes": votes}


def week_of(the_plan, day):
    for wk in the_plan["weeks"]:
        if wk["start"] <= day <= wk["end"]:
            return wk
    return None


def next_week(the_plan, today=None):
    """De eerstvolgende week die nog niet begonnen is."""
    today = (today or date.today()).isoformat()
    for wk in the_plan["weeks"]:
        if wk["start"] > today:
            return wk
    return None
