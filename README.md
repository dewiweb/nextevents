# nextevents — diaporama OBS des rencontres aux Champs Libres

Récupère les rencontres à venir depuis
<https://www.leschampslibres.fr/au-programme/categorie/rencontres-aux-champs-libres>
et génère des diapos **1920×1080** (PNG) reprenant la charte du site
(fonte Oldschool Grotesk, palette pastel, icônes, coins arrondis sur fond noir).

## Architecture

```
Serveur Debian (Docker) ──volume──> montage NAS (SMB/NFS) ──> poste OBS
        │                └── ou FTP ──> NAS (partage FTP)
        └─ web UI : http://serveur:8080
```

- `webui.py` : interface web — bouton « Générer », rafraîchissement auto
  toutes les N heures, galerie des diapos, journal en direct.
  Sert aussi les PNG sur le réseau (`/slides/<nom>`).
- `generate_slides.py` : moteur de génération (utilisable aussi en CLI).

## Déploiement Docker (sur le serveur)

Voir **[DEPLOY.md](DEPLOY.md)** pour les instructions complètes.
Version courte :

```bash
docker build -t nextevents .
docker run -d --name nextevents --restart unless-stopped \
  -p 8080:8080 \
  -v /mnt/nas/diaporama:/data \
  nextevents
```

`/mnt/nas/diaporama` = montage du partage NAS sur le serveur
(CIFS ou NFS, à définir dans `/etc/fstab` du serveur).

Tout est embarqué dans l'image : Python, les libs et Chromium
(rendu via Playwright, capture ×2 puis downscale → texte très net).

## Rafraîchissement

- **Manuel** : bouton « Générer maintenant » dans l'UI.
- **Auto** : régler « Rafraîchissement auto » (heures) dans l'UI.
- **Cron** (alternative) :
  `0 7 * * * docker exec nextevents python generate_slides.py --out /data`

À chaque génération, les anciennes diapos sont **supprimées puis
remplacées** (en local comme sur le FTP). Côté OBS, la source Diaporama
recharge automatiquement le dossier.

## Envoi FTP / SMB (optionnel)

Si le NAS n'est pas montable en volume Docker, l'UI permet de pousser
les diapos après chaque génération :

- **FTP** : hôte, port, chemin distant, identifiant, mot de passe,
  FTPS optionnel
- **SMB** : hôte (IP ou nom du poste OBS / NAS), nom du partage,
  sous-dossier optionnel, identifiant (`DOMAINE\user` accepté),
  mot de passe — via `smbprotocol`, aucun montage requis côté serveur

Chaque section a un bouton « Tester la connexion ». Les diapos
obsolètes sont supprimées de la destination à chaque synchro.

Les mots de passe sont stockés en clair dans `<out>/settings.json`
(volume `/data`) — jamais renvoyés au navigateur, mais protégez
l'accès à ce fichier et à l'UI (réseau local de confiance).

## OBS

La source **Diaporama** accepte les images (png, jpg, bmp, gif, tif, webp).
Sur le poste OBS : monter le partage NAS
(ex. `\\NAS\diaporama` ou `smb://…`) puis pointer la source Diaporama
sur ce dossier, régler intervalle et transition.

Les coins arrondis sont noir pur (`#000`) — sur fond noir en scène,
seuls les coins de la carte sont visibles.

Les fichiers `html/` (dans le dossier de sortie) sont autonomes
(fontes et images en base64) — utilisables via une source **Navigateur**.

## Usage local (hors Docker)

```bash
python3 generate_slides.py            # régénère dans ./diaporama/
python3 generate_slides.py --max 3    # test rapide
python3 generate_slides.py --out /chemin/nas/diaporama
python3 webui.py                      # UI sur http://localhost:8080
```

Dépendances : `pip install -r requirements.txt` puis
`playwright install chromium`. Sans Playwright, le script retombe
sur `firefox --headless` (rendu un peu moins net).
