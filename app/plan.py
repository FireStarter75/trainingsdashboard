"""Trainingsplangenerator.

Doelgestuurd en deterministisch: uit een doel (afstand, datum, eventueel een
streeftijd) en een basislijn rolt een periodiseerd schema.

Twee modi:

priority="health"  - gezond uitkomen. Alles onder LT1, run/walk, lage prikkel.
priority="time"    - een streeftijd halen. Vier dagen, een wekelijkse
                     kwaliteitssessie op drempel, en in de piekfase blokken op
                     wedstrijdtempo in de duurloop.

Gemeenschappelijk: elke 4e week herstel op 75%, twee weken taper, en de
hartslagbanden komen uit de eigen drempels (LT1, LTHR, HRmax) in plaats van uit
Garmins named zones, die daar te grof voor zijn.
"""
from datetime import date, datetime, timedelta

DAY_PATTERNS = {
    2: [1, 6],
    3: [1, 3, 6],
    4: [1, 3, 5, 6],
    5: [0, 1, 3, 5, 6],
}

RUN_WALK_LADDER = [
    (0.00, 120, 60), (0.18, 180, 60), (0.36, 240, 60),
    (0.54, 300, 60), (0.72, 360, 60), (0.88, 540, 60),
]

# Riegel-exponenten: hoe hoger, hoe sterker de terugval op de lange afstand.
EXP_UNTRAINED = 1.15
EXP_TRAINED = 1.06
# Verwachte winst op een eerdere wedstrijdtijd na een volledig, consistent blok.
PR_GAIN = 0.05
PR_GAIN_BAND = 0.03

DEFAULT_CONFIG = {
    "goal_name": "NN CPC Loop Den Haag - halve marathon",
    "race_date": "2027-03-14",
    "distance_km": 21.1,
    "days_per_week": 3,          # LOOPdagen; de krachtdag staat los
    "strength_day": 5,           # 0=ma .. 6=zo; None = geen krachttraining
    "priority": "time",
    "target_time_min": 120,
    # Terugkerend na een lange pauze: de eerste weken bewust vlak houden.
    # Pezen en botten passen zich trager aan dan hart en longen.
    "acwr_cap": 1.40,
    "ramp_in_weeks": 3,
    "ramp_in_factor": 0.82,
    "start_long_min": 35,
    "easy_hr": [128, 147],        # onder LT1 (149)
    "steady_hr": [150, 160],      # tussen LT1 en LTHR: wedstrijdtempo-gevoel
    "threshold_hr": [160, 170],   # rond LTHR (166)
    "interval_hr": [172, 182],    # boven drempel
    "walk_hr": [95, 130],
    "start_date": None,
}


def _monday(d):
    return d - timedelta(days=d.weekday())


def _parse(d):
    if isinstance(d, date):
        return d
    return datetime.strptime(d, "%Y-%m-%d").date()


def run_walk_for(progress):
    run_s, walk_s = RUN_WALK_LADDER[0][1], RUN_WALK_LADDER[0][2]
    for threshold, r, w in RUN_WALK_LADDER:
        if progress >= threshold:
            run_s, walk_s = r, w
    return run_s, walk_s


def riegel(ref_min, ref_km, target_km, exponent, speed_gain=0.0):
    if ref_km < 1.0:
        return ref_min
    return ref_min * (1.0 - speed_gain) * ((target_km / ref_km) ** exponent)


def estimates(cfg, baseline):
    """Verwachtingen voor de racedag.

    Een eerdere wedstrijd op (ongeveer) de doelafstand is verreweg de beste
    voorspeller; die krijgt voorrang boven extrapolatie uit een korte run.
    """
    d = cfg["distance_km"]
    pace = baseline.get("pace_min_per_km") or 7.5
    ref_km = baseline.get("longest_km") or 5.0
    now = riegel(pace * ref_km, ref_km, d, EXP_UNTRAINED)

    pr = baseline.get("best_race") or None
    out = {
        "race_minutes_now": round(now, 1),
        "basis": "huidige vorm",
        "reference": {"km": ref_km, "minutes": round(pace * ref_km, 1),
                      "pace_min_per_km": round(pace, 3)},
        "model": {"exponent_now": EXP_UNTRAINED, "exponent_after": EXP_TRAINED},
    }

    if pr:
        pr_at_target = riegel(pr["minutes"], pr["km"], d, EXP_TRAINED)
        after = pr_at_target * (1.0 - PR_GAIN)
        best = pr_at_target * (1.0 - PR_GAIN - PR_GAIN_BAND)
        worst = pr_at_target * (1.0 - max(0.0, PR_GAIN - PR_GAIN_BAND))
        out.update({
            "basis": "eerdere wedstrijd",
            "pr": pr,
            "pr_at_distance_min": round(pr_at_target, 1),
            "race_minutes_after": round(after, 1),
            "race_minutes_best": round(best, 1),
            "race_minutes_worst": round(worst, 1),
            "note": ("Gebaseerd op je eigen wedstrijd van %s (%s km in %d:%02d). "
                     "Verwachte winst %d%% uit een vollediger en consistenter blok "
                     "dan toen. Schatting, geen belofte."
                     % (pr["date"], pr["km"], pr["minutes"] // 60, pr["minutes"] % 60,
                        round(PR_GAIN * 100))),
        })
    else:
        after = riegel(pace * ref_km, ref_km, d, EXP_TRAINED, 0.05)
        out.update({
            "race_minutes_after": round(after, 1),
            "race_minutes_best": round(after * 0.95, 1),
            "race_minutes_worst": round(after * 1.05, 1),
            "note": ("Geextrapoleerd uit je langste recente run; er is geen eerdere "
                     "wedstrijd op deze afstand om op te bouwen. Ruime marge."),
        })

    tgt = cfg.get("target_time_min")
    if tgt:
        out["target_min"] = tgt
        out["target_pace_min_per_km"] = round(tgt / d, 3)
        out["target_gap_min"] = round(out["race_minutes_after"] - tgt, 1)
        out["target_within_band"] = out["race_minutes_best"] <= tgt
    return out


