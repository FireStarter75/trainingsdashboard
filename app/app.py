"""Garmin trainingsdashboard.

Leest data uit de twee garmin-mcp servers, rekent voortgang tegen het plan af,
en kan trainingen als workout naar Garmin Connect schrijven en inplannen.
"""
import os
import re
import time
import traceback
from datetime import date, datetime, timedelta

from flask import Flask, jsonify, redirect, render_template, request, session, url_for

import adapt
import auth
import coach
import mcp_client
import plan as planner
import scheduler
import store

app = Flask(__name__)
app.secret_key = os.environ.get("DASH_SECRET") or os.urandom(32)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("DASH_COOKIE_SECURE", "0") == "1",
    PERMANENT_SESSION_LIFETIME=timedelta(days=int(os.environ.get("DASH_SESSION_DAYS", "60"))),
)
store.init()

TAX, END = mcp_client.from_env()
GPX_DIR = os.environ.get("GPX_DIR", "/gpx")
CACHE_TTL = int(os.environ.get("CACHE_TTL", "900"))   # 15 min


# ---------------------------------------------------------------- hulpfuncties

def safe(label, fn, default=None):
    """Roept fn aan en slikt fouten, zodat een kapotte bron de pagina niet sloopt."""
    try:
        return {"ok": True, "value": fn()}
    except Exception as e:                                    # noqa: BLE001
        app.logger.warning("%s faalde: %s", label, e)
        return {"ok": False, "error": str(e)[:300], "value": default}


def cached(key, fn, ttl=None):
    ttl = CACHE_TTL if ttl is None else ttl
    hit, _ = store.cache_get(key, ttl)
    if hit is not None:
        return hit
    val = fn()
    if val is not None:
        store.cache_put(key, val)
    return val


def goal_config():
    cfg = dict(planner.DEFAULT_CONFIG)
    cfg.update(store.load_goal())
    return cfg


def iso(d):
    return d.isoformat()


def asset_version():
    """Stempel uit de mtimes van de statics, zodat een browser nooit een oude
    app.js of style.css uit zijn cache blijft gebruiken na een update."""
    newest = 0.0
    for rel in ("static/app.js", "static/style.css",
                "static/coach.js", "static/coach.css"):
        try:
            newest = max(newest, os.path.getmtime(os.path.join(app.root_path, rel)))
        except OSError:
            pass
    return str(int(newest))


# ----------------------------------------------------------------- data ophalen

def fetch_runs(days=1460):
    end_d = date.today()
    start_d = end_d - timedelta(days=days)
    out, page = [], 0
    while True:
        res = TAX.call("get_activities_by_date", {
            "start_date": iso(start_d), "end_date": iso(end_d),
            "activity_type": "running", "page": page,
        }) or {}
        out.extend(res.get("activities") or [])
        if not res.get("has_more") or page > 20:
            break
        page += 1
    return out


