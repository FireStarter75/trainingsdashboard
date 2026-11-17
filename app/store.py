"""Opslag: doelconfiguratie, cache van Garmin-data en log van ge-uploade workouts."""
import json
import os
import sqlite3
import threading
import time

DATA_DIR = os.environ.get("DASH_DATA_DIR", "/data")
DB_PATH = os.path.join(DATA_DIR, "dashboard.db")
GOAL_PATH = os.path.join(DATA_DIR, "goal.json")

_lock = threading.Lock()


def _conn():
    os.makedirs(DATA_DIR, exist_ok=True)
    c = sqlite3.connect(DB_PATH, timeout=30)
    c.row_factory = sqlite3.Row
    return c


def init():
    with _lock, _conn() as c:
        c.executescript("""
            CREATE TABLE IF NOT EXISTS cache (
                key        TEXT PRIMARY KEY,
                fetched_at REAL NOT NULL,
                payload    TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS adaptations (
                week_start   TEXT PRIMARY KEY,
                decided_at   REAL NOT NULL,
                scale        REAL NOT NULL,
                drop_quality INTEGER NOT NULL DEFAULT 0,
                severity     TEXT,
                reasons      TEXT,
                signals      TEXT
            );
            CREATE TABLE IF NOT EXISTS uploads (
                session_date TEXT NOT NULL,
                kind         TEXT NOT NULL,
                workout_id   INTEGER,
                workout_name TEXT,
                scheduled    INTEGER NOT NULL DEFAULT 0,
                created_at   REAL NOT NULL,
                PRIMARY KEY (session_date, kind)
            );
            -- Gesprek met de coach. Bewaard omdat de chat anders bij elke
            -- paginavernieuwing leeg is, en omdat de coach de vorige beurten
            -- nodig heeft om een vervolgvraag te begrijpen.
            CREATE TABLE IF NOT EXISTS chat (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                ts      REAL NOT NULL,
                role    TEXT NOT NULL,          -- 'user' of 'coach'
                text    TEXT NOT NULL,
                meta    TEXT                    -- json: kosten, acties, model
            );
            -- Eigen logboek: wat Garmin niet weet. Gevoel, spierpijn, context.
            CREATE TABLE IF NOT EXISTS trainlog (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                day         TEXT NOT NULL,
                km          REAL,
                minutes     REAL,
                feel        INTEGER,            -- 1 slecht .. 5 uitstekend
                soreness    INTEGER,            -- 0 geen .. 5 fors
                rpe         INTEGER,            -- 1 .. 10 ervaren zwaarte
                note        TEXT,
                source      TEXT NOT NULL DEFAULT 'chat',
                created_at  REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS trainlog_day ON trainlog(day);
            -- Voorstellen van de coach. Hij voert zelf niets uit: een voorstel
            -- blijft 'pending' tot de gebruiker erop klikt. Zo staat elke
            -- wijziging onder een menselijk besluit.
            CREATE TABLE IF NOT EXISTS coach_actions (
                id         TEXT PRIMARY KEY,
                created_at REAL NOT NULL,
                kind       TEXT NOT NULL,
                payload    TEXT NOT NULL,
                status     TEXT NOT NULL DEFAULT 'pending',
                result     TEXT,
                decided_at REAL
            );
        """)


def cache_get(key, max_age_s=None):
    with _lock, _conn() as c:
        row = c.execute("SELECT fetched_at, payload FROM cache WHERE key = ?", (key,)).fetchone()
    if not row:
        return None, None
    if max_age_s is not None and (time.time() - row["fetched_at"]) > max_age_s:
        return None, row["fetched_at"]
    try:
        return json.loads(row["payload"]), row["fetched_at"]
    except json.JSONDecodeError:
        return None, row["fetched_at"]


def cache_put(key, payload):
    with _lock, _conn() as c:
        c.execute(
            "INSERT INTO cache (key, fetched_at, payload) VALUES (?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET fetched_at=excluded.fetched_at, payload=excluded.payload",
            (key, time.time(), json.dumps(payload)),
        )


def cache_ages():
    with _lock, _conn() as c:
        rows = c.execute("SELECT key, fetched_at FROM cache").fetchall()
    return {r["key"]: r["fetched_at"] for r in rows}


def record_upload(session_date, kind, workout_id, workout_name, scheduled):
    with _lock, _conn() as c:
        c.execute(
            "INSERT INTO uploads (session_date, kind, workout_id, workout_name, scheduled, created_at) "
            "VALUES (?,?,?,?,?,?) ON CONFLICT(session_date, kind) DO UPDATE SET "
            "workout_id=excluded.workout_id, workout_name=excluded.workout_name, "
            "scheduled=excluded.scheduled, created_at=excluded.created_at",
            (session_date, kind, workout_id, workout_name, 1 if scheduled else 0, time.time()),
        )


def uploads():
    with _lock, _conn() as c:
        rows = c.execute("SELECT * FROM uploads").fetchall()
    return {f"{r['session_date']}|{r['kind']}": dict(r) for r in rows}


def load_goal():
    if not os.path.exists(GOAL_PATH):
        return {}
    try:
        with open(GOAL_PATH) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def save_goal(cfg):
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = GOAL_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(cfg, f, indent=2)
    os.replace(tmp, GOAL_PATH)


