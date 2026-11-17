"""Inlog voor het dashboard.

Een formulier met een wachtwoord en een langlevende sessiecookie, zodat je op je
telefoon ingelogd blijft. Pogingen worden per IP afgeknepen.

Achter Cloudflare is request.remote_addr het adres van Cloudflare, dus we kijken
naar CF-Connecting-IP als die er is.
"""
import hmac
import os
import time
from functools import wraps

from flask import redirect, request, session, url_for

PASSWORD = os.environ.get("DASH_PASSWORD", "")
MAX_TRIES = int(os.environ.get("DASH_MAX_TRIES", "8"))
LOCK_SECONDS = int(os.environ.get("DASH_LOCK_SECONDS", "900"))

_tries = {}


def client_ip():
    for h in ("CF-Connecting-IP", "X-Forwarded-For"):
        v = request.headers.get(h)
        if v:
            return v.split(",")[0].strip()
    return request.remote_addr or "?"


def _state(ip):
    n, until = _tries.get(ip, (0, 0.0))
    if until and until < time.time():
        n, until = 0, 0.0
        _tries.pop(ip, None)
    return n, until


def locked_for(ip):
    _, until = _state(ip)
    return max(0, int(until - time.time()))


def note_failure(ip):
    n, _ = _state(ip)
    n += 1
    until = time.time() + LOCK_SECONDS if n >= MAX_TRIES else 0.0
    _tries[ip] = (n, until)
    return n


def clear(ip):
    _tries.pop(ip, None)


def check(password):
    if not PASSWORD:
        return False
    return hmac.compare_digest(str(password or ""), PASSWORD)


def enabled():
    return bool(PASSWORD)


def require_auth(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        if not enabled() or session.get("auth") is True:
            return fn(*a, **kw)
        if request.path.startswith("/api/"):
            return {"error": "niet ingelogd"}, 401
        return redirect(url_for("login", next=request.path))
    return wrapper
