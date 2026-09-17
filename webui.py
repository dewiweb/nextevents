#!/usr/bin/env python3
"""
Petite UI web pour piloter la génération du diaporama OBS.

- Bouton « Générer maintenant »
- Rafraîchissement automatique toutes les N heures
- Galerie des diapos + journal d'exécution
- Sert aussi les PNG sur le réseau

Écoute sur 0.0.0.0:$PORT (défaut 8080). Dossier de sortie : $OUT_DIR
(défaut ./diaporama). Réglages persistés dans <out>/settings.json.
"""

import contextlib
import io
import json
import os
import threading
import time
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

import generate_slides

ROOT = Path(__file__).resolve().parent
OUT_DIR = Path(os.environ.get("OUT_DIR", ROOT / "diaporama"))
SETTINGS_FILE = Path(os.environ.get("SETTINGS_FILE", OUT_DIR / "settings.json"))
PORT = int(os.environ.get("PORT", "8080"))

app = Flask(__name__)

state = {"running": False, "last_run": None, "last_error": None, "log": []}
lock = threading.Lock()

DEFAULTS = {
    "interval_hours": 0,
    "max_events": 0,
    "resolution": "uhd",
    "ftp_host": "",
    "ftp_port": 21,
    "ftp_user": "",
    "ftp_pass": "",
    "ftp_path": "/",
    "ftp_tls": 0,
    "smb_host": "",
    "smb_share": "",
    "smb_path": "",
    "smb_user": "",
    "smb_pass": "",
}


def load_settings():
    try:
        s = json.loads(SETTINGS_FILE.read_text())
    except Exception:
        s = {}
    out = dict(DEFAULTS)
    for k, d in DEFAULTS.items():
        v = s.get(k, d)
        if isinstance(d, int):
            try:
                out[k] = int(v)
            except (TypeError, ValueError):
                pass
        else:
            out[k] = str(v)
    if s.get("last_run"):
        state["last_run"] = s["last_run"]
    return out


def save_settings(s):
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(s)
    if state["last_run"]:
        payload["last_run"] = state["last_run"]
    SETTINGS_FILE.write_text(json.dumps(payload, indent=2))


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
            generate_slides.generate(
                out_dir=OUT_DIR, max_events=s["max_events"], cfg=s,
                size=generate_slides.SIZES.get(
                    s["resolution"], generate_slides.DEFAULT_SIZE
                ),
            )
        state["last_run"] = time.time()
    except Exception as e:
        state["last_error"] = str(e)
    finally:
        state["running"] = False
        save_settings(load_settings())


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
    if not OUT_DIR.exists():
        return []
    return sorted(p.name for p in OUT_DIR.glob("*.png"))


