"""Wekelijkse achtergrondtaak die het plan bijstelt.

Draait in precies een gunicorn-worker. Dat wordt afgedwongen met een
bestandsvergrendeling: de worker die hem krijgt, draait de planner; de andere
doen niets. Zonder dat zou de taak twee keer draaien.
"""
import fcntl
import logging
import os
import threading
import time
from datetime import date, datetime

log = logging.getLogger("scheduler")

LOCK_PATH = os.path.join(os.environ.get("DASH_DATA_DIR", "/data"), "scheduler.lock")
CHECK_EVERY_S = 20 * 60
RUN_WEEKDAY = int(os.environ.get("ADAPT_WEEKDAY", "0"))   # 0 = maandag
RUN_AFTER_HOUR = int(os.environ.get("ADAPT_HOUR", "5"))

_started = False


def _acquire():
    """Pakt de vergrendeling, of geeft None als een andere worker hem al heeft."""
    try:
        fh = open(LOCK_PATH, "w")
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fh.write(str(os.getpid()))
        fh.flush()
        return fh
    except (OSError, IOError):
        return None


def start(run_callback, last_run_key, heartbeat=None):
    """Start de lus. `run_callback(reason)` doet het echte werk.

    `last_run_key()` geeft terug voor welke week al een besluit bestaat, zodat
    een herstart binnen dezelfde week niet opnieuw draait.
    """
    global _started
    if _started:
        return False
    fh = _acquire()
    if not fh:
        log.info("planner draait al in een andere worker")
        return False
    _started = True

    def beat(status):
        if heartbeat:
            try:
                heartbeat({"pid": os.getpid(), "at": time.time(), "status": status,
                           "weekday": RUN_WEEKDAY, "after_hour": RUN_AFTER_HOUR,
                           "interval_s": CHECK_EVERY_S})
            except Exception:                                 # noqa: BLE001
                log.exception("hartslag schrijven faalde")

    def loop():
        log.info("planner actief (pid %s)", os.getpid())
        beat("gestart")
        while True:
            try:
                now = datetime.now()
                monday = (now.date() - __import__("datetime").timedelta(days=now.weekday())).isoformat()
                due = (now.weekday() == RUN_WEEKDAY and now.hour >= RUN_AFTER_HOUR
                       and last_run_key() != monday)
                if due:
                    log.info("wekelijkse aanpassing voor week van %s", monday)
                    beat("bezig")
                    run_callback("wekelijks")
                    beat("klaar")
                else:
                    beat("wachtend")
            except Exception:                                  # noqa: BLE001
                log.exception("planner faalde; we proberen het later opnieuw")
            time.sleep(CHECK_EVERY_S)

    t = threading.Thread(target=loop, name="adapt-scheduler", daemon=True)
    t.start()
    return True
