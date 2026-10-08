"""Exécution des générations : thread, journal capturé, planificateur."""

import contextlib
import io
import threading
import time

from .generate import generate
from .slide import SIZES, DEFAULT_SIZE
from .settings import (
    load_settings, resolve_out_dir, save_settings, lock, state,
)


class LogWriter(io.TextIOBase):
    def write(self, s):
        for line in s.splitlines():
            if line.strip():
                state["log"].append(line)
                del state["log"][:-500]
        return len(s)


def run_generation():
    with lock:
        if state["running"]:
            return
        state.update(running=True, last_error=None, log=[])
    try:
        s = load_settings()
        with contextlib.redirect_stdout(LogWriter()):
            generate(
                out_dir=resolve_out_dir(s), max_events=s["max_events"], cfg=s,
                size=SIZES.get(s["resolution"], DEFAULT_SIZE),
            )
        state["last_run"] = time.time()
    except Exception as e:
        state["last_error"] = str(e)
    finally:
        state["running"] = False
        last = state["last_run"]  # load_settings() réinjecterait
        s = load_settings()       # l'ancienne valeur du fichier
        state["last_run"] = last
        save_settings(s)


def _interval_min(s):
    """Intervalle en minutes — interval_min prime ; interval_hours
    (réglage legacy) sert de repli."""
    return (s["interval_min"] if s.get("interval_min")
            else s.get("interval_hours", 0) * 60)


def _times_due(spec, last_run, now=None):
    """Heures fixes « HH:MM, HH:MM » — vrai si la plus récente
    occurrence passée (aujourd'hui ou hier) est postérieure à
    last_run. last_run None → l'occurrence passée du jour est due
    (rattrapage au lancement)."""
    import datetime as dt
    now = now or dt.datetime.now()
    times = []
    for tok in spec.split(","):
        tok = tok.strip()
        if not tok:
            continue
        try:
            h, m = (int(x) for x in tok.split(":"))
            times.append(dt.time(h % 24, m % 60))
        except ValueError:
            continue
    if not times:
        return False
    past = [dt.datetime.combine(d, t).timestamp()
            for d in (now.date(), now.date() - dt.timedelta(days=1))
            for t in times
            if dt.datetime.combine(d, t).timestamp() <= now.timestamp()]
    return bool(past) and (last_run is None or last_run < max(past))


def next_run(s, last_run, now=None):
    """Timestamp de la prochaine exécution planifiée, ou None si rien
    n'est programmé (ni intervalle ni heures fixes)."""
    import datetime as dt
    now = now or dt.datetime.now()
    now_ts = now.timestamp()
    cands = []
    mins = _interval_min(s)
    if mins > 0:
        # prochaine échéance après now, à partir du dernier run
        base = last_run or (now_ts - mins * 60)
        n = base + mins * 60
        while n <= now_ts:
            n += mins * 60
        cands.append(n)
    for tok in (s.get("sched_times") or "").split(","):
        try:
            h, m = (int(x) for x in tok.strip().split(":"))
        except ValueError:
            continue
        t = dt.time(h % 24, m % 60)
        for day in (now.date(), now.date() + dt.timedelta(days=1)):
            ts = dt.datetime.combine(day, t).timestamp()
            if ts > now_ts:
                cands.append(ts)
                break
    return min(cands) if cands else None


def scheduler():
    while True:
        time.sleep(60)
        try:
            s = load_settings()
            mins = _interval_min(s)
            due = not state["running"] and (
                (mins > 0 and (
                    state["last_run"] is None
                    or time.time() - state["last_run"] >= mins * 60))
                or _times_due(s.get("sched_times", ""),
                              state["last_run"]))
            if due:
                threading.Thread(target=run_generation, daemon=True).start()
        except Exception:
            pass


def slides():
    d = resolve_out_dir()
    if not d.exists():
        return []
    return sorted(p.name for p in d.glob("*.png"))


def slides_portrait():
    """Diapos portrait (sous-dossier, non poussées par les synchros)."""
    d = resolve_out_dir() / "portrait"
    if not d.exists():
        return []
    return sorted(p.name for p in d.glob("*.png"))