def save_adaptation(week_start, decision, signals):
    with _lock, _conn() as c:
        c.execute(
            "INSERT INTO adaptations (week_start, decided_at, scale, drop_quality, "
            "severity, reasons, signals) VALUES (?,?,?,?,?,?,?) "
            "ON CONFLICT(week_start) DO UPDATE SET decided_at=excluded.decided_at, "
            "scale=excluded.scale, drop_quality=excluded.drop_quality, "
            "severity=excluded.severity, reasons=excluded.reasons, signals=excluded.signals",
            (week_start, time.time(), float(decision["scale"]),
             1 if decision["drop_quality"] else 0, decision.get("severity"),
             json.dumps(decision.get("reasons") or []), json.dumps(signals or {})),
        )


def adaptations():
    with _lock, _conn() as c:
        rows = c.execute("SELECT * FROM adaptations ORDER BY week_start").fetchall()
    out = {}
    for r in rows:
        d = dict(r)
        for k in ("reasons", "signals"):
            try:
                d[k] = json.loads(d[k] or "null")
            except (TypeError, json.JSONDecodeError):
                d[k] = None
        d["drop_quality"] = bool(d["drop_quality"])
        out[d["week_start"]] = d
    return out


def delete_adaptation(week_start):
    """Haalt een bijstelling weg, zodat het plan voor die week weer puur uit de
    opbouwcurve komt. Nodig omdat een coachvoorstel ook terug te draaien moet
    zijn zonder in de database te duiken."""
    with _lock, _conn() as c:
        cur = c.execute("DELETE FROM adaptations WHERE week_start = ?", (week_start,))
        return cur.rowcount


def last_coach_clear(week_start):
    """Tijdstip van de laatste toegepaste coach-terugdraai voor deze week.

    Een terugdraai haalt de bijstellingsrij weg, en daarmee ook elk spoor van
    het besluit. De automatische beoordeling moet zo'n bewuste terugdraai
    kunnen zien zonder dat er nog een rij is; daarvoor staat hij in
    coach_actions, met zijn goedkeuring als tijdstip.
    """
    with _lock, _conn() as c:
        row = c.execute(
            "SELECT MAX(decided_at) FROM coach_actions "
            "WHERE status = 'applied' AND kind = 'clear_week_adjustment' "
            "AND payload LIKE ?",
            ('%"week_start": "' + week_start + '"%',),
        ).fetchone()
        return row[0] if row and row[0] else None


# --------------------------------------------------------------------- chat

def chat_add(role, text, meta=None):
    with _lock, _conn() as c:
        cur = c.execute("INSERT INTO chat (ts, role, text, meta) VALUES (?,?,?,?)",
                        (time.time(), role, text, json.dumps(meta or {})))
        return cur.lastrowid


def chat_history(limit=40):
    """Oudste eerst, zodat het rechtstreeks in een gesprek te gieten is."""
    with _lock, _conn() as c:
        rows = c.execute("SELECT * FROM chat ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    out = []
    for r in reversed(rows):
        d = dict(r)
        try:
            d["meta"] = json.loads(d["meta"] or "{}")
        except json.JSONDecodeError:
            d["meta"] = {}
        out.append(d)
    return out


def chat_clear():
    with _lock, _conn() as c:
        c.execute("DELETE FROM chat")


def chat_count_since(ts):
    with _lock, _conn() as c:
        row = c.execute("SELECT COUNT(*) n FROM chat WHERE role='user' AND ts >= ?",
                        (ts,)).fetchone()
    return int(row["n"] or 0)


# ------------------------------------------------------------------ logboek

def log_add(entry):
    with _lock, _conn() as c:
        cur = c.execute(
            "INSERT INTO trainlog (day, km, minutes, feel, soreness, rpe, note, source, "
            "created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (entry["day"], entry.get("km"), entry.get("minutes"), entry.get("feel"),
             entry.get("soreness"), entry.get("rpe"), entry.get("note"),
             entry.get("source") or "chat", time.time()))
        return cur.lastrowid


def log_recent(limit=25):
    with _lock, _conn() as c:
        rows = c.execute("SELECT * FROM trainlog ORDER BY day DESC, id DESC LIMIT ?",
                         (limit,)).fetchall()
    return [dict(r) for r in rows]


def log_delete(entry_id):
    with _lock, _conn() as c:
        cur = c.execute("DELETE FROM trainlog WHERE id = ?", (int(entry_id),))
        return cur.rowcount


# -------------------------------------------------------- voorstellen coach

def action_put(action_id, kind, payload):
    with _lock, _conn() as c:
        c.execute("INSERT OR REPLACE INTO coach_actions (id, created_at, kind, payload, "
                  "status) VALUES (?,?,?,?, 'pending')",
                  (action_id, time.time(), kind, json.dumps(payload)))


def action_get(action_id):
    with _lock, _conn() as c:
        row = c.execute("SELECT * FROM coach_actions WHERE id = ?", (action_id,)).fetchone()
    if not row:
        return None
    d = dict(row)
    try:
        d["payload"] = json.loads(d["payload"])
    except json.JSONDecodeError:
        d["payload"] = {}
    return d


def action_mark(action_id, status, result=None):
    with _lock, _conn() as c:
        c.execute("UPDATE coach_actions SET status = ?, result = ?, decided_at = ? "
                  "WHERE id = ?", (status, json.dumps(result) if result is not None else None,
                                   time.time(), action_id))


def actions_status(ids):
    if not ids:
        return {}
    q = ",".join("?" for _ in ids)
    with _lock, _conn() as c:
        rows = c.execute("SELECT id, status FROM coach_actions WHERE id IN (%s)" % q,
                         list(ids)).fetchall()
    return {r["id"]: r["status"] for r in rows}
