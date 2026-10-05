// Nextevents — logique de la page de contrôle (webui.html)

// onglets — panneau actif persisté en localStorage
document.querySelectorAll('.tabs button').forEach(b => {
  b.addEventListener('click', () => {
    document.querySelectorAll('.tabs button')
      .forEach(x => x.classList.toggle('active', x === b));
    document.querySelectorAll('.tabpanel').forEach(p =>
      p.classList.toggle('active', p.id === 'tab_' + b.dataset.tab));
    localStorage['tab'] = b.dataset.tab;
    if (b.dataset.tab === 'today')
      requestAnimationFrame(fitTodayPreview);
  });
});
if (localStorage['tab'])
  document.querySelector(
    `.tabs button[data-tab="${localStorage['tab']}"]`)?.click();
// sections pliables : état persisté en localStorage
document.querySelectorAll('details.card[id]').forEach(d => {
  const k = 'sec_' + d.id;
  if (localStorage[k] !== undefined) d.open = localStorage[k] === '1';
  d.addEventListener('toggle',
    () => localStorage[k] = d.open ? '1' : '0');
});
// champs en cours d'édition : ne pas les écraser au rafraîchissement auto
// (limité aux réglages — les champs de la diapo du jour ne sont pas
// envoyés par save(), ils ne doivent pas allumer le bouton)
const dirty = new Set();
function updSavebar(){
  const b = document.getElementById('btn_save');
  b.classList.toggle('dirty', dirty.size > 0);
  b.textContent = dirty.size ? '● Enregistrer les réglages'
                             : 'Enregistrer les réglages';
}
document.querySelectorAll(
  '#tab_cfg input,#tab_cfg select,#tab_cfg textarea,' +
  '#tab_gal input,#tab_gal select').forEach(el => {
  const mark = () => { dirty.add(el.id); updSavebar(); };
  el.addEventListener('input', mark);
  el.addEventListener('change', mark);
});
// Catégories : une case par catégorie connue (renvoyée par /api/status)
// + champ « autres slugs » pour les pages catégorie non listées. La
// valeur canonique reste la liste de slugs à virgules (hidden
// #gen_categories) — aucune case cochée et extras vide = 5 vitrine.
function setCats(v, cats){
  const box = document.getElementById('cat_boxes');
  if (!box) return;
  if (!box.childElementCount){
    cats.forEach(c => {
      const cb = document.createElement('input');
      cb.type = 'checkbox'; cb.id = 'cat_' + c.slug;
      cb.dataset.slug = c.slug;
      cb.addEventListener('change', syncCats);
      const lb = document.createElement('label');
      lb.className = 'cat'; lb.title = c.slug;
      lb.append(cb, document.createTextNode(' ' + c.label));
      box.appendChild(lb);
    });
  }
  if (dirty.has('gen_categories') ||
      dirty.has('gen_categories_extra')) return;
  const known = new Set(cats.map(c => c.slug));
  const vals = (v || '').split(',').map(x => x.trim()).filter(Boolean);
  box.querySelectorAll('input[type=checkbox]').forEach(cb =>
    cb.checked = vals.includes(cb.dataset.slug));
  const ex = document.getElementById('gen_categories_extra');
  if (ex !== document.activeElement)
    ex.value = vals.filter(x => !known.has(x)).join(', ');
  document.getElementById('gen_categories').value = v || '';
}
function syncCats(){
  const vals = [...document.querySelectorAll('#cat_boxes input:checked')]
    .map(cb => cb.dataset.slug);
  const extra = document.getElementById('gen_categories_extra').value
    .split(',').map(x => x.trim()).filter(Boolean);
  document.getElementById('gen_categories').value =
    [...vals, ...extra].join(', ');
  dirty.add('gen_categories'); updSavebar();
}
document.getElementById('gen_categories_extra')
  .addEventListener('input', syncCats);

