# Déploiement — nextevents

Génère les diapos 1920×1080 des rencontres aux Champs Libres et les
publie vers le poste OBS, via un partage réseau (NAS ou poste OBS).

## Prérequis

- Serveur Debian avec **Docker** et **git** installés
- Voir la **checklist réseau** en fin de document si le déploiement est
  fait par une équipe SI sur son propre réseau
- Cloner le dépôt privé sur le serveur :

  ```bash
  git clone https://github.com/dewiweb/nextevents.git
  cd nextevents
  ```

  Le dépôt étant privé, il faut une authentification GitHub sur le
  serveur : soit un **token d'accès personnel (PAT)** avec scope `repo`
  (`git clone https://<TOKEN>@github.com/dewiweb/nextevents.git`),
  soit une **clé de déploiement SSH** ajoutée au dépôt
  (Settings → Deploy keys → lecture seule suffit).

- Une des destinations suivantes :
  - partage **SMB sur le poste OBS** (Windows : clic droit sur le
    dossier → Propriétés → Partage) ou sur le **NAS**
  - **FTP** actif sur le NAS
  - ou le NAS **monté directement** sur le serveur (voir plus bas)

## 1. Build & lancement

```bash
docker build -t nextevents .

docker run -d --name nextevents --restart unless-stopped \
  -p 8080:8080 \
  -v nextevents-data:/data \
  nextevents
```

L'UI est alors accessible sur `http://<serveur>:8080`.

> `-v nextevents-data:/data` crée un volume Docker nommé : les diapos
> locales et `settings.json` y sont persistés. Pour utiliser un dossier
> du serveur ou un montage NAS à la place :
> `-v /mnt/nas/diaporama:/data`

## 2. Configuration dans l'UI

Ouvrir `http://<serveur>:8080` puis :

1. Cliquer **Générer maintenant** pour vérifier que tout fonctionne
   (suivre le journal en bas de page)
2. Renseigner la destination :
   - **SMB** : IP/hostname du poste OBS ou du NAS, nom du partage,
     sous-dossier optionnel, `DOMAINE\user` ou `user`, mot de passe
   - **FTP** : hôte, port (21), chemin distant, identifiants, FTPS
   - Cliquer **Tester la connexion**, puis **Enregistrer**
   - Les deux peuvent être actifs en même temps ; champ hôte vide =
     envoi désactivé
3. Régler **Rafraîchissement auto** (ex. `24` = regénère chaque jour)
   ou laisser à `0` pour du manuel uniquement

À chaque génération : les anciennes diapos sont supprimées et remplacées,
en local **et** sur FTP/SMB.

## 3. Côté poste OBS

**Option A — partage sur le poste OBS (Windows)** : partager un dossier
(ex. `C:\diaporama`) en lecture/écriture pour le compte configuré dans
l'UI. L'app écrit directement dedans.

**Option B — NAS intermédiaire** : l'app pousse sur le NAS (FTP ou SMB) ;
le poste OBS monte ce partage en lecteur réseau.

Dans OBS : source **Diaporama** → pointer sur le dossier (lecteur réseau
ou chemin local) → régler l'intervalle et la transition. OBS recharge
automatiquement le dossier quand les fichiers changent.

## 4. Alternative : NAS monté sur le serveur

Si vous préférez éviter FTP/SMB applicatif, monter le partage NAS sur le
serveur Debian :

```fstab
# /etc/fstab — exemple CIFS
//NAS/diaporama  /mnt/nas/diaporama  cifs  credentials=/root/.nas-creds,iocharset=utf8,uid=1000,gid=1000  0  0
```

```bash
mkdir -p /mnt/nas/diaporama
echo 'username=obs
password=xxx' > /root/.nas-creds && chmod 600 /root/.nas-creds
mount -a
docker run -d ... -v /mnt/nas/diaporama:/data nextevents
```

Avec cette option, laissez les sections FTP/SMB de l'UI vides : l'app
écrit directement dans `/data`.

## 5. Maintenance

```bash
docker logs -f nextevents          # journal du container
docker exec nextevents python generate_slides.py --out /data   # run manuel
docker restart nextevents          # redémarrage
```

**Mise à jour de l'app** après modification du code :

```bash
cd nextevents && git pull \
  && docker build -t nextevents . \
  && docker rm -f nextevents \
  && docker run -d --name nextevents --restart unless-stopped \
       -p 8080:8080 -v nextevents-data:/data nextevents
```

Les réglages (`settings.json` dans `/data`) sont conservés.

## Dépannage

| Symptôme | Piste |
|---|---|
| Diapos sans texte / polices par défaut | le container n'a pas pu télécharger les fontes (accès Internet requis au 1er run) |
| `connexion OK` échoue en SMB | partage inaccessible : firewall Windows (port 445), droits du compte, SMB1 désactivé (OK : smbprotocol fait du SMB2/3) |
| Test FTP échoue | port 21 bloqué, ou le NAS exige FTPS → cocher la case |
| UI inaccessible | `docker ps`, `docker logs nextevents`, port 8080 déjà pris → changer `-p 9080:8080` |
| OBS ne voit pas les nouvelles diapos | vérifier que le lecteur réseau est monté et pointe sur le bon dossier |

## Checklist réseau (déploiement par une équipe SI)

Tout ce dont le container a besoin, à faire valider/ouvrir :

| Besoin | Détail |
|---|---|
| **Sortie HTTPS (443)** | `www.leschampslibres.fr` (programme + fontes), `openagenda.com` et `img.openagenda.com` (images HD) |
| **Sortie SMB (445)** ou **FTP (21)** | vers le poste OBS ou le NAS de destination — si utilisé |
| **Port UI (8080)** | entrant, à restreindre au réseau régie/admin (pas d'authentification) |
| **Volume persistant** | `/data` : diapos + `settings.json` (réglages, identifiants SMB/FTP **en clair** — protéger l'accès au volume) |
| **Ressources** | ~1 vCPU, 1–2 Go RAM (rendu Chromium), ~2 Go disque (image + diapos + cache) |
| **Timezone** | `-e TZ=Europe/Paris` sur le `docker run` — sinon le planificateur auto tourne en UTC |
| **DNS** | résolution des noms ci-dessus |

Le container n'a besoin d'**aucun** port entrant autre que l'UI et
d'aucun accès à Internet en dehors des domaines listés. Sans sortie
SMB/FTP, l'app fonctionne quand même : les diapos sont alors récupérées
via `GET /api/download` (zip) ou montage du volume `/data` sur la
destination.
