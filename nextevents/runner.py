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


def scheduler():
    while True:
        time.sleep(60)
        try:
            s = load_settings()
            due = (
                s["interval_hours"] > 0
                and not state["running"]
                and (
                    state["last_run"] is None
                    or time.time() - state["last_run"] >= s["interval_hours"] * 3600
                )
            )
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
