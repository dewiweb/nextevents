# nextevents — diaporama OBS des événements des Champs Libres

Récupère les événements à venir (rencontres, concerts, projections,
spectacles, temps forts multi-jours) depuis
<https://www.leschampslibres.fr/au-programme> et génère des diapos
**UHD 3840×2160** (PNG, prêtes pour le très grand écran — OBS les adapte
à la toile ; HD 1920×1080 en option dans l'UI ou `--size hd`) reprenant
la charte du site : fonte Oldschool Grotesk, **fond pastel de la card de
l'événement** (`v-event--{couleur}` lu sur le site, neutre par défaut),
icônes, coins arrondis sur fond noir.
Les images sont récupérées en résolution native depuis OpenAgenda
quand l'événement en provient.

Specs affichées : date, durée, lieu, tarif + **public** (« Tout
public »…, lu dans le bloc `.v-audience` — le site reflète les champs
OpenAgenda `publics`/`accessibility`) et **accessibilité** quand la
description mentionne un dispositif « actionable » (« interprétée en
LSF », audiodescription, surtitrage, amplification d'écoute) — les
handicaps pris en compte sur place (`access_venue`) restent en
référence dans la webui, pas en spec. Les temps forts n'affichent pas
de lieu (plusieurs espaces du bâtiment).

## Architecture

```
Serveur Debian (Docker) ──volume──> montage NAS (SMB/NFS) ──> poste OBS
        │                └── ou FTP/SMB applicatif ──> NAS / poste OBS
        └─ web UI : http://serveur:8080
```

- `webui.py` : interface web — bouton « Générer », rafraîchissement auto
  toutes les N heures, galerie des diapos, journal en direct,
  téléchargement du dossier en .zip.
  Sert aussi les PNG sur le réseau (`/slides/<nom>`).
- `generate_slides.py` : CLI — la logique vit dans le package
  **`nextevents/`** :

| Module | Rôle |
|---|---|
| `paths.py` | chemins (racine, assets, cache) |
| `scrape.py` | scraping des pages catégories + détails, couleur de card (`CARD_COLORS`) |
| `media.py` | fontes du site, images OpenAgenda, cache |
| `slide.py` | remplit `assets/slide_template.html`, rendu PNG (Playwright / firefox) |
| `today.py` | « diapo du jour » : slide fixe sans visuel pour l'événement en cours à l'auditorium |
| `sync.py` | envoi FTP / SMB avec suppression des fichiers obsolètes |
| `generate.py` | orchestration de la génération complète |
| `settings.py` | réglages persistés + état runtime (webui) |
| `runner.py` | exécution des générations + planificateur (webui) |
| `webapp.py` | routes Flask ; page servie depuis `assets/webui.html` |

## Layout des diapos

Le gabarit **`assets/slide_template.html`** (1920×1080) reproduit la card
« événement » du site. Il est utilisable tel quel dans un navigateur
(variables `$xxx` à remplacer) pour produire une diapo hors-site ou faire
valider la charte. Les `html/slide-*.html` générés sont autonomes
(fontes et images en base64) — utilisables via une source **Navigateur**.

### Layout portrait

Une variante **portrait** de la même card (gabarit
**`assets/slide_template_portrait.html`**, ratio **A4**) existe pour les
autres usages de la com — pensée pour l'impression : HD → 1240×1754
(150 dpi), UHD → **2480×3508 (300 dpi)**. Dans la webui, « Layouts
générés » coche **Paysage** et/ou **Portrait** ; en CLI, `--portrait`
ajoute le format portrait au rendu paysage.

Les PNG portrait sont écrits dans `<out>/portrait/` (avec leur propre
`html/` et `manifest.txt`). **Ce sous-dossier n'est jamais poussé par
les synchros FTP/SMB** — les partages ne reçoivent que le paysage.
Récupération via le .zip (`/api/download`, qui inclut `portrait/`), la
galerie webui ou `/slides/portrait/<nom>`. Les deux jeux peuvent
cohabiter : chacun a son dossier, son cache et son nettoyage.

## Diapo du jour (auditorium)

Pendant une rencontre à l'auditorium, on diffuse une **slide fixe sans
visuel**, en version sombre de la charte : composition centrée, sigle
en filigrane croppé aux coins, titre, intervenants + qualités,
animateur (accord animé/animée selon la catégorie), un champ « notes »
optionnel en pied de page (partenaires, séance de dédicace… — prérempli
depuis les mentions de la description détaillée, aucun espace occupé si
vide) et un champ « accessibilité » optionnel (LSF, audiodescription… —
prérempli depuis la description, indice « sur place » avec les handicaps
pris en compte, aucun espace occupé si vide). Le fond se choisit dans
la webui sur une palette de pastilles (7 variantes sombres : encre,
anthracite, pastels assombris). La webui a une
section « Diapo du jour » : choix de l'événement → champs préremplis par
le scraping (`<strong>` dans la description détaillée, « animé par »),
**description complète affichée pour vérification**, champs éditables
(extraction best-effort — les rédacteurs ont une certaine liberté),
puis « Générer » écrit `today/index.html` **et `today/index.png`**
(même réglage de résolution que les autres diapos — source Navigateur
ou Image dans OBS) et les pousse vers le partage SMB/FTP dans le
sous-dossier `today/`. Corriger et régénérer écrase les fichiers
distants. Gabarit : **`assets/today_template.html`** (1920×1080,
autonome).

**Séries** (ex. *Les grands témoins*) : `scrape.py` marque les
événements appartenant à une série éditoriale du site (page
`/au-programme/<slug>` + bloc « En savoir plus » des pages détail).
La diapo du jour bascule alors sur le **modèle com transposé en
sombre** : rond marine à gauche (nom de la série + logo), fond bleu
nuit, titre majuscule — composition centrée conservée. Une seconde
slide **`today/qr.html` / `qr.png`** est générée en plus : QR code vers
la page de la série (gabarit `assets/today_qr_template.html`). Ajouter
une série = une ligne dans `SERIES` (`nextevents/scrape.py`).

## Déploiement Docker

Voir **[DEPLOY.md](DEPLOY.md)**. Version courte :

```bash
docker build -t nextevents .
docker run -d --name nextevents --restart unless-stopped \
  -p 8080:8080 \
  -e TZ=Europe/Paris \
  -v /mnt/nas/diaporama:/data \
  nextevents
```

Tout est embarqué dans l'image : Python, les libs et Chromium
(rendu via Playwright, capture ×2 puis downscale → texte très net).
Le port est libre (`-p <port>:8080`).

## Rafraîchissement

- **Manuel** : bouton « Générer maintenant » ou `POST /api/run`.
- **Auto** : « Rafraîchissement auto » (heures) dans l'UI.
- **Cron** : `0 7 * * * docker exec nextevents python generate_slides.py --out /data`

À chaque génération, les diapos obsolètes sont **supprimées puis
remplacées** (en local comme sur FTP/SMB). Côté OBS, la source Diaporama
recharge automatiquement le dossier.

## API

| Requête | Effet |
|---|---|
| `POST /api/run` | lance une génération (scrape → rendu → synchros) |
| `GET /api/status` | état, journal, liste des diapos, réglages |
| `POST /api/settings` | enregistre les réglages (JSON) |
| `POST /api/ftp/test` · `POST /api/smb/test` | teste la destination |
| `GET /api/download` | archive .zip du dossier de diapos |
| `GET /slides/<nom>` | sert un PNG |
| `GET /api/today/events` | événements connus (depuis `events.json`) |
| `GET /api/today/event/<i>` | champs préremplis d'un événement |
| `POST /api/today` | génère `today/index.html` + envoi SMB/FTP |
| `GET /today/index.html` | aperçu de la diapo du jour |

### Payloads (pour Bitfocus Companion « generic-http » et similaires)

Toutes les réponses sont du JSON. `POST` accepte un body JSON
(`Content-Type: application/json`) — corps vide ou `{}` toléré.

**`POST /api/run`** — aucun body. Lance la génération en arrière-plan ;
suivre l'avancement via `GET /api/status` (`running`, `log`).

**`GET /api/status`** →

```json
{
  "running": false,
  "last_run": 1758549000,
  "last_run_iso": "2026-09-22T10:31:24",
  "last_error": null, "log": ["…"],
  "slides": ["slide-….png"], "slides_count": 41,
  "slides_portrait": ["slide-….png"],
  "settings": {"interval_hours": 24, "resolution": "uhd",
               "gen_landscape": 1, "gen_portrait": 0,
               "ftp_host": "…", "has_pass": true, "has_smb_pass": true}
}
```

`last_run` = timestamp Unix (float), `last_run_iso` = même instant en
ISO 8601 (fuseau du container — penser à `-e TZ=Europe/Paris`),
`slides_count` = nombre de diapos générées. Ce sont les champs à
exploiter pour un feedback Companion.

**`POST /api/settings`** — clés optionnelles, les absentes sont
inchangées, `ftp_pass`/`smb_pass` vides = inchangés :

```json
{"interval_hours": 24, "max_events": 0, "resolution": "uhd",
 "gen_landscape": 1, "gen_portrait": 0,
 "ftp_host": "", "ftp_port": 21, "ftp_user": "", "ftp_pass": "",
 "ftp_path": "/", "ftp_tls": 0,
 "smb_host": "", "smb_share": "", "smb_path": "",
 "smb_user": "", "smb_pass": ""}
```

**`POST /api/today`** — génère la diapo du jour (+ `qr.png` si
`series` non vide) et pousse vers SMB/FTP :

```json
{"title": "Titre de la rencontre", "tag": "Rencontre",
 "color": null, "bg": "#141414",
 "date": "22/09/26 à 20h30", "lieu": "Auditorium",
 "speakers": [{"name": "Prénom Nom", "quality": "Qualité"}],
 "moderator": "Prénom Nom", "note": "Suivi d'une dédicace…",
 "access": "Interprétation en LSF", "series": "Les grands témoins"}
```

Réponse : `{"ok": true}` ou `{"ok": false, "errors": ["…"]}`.
`bg` vide = choix auto (marine si série, encre sinon) ; `series`
déclenche le modèle « Grands témoins ».

## Envoi FTP / SMB (optionnel)

L'UI permet de pousser les diapos après chaque génération :

- **FTP** : hôte, port, chemin distant, identifiant, mot de passe, FTPS
- **SMB** : hôte (IP ou nom du poste OBS / NAS), nom du partage,
  sous-dossier optionnel, identifiant (`DOMAINE\user` accepté),
  mot de passe — via `smbprotocol`, aucun montage requis côté serveur

Chaque section a un bouton « Tester la connexion ». Les diapos
obsolètes sont supprimées de la destination à chaque synchro.

Les mots de passe sont stockés en clair dans `<out>/settings.json`
(volume `/data`) — jamais renvoyés au navigateur ni inclus dans le
.zip — mais protégez l'accès à ce fichier et à l'UI
(réseau local de confiance).

## OBS

La source **Diaporama** accepte les images (png, jpg, bmp, gif, tif, webp).
Pointer la source sur le dossier (partage monté ou chemin local),
régler intervalle et transition.

Les coins arrondis sont noir pur (`#000`) — sur fond noir en scène,
seuls les coins de la carte sont visibles.

## Usage local (hors Docker)

```bash
pip install -r requirements.txt && playwright install chromium
python3 generate_slides.py            # régénère dans ./diaporama/
python3 generate_slides.py --max 3    # test rapide
python3 generate_slides.py --out /chemin/nas/diaporama --size hd
python3 webui.py                      # UI sur http://localhost:8080
```

Sans Playwright, le script retombe sur `firefox --headless`
(rendu un peu moins net).

## Sobriété

Aligné sur l'éco-conception du site : à chaque run, seules les diapos
dont le contenu a changé sont re-rendues ; les images (URLs versionnées)
ne sont téléchargées qu'une fois (`assets/cache/`) ; la synchro FTP/SMB
n'envoie que les fichiers absents ou modifiés et vérifie le résultat
contre le manifeste.

## Porter vers un autre site

Le pipeline (rendu HTML→PNG, webui, synchro SMB/FTP, diapo du jour)
est générique. La bonne structure pour une adaptation est un **fork**
du dépôt (charte et sélecteurs changent en bloc — une branche subirait
des conflits permanents à chaque merge depuis `main`).

Ce qui est **spécifique à leschampslibres.fr** :

| À adapter | Contenu |
|---|---|
| `scrape.py` | `BASE`, `CATEGORIES` (slugs des pages catégorie), `CARD_COLORS` (modifieurs CSS du site), `SERIES`, et surtout les sélecteurs `parse_card`/`parse_detail` (classes `.v-event`, `.v-banner`, `.v-audience`…) |
| `media.py` | `ensure_fonts()` (URLs des fontes du site) ; `openagenda_image()` est **réutilisable tel quel** pour tout site alimenté par OpenAgenda (page `openagenda.com/events/<uid>` → `og:image` HD) |
| `assets/*_template.html` | charte graphique des trois gabarits (diapo, diapo du jour, QR série) |
| `today.py` | libellés (« Animé(e) par »…), gabarits, URL du QR |

`events.json` (consommé par la webui) attend par événement : `title`,
`url`, `tag`, `color`, `specs` (dict libellé→valeur), `desc`,
`desc_long`, `speakers` (`[{name, quality}]`), `moderator`, `note`,
`audience`, `access`, `access_venue` (liste), `series`. Produire ce
format depuis une autre source suffit à alimenter la webui.

## Licence

Contenus du site leschampslibres.fr diffusés sous
[CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/deed.fr) —
attribution « Les Champs Libres ». Voir `LICENSE`.