PAGE = """<!DOCTYPE html>
<html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Nextevents — Diaporama Champs Libres</title>
<style>
*{margin:0;box-sizing:border-box}
body{font-family:'Oldschool Grotesk',system-ui,sans-serif;background:#141414;
 color:#efeae6;max-width:1200px;margin:0 auto;padding:32px 24px 60px}
h1{font-size:34px;font-weight:500}
h1 .dot{color:#bf4c3c}
.sub{color:#8f8c8a;margin:6px 0 28px;font-size:15px}
.card{background:#1e1d1c;border:1px solid #302f2e;border-radius:14px;
 padding:20px 22px;margin-bottom:22px}
.row{display:flex;gap:14px;flex-wrap:wrap;align-items:center}
label{font-size:14px;color:#8f8c8a}
input,select{background:#141414;border:1px solid #302f2e;color:#efeae6;
 border-radius:8px;padding:8px 12px;font:inherit;width:110px}
button{background:#bf4c3c;color:#fff;border:0;border-radius:8px;
 padding:10px 22px;font:inherit;font-weight:500;cursor:pointer}
button:disabled{opacity:.45;cursor:default}
button.ghost{background:#302f2e}
.status{font-size:14px}
.status .ok{color:#9daa9f}.status .err{color:#c99483}.status .run{color:#f6e3bb}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));
 gap:14px}
.grid a{display:block;border-radius:10px;overflow:hidden;
 border:1px solid #302f2e}
.grid img{width:100%;display:block}
.caption{font-size:12px;color:#8f8c8a;padding:6px 8px;background:#1e1d1c;
 white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
pre{background:#141414;border:1px solid #302f2e;border-radius:10px;
 padding:14px;font-size:12.5px;max-height:300px;overflow:auto;
 white-space:pre-wrap;color:#bfbbb8}
a.link{color:#e3c2b7}
</style></head><body>
<h1><span class="dot">●</span> Nextevents</h1>
<p class="sub">Diaporama OBS des rencontres aux Champs Libres — PNG 16:9</p>

<div class="card">
  <div class="row">
    <button id="run" onclick="run()">Générer maintenant</button>
    <span class="status" id="status">…</span>
  </div>
</div>

<div class="card">
  <div class="row">
    <label>Rafraîchissement auto (heures, 0 = off)
      <input id="interval" type="number" min="0" step="1"></label>
    <label>Nb max d'événements (0 = tous)
      <input id="maxev" type="number" min="0" step="1"></label>
    <label>Résolution
      <select id="res" style="width:auto">
        <option value="uhd">UHD 3840×2160</option>
        <option value="hd">HD 1920×1080</option>
      </select></label>
    <button class="ghost" onclick="save()">Enregistrer</button>
    <span class="status" id="saved"></span>
  </div>
  <p class="sub" style="margin:10px 0 0">Changer de résolution re-rend
  toutes les diapos à la prochaine génération.</p>
</div>

<div class="card">
  <div class="row">
    <label>Serveur FTP <input id="ftp_host" placeholder="nas.local"></label>
    <label>Port <input id="ftp_port" type="number" min="1" style="width:80px"></label>
    <label>Chemin distant <input id="ftp_path" placeholder="/diaporama"></label>
    <label>Utilisateur <input id="ftp_user"></label>
    <label>Mot de passe <input id="ftp_pass" type="password"
      placeholder="(inchangé si vide)"></label>
    <label style="align-self:end"><input id="ftp_tls" type="checkbox"
      style="width:auto"> FTPS</label>
    <button class="ghost" onclick="save()">Enregistrer</button>
    <button class="ghost" onclick="testFtp()">Tester la connexion</button>
    <span class="status" id="ftptest"></span>
  </div>
  <p class="sub" style="margin:10px 0 0">Laisser « Serveur FTP » vide pour
  désactiver l'envoi. Les diapos sont aussi écrites dans le dossier local.</p>
</div>

<div class="card">
  <div class="row">
    <label>Hôte SMB (IP ou nom du poste OBS / NAS)
      <input id="smb_host" placeholder="192.168.1.20"></label>
    <label>Partage <input id="smb_share" placeholder="diaporama"></label>
    <label>Sous-dossier <input id="smb_path" placeholder="(optionnel)"></label>
    <label>Utilisateur <input id="smb_user" placeholder="DOMAINE\\user"></label>
    <label>Mot de passe <input id="smb_pass" type="password"
      placeholder="(inchangé si vide)"></label>
    <button class="ghost" onclick="save()">Enregistrer</button>
    <button class="ghost" onclick="testSmb()">Tester la connexion</button>
    <span class="status" id="smbtest"></span>
  </div>
</div>

<div class="card"><div class="grid" id="grid"></div></div>

<div class="card"><label>Journal</label><pre id="log">—</pre></div>

<script>
// champs en cours d'édition : ne pas les écraser au rafraîchissement auto
const dirty = new Set();
document.querySelectorAll('input,select').forEach(el => {
  el.addEventListener('input', () => dirty.add(el.id));
  el.addEventListener('change', () => dirty.add(el.id));
});
function setVal(id, v){
  const el = document.getElementById(id);
  if (!el || dirty.has(id) || el === document.activeElement) return;
  el.value = v;
}
function setChecked(id, v){
  const el = document.getElementById(id);
  if (!el || dirty.has(id) || el === document.activeElement) return;
  el.checked = !!v;
}
async function refresh(){
  const s = await (await fetch('/api/status')).json();
  setVal('interval', s.settings.interval_hours);
  setVal('maxev', s.settings.max_events);
  setVal('res', s.settings.resolution);
  setVal('ftp_host', s.settings.ftp_host);
  setVal('ftp_port', s.settings.ftp_port);
  setVal('ftp_path', s.settings.ftp_path);
  setVal('ftp_user', s.settings.ftp_user);
  setChecked('ftp_tls', s.settings.ftp_tls);
  document.getElementById('ftp_pass').placeholder =
    s.settings.has_pass ? '(enregistré — vide = inchangé)' : '(non défini)';
  setVal('smb_host', s.settings.smb_host);
  setVal('smb_share', s.settings.smb_share);
  setVal('smb_path', s.settings.smb_path);
  setVal('smb_user', s.settings.smb_user);
  document.getElementById('smb_pass').placeholder =
    s.settings.has_smb_pass ? '(enregistré — vide = inchangé)' : '(non défini)';
  const el = document.getElementById('status');
  const last = s.last_run ? new Date(s.last_run*1000).toLocaleString('fr-FR') : 'jamais';
  el.className = 'status ' + (s.running ? 'run' : s.last_error ? 'err' : 'ok');
  el.textContent = s.running ? '⏳ génération en cours…'
    : (s.last_error ? '⚠ '+s.last_error+' — ' : '') +
      s.slides.length+' diapos · dernière génération : '+last;
  document.getElementById('run').disabled = s.running;
  document.getElementById('log').textContent = s.log.join('\\n') || '—';
  document.getElementById('grid').innerHTML = s.slides.map(n =>
    `<a href="/slides/${n}" target="_blank"><img loading="lazy"
      src="/slides/${n}"><div class="caption">${n}</div></a>`).join('');
}
async function run(){ await fetch('/api/run',{method:'POST'}); refresh(); }
async function save(){
  await fetch('/api/settings',{method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({
      interval_hours:+interval.value, max_events:+maxev.value,
      resolution:res.value,
      ftp_host:ftp_host.value, ftp_port:+ftp_port.value,
      ftp_path:ftp_path.value, ftp_user:ftp_user.value,
      ftp_pass:ftp_pass.value, ftp_tls:ftp_tls.checked?1:0,
      smb_host:smb_host.value, smb_share:smb_share.value,
      smb_path:smb_path.value, smb_user:smb_user.value,
      smb_pass:smb_pass.value})});
  dirty.clear();
  document.getElementById('saved').textContent = 'enregistré ✓';
  setTimeout(()=>document.getElementById('saved').textContent='',2000);
}
async function testFtp(){
  await save();
  const el = document.getElementById('ftptest');
  el.textContent = 'test…';
  const r = await (await fetch('/api/ftp/test',{method:'POST'})).json();
  el.textContent = r.ok ? 'connexion OK ✓' : 'échec : '+r.error;
}
async function testSmb(){
  await save();
  const el = document.getElementById('smbtest');
  el.textContent = 'test…';
  const r = await (await fetch('/api/smb/test',{method:'POST'})).json();
  el.textContent = r.ok ? 'connexion OK ✓' : 'échec : '+r.error;
}
refresh(); setInterval(refresh, 3000);
</script>
</body></html>"""