def build_plan(config=None, baseline=None, adaptations=None):
    cfg = dict(DEFAULT_CONFIG)
    cfg.update(config or {})
    baseline = baseline or {}
    adaptations = adaptations or {}
    timed = cfg.get("priority") == "time"

    race = _parse(cfg["race_date"])
    start = _parse(cfg["start_date"]) if cfg.get("start_date") else _monday(date.today()) + timedelta(days=7)
    start = _monday(start)
    weeks_total = max(1, int((_monday(race) - start).days / 7) + 1)
    days = DAY_PATTERNS.get(int(cfg["days_per_week"]), DAY_PATTERNS[3])

    taper_weeks = 2 if weeks_total >= 12 else (1 if weeks_total >= 6 else 0)
    block = weeks_total - 1 - taper_weeks
    base_weeks = max(1, round(block * (0.35 if timed else 0.45)))
    peak_weeks = max(1, round(block * (0.25 if timed else 0.20)))
    dev_weeks = max(0, block - base_weeks - peak_weeks)

    est = estimates(cfg, baseline)
    goal_min = cfg.get("target_time_min") or est["race_minutes_after"]

    # Duurloop: bij een tijdsdoel wil je tegen de wedstrijdduur aan zitten,
    # bij gezond uitkomen juist ruim eronder blijven.
    peak_long = min(165.0 if timed else 150.0, goal_min * (1.0 if timed else 0.85))
    start_long = float(cfg["start_long_min"])
    peak_long = max(peak_long, start_long * 1.5)

    weeks = []
    week_meta = []
    qcount = {}
    for w in range(weeks_total):
        wk_start = start + timedelta(days=7 * w)
        remaining = weeks_total - w

        if remaining == 1:
            phase = "race"
        elif remaining <= 1 + taper_weeks:
            phase = "taper"
        elif w < base_weeks:
            phase = "basis"
        elif w < base_weeks + dev_weeks:
            phase = "opbouw"
        else:
            phase = "piek"

        progress = min(1.0, w / max(1, block - 1))
        deload = phase in ("basis", "opbouw", "piek") and (w + 1) % 4 == 0

        if phase == "race":
            long_min = 0.0
        elif phase == "taper":
            long_min = peak_long * (0.38 if remaining - 1 == 1 else 0.62)
        else:
            long_min = start_long * ((peak_long / start_long) ** progress)
            if w < int(cfg.get("ramp_in_weeks") or 0):
                # Gewenningsperiode: nog niet de volle curve volgen.
                long_min *= float(cfg.get("ramp_in_factor") or 1.0)
            if deload:
                long_min *= 0.75

        run_s, walk_s = run_walk_for(progress)
        if phase != "race" and not deload:
            qslot = qcount.get(phase, 0)
            qcount[phase] = qslot + 1
        else:
            qslot = qcount.get(phase, 0)

        sessions = _week_sessions(wk_start, days, cfg, timed, phase, deload,
                                  progress, long_min, run_s, walk_s, goal_min,
                                  qslot=qslot)

        week_meta.append({"wk_start": wk_start, "progress": progress,
                          "run_s": run_s, "walk_s": walk_s, "qslot": qslot})

        sday = cfg.get("strength_day")
        if sday is not None and phase != "race":
            sessions.append(_strength(wk_start + timedelta(days=int(sday)), phase, deload))
        sessions.sort(key=lambda x: x["date"])

        weeks.append({
            "index": w + 1, "start": wk_start.isoformat(),
            "end": (wk_start + timedelta(days=6)).isoformat(),
            "phase": phase, "deload": deload,
            "long_min": round(long_min),
            "planned_min": round(sum(s["minutes"] for s in sessions
                                    if s["kind"] not in ("race", "strength"))),
            "race_min": round(sum(s["minutes"] for s in sessions if s["kind"] == "race")),
            "run_walk": "%d:%d" % (run_s // 60, walk_s // 60) if not timed else None,
            "sessions": sessions,
        })

    meta = {w["index"]: m for w, m in zip(weeks, week_meta)}

    def rebuild(wk, new_long):
        m = meta[wk["index"]]
        ad = adaptations.get(wk["start"]) or {}
        wk["long_min"] = round(new_long)
        wk["sessions"] = _week_sessions(m["wk_start"], days, cfg, timed, wk["phase"],
                                        wk["deload"], m["progress"], new_long,
                                        m["run_s"], m["walk_s"], goal_min,
                                        drop_quality=bool(ad.get("drop_quality")),
                                        qslot=m.get("qslot", 0))
        week_meta.append({"wk_start": wk_start, "progress": progress,
                          "run_s": run_s, "walk_s": walk_s, "qslot": qslot})

        sday = cfg.get("strength_day")
        if sday is not None and wk["phase"] != "race":
            wk["sessions"].append(_strength(m["wk_start"] + timedelta(days=int(sday)),
                                            wk["phase"], wk["deload"]))
        wk["sessions"].sort(key=lambda x: x["date"])

    # Wekelijkse aanpassing uit de echte Garmin-data toepassen voordat de
    # ACWR-bewaking eroverheen gaat: de bewaking mag een verlichting nooit
    # ongedaan maken, alleen verder verlagen.
    for wk in weeks:
        ad = adaptations.get(wk["start"])
        if ad and wk["phase"] != "race":
            rebuild(wk, wk["long_min"] * float(ad.get("scale") or 1.0))
            wk["adapted"] = {"scale": ad.get("scale"), "severity": ad.get("severity"),
                             "reasons": ad.get("reasons"),
                             "drop_quality": bool(ad.get("drop_quality")),
                             "decided_at": ad.get("decided_at")}

    for wk in weeks:
        wk["_raw_load"] = week_load(wk)
    weeks = apply_acwr_guard(weeks, baseline.get("recent_weekly_load"), rebuild,
                             float(cfg.get("acwr_cap") or ACWR_CAP),
                             seed_long=baseline.get("longest_min"))
    for wk in weeks:
        wk.pop("_raw_load", None)

    return {
        "config": cfg,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "load_model": {
            "weights": LOAD_WEIGHTS, "acwr_warn": ACWR_WARN, "acwr_cap": ACWR_CAP,
            "acwr_low": ACWR_LOW, "chronic_floor": CHRONIC_FLOOR,
            "acwr_cap_used": float(cfg.get("acwr_cap") or ACWR_CAP),
            "max_jump_warmup": WARMUP_MAX_JUMP, "max_jump_normal": NORMAL_MAX_JUMP,
        },
        "weeks_total": weeks_total,
        "phases": {"basis": base_weeks, "opbouw": dev_weeks,
                   "piek": peak_weeks, "taper": taper_weeks, "race": 1},
        "estimate": dict(est, peak_long_min=round(peak_long)),
        "weeks": weeks,
    }



def _week_sessions(wk_start, days, cfg, timed, phase, deload, progress,
                   long_min, run_s, walk_s, goal_min, drop_quality=False,
                   qslot=0):
    """Bouwt de loopsessies van een week uit de duurloopduur.

    Alles schaalt met `long_min`, dus het weekvolume bijstellen gebeurt door
    deze functie opnieuw aan te roepen met een andere waarde - niet door
    sessies achteraf te verkleinen, want dan klopt de omschrijving niet meer.
    """
    out = []
    for slot, dow in enumerate(days):
        sdate = wk_start + timedelta(days=dow)
        is_last = slot == len(days) - 1
        if phase == "race":
            out.append(_race_session(sdate, cfg, goal_min) if is_last
                       else _easy(sdate, 25, cfg, timed, run_s, walk_s, "Losmaken"))
        elif is_last:
            out.append(_long(sdate, long_min, cfg, timed, run_s, walk_s, phase, progress, goal_min))
        elif timed and slot == 1 and not deload and not drop_quality and (
                phase != "basis" or progress > 0.08):
            kind = quality_kind(phase, qslot)
            if kind == "tempo":
                out.append(_tempo(sdate, cfg, long_min, phase))
            elif kind == "intervals":
                out.append(_intervals(sdate, cfg, long_min, progress,
                                      taper=(phase == "taper")))
            elif kind == "hills":
                out.append(_hills(sdate, cfg, long_min, phase))
            elif kind == "strides":
                out.append(_strides(sdate, cfg, long_min))
            else:
                out.append(_quality(sdate, cfg, phase, progress,
                                    taper=(phase == "taper"), long_min=long_min))
        elif not timed and slot == 1 and phase in ("opbouw", "piek") and not deload:
            out.append(_quality(sdate, cfg, phase, progress, long_min=long_min))
        else:
            # De rustige run groeit mee met de duurloop. Een hoge ondergrens
            # zou hem wekenlang vastzetten, waardoor alle volumegroei op de
            # duurloop terechtkomt - precies het patroon dat blessures geeft.
            share = 0.6 if timed else 0.5
            em = max(20.0, min(long_min * share, 75.0))
            out.append(_easy(sdate, em, cfg, timed, run_s, walk_s))
    return out


# --------------------------------------------------------------- belasting
#
# ACWR = acute belasting (deze week) gedeeld door chronische (gemiddelde van de
# vier weken ervoor). Boven 1,3 loopt het blessurerisico op, boven 1,5 sterk.
# Drempels gelijkgehouden aan die van de endurance-server.
#
# Belangrijke beperking: bij een chronische belasting van bijna nul is ACWR
# betekenisloos. Wie terugkomt van maanden niets heeft per definitie een
# enorme ratio, hoe voorzichtig hij ook begint. Daarom twee regimes:
#
#   opwarmen  - chronisch onder de vloer: stuur op absolute weekgroei
#   normaal   - chronisch boven de vloer: stuur op ACWR
#
# Krachttraining telt niet mee: de ACWR-drempels komen uit looponderzoek, en
# de belasting op pezen van squats laat zich niet in loopminuten uitdrukken.

LOAD_WEIGHTS = {"easy": 1.0, "long": 1.15, "strides": 1.1, "hills": 1.45,
                "tempo": 1.4, "intervals": 1.6, "threshold": 1.5,
                "steady": 1.3, "race": 1.5, "strength": 0.0}

ACWR_WARN = 1.3
ACWR_CAP = 1.25          # waar het plan zichzelf op afremt
ACWR_LOW = 0.8
CHRONIC_FLOOR = 60.0     # loopminuten/week waaronder ACWR niets zegt
# Sprong in de duurloop ten opzichte van de langste van de vier weken ervoor.
# Hiervoor is de evidentie sterker dan voor ACWR: boven ~130% is een stijging
# van het blessurerisico gemeten, terwijl de ACWR-drempels omstreden zijn.
LONG_SPIKE_CAP = 1.15
WARMUP_MAX_JUMP = 0.22   # maximale weekgroei tijdens het opwarmen
NORMAL_MAX_JUMP = 0.15   # daarna, gelijk aan de week_jump_pct van de server


def session_load(sess):
    return sess["minutes"] * LOAD_WEIGHTS.get(sess["kind"], 1.0)


def week_load(week):
    return sum(session_load(s) for s in week["sessions"] if s["kind"] != "race")


def apply_acwr_guard(weeks, seed_loads, rebuild, cap=ACWR_CAP, seed_long=None):
    """Begrenst de opbouwsnelheid en noteert de ACWR per week.

    `rebuild(week, long_min)` bouwt de sessies van een week opnieuw op; zo
    blijft de omschrijving altijd kloppen met de duur.

    `seed_loads` zijn de werkelijke loopbelastingen van de laatste vier weken,
    zodat de eerste planweken tegen de echte situatie worden afgezet.
    """
    history = [float(x) for x in (seed_loads or [])][-4:]
    while len(history) < 4:
        history.insert(0, 0.0)
    long_hist = [float(seed_long or 0)] if seed_long else []

    for wk in weeks:
        if wk["phase"] == "race":
            wk["load"] = round(week_load(wk))
            wk["acwr"] = None
            wk["acwr_note"] = "racewk"
            continue

        chronic = sum(history) / len(history)
        recent_peak = max(history[-3:]) if history else 0.0
        warming = chronic < CHRONIC_FLOOR

        # De weeksprong wordt afgezet tegen de zwaarste van de laatste drie
        # weken, niet tegen de vorige. Anders straft de regel het terugkeren
        # na een herstelweek af, terwijl dat volume al bewezen haalbaar was.
        if warming:
            ceiling = max(recent_peak * (1.0 + WARMUP_MAX_JUMP), 45.0)
            reason = "opwarmen"
        else:
            by_acwr = cap * chronic
            by_spike = recent_peak * 1.35 if recent_peak > 0 else by_acwr
            ceiling = min(by_acwr, by_spike)
            reason = "acwr" if by_acwr <= by_spike else "piekbegrenzing"

        # Eerst de duurloop zelf begrenzen: een sprong daarin is een sterkere
        # blessurevoorspeller dan het weektotaal, en de ACWR-bewaking hieronder
        # ziet hem niet omdat die alleen naar de som kijkt.
        ref_long = max(long_hist[-4:]) if long_hist else 0.0
        if ref_long > 0 and wk["long_min"] > ref_long * LONG_SPIKE_CAP:
            rebuild(wk, ref_long * LONG_SPIKE_CAP)
            wk["long_capped"] = {"ref": round(ref_long),
                                 "cap": round(ref_long * LONG_SPIKE_CAP)}

        load = week_load(wk)
        if load > ceiling > 0:
            # De belasting is niet helemaal lineair in de duurloopduur (de
            # drempelsessie heeft een ondergrens), dus een paar rondes.
            for _ in range(5):
                factor = ceiling / max(load, 1e-6)
                if factor >= 0.995:
                    break
                new_long = max(20.0, wk["long_min"] * factor)
                rebuild(wk, new_long)
                load = week_load(wk)
            wk["capped"] = {"reason": reason,
                            "factor": round(load / max(week_load_uncapped(wk), 1e-6), 3)}

        wk["planned_min"] = round(sum(x["minutes"] for x in wk["sessions"]
                                      if x["kind"] not in ("race", "strength")))
        wk["load"] = round(load)
        wk["acwr"] = round(load / chronic, 2) if chronic > 1 else None
        wk["acwr_note"] = "opwarmen" if warming else "normaal"
        wk["chronic"] = round(chronic)
        wk["acwr_ceiling"] = round(ceiling)
        history.append(load)
        history = history[-4:]
        long_hist.append(wk["long_min"])
        long_hist = long_hist[-6:]
    return weeks


def week_load_uncapped(wk):
    return wk.get("_raw_load") or week_load(wk)


# ------------------------------------------------------------------ sessies

def _easy(d, minutes, cfg, timed, run_s, walk_s, label="Rustige duurloop"):
    minutes = round(minutes)
    lo, hi = cfg["easy_hr"]
    if timed:
        return {
            "date": d.isoformat(), "kind": "easy", "label": label,
            "minutes": minutes, "hr": [lo, hi],
            "builder": "create_run_workout",
            "args": {"run_seconds": max(600, (minutes - 10) * 60),
                     "warmup_min": 5, "cooldown_min": 5, "hr_min": lo, "hr_max": hi},
            "detail": "5 min inlopen, %d min rustig op %d-%d bpm, 5 min uitlopen"
                      % (max(10, minutes - 10), lo, hi),
            "uploadable": True,
        }
    warm = cool = 5
    body = max(run_s // 60, minutes - warm - cool)
    reps = max(1, round(body * 60 / (run_s + walk_s)))
    return {
        "date": d.isoformat(), "kind": "easy", "label": label,
        "minutes": warm + cool + round(reps * (run_s + walk_s) / 60), "hr": [lo, hi],
        "builder": "create_run_interval_workout",
        "args": {"repeats": reps, "rep_seconds": run_s, "recovery_seconds": walk_s,
                 "warmup_min": warm, "cooldown_min": cool, "hr_min": lo, "hr_max": hi,
                 "recovery_hr_min": cfg["walk_hr"][0], "recovery_hr_max": cfg["walk_hr"][1]},
        "detail": "5 min inwandelen, %dx (%d min lopen op %d-%d bpm / %d min wandelen), 5 min uit"
                  % (reps, run_s // 60, lo, hi, walk_s // 60),
        "uploadable": True,
    }


def _long(d, minutes, cfg, timed, run_s, walk_s, phase, progress, goal_min):
    minutes = round(minutes)
    lo, hi = cfg["easy_hr"]
    slo, shi = cfg["steady_hr"]

    # In de piekfase een blok op wedstrijdtempo achterin de duurloop: dat traint
    # precies waar een halve marathon beslist wordt.
    if timed and phase in ("piek", "opbouw") and progress > 0.55:
        rp_min = 20 if phase == "opbouw" else 30
        easy_min = max(20, minutes - rp_min - 10)
        return {
            "date": d.isoformat(), "kind": "long", "label": "Duurloop met wedstrijdtempo",
            "minutes": minutes, "hr": [lo, shi],
            "builder": "create_run_interval_workout",
            "args": {"repeats": 1, "rep_seconds": easy_min * 60,
                     "recovery_seconds": rp_min * 60,
                     "warmup_min": 5, "cooldown_min": 5,
                     "hr_min": lo, "hr_max": hi,
                     "recovery_hr_min": slo, "recovery_hr_max": shi},
            "detail": ("5 min inlopen, %d min rustig op %d-%d bpm, dan %d min op "
                       "wedstrijdtempo %d-%d bpm, 5 min uitlopen"
                       % (easy_min, lo, hi, rp_min, slo, shi)),
            "uploadable": True,
            "note": "Het tempoblok komt achteraan, op vermoeide benen. Dat is het punt.",
        }

    if timed:
        return {
            "date": d.isoformat(), "kind": "long", "label": "Duurloop",
            "minutes": minutes, "hr": [lo, hi],
            "builder": "create_run_workout",
            "args": {"run_seconds": max(900, (minutes - 12) * 60),
                     "warmup_min": 7, "cooldown_min": 5, "hr_min": lo, "hr_max": hi},
            "detail": "7 min inlopen, %d min op %d-%d bpm, 5 min uitlopen"
                      % (max(15, minutes - 12), lo, hi),
            "uploadable": True,
            "note": "Rustig betekent rustig. Kun je niet praten, dan ga je te hard.",
        }

    warm, cool = 8, 7
    body = max(run_s // 60, minutes - warm - cool)
    reps = max(1, round(body * 60 / (run_s + walk_s)))
    return {
        "date": d.isoformat(), "kind": "long", "label": "Duurloop",
        "minutes": warm + cool + round(reps * (run_s + walk_s) / 60), "hr": [lo, hi],
        "builder": "create_run_interval_workout",
        "args": {"repeats": reps, "rep_seconds": run_s, "recovery_seconds": walk_s,
                 "warmup_min": warm, "cooldown_min": cool, "hr_min": lo, "hr_max": hi,
                 "recovery_hr_min": cfg["walk_hr"][0], "recovery_hr_max": cfg["walk_hr"][1]},
        "detail": "8 min inwandelen, %dx (%d min lopen op %d-%d bpm / %d min wandelen), 7 min uit"
                  % (reps, run_s // 60, lo, hi, walk_s // 60),
        "uploadable": True,
        "note": "Tempo doet niet mee. Kun je niet praten, dan ga je te hard.",
    }


def _strides(d, cfg, long_min):
    """Korte versnellingen in de basisfase: wekt de benen zonder echte belasting."""
    lo, hi = cfg["easy_hr"]
    ilo, ihi = cfg["interval_hr"]
    return {
        "date": d.isoformat(), "kind": "strides", "label": "Rustig met versnellingen",
        "minutes": 20 + 6, "hr": [lo, hi],
        "builder": "create_run_interval_workout",
        "args": {"repeats": 6, "rep_seconds": 20, "recovery_seconds": 40,
                 "warmup_min": 12, "cooldown_min": 8,
                 "hr_min": ilo, "hr_max": ihi,
                 "recovery_hr_min": lo, "recovery_hr_max": hi},
        "detail": "12 min inlopen, 6x 20 sec vlot (niet sprinten) met 40 sec dribbelen, 8 min uitlopen",
        "uploadable": True,
        "note": "Dit is techniek, geen training. Soepel en ontspannen.",
    }



# Met drie loopdagen passen tempoloop, interval en twee herstelruns niet samen
# in een week. De donderdagse kwaliteitssessie rouleert daarom over de weken,
# zodat alle prikkels aan bod komen zonder de week te overladen.
#
# De volgorde per fase is bewust:
#   basis   - versnellingen en heuvels: kracht en techniek, weinig belasting
#   opbouw  - drempel is de motor, tempo en interval eromheen voor variatie
#   piek    - wedstrijdtempo krijgt het meeste gewicht, interval houdt scherp
#   taper   - kort en scherp, geen vermoeidheid meer opbouwen
QUALITY_ROTATION = {
    "basis": ["strides", "hills", "strides", "hills"],
    # Voor deze loper ligt de beperking in vermoeidheidsbestendigheid, niet in
    # de top: hij liep de eerste 11 km van zijn race al op doeltempo en zakte
    # daarna weg. Drempel en wedstrijdtempo wegen daarom zwaarder dan VO2max-
    # intervallen, die hier het minst opleveren.
    "opbouw": ["threshold", "tempo", "hills", "threshold", "intervals", "tempo"],
    "piek": ["threshold", "tempo", "intervals", "tempo"],
    "taper": ["tempo", "tempo"],
}


def quality_kind(phase, slot_index):
    seq = QUALITY_ROTATION.get(phase) or ["threshold"]
    return seq[slot_index % len(seq)]



def _warm_cool(long_min, base_warm=12, base_cool=8):
    """In- en uitlopen meeschalen met de omvang van de week.

    Een vaste 12 + 8 minuten is in een basisweek met een duurloop van 26
    minuten onevenredig: de kwaliteitssessie wordt dan langer dan de duurloop.
    """
    if not long_min:
        return base_warm, base_cool
    w = int(max(6, min(base_warm, long_min * 0.28)))
    c = int(max(5, min(base_cool, long_min * 0.20)))
    return w, c


def _tempo(d, cfg, long_min, phase):
    """Aaneengesloten blok op wedstrijdtempo. Comfortabel hard, geen race."""
    lo, hi = cfg["steady_hr"]
    block = 20 if phase == "opbouw" else (30 if phase == "piek" else 15)
    if long_min:
        block = int(max(10, min(block, long_min * 0.45)))
    warm, cool = _warm_cool(long_min)
    return {
        "date": d.isoformat(), "kind": "tempo", "label": "Tempoloop",
        "minutes": warm + block + cool, "hr": [lo, hi],
        "builder": "create_run_workout",
        "args": {"run_seconds": block * 60, "warmup_min": warm, "cooldown_min": cool,
                 "hr_min": lo, "hr_max": hi},
        "detail": "%d min inlopen, %d min aaneengesloten op %d-%d bpm, %d min uitlopen"
                  % (warm, block, lo, hi, cool),
        "uploadable": True,
        "note": "Dit is je wedstrijdtempo. Je moet het aan het eind nog 10 minuten vol kunnen houden.",
    }


def _intervals(d, cfg, long_min, progress, taper=False):
    """Korte blokken boven de drempel. Houdt de top scherp en traint VO2max."""
    lo, hi = cfg["interval_hr"]
    rlo, rhi = cfg["easy_hr"]
    if taper:
        # Scherp houden zonder vermoeidheid: weinig herhalingen, kort.
        reps, rep_s, rec_s = 4, 120, 120
    elif progress < 0.55:
        reps, rep_s, rec_s = 5, 180, 120
    else:
        reps, rep_s, rec_s = 6, 180, 120
    if long_min:
        while reps > 3 and reps * rep_s > long_min * 60 * 0.35:
            reps -= 1
    warm, cool = _warm_cool(long_min)
    return {
        "date": d.isoformat(), "kind": "intervals", "label": "Intervaltraining",
        "minutes": warm + cool + round(reps * (rep_s + rec_s) / 60), "hr": [lo, hi],
        "builder": "create_run_interval_workout",
        "args": {"repeats": reps, "rep_seconds": rep_s, "recovery_seconds": rec_s,
                 "warmup_min": warm, "cooldown_min": cool,
                 "hr_min": lo, "hr_max": hi,
                 "recovery_hr_min": rlo, "recovery_hr_max": rhi},
        "detail": "%d min inlopen, %dx %d min stevig op %d-%d bpm met %d min dribbelen, %d min uitlopen"
                  % (warm, reps, rep_s // 60, lo, hi, rec_s // 60, cool),
        "uploadable": True,
        "note": "Hard, maar gelijkmatig. De laatste herhaling net zo snel als de eerste.",
    }


def _hills(d, cfg, long_min, phase):
    """Heuvelherhalingen: kracht in de benen zonder de snelheid van vlak werk.

    Scheelt impact ten opzichte van intervallen op vlak terrein, en dat telt
    bij een terugkerende loper. Een brug of viaduct voldoet prima.
    """
    lo, hi = cfg["interval_hr"]
    rlo, rhi = cfg["easy_hr"]
    reps = 6 if phase == "basis" else 9
    rep_s, rec_s = 60, 120
    if long_min:
        while reps > 4 and reps * rep_s > long_min * 60 * 0.3:
            reps -= 1
    warm, cool = _warm_cool(long_min)
    return {
        "date": d.isoformat(), "kind": "hills", "label": "Heuvelherhalingen",
        "minutes": warm + cool + round(reps * (rep_s + rec_s) / 60), "hr": [lo, hi],
        "builder": "create_run_interval_workout",
        "args": {"repeats": reps, "rep_seconds": rep_s, "recovery_seconds": rec_s,
                 "warmup_min": warm, "cooldown_min": cool,
                 "hr_min": lo, "hr_max": hi,
                 "recovery_hr_min": rlo, "recovery_hr_max": rhi},
        "detail": "%d min inlopen, %dx 1 min stevig omhoog met rustig terugdribbelen, %d min uitlopen"
                  % (warm, reps, cool),
        "uploadable": True,
        "note": "Een brug of viaduct volstaat. Korte pas, rechtop, niet voorover hangen.",
    }


def _quality(d, cfg, phase, progress, taper=False, long_min=None):
    """Drempelsessie. Wordt langer en minder versnipperd naarmate het blok vordert."""
    lo, hi = cfg["threshold_hr"]
    rlo, rhi = cfg["easy_hr"]
    if progress < 0.45:
        reps, rep_s, rec_s = 5, 300, 120
    elif progress < 0.7:
        reps, rep_s, rec_s = 4, 480, 150
    else:
        reps, rep_s, rec_s = 3, 720, 180
    if taper:
        # Scherp blijven, maar de vermoeidheid eruit: minder herhalingen.
        reps = max(2, reps - 1)
        rep_s = min(rep_s, 360)

    # De arbeid in een drempelsessie mag niet groter zijn dan ongeveer de helft
    # van de duurloop van die week. Zonder die koppeling blijft een zwaar blok
    # staan terwijl de rest van de week wordt afgeremd, en schiet de ACWR er
    # alsnog overheen - precies wat de bewaking moet voorkomen.
    if long_min:
        max_work = max(360.0, long_min * 60.0 * 0.5)
        while reps > 2 and reps * rep_s > max_work:
            reps -= 1
        if reps * rep_s > max_work:
            rep_s = max(240, int(max_work / reps))
    warm, cool = _warm_cool(long_min)
    return {
        "date": d.isoformat(), "kind": "threshold", "label": "Drempelblok",
        "minutes": warm + cool + round(reps * (rep_s + rec_s) / 60), "hr": [lo, hi],
        "builder": "create_run_interval_workout",
        "args": {"repeats": reps, "rep_seconds": rep_s, "recovery_seconds": rec_s,
                 "warmup_min": warm, "cooldown_min": cool,
                 "hr_min": lo, "hr_max": hi,
                 "recovery_hr_min": rlo, "recovery_hr_max": rhi},
        "detail": ("%d min inlopen, %dx %d min op drempel %d-%d bpm met %d min dribbelen, "
                   "%d min uitlopen" % (warm, reps, rep_s // 60, lo, hi, rec_s // 60, cool)),
        "uploadable": True,
        "note": "Comfortabel zwaar: je kunt nog korte zinnen zeggen, geen gesprek.",
    }


def _race_session(d, cfg, goal_min):
    return {
        "date": d.isoformat(), "kind": "race", "label": cfg["goal_name"],
        "minutes": round(goal_min), "hr": None, "builder": None, "args": {},
        "detail": "%s km op %.2f min/km. Eerste 5 km bewust iets langzamer."
                  % (cfg["distance_km"], goal_min / cfg["distance_km"]),
        "uploadable": False,
    }


# Krachttraining voor hardlopers.
#
# Doel is niet spiermassa en ook niet conditie - dat laatste komt van het lopen.
# Het gaat om twee dingen: weefsel dat de belasting aankan, en loopeconomie.
# Zwaar krachtwerk verlaagt het zuurstofverbruik op hetzelfde tempo; dat is de
# enige route waarlangs de sportschool je tijd op 14 maart verbetert.
#
# De oefeningen mikken op de plekken waar een terugkerende loper stukgaat:
# kuit en achillespees (veruit nummer een), hamstring, bilspieren voor de
# zijwaartse stabiliteit van de knie, en de romp tegen wegzakken laat in de race.
#
# Opbouw in drie blokken, net als het looppplan:
#   basis   - bewegingen leren, pezen laten wennen, veel herhalingen licht
#   opbouw  - zwaar en laag in herhalingen; hier zit de winst
#   piek    - onderhouden met minder volume, benen fris houden voor het lopen
#   taper   - alleen nog prikkelen

STRENGTH_BLOCKS = {
    "basis": {
        "sets": 3, "rest": 90, "label": "Kracht - wennen",
        "focus": ("Techniek eerst, daarna elke week gewicht erbij. Krachttraining "
                  "halveert het risico op overbelastingsblessures; dat effect komt "
                  "van zwaar werk, niet van lichte herhalingen."),
        "exercises": [
            ("Kuitheffing staand, per been", None, "15", "Achillespees. Langzaam omhoog, 3 sec zakken."),
            ("Kuitheffing gebogen knie, per been", None, "15", "Raakt de soleus, de spier die bij lopen het hardst werkt."),
            ("Split squat, per been", "LUNGE", "10", "Vasthouden aan iets als je wiebelt. Knie over de tenen mag."),
            ("Glute bridge, per been", None, "12", "Knijp de bil aan, duw niet met de onderrug."),
            ("Side plank, per kant", "PLANK", "30 sec", "Tegen het wegzakken van de heup bij elke landing."),
            ("Dead bug", None, "10", "Onderrug blijft plat op de grond."),
        ],
    },
    "opbouw": {
        "sets": 3, "rest": 120, "label": "Kracht - zwaar",
        "focus": "Zwaar en laag in herhalingen. Hier verbetert je loopeconomie.",
        "exercises": [
            ("Back squat of goblet squat", "SQUAT", "6", "Zwaar. Laatste herhaling moet echt moeite kosten."),
            ("Romanian deadlift", "DEADLIFT", "8", "Hamstrings en bilspieren. Rug recht, heupen naar achteren."),
            ("Bulgarian split squat, per been", "LUNGE", "8", "Met gewicht. De oefening die het meest op lopen lijkt."),
            ("Kuitheffing met gewicht, per been", None, "10", "3 sec zakken. Niet overslaan, dit is de belangrijkste."),
            ("Nordic hamstring curl", None, "5", "Met hulp of weerstandsband. Zak zo langzaam mogelijk."),
            ("Pallof press, per kant", None, "10", "Tegen rotatie. Romp stil houden terwijl de armen duwen."),
        ],
    },
    "piek": {
        "sets": 2, "rest": 120, "label": "Kracht - onderhoud",
        "focus": "Zwaar blijven, maar minder volume. De benen moeten fris zijn voor de duurloop.",
        "exercises": [
            ("Back squat of goblet squat", "SQUAT", "5", "Zwaar, maar stop met twee herhalingen in de tank."),
            ("Romanian deadlift", "DEADLIFT", "6", "Zelfde gewicht als in de opbouw."),
            ("Kuitheffing met gewicht, per been", None, "10", "Blijft staan tot het eind."),
            ("Side plank, per kant", "PLANK", "40 sec", ""),
            ("Pallof press, per kant", None, "10", ""),
        ],
    },
    "taper": {
        "sets": 1, "rest": 90, "label": "Kracht - licht",
        "focus": "Alleen prikkelen, geen vermoeidheid opbouwen. Laatste sessie uiterlijk dinsdag voor de race.",
        "exercises": [
            ("Goblet squat", "SQUAT", "8", "Half zo zwaar als normaal."),
            ("Kuitheffing, per been", None, "12", "Zonder extra gewicht."),
            ("Glute bridge, per been", None, "12", ""),
            ("Side plank, per kant", "PLANK", "30 sec", ""),
        ],
    },
}


def _strength(d, phase, deload):
    block = STRENGTH_BLOCKS.get(phase if phase in STRENGTH_BLOCKS else "opbouw")
    sets = max(1, block["sets"] - 1) if deload else block["sets"]
    ex, lines = [], []
    for name, cat, reps, hint in block["exercises"]:
        numeric = "".join(ch for ch in reps if ch.isdigit())
        item = {"name": name, "sets": sets,
                "reps": int(numeric or 10), "rest_seconds": block["rest"]}
        if cat:
            item["category"] = cat
        ex.append(item)
        lines.append({"name": name, "sets": sets, "reps": reps, "hint": hint})
    return {
        "date": d.isoformat(), "kind": "strength",
        "label": block["label"] + (" (licht)" if deload else ""),
        "minutes": 12 + sets * len(ex) * 2, "hr": None,
        "builder": "create_strength_workout",
        "args": {"exercises": ex},
        "detail": "%d sets - %s" % (sets, ", ".join(e["name"] for e in lines)),
        "exercises": lines,
        "focus": block["focus"],
        "uploadable": True,
        "note": "Krachttraining verbetert je loopeconomie en je weerstand tegen blessures, niet je VO2max.",
    }