// Détection des séries éditoriales (pages série du site + keywords
// OpenAgenda) — les clés déjà présentes dans series_map ne sont pas
// reproposées
async function detectSeries(){
  const box = document.getElementById('series_detect');
  const acts = document.getElementById('series_detect_acts');
  const msg = document.getElementById('series_msg');
  box.style.display = 'none'; acts.style.display = 'none';
  msg.textContent = 'détection en cours — ~1 min (pages du site + OpenAgenda)…';
  let r;
  try {
    r = await (await fetch('/api/series/detect', {method:'POST'})).json();
  } catch(e){ msg.textContent = 'échec : ' + e; return; }
  if (!r.ok){ msg.textContent = 'échec : ' + (r.error || '?'); return; }
  const ta = document.getElementById('series_map');
  const known = new Set(
    [...ta.value.matchAll(/^\s*([^=#]+?)\s*=/gm)].map(m => m[1]));
  const fresh = r.series.filter(s => !known.has(s.key));
  msg.textContent = fresh.length
    ? r.series.length + ' série(s) détectée(s), ' + fresh.length +
      ' nouvelle(s) — cocher puis ajouter :'
    : 'aucune nouvelle série détectée';
  if (!fresh.length) return;
  box.innerHTML = '';
  fresh.forEach(s => {
    const cb = document.createElement('input');
    cb.type = 'checkbox'; cb.checked = true;
    cb.dataset.k = s.key; cb.dataset.l = s.label;
    const lb = document.createElement('label');
    lb.className = 'cat'; lb.title = s.key;
    lb.append(cb, document.createTextNode(' ' + s.label));
    box.appendChild(lb);
  });
  box.style.display = 'grid';
  acts.style.display = 'flex';
}
function addDetected(){
  const ta = document.getElementById('series_map');
  const lines = [...document.querySelectorAll(
    '#series_detect input:checked')]
    .map(cb => cb.dataset.k + ' = ' + cb.dataset.l);
  if (lines.length){
    ta.value = (ta.value.replace(/\s+$/, '') + '\n' +
                lines.join('\n') + '\n').replace(/^\n/, '');
    dirty.add('series_map'); updSavebar();
    refreshLogoTargets();
  }
  closeDetect();
}
function closeDetect(){
  document.getElementById('series_detect').style.display = 'none';
  document.getElementById('series_detect_acts').style.display = 'none';
  document.getElementById('series_msg').textContent = '';
}

// Lignes « clé = Libellé | logo » du champ series_map → {i, key,
// label, logo} — sert à peupler le select de cible du logo
function seriesRows(){
  return document.getElementById('series_map').value.split('\n')
    .map((l, i) => {
      const t = l.trim();
      if (!t || t.startsWith('#') || !t.includes('=')) return null;
      const [k, rest] = [l.slice(0, l.indexOf('=')),
                         l.slice(l.indexOf('=') + 1)];
      const [label, logo] = [rest.split('|')[0].trim(),
                             (rest.split('|')[1] || '').trim()];
      return {i, key: k.trim(), label, logo};
    }).filter(Boolean);
}
function refreshLogoTargets(){
  const sel = document.getElementById('logo_target');
  const cur = sel.value;
  sel.innerHTML = '';
  const rows = seriesRows();
  if (!rows.length){
    const o = document.createElement('option');
    o.value = ''; o.textContent = '(déclarer une série ci-dessus)';
    sel.appendChild(o); return;
  }
  rows.forEach(rw => {
    const o = document.createElement('option');
    o.value = rw.key;
    o.textContent = rw.label + ' (' + rw.key + ')' +
                    (rw.logo ? '  ◉' : '');
    sel.appendChild(o);
  });
  if (cur && rows.some(rw => rw.key === cur)) sel.value = cur;
}
document.getElementById('series_map')
  .addEventListener('input', refreshLogoTargets);

async function uploadLogo(inp){
  const f = inp.files[0]; inp.value = '';
  const msg = document.getElementById('logo_up_msg');
  if (!f) return;
  const key = document.getElementById('logo_target').value;
  if (!key){
    msg.textContent = 'ajouter d\'abord la ligne de la série ci-dessus';
    return;
  }
  msg.textContent = 'envoi…';
  const fd = new FormData(); fd.append('file', f);
  let r;
  try {
    r = await (await fetch('/api/series/logo',
      {method:'POST', body:fd})).json();
  } catch(e){ msg.textContent = 'échec : ' + e; return; }
  if (!r.ok){ msg.textContent = 'échec : ' + (r.error || '?'); return; }
  // associe le logo à la ligne de la série choisie dans le select
  const ta = document.getElementById('series_map');
  const lines = ta.value.split('\n');
  const row = seriesRows().find(rw => rw.key === key);
  if (row){
    lines[row.i] = row.key + ' = ' + row.label + ' | ' + r.name;
    ta.value = lines.join('\n');
    dirty.add('series_map'); updSavebar();
    refreshLogoTargets();
    document.getElementById('logo_target').value = key;
    msg.textContent = r.name + ' associé à « ' + row.label + ' »';
  } else {
    msg.textContent = 'enregistré — ligne « ' + key +
      ' » introuvable, ajouter « | ' + r.name + ' » à la main';
  }
}

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
  setVal('interval', s.settings.interval_min);
  setVal('sched_times', s.settings.sched_times);
  setVal('maxev', s.settings.max_events);
  setVal('data_source', s.settings.data_source);
  setVal('oa_agenda', s.settings.oa_agenda);
  document.getElementById('oa_api_key').placeholder =
    s.settings.has_oa_key ? '(enregistrée — vide = inchangée)'
                          : '(vide = export legacy déprécié)';
  setCats(s.settings.gen_categories, s.categories || []);
  setVal('next_label', s.settings.next_label);
  setVal('series_map', s.settings.series_map);
  refreshLogoTargets();
  setVal('specs_show', s.settings.specs_show);
  setVal('spec_drops', s.settings.spec_drops);
  setVal('spec_over', s.settings.spec_overrides);
  setVal('res', s.settings.resolution);
  setChecked('gen_ls', s.settings.gen_landscape);
  setChecked('gen_pt', s.settings.gen_portrait);
  setVal('ftp_host', s.settings.ftp_host);
  setVal('ftp_port', s.settings.ftp_port);
  setVal('ftp_path', s.settings.ftp_path);
  setVal('ftp_user', s.settings.ftp_user);
  setChecked('ftp_tls', s.settings.ftp_tls);
  setChecked('ftp_ls', s.settings.ftp_send_landscape);
  setChecked('ftp_pt', s.settings.ftp_send_portrait);
  document.getElementById('ftp_pass').placeholder =
    s.settings.has_pass ? '(enregistré — vide = inchangé)' : '(non défini)';
  setVal('smb_host', s.settings.smb_host);
  setVal('smb_share', s.settings.smb_share);
  setVal('smb_path', s.settings.smb_path);
  setVal('smb_user', s.settings.smb_user);
  setChecked('smb_ls', s.settings.smb_send_landscape);
  setChecked('smb_pt', s.settings.smb_send_portrait);
  document.getElementById('smb_pass').placeholder =
    s.settings.has_smb_pass ? '(enregistré — vide = inchangé)' : '(non défini)';
  setVal('out_dir', s.settings.out_dir);
  setVal('local_dir', s.settings.local_dir);
  setVal('ss_delay', s.settings.ss_delay);
  setVal('ss_transition', s.settings.ss_transition);
  setVal('ss_tdur', s.settings.ss_tdur);
  setVal('ss_delay_p', s.settings.ss_delay_p);
  setVal('ss_transition_p', s.settings.ss_transition_p);
  setVal('ss_tdur_p', s.settings.ss_tdur_p);
  const el = document.getElementById('status');
  const last = s.last_run ? new Date(s.last_run*1000).toLocaleString('fr-FR') : 'jamais';
  const hb = document.getElementById('hbadge');
  hb.className = 'hbadge' + (s.running ? ' run' : s.last_error ? ' err' : '');
  hb.textContent = s.running ? '⏳ génération en cours'
    : s.last_error ? '⚠ erreur — voir journal'
    : s.slides.length + ' diapos · ' + last;
  hb.title = s.last_error || '';
  el.className = 'status ' + (s.running ? 'run' : s.last_error ? 'err' : 'ok');
  el.textContent = s.running ? '⏳ génération en cours…'
    : (s.last_error ? '⚠ '+s.last_error+' — ' : '') +
      s.slides.length+' diapos · dernière génération : '+last;
  document.getElementById('btn_run').disabled = s.running;
  document.getElementById('btn_run').textContent =
    s.running ? '⏳ génération…' : 'Générer maintenant';
  document.getElementById('log').textContent = s.log.join('\n') || '—';
  const esc = t => t.replace(/&/g,'&amp;').replace(/</g,'&lt;')
                    .replace(/>/g,'&gt;');
  const meta = s.slide_meta || {};
  const cell = (n, sub) =>
    `<div class="cell"><a href="/slides/${sub||''}${n}" target="_blank">
      <img loading="lazy" src="/slides/${sub||''}${n}"></a>
     <div class="caption" title="${n}">${esc(meta[n] || prettyName(n))}</div>
     <div class="acts">
       <button data-regen="${n}"
         title="Re-rendre le PNG depuis le HTML">↻</button>
       <button data-del="${n}" title="Supprimer la diapo">✕</button>
     </div></div>`;
  document.getElementById('grid').innerHTML =
    s.slides.map(n => cell(n, '')).join('');
  const sp = s.slides_portrait || [];
  document.getElementById('card_p').style.display =
    sp.length ? '' : 'none';
  document.getElementById('grid_p').innerHTML =
    sp.map(n => cell(n, 'portrait/')).join('');
  // tant qu'aucun événement n'a été chargé on réessaie à chaque
  // refresh — sinon la liste restait vide après la 1re génération
  // (le <option> placeholder faisait passer options.length à 1)
  if (!todayEvents.length) loadTodayEvents();
  // séries connues (series_map + tables par défaut) pour le choix
  // manuel quand l'événement n'est pas dans la liste
  const ssel = document.getElementById('t_series_sel');
  if (ssel && ssel.options.length <= 1 && s.series_options){
    (s.series_options).forEach(l => {
      const o = document.createElement('option');
      o.value = l; o.textContent = l;
      ssel.appendChild(o);
    });
  }
  // l'aperçu reste si un live-preview srcdoc est affiché, même quand
  // index.html n'existe pas encore sur le disque
  fetch('/today/index.html', {method:'HEAD'})
    .then(r => showTodayTools(r.ok || !!t_frame().srcdoc))
    .catch(() => {});
  fetch('/today/qr.html', {method:'HEAD'}).then(r => {
    document.getElementById('t_files').style.display = r.ok ? '' : 'none';
  }).catch(() => {});
}
// slide-AAAA-MM-JJ-HHhMM-slug.png → "04/10 · 16h00 · le cueilleur de moire"
function prettyName(n){
  const m = n.match(/^slide-\d{4}-(\d{2})-(\d{2})-(\d{2})h(\d{2})-(.+)\.png$/);
  if (!m) return n;
  return `${m[2]}/${m[1]} · ${m[3]}h${m[4]} · ${m[5].replace(/-/g,' ')}`;
}
async function run(){ await fetch('/api/run',{method:'POST'}); refresh(); }

// actions galerie (délégation — les boutons sont recréés au refresh)
document.addEventListener('click', async ev => {
  const regen = ev.target.closest('[data-regen]');
  const del = ev.target.closest('[data-del]');
  if (regen) {
    regen.disabled = true; regen.textContent = '…';
    const r = await (await fetch(
      `/api/slides/${regen.dataset.regen}/regen`,
      {method:'POST'})).json();
    if (r.error) alert('Régénération : ' + r.error);
    refresh();
  } else if (del) {
    if (!confirm(`Supprimer ${del.dataset.del} ?\n` +
                 '(PNG + HTML, paysage et portrait — elle reviendra ' +
                 'à la prochaine génération si l\'événement est ' +
                 'toujours au programme)')) return;
    const r = await (await fetch(
      `/api/slides/${del.dataset.del}`, {method:'DELETE'})).json();
    if (r.error) alert('Suppression : ' + r.error);
    refresh();
  }
});

// ——— diapo du jour ———
const BG_CHOICES = [
  ['#141414','Encre'],['#302f2e','Anthracite'],['#363129','Jaune nuit'],
  ['#2b2e2c','Vert nuit'],['#312a28','Terre nuit'],['#313134','Bleu nuit'],
  ['#3d1813','Rouge nuit'],['#16203f','Marine (séries)']];
let todayBg = BG_CHOICES[0][0];
// le fond marine posé automatiquement quand une série est choisie est
// défait si l'événement/série suivant n'en a pas — un choix manuel
// de l'utilisateur n'est jamais écrasé
let bgAuto = false;
function buildBgPalette(){
  const box = document.getElementById('t_bg');
  box.innerHTML = '';
  BG_CHOICES.forEach(([v,name]) => {
    const b = document.createElement('button');
    b.type = 'button'; b.title = name;
    b.style.cssText = 'width:42px;height:42px;border-radius:50%;' +
      'cursor:pointer;padding:0;background:'+v+';border:3px solid ' +
      (v===todayBg ? '#f6e3bb' : 'rgba(239,234,230,.15)') +
      ';box-shadow:' + (v===todayBg ? '0 0 0 2px #f6e3bb' : 'none');
    b.onclick = () => { todayBg = v; bgAuto = false;
      buildBgPalette(); liveTodayPreview(); };
    box.appendChild(b);
  });
}
buildBgPalette();
// série effective : celle de l'événement choisi, sinon la série choisie
// manuellement (événement hors liste — généré entre deux runs)
function effectiveSeries(){
  const ev = todayEvents.find(e => e.i == t_ev.value) || {};
  return ev.series || document.getElementById('t_series_sel').value;
}
function refreshSeriesBadge(){
  const s = effectiveSeries();
  document.getElementById('t_series').textContent =
    s ? 'Série : '+s+' — modèle com appliqué' : '';
}
let todayEvents = [];
// « JJ/MM/AA » du jour (format du spec Date du site)
function todayShort(){
  const t = new Date();
  return String(t.getDate()).padStart(2,'0') + '/' +
    String(t.getMonth()+1).padStart(2,'0') + '/' +
    String(t.getFullYear()).slice(2);
}
function evIsToday(d){
  d = d || '';
  const m = d.match(/(\d{2})\/(\d{2})\/(\d{2})\s*au\s*(\d{2})\/(\d{2})\/(\d{2})/);
  if (m){  // « Du JJ/MM/AA au JJ/MM/AA » : en cours si aujourd'hui dedans
    const a = `20${m[3]}-${m[2]}-${m[1]}`, b = `20${m[6]}-${m[5]}-${m[4]}`;
    const t = new Date();
    const iso = t.getFullYear() + '-' +
      String(t.getMonth()+1).padStart(2,'0') + '-' +
      String(t.getDate()).padStart(2,'0');
    return a <= iso && iso <= b;
  }
  return d.includes(todayShort());
}
async function loadTodayEvents(){
  try {
    todayEvents = await (await fetch('/api/today/events')).json();
  } catch(e){ return; }
  const sel = document.getElementById('t_ev');
  // restauration par identité (date|titre), pas par index : une
  // régénération peut réordonner la liste
  const prevKey = sel.selectedIndex >= 0
    ? (sel.options[sel.selectedIndex].dataset.k || '') : '';
  sel.innerHTML = '';
  const ph = document.createElement('option');
  ph.value = ''; ph.textContent = '— choisir un événement —';
  sel.appendChild(ph);
  const groups = [
    ['Aujourd\u2019hui', todayEvents.filter(e => evIsToday(e.date))],
    ['À venir', todayEvents.filter(e => !evIsToday(e.date))],
  ];
  for (const [label, evs] of groups){
    if (!evs.length) continue;
    const g = document.createElement('optgroup');
    g.label = label;
    for (const e of evs){
      const o = document.createElement('option');
      o.value = e.i;
      o.dataset.k = (e.date || '') + '|' + (e.title || '');
      o.textContent = [e.date, e.tag, e.title]
        .filter(Boolean).join(' · ');
      g.appendChild(o);
    }
    sel.appendChild(g);
  }
  if (prevKey){
    const m = [...sel.options].find(o => o.dataset.k === prevKey);
    sel.value = m ? m.value : '';
  }
}
function addSpeaker(name, qual){
  const d = document.createElement('div');
  d.className = 'row';
  d.innerHTML =
    `<input class="spk_name" placeholder="Nom Prénom" style="width:230px"
      value="${name.replace(/"/g,'&quot;')}">
     <input class="spk_qual" placeholder="Qualité (fonction, affiliation…)"
      style="flex:1" value="${qual.replace(/"/g,'&quot;')}">
     <button class="ghost" style="padding:6px 12px"
      onclick="this.parentNode.remove()">×</button>`;
  document.getElementById('t_speakers').appendChild(d);
}
async function prefillToday(){
  const i = document.getElementById('t_ev').value;
  if (i === '') return;
  const e = await (await fetch('/api/today/event/'+i)).json();
  // la série de l'événement l'emporte sur le choix manuel
  if (e.series) document.getElementById('t_series_sel').value = '';
  refreshSeriesBadge();
  if (e.series) { todayBg = '#16203f'; bgAuto = true; buildBgPalette(); }
  else if (bgAuto) {
    todayBg = BG_CHOICES[0][0]; bgAuto = false; buildBgPalette();
  }
  // nouvel événement = nouvelle session d'édition : l'aperçu repart
  // des champs, d'éventuelles retouches d'une diapo précédente ne
  // bloquent plus le live-preview
  previewDirty = false;
  document.getElementById('t_title').value = e.title || '';
  document.getElementById('t_sub').value = '';
  document.getElementById('t_mod').value = e.moderator || '';
  document.getElementById('t_note').value = e.note || '';
  document.getElementById('t_access').value = e.access || '';
  document.getElementById('t_access_hint').textContent =
    (e.access_venue||[]).length
      ? 'Sur place : '+e.access_venue.join(' · ') : '';
  document.getElementById('t_speakers').innerHTML = '';
  (e.speakers||[]).forEach(s => addSpeaker(s.name||'', s.quality||''));
  if (!(e.speakers||[]).length) addSpeaker('','');
  document.getElementById('t_desc').textContent =
    e.desc_long || e.desc || '—';
  liveTodayPreview();
}
// champs du formulaire → payload commun (générer / live-preview)
function collectToday(){
  const ev = todayEvents.find(e => e.i == t_ev.value) || {};
  const speakers = [...document.querySelectorAll('#t_speakers .row')]
    .map(r => ({name: r.querySelector('.spk_name').value,
                quality: r.querySelector('.spk_qual').value}))
    .filter(s => s.name.trim());
  return {title:t_title.value, subtitle:t_sub.value,
    moderator:t_mod.value, speakers, note:t_note.value,
    access:t_access.value,
    tag:ev.tag||'', color:ev.color||null, bg:todayBg,
    series:ev.series||document.getElementById('t_series_sel').value};
}
// live-preview : HTML généré côté serveur injecté dans l'iframe (srcdoc)
// — rien n'est écrit, rendu ou poussé avant « Générer »
// previewDirty : l'utilisateur a retouché l'aperçu (contentEditable /
// barre de formatage) sans enregistrer — le live-preview ne doit pas
// écraser ces retouches, il suspend juste sa mise à jour
// srcDirty : le textarea « Source HTML » diffère du fichier sur disque
let previewDirty = false, srcDirty = false;
function armPreviewEdit(){
  const d = t_frame().contentDocument;
  if (d && d.body){
    d.body.contentEditable = 'true';
    d.body.addEventListener('input', () => {
      previewDirty = true;
      document.getElementById('t_gen').textContent =
        'aperçu : retouches en cours — « Enregistrer les retouches » ' +
        'pour publier';
    });
  }
}
let _prevTimer = null;
function liveTodayPreview(){
  clearTimeout(_prevTimer);
  _prevTimer = setTimeout(async () => {
    if (todaySrcMode) return;
    if (previewDirty){
      document.getElementById('t_gen').textContent =
        'aperçu : retouches en cours — « Enregistrer les retouches » ' +
        'pour publier';
      return;
    }
    const d = collectToday();
    if (!d.title.trim()) return;
    const r = await (await fetch('/api/today/preview',{method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify(d)})).json();
    if (!r.ok) return;
    const f = t_frame();
    if (r.html === f.dataset.lastHtml) return;  // pas de reload si identique
    f.dataset.lastHtml = r.html;
    const p = document.getElementById('t_prev');
    if (p.style.display === 'none'){
      p.dataset.loaded = '1';   // srcdoc prime : pas de chargement fichier
      showTodayTools(true);
    }
    p.style.opacity = '0';      // fondu plutôt que flash noir au rechargement
    f.onload = () => {
      armPreviewEdit();
      p.style.opacity = '1';
    };
    f.removeAttribute('src');
    f.srcdoc = r.html;
    // la srcdoc affichée n'est pas le fichier poussé : le statut le dit
    document.getElementById('t_gen').textContent =
      'aperçu — non envoyée';
  }, 700);
}
// « change » seulement : la preview se rafraîchit quand on quitte le
// champ (pas à chaque frappe — change se déclenche au blur)
['t_ev','t_title','t_sub','t_mod','t_note','t_access'].forEach(id =>
  document.getElementById(id)
    .addEventListener('change', liveTodayPreview));
document.getElementById('t_speakers')
  .addEventListener('change', liveTodayPreview);
// série choisie à la main (événement hors liste) : badge, fond marine
// et live-preview — n'a d'effet que si l'événement choisi n'a pas
// déjà une série (l'événement l'emporte)
document.getElementById('t_series_sel')
  .addEventListener('change', () => {
    const ev = todayEvents.find(e => e.i == t_ev.value) || {};
    if (!ev.series){
      const v = document.getElementById('t_series_sel').value;
      if (v){ todayBg = '#16203f'; bgAuto = true; }
      else if (bgAuto){ todayBg = BG_CHOICES[0][0]; bgAuto = false; }
      buildBgPalette();
    }
    refreshSeriesBadge();
    liveTodayPreview();
  });
async function genToday(){
  const btn = document.getElementById('t_genbtn');
  const el = document.getElementById('t_gen');
  btn.disabled = true;
  el.textContent = 'génération…';
  let r;
  try {
    r = await (await fetch('/api/today',{method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify(collectToday())})).json();
  } finally {
    btn.disabled = false;
  }
  el.textContent = r.ok ? 'générée ✓ envoyée sur les partages'
    : 'échec : '+(r.errors||[r.error||'erreur']).join(' ; ');
  if (r.ok){
    // le fichier disque est la nouvelle référence
    previewDirty = false; srcDirty = false;
    document.getElementById('t_prev').dataset.loaded = '1';
    showTodayTools(true);
    if (todaySrcMode) toggleTodaySrc();
    setTodayFile('index');
    refreshQrTab();
  }
}

// ——— aperçu + retouche WYSIWYG de la diapo du jour ———
// L'aperçu iframe (same-origin) passe en contentEditable : les textes
// s'éditent en place. « Source HTML » expose le code brut à la place.
function t_frame(){ return document.getElementById('t_frame'); }
// barre de formatage : mousedown empêché pour préserver la sélection
// dans l'iframe (sinon le clic sur un bouton la perd)
function fmt(cmd, val){
  const w = t_frame().contentWindow;
  w.focus();
  previewDirty = true;
  w.document.execCommand(cmd, false, val || null);
  document.getElementById('t_gen').textContent =
    'aperçu : retouches en cours — « Enregistrer les retouches » ' +
    'pour publier';
}
// taille relative : ±15 % de la taille calculée au point de sélection,
// appliquée via un <span style="font-size"> qui enveloppe la sélection
function fontSizeStep(dir){
  const w = t_frame().contentWindow, d = w.document;
  const sel = w.getSelection();
  if (!sel || !sel.rangeCount || sel.isCollapsed) return;
  previewDirty = true;
  const range = sel.getRangeAt(0);
  const node = range.startContainer.nodeType === 3
    ? range.startContainer.parentElement : range.startContainer;
  const cur = parseFloat(w.getComputedStyle(node).fontSize) || 32;
  const span = d.createElement('span');
  span.style.fontSize =
    Math.max(8, Math.round(cur * (dir > 0 ? 1.15 : 0.87))) + 'px';
  try { range.surroundContents(span); }
  catch(e){
    span.appendChild(range.extractContents());
    range.insertNode(span);
  }
  sel.removeAllRanges();
  const r = d.createRange(); r.selectNodeContents(span);
  sel.addRange(r);
}
document.querySelectorAll('#t_fmt button').forEach(b => {
  b.addEventListener('mousedown', e => e.preventDefault());
  b.addEventListener('click', () => {
    if (b.dataset.cmd) fmt(b.dataset.cmd);
    else if (b.dataset.size)
      fontSizeStep(b.dataset.size === 'up' ? 1 : -1);
    else if (b.dataset.color) fmt('foreColor', b.dataset.color);
  });
});
document.getElementById('t_block').addEventListener('change', e => {
  if (e.target.value) fmt('formatBlock', e.target.value);
  e.target.value = '';
});
function showTodayTools(on){
  ['t_savebtn','t_srcbtn','t_full','t_fmt','t_hint','t_delbtn']
    .forEach(id =>
    document.getElementById(id).style.display =
      on && !(id === 't_fmt' && todaySrcMode) ? '' : 'none');
  const p = document.getElementById('t_prev');
  p.style.display = on ? '' : 'none';
  if (on){
    if (!p.dataset.loaded){
      p.dataset.loaded = '1';
      loadTodayPreview();
    }
    requestAnimationFrame(fitTodayPreview);
  }
  if (!on) delete p.dataset.loaded;
}
// today/ peut contenir deux diapos : index.html (diapo du jour) et
// qr.html (slide série). Le sélecteur bascule l'aperçu/éditeur.
let todayFile = 'index';
function setTodayFile(f){
  if (f !== todayFile && (previewDirty || srcDirty) &&
      !confirm('Des retouches ne sont pas enregistrées — ' +
               'changer de diapo les abandonne. Continuer ?')) return;
  previewDirty = false; srcDirty = false;
  todayFile = f;
  document.getElementById('tf_index').classList.toggle('on', f==='index');
  document.getElementById('tf_qr').classList.toggle('on', f==='qr');
  document.getElementById('t_full').href = '/today/' + f + '.html';
  if (todaySrcMode) toggleTodaySrc();
  loadTodayPreview();
}
function refreshQrTab(){
  fetch('/today/qr.html', {method:'HEAD'}).then(r => {
    document.getElementById('t_files').style.display = r.ok ? '' : 'none';
  }).catch(() => {});
}
// l'aperçu remplit la colonne : la diapo fait 1920×1080 fixe, on adapte
// l'échelle à la largeur dispo (le conteneur garde le ratio 16/9)
function fitTodayPreview(){
  const p = document.getElementById('t_prev');
  if (!p || p.style.display === 'none' || !p.clientWidth) return;
  t_frame().style.transform = 'scale(' + (p.clientWidth / 1920) + ')';
}
window.addEventListener('resize', fitTodayPreview);
function loadTodayPreview(){
  const f = t_frame();
  previewDirty = false;
  delete f.dataset.lastHtml;    // la source redevient le fichier disque
  // cache-bust : index.html vient d'être réécrit
  f.onload = armPreviewEdit;
  f.removeAttribute('srcdoc');   // srcdoc primerait sur src sinon
  f.src = '/today/' + todayFile + '.html?t=' + Date.now();
  // recharge aussi la source pour rester sync si on bascule
  fetch('/api/today/html?f=' + todayFile).then(r => r.json()).then(j => {
    if (j.ok){
      document.getElementById('t_html').value = j.html;
      srcDirty = false;
      syncHl();
    }
  }).catch(() => {});
}
// ——— éditeur source embarqué : textarea transparent sur <pre> coloré ———
function hlHtml(src){
  const esc = src.replace(/&/g,'&amp;').replace(/</g,'&lt;')
                 .replace(/>/g,'&gt;');
  return esc
    .replace(/(&lt;!--[\s\S]*?--&gt;)/g, '<span class="cm">$1</span>')
    .replace(/(&lt;!doctype[^&]*?&gt;)/gi, '<span class="dt">$1</span>')
    .replace(/(&lt;\/?)([\w-]+)((?:(?!&gt;)[\s\S])*?)(\/?&gt;)/g,
      (m, o, t, a, c) =>
        `<span class="tg">${o}${t}</span>` +
        a.replace(/([\w.-]+)(=)("[^"]*")?/g,
          (mm, n, e, v) => `<span class="at">${n}</span>${e}` +
            (v ? `<span class="st">${v}</span>` : '')) +
        `<span class="tg">${c}</span>`);
}
function syncHl(){
  const ta = document.getElementById('t_html');
  document.getElementById('t_hlcode').innerHTML = hlHtml(ta.value) + '\n';
  const hl = document.getElementById('t_hl');
  hl.scrollTop = ta.scrollTop;
  hl.scrollLeft = ta.scrollLeft;
}
document.getElementById('t_html').addEventListener('input', () => {
  srcDirty = true; syncHl();
});
document.getElementById('t_html').addEventListener('scroll', syncHl);
let todaySrcMode = false;
function toggleTodaySrc(){
  // entrer en mode source remplace le textarea par un snapshot de
  // l'aperçu — des modifs non enregistrées seraient perdues
  if (!todaySrcMode && srcDirty &&
      !confirm('La source a été modifiée sans être enregistrée — ' +
               'la remplacer par le contenu de l\'aperçu ?')) return;
  todaySrcMode = !todaySrcMode;
  document.getElementById('t_prev').style.display =
    todaySrcMode ? 'none' : '';
  document.getElementById('t_fmt').style.display =
    todaySrcMode ? 'none' : '';
  document.getElementById('t_codebox').style.display =
    todaySrcMode ? '' : 'none';
  document.getElementById('t_srcbtn').textContent =
    todaySrcMode ? 'Aperçu éditable' : 'Source HTML';
  if (todaySrcMode){
    // snapshot de l'aperçu courant → la source reflète les retouches
    const d = t_frame().contentDocument;
    if (d && d.documentElement){
      d.body && d.body.removeAttribute('contenteditable');
      document.getElementById('t_html').value =
        '<!DOCTYPE html>\n' + d.documentElement.outerHTML;
    }
    srcDirty = false;
    syncHl();
  } else if (srcDirty){
    // quitter le mode source avec des modifs non enregistrées :
    // l'aperçu reste celui du fichier — on le signale
    document.getElementById('t_edit').textContent =
      'source modifiée — non enregistrée';
  }
}
async function saveTodayHtml(){
  const el = document.getElementById('t_edit');
  el.textContent = 'enregistrement…';
  let h;
  if (todaySrcMode){
    h = document.getElementById('t_html').value;
  } else {
    const d = t_frame().contentDocument;
    if (!d || !d.documentElement){
      el.textContent = 'aperçu vide — génère d\'abord la diapo';
      return;
    }
    d.body && d.body.removeAttribute('contenteditable');
    h = '<!DOCTYPE html>\n' + d.documentElement.outerHTML;
  }
  const r = await (await fetch('/api/today/html?f=' + todayFile,
    {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({html:h})})).json();
  el.textContent = r.ok ? 'enregistré ✓ PNG re-rendu, envoyé'
    : 'enregistrement : '+(r.errors||[r.error||'erreur']).join(' ; ');
  if (r.ok){
    // le fichier disque est la nouvelle référence — l'aperçu se
    // recharge même en mode source (sinon il afficherait la version
    // d'avant enregistrement en revenant à l'aperçu)
    previewDirty = false; srcDirty = false;
    loadTodayPreview();
  }
}
async function delToday(){
  if (!confirm('Retirer la diapo du jour ?\n(fichiers today/ supprimés ' +
               'en local puis sur les partages à la synchro)')) return;
  const r = await (await fetch('/api/today', {method:'DELETE'})).json();
  const el = document.getElementById('t_gen');
  el.textContent = r.ok ? 'retirée ✓' : 'retrait : ' + (r.error || '?');
  if (!r.ok) return;
  previewDirty = false; srcDirty = false;
  const f = t_frame();
  f.removeAttribute('src'); f.removeAttribute('srcdoc');
  todayFile = 'index';
  document.getElementById('tf_index').classList.add('on');
  document.getElementById('tf_qr').classList.remove('on');
  showTodayTools(false);
  refreshQrTab();
}
async function save(){
  await fetch('/api/settings',{method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({
      interval_min:+interval.value, sched_times:sched_times.value,
      max_events:+maxev.value,
      data_source:data_source.value, oa_agenda:oa_agenda.value,
      oa_api_key:oa_api_key.value,
      gen_categories:gen_categories.value,
      next_label:next_label.value, series_map:series_map.value,
      specs_show:specs_show.value, spec_drops:spec_drops.value,
      spec_overrides:spec_over.value,
      resolution:res.value,
      gen_landscape:gen_ls.checked?1:0, gen_portrait:gen_pt.checked?1:0,
      ftp_host:ftp_host.value, ftp_port:+ftp_port.value,
      ftp_path:ftp_path.value, ftp_user:ftp_user.value,
      ftp_pass:ftp_pass.value, ftp_tls:ftp_tls.checked?1:0,
      ftp_send_landscape:ftp_ls.checked?1:0,
      ftp_send_portrait:ftp_pt.checked?1:0,
      smb_host:smb_host.value, smb_share:smb_share.value,
      smb_path:smb_path.value, smb_user:smb_user.value,
      smb_pass:smb_pass.value,
      smb_send_landscape:smb_ls.checked?1:0,
      smb_send_portrait:smb_pt.checked?1:0,
      out_dir:out_dir.value,
      local_dir:local_dir.value,
      ss_delay:+ss_delay.value, ss_transition:ss_transition.value,
      ss_tdur:+ss_tdur.value,
      ss_delay_p:+ss_delay_p.value,
      ss_transition_p:ss_transition_p.value,
      ss_tdur_p:+ss_tdur_p.value})});
  dirty.clear(); updSavebar();
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