def fetch_baseline(runs, goal_distance_km=21.1):
    """Wat kan hij nu aan, en wat heeft hij ooit gelopen.

    Het onderscheid is belangrijk: de huidige vorm bepaalt waar het plan start,
    maar een eerdere wedstrijd op de doelafstand is verreweg de beste voorspeller
    van wat haalbaar is. Die wordt apart bijgehouden als `best_race`.
    """
    if not runs:
        return {"longest_km": 0, "pace_min_per_km": None, "runs_90d": 0, "km_90d": 0,
                "total_runs": 0, "best_race": None, "recent_longest_km": 0}

    cutoff90 = (date.today() - timedelta(days=90)).isoformat()
    recent = [r for r in runs if (r.get("start_time") or "")[:10] >= cutoff90]

    def km(r):
        return (r.get("distance_meters") or 0) / 1000.0

    def mins(r):
        return (r.get("duration_seconds") or 0) / 60.0

    pool = recent or runs
    longest = max(pool, key=km)
    lk, lm = km(longest), mins(longest)

    out = {
        "longest_km": round(lk, 2),
        "longest_min": round(lm, 1),
        "pace_min_per_km": round(lm / lk, 3) if lk > 0.3 else None,
        "runs_90d": len(recent),
        "km_90d": round(sum(km(r) for r in recent), 1),
        "total_runs": len(runs),
        "first_run": min((r.get("start_time") or "")[:10] for r in runs if r.get("start_time")),
        "all_time_longest_km": round(max(km(r) for r in runs), 2),
    }

    # Werkelijke loopbelasting van de laatste vier volle weken, als startpunt
    # voor de ACWR-bewaking in het plan. Zonder dit rekent het plan af tegen
    # nul en lijkt elke eerste week een enorme sprong.
    today = date.today()
    this_monday = today - timedelta(days=today.weekday())
    recent_load = []
    for back in range(3, -1, -1):
        wk_start = this_monday - timedelta(days=7 * back)
        wk_end = wk_start + timedelta(days=6)
        total = sum(mins(r) for r in runs
                    if wk_start.isoformat() <= (r.get("start_time") or "")[:10] <= wk_end.isoformat())
        recent_load.append(round(total, 1))
    out["recent_weekly_load"] = recent_load

    # Beste eerdere prestatie op de doelafstand. Eerst kijken naar inspanningen
    # van minstens 80% van de doelafstand: een snellere maar veel kortere run
    # extrapoleert te optimistisch. Pas als die er niet zijn, de drempel zakken.
    goal_km = float(goal_distance_km or 21.1)
    longs = [r for r in runs if km(r) >= 0.8 * goal_km and mins(r) > 0]
    if not longs:
        longs = [r for r in runs if km(r) >= 0.6 * goal_km and mins(r) > 0]
    if longs:
        best = min(longs, key=lambda r: mins(r) / km(r))
        out["best_race"] = {
            "date": (best.get("start_time") or "")[:10],
            "name": best.get("name"),
            "km": round(km(best), 2),
            "minutes": round(mins(best), 1),
            "pace_min_per_km": round(mins(best) / km(best), 3),
            "avg_hr": best.get("avg_hr_bpm"),
        }
    else:
        out["best_race"] = None
    return out


def weekly_actuals(runs):
    """Werkelijk gelopen minuten en km per ISO-week."""
    buckets = {}
    for r in runs:
        ts = (r.get("start_time") or "")[:10]
        if not ts:
            continue
        d = datetime.strptime(ts, "%Y-%m-%d").date()
        monday = (d - timedelta(days=d.weekday())).isoformat()
        b = buckets.setdefault(monday, {"minutes": 0.0, "km": 0.0, "sessions": 0})
        b["minutes"] += (r.get("duration_seconds") or 0) / 60.0
        b["km"] += (r.get("distance_meters") or 0) / 1000.0
        b["sessions"] += 1
    for b in buckets.values():
        b["minutes"] = round(b["minutes"])
        b["km"] = round(b["km"], 1)
    return buckets


def build_state(force=False):
    ttl = 0 if force else CACHE_TTL
    cfg = goal_config()

    runs = cached("runs", fetch_runs, ttl) or []
    baseline = fetch_baseline(runs, cfg.get("distance_km", 21.1))
    if not cfg.get("start_long_min") or cfg.get("auto_start_long", True):
        if baseline.get("longest_min"):
            cfg["start_long_min"] = max(25, round(baseline["longest_min"] * 1.15))

    the_plan = planner.build_plan(cfg, baseline, store.adaptations())

    metrics = {
        "race_predictions": safe("race_predictions", lambda: cached(
            "race_pred", lambda: TAX.call("get_race_predictions", {}), ttl)),
        "training_status": safe("training_status", lambda: cached(
            "train_status", lambda: TAX.call("get_training_status", {"date": iso(date.today())}), ttl)),
        "load": safe("load", lambda: cached("load", lambda: END.call("get_load", {
            "from": iso(date.today() - timedelta(days=42)), "to": iso(date.today()),
            "include_series": True}), ttl)),
        "readiness": safe("readiness", lambda: cached(
            "readiness", lambda: END.call("get_readiness", {}), ttl)),
        "health": safe("health", lambda: cached("health", lambda: END.call("query_health", {
            "metrics": ["resting_hr", "hrv", "sleep", "body_battery"],
            "from": iso(date.today() - timedelta(days=60)), "to": iso(date.today())}), ttl)),
        "thresholds": safe("thresholds", lambda: cached(
            "thresholds", lambda: END.call("get_thresholds", {}), ttl)),
        "scheduled": safe("scheduled", lambda: cached("scheduled", lambda: TAX.call(
            "get_scheduled_workouts", {"start_date": iso(date.today()),
                                       "end_date": iso(date.today() + timedelta(days=28))}), ttl)),
    }

    return {
        "today": iso(date.today()),
        "goal": cfg,
        "days_to_race": (planner._parse(cfg["race_date"]) - date.today()).days,
        "baseline": baseline,
        "plan": the_plan,
        "actuals": weekly_actuals(runs),
        "runs": runs[:40],
        "metrics": metrics,
        "uploads": store.uploads(),
        "last_adaptation_week": _last_adaptation_week(),
        "scheduler": (store.cache_get("scheduler_heartbeat")[0] or None),
        "cache_ages": store.cache_ages(),
    }