@app.get("/")
def index():
    return PAGE


@app.get("/api/status")
def api_status():
    s = load_settings()
    has_pass = bool(s.pop("ftp_pass"))
    has_smb_pass = bool(s.pop("smb_pass"))
    return jsonify(
        running=state["running"],
        last_run=state["last_run"],
        last_error=state["last_error"],
        log=state["log"],
        slides=slides(),
        settings={**s, "has_pass": has_pass, "has_smb_pass": has_smb_pass},
    )


@app.post("/api/run")
def api_run():
    threading.Thread(target=run_generation, daemon=True).start()
    return jsonify(ok=True)


@app.post("/api/settings")
def api_settings():
    body = request.get_json(force=True, silent=True) or {}
    s = load_settings()
    for k, d in DEFAULTS.items():
        if k not in body:
            continue
        if k in ("ftp_pass", "smb_pass") and body[k] == "":
            continue  # vide = inchangé
        if k == "resolution" and body[k] not in generate_slides.SIZES:
            continue
        if isinstance(d, int):
            try:
                s[k] = max(0, int(body[k]))
            except (TypeError, ValueError):
                pass
        else:
            s[k] = str(body[k])
    save_settings(s)
    return jsonify(ok=True)


@app.post("/api/ftp/test")
def api_ftp_test():
    import ftplib

    s = load_settings()
    try:
        cls = ftplib.FTP_TLS if s["ftp_tls"] else ftplib.FTP
        ftp = cls()
        ftp.connect(s["ftp_host"], s["ftp_port"], timeout=15)
        ftp.login(s["ftp_user"], s["ftp_pass"])
        if s["ftp_tls"]:
            ftp.prot_p()
        for part in [p for p in s["ftp_path"].split("/") if p]:
            ftp.cwd(part)
        ftp.quit()
        return jsonify(ok=True)
    except Exception as e:
        return jsonify(ok=False, error=str(e))


@app.post("/api/smb/test")
def api_smb_test():
    s = load_settings()
    try:
        from smbclient import listdir, register_session

        register_session(
            s["smb_host"], username=s["smb_user"], password=s["smb_pass"]
        )
        path = f"\\\\{s['smb_host']}\\{s['smb_share']}"
        if s["smb_path"]:
            path += "\\" + s["smb_path"].strip("/\\")
        listdir(path)
        return jsonify(ok=True)
    except Exception as e:
        return jsonify(ok=False, error=str(e))


@app.get("/slides/<path:name>")
def slide_file(name):
    return send_from_directory(OUT_DIR, name)


if __name__ == "__main__":
    load_settings()
    threading.Thread(target=scheduler, daemon=True).start()
    app.run(host="0.0.0.0", port=PORT)