# ---------------------------------------------------------------------- routes

@app.route("/login", methods=["GET", "POST"])
def login():
    if not auth.enabled():
        return redirect(url_for("index"))
    nxt = request.values.get("next") or "/"
    if not nxt.startswith("/"):
        nxt = "/"
    ip = auth.client_ip()
    wait = auth.locked_for(ip)
    error = None
    if request.method == "POST":
        if wait:
            error = "Te veel pogingen. Wacht %d minuten." % max(1, wait // 60)
        elif auth.check(request.form.get("password")):
            auth.clear(ip)
            session.permanent = True
            session["auth"] = True
            return redirect(nxt)
        else:
            n = auth.note_failure(ip)
            left = max(0, auth.MAX_TRIES - n)
            error = "Onjuist wachtwoord." + (" Nog %d pogingen." % left if left else " Geblokkeerd.")
            app.logger.warning("mislukte login van %s (%d)", ip, n)
            wait = auth.locked_for(ip)
    return render_template("login.html", error=error, next=nxt, v=asset_version(),
                           locked=bool(wait), goal=goal_config()["goal_name"]), (401 if error else 200)


@app.route("/logout", methods=["POST", "GET"])
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@auth.require_auth
def index():
    return render_template("index.html", v=asset_version())


@app.route("/api/state")
@auth.require_auth
def api_state():
    force = request.args.get("refresh") == "1"
    try:
        return jsonify(build_state(force))
    except Exception as e:                                    # noqa: BLE001
        app.logger.error("state faalde: %s", traceback.format_exc())
        return jsonify({"error": str(e)}), 500


@app.route("/api/goal", methods=["POST"])
@auth.require_auth
def api_goal():
    body = request.get_json(silent=True) or {}
    cfg = dict(store.load_goal())
    for k in ("goal_name", "race_date", "distance_km", "days_per_week",
              "priority", "target_time_min", "start_long_min", "auto_start_long",
              "acwr_cap", "strength_day", "ramp_in_weeks", "start_date"):
        if k in body:
            cfg[k] = body[k]
    if "race_date" in cfg and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(cfg["race_date"])):
        return jsonify({"error": "race_date moet YYYY-MM-DD zijn"}), 400
    store.save_goal(cfg)
    return jsonify({"ok": True, "goal": goal_config()})


@app.route("/api/health")
@auth.require_auth
def api_health():
    out = {}
    for name, srv in (("taxuspt", TAX), ("endurance", END)):
        try:
            out[name] = {"ok": True, "tools": len(srv.list_tools())}
        except Exception as e:                                # noqa: BLE001
            out[name] = {"ok": False, "error": str(e)[:200]}
    return jsonify(out)


@app.route("/api/routes")
@auth.require_auth
def api_routes():
    """Polylines van recente runs, uit GPX in de gedeelde map."""
    want = int(request.args.get("limit", "6"))
    runs = cached("runs", fetch_runs) or []
    out = []
    for r in runs[:want]:
        aid = r.get("id")
        if not aid:
            continue
        path = os.path.join(GPX_DIR, "%s.gpx" % aid)
        if not os.path.exists(path):
            try:
                TAX.call("download_activity_file",
                         {"activity_id": aid, "format": "gpx", "output_dir": GPX_DIR})
            except Exception as e:                            # noqa: BLE001
                app.logger.warning("gpx %s faalde: %s", aid, e)
                continue
        pts = parse_gpx(path)
        if pts:
            out.append({
                "id": aid, "name": r.get("name"), "date": (r.get("start_time") or "")[:10],
                "km": round((r.get("distance_meters") or 0) / 1000.0, 2),
                "minutes": round((r.get("duration_seconds") or 0) / 60.0),
                "avg_hr": r.get("avg_hr_bpm"), "points": pts,
            })
    return jsonify(out)


GPX_RE = re.compile(r'<trkpt[^>]*lat="([-\d.]+)"[^>]*lon="([-\d.]+)"')


def parse_gpx(path, max_points=400):
    try:
        with open(path, "r", errors="ignore") as f:
            raw = f.read()
    except OSError:
        return []
    pts = [(round(float(a), 5), round(float(b), 5)) for a, b in GPX_RE.findall(raw)]
    if not pts:
        return []
    step = max(1, len(pts) // max_points)
    thinned = pts[::step]
    if thinned[-1] != pts[-1]:
        thinned.append(pts[-1])
    return thinned


def do_upload(body):
    """Maakt workouts aan in Garmin Connect en zet ze op de agenda.

    Body: {"sessions": [{date, kind}, ...]} of {"week": <index>}
    Alleen sessies uit het huidige plan worden geaccepteerd.

    Staat los van de route omdat de coach dezelfde weg gebruikt: één
    implementatie, dus ook één plek waar de controle op het plan gebeurt.
    """
    state = build_state(False)
    the_plan = state["plan"]

    index = {}
    for wk in the_plan["weeks"]:
        for s in wk["sessions"]:
            index["%s|%s" % (s["date"], s["kind"])] = (wk, s)

    wanted = []
    if body.get("week"):
        for wk in the_plan["weeks"]:
            if wk["index"] == int(body["week"]):
                wanted = [("%s|%s" % (s["date"], s["kind"])) for s in wk["sessions"] if s["uploadable"]]
    else:
        for item in body.get("sessions") or []:
            wanted.append("%s|%s" % (item.get("date"), item.get("kind")))

    if not wanted:
        return {"error": "geen sessies opgegeven", "uploaded": 0, "total": 0, "results": []}

    results = []
    for key in wanted:
        entry = index.get(key)
        if not entry:
            results.append({"key": key, "ok": False, "error": "sessie staat niet in het plan"})
            continue
        wk, sess = entry
        if not sess.get("uploadable"):
            results.append({"key": key, "ok": False, "error": "niet uploadbaar"})
            continue
        name = "W%02d %s %s" % (wk["index"], sess["label"], sess["date"][5:])
        try:
            args = dict(sess["args"])
            args["name"] = name[:250]
            created = TAX.call(sess["builder"], args) or {}
            wid = created.get("workout_id") or created.get("id")
            if not wid:
                raise mcp_client.MCPError("geen workout_id terug: %s" % str(created)[:200])
            TAX.call("schedule_workout", {"workout_id": int(wid),
                                          "calendar_date": sess["date"]})
            store.record_upload(sess["date"], sess["kind"], int(wid), name, True)
            results.append({"key": key, "ok": True, "workout_id": wid, "name": name})
        except Exception as e:                                # noqa: BLE001
            app.logger.warning("upload %s faalde: %s", key, e)
            results.append({"key": key, "ok": False, "error": str(e)[:300]})
        time.sleep(0.4)       # Garmin niet overvragen

    store.cache_put("scheduled_dirty", time.time())
    ok = sum(1 for r in results if r["ok"])
    return {"uploaded": ok, "total": len(results), "results": results}


@app.route("/api/upload", methods=["POST"])
@auth.require_auth
def api_upload():
    out = do_upload(request.get_json(silent=True) or {})
    return jsonify(out), (400 if out.get("error") else 200)



# ------------------------------------------------------- wekelijkse aanpassing

def run_adaptation(reason="handmatig"):
    """Weegt de verse Garmin-data en stelt de eerstvolgende week bij."""
    state = build_state(force=True)
    the_plan = state["plan"]
    upcoming = adapt.next_week(the_plan)
    if not upcoming:
        return {"ok": False, "error": "geen komende week meer in het plan"}

    today = date.today().isoformat()
    recent = [w for w in the_plan["weeks"] if w["end"] < today][-4:]

    load_data = (state["metrics"]["load"].get("value") or {}).get("data") or {}
    rd = (state["metrics"]["readiness"].get("value") or {}).get("data") or {}
    rows = ((state["metrics"]["health"].get("value") or {}).get("data") or {}).get("rows") or []

    signals = adapt.gather_signals(load_data, rd, rows, state["actuals"], upcoming, recent)
    decision = adapt.decide(signals)
    signals["reason"] = reason

    # Heeft de coach deze week al verlicht op iets wat niet in de data staat -
    # spierpijn, een drukke week, een beginnende blessure - dan mag deze
    # beoordeling dat niet ongedaan maken. Zelfde regel als binnen adapt.decide:
    # het zwaarste signaal bepaalt, dus de laagste factor wint.
    prev = store.adaptations().get(upcoming["start"])
    if prev and (prev.get("signals") or {}).get("via") == "chat":
        if float(prev["scale"]) < float(decision["scale"]):
            decision["scale"] = float(prev["scale"])
            decision["drop_quality"] = decision["drop_quality"] or bool(prev["drop_quality"])
            decision["reasons"] = list(prev.get("reasons") or []) + list(decision["reasons"])
            decision["severity"] = ("fors lichter" if decision["scale"] <= 0.75 else
                                    "lichter" if decision["scale"] < 0.98 else
                                    "zwaarder" if decision["scale"] > 1.02 else "ongewijzigd")
            signals["kept_coach_adjustment"] = prev["scale"]

    # Een bewuste terugdraai door de coach (met jouw klik goedgekeurd) telt als
    # besluit: de automatische beoordeling zet die week niet terug op de curve.
    # Zolang de week nog niet begonnen is blijft die bescherming staan; zodra
    # hij begint, doen de signalen weer mee. Zonder dit werd een teruggedraaide
    # week bij de eerstvolgende beoordeling stilletjes opnieuw verlicht, omdat
    # er na een terugdraai geen rij (en dus geen herinnering) meer overbleef.
    cleared_at = store.last_coach_clear(upcoming["start"])
    prev_is_clear = bool(prev) and (prev.get("signals") or {}).get("via") == "coach_clear"
    clear_protected = False
    if cleared_at and str(upcoming["start"]) > today:
        if prev is None or prev_is_clear or cleared_at > float(prev.get("decided_at") or 0):
            clear_protected = True
    if clear_protected:
        decision = {
            "scale": 1.0, "drop_quality": False, "severity": "ongewijzigd",
            "reasons": ["Teruggedraaid door de coach op %s; de automatische beoordeling "
                        "zet dit niet terug zolang de week nog niet begonnen is."
                        % time.strftime("%d-%m", time.localtime(cleared_at))],
        }
        signals["coach_clear_respected"] = cleared_at

    store.save_adaptation(upcoming["start"], decision, signals)
    store.cache_put("last_adaptation_week",
                    (date.today() - timedelta(days=date.today().weekday())).isoformat())
    app.logger.info("aanpassing %s voor week %s: %s (x%.2f) - %s",
                    reason, upcoming["start"], decision["severity"],
                    decision["scale"], "; ".join(decision["reasons"]))
    return {"ok": True, "week": upcoming["start"], "decision": decision, "signals": signals}


def _last_adaptation_week():
    val, _ = store.cache_get("last_adaptation_week")
    return val


@app.route("/api/adapt", methods=["POST"])
@auth.require_auth
def api_adapt():
    try:
        return jsonify(run_adaptation("handmatig"))
    except Exception as e:                                    # noqa: BLE001
        app.logger.error("aanpassing faalde: %s", traceback.format_exc())
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/adaptations")
@auth.require_auth
def api_adaptations():
    hb, _ = store.cache_get("scheduler_heartbeat")
    return jsonify({"last_run_week": _last_adaptation_week(),
                    "scheduler": hb, "items": store.adaptations()})


# ------------------------------------------------------------------- coach
#
# De chatbot zit in een eigen blueprint en praat met Claude via een aparte
# container. Hij krijgt hier alleen leesrechten (de state) en één schrijfweg
# (do_upload) mee; al het andere dat hij kan voorstellen loopt via store.
coach.init(state_provider=build_state, upload_fn=do_upload)
app.register_blueprint(coach.bp)


def _start_scheduler():
    if os.environ.get("ADAPT_ENABLED", "1") != "1":
        return
    scheduler.start(lambda reason: run_adaptation(reason), _last_adaptation_week,
                    heartbeat=lambda info: store.cache_put("scheduler_heartbeat", info))


_start_scheduler()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=False)
