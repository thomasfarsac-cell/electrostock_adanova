# ElectroStock

Application web legere pour gerer un stock d'articles de fablab ou d'association, leurs emplacements, leurs mouvements et leurs medias, avec import/export CSV et aide au pre-remplissage par IA.

## Stack
- FastAPI
- Jinja2
- SQLite
- SQLAlchemy
- Pillow
- qrcode
- reportlab
- openpyxl / xlrd / odfpy pour les imports tableur

## Fonctions principales
- gestion des articles avec reference, designation, famille, marque/fabricant, format/conditionnement, emplacement, notes et fiche technique
- historique des mouvements de stock par article
- champs personnalises
- gestion des categories en arborescence
- gestion des fabricants, boitiers et champs personnalises dans les referentiels
- vraie section `Emplacements` avec fiche dediee, photo optionnelle, QR et contenu de l'emplacement
- QR code pour articles et emplacements
- impression d'etiquettes PDF pour articles et emplacements
- scanner intelligent depuis la barre haute
- import articles via CSV, XLS, XLSX et ODS
- export CSV des articles et des mouvements
- sauvegarde complete en `.zip`
- restauration d'une sauvegarde en mode fusion ou remplacement
- pre-remplissage IA des fiches articles via l'API OpenAI

## Aide IA de fiche
La fiche article peut lancer une aide IA a partir d'une simple reference.

L'IA peut :
- proposer une designation plus complete
- proposer une description multi-ligne
- renseigner fabricant, boitier, categorie, mots-cles, datasheet et champs personnalises
- utiliser le web si l'option est activee

L'IA ne doit pas :
- choisir l'emplacement physique de stockage a la place de l'utilisateur

Si un boitier propose n'existe pas encore dans la base, il peut etre ajoute automatiquement.

## Page Parametres
La page `Parametres` permet de :
- gerer la cle API OpenAI
- modifier le prompt systeme de recherche IA
- enregistrer et rappeler des presets de prompt
- creer une archive de sauvegarde complete
- restaurer une archive existante

## Sauvegarde
La sauvegarde n'est pas une simple copie brute de `app.db`.

Le bouton de sauvegarde genere une archive `.zip` contenant :
- `db/` : un CSV par table SQL
- `settings/.env`
- `settings/app_env.csv`
- `settings/component_lookup_prompt_presets.json` si present
- `settings/auth_password.hash` si l'authentification est activee
- `media/images/...` pour les photos et miniatures
- `manifest.json`
- `README.txt`

Cette archive est pensee pour pouvoir :
- archiver proprement la base
- restaurer un etat complet
- completer une autre base plus tard

## Restauration
La restauration accepte une archive `.zip` generee par l'application.

Deux modes sont disponibles :
- `Completer / fusionner` : ajoute et fusionne les donnees de l'archive avec la base existante
- `Remplacer completement` : restaure l'etat complet de l'archive, y compris les medias et certains parametres

Conseil :
- commencer par tester `Completer / fusionner`
- garder `Remplacer completement` pour une vraie restauration d'etat

## Emplacements
La section `Emplacements` permet de :
- creer et modifier des emplacements
- ajouter une description plus riche
- ajouter une photo optionnelle
- afficher la liste des articles presents dans un emplacement
- afficher le QR de l'emplacement
- imprimer une etiquette QR pour coller sur une boite, un bac ou un tiroir

Si aucune photo n'est definie, rien n'est affiche a la place.

## QR et scan
L'application reconnait notamment :
- `C:123` pour un article
- `COMPONENT_ID:123`
- `L:12` pour un emplacement
- `LOCATION_ID:12`
- une reference exacte d'article
- un nom exact d'emplacement

## Import conseille
1. Exporter un CSV depuis la liste articles.
2. Ouvrir le fichier dans Excel ou LibreOffice.
3. Modifier ou completer les lignes.
4. Reimporter le fichier depuis `Imports`.
5. Mapper les colonnes si besoin.

## Lancement Docker
Depuis le dossier `electrostock` :

```bash
docker compose up -d --build
```

En dev, si tu utilises le compose dedie :

```bash
docker compose -f docker-compose_dev.yml up -d --build
```

Copier ensuite `.env.example` vers `.env` et renseigner au minimum `OPENAI_API_KEY` si tu veux activer l'aide IA sur les fiches articles.

Puis ouvrir :

```text
http://localhost:8036
```

En production, le fichier `docker-compose.yml` publie l'application via le
Traefik existant à l'adresse :

```text
https://stock.adanova83.org
```

Le domaine peut être remplacé avec la variable `APP_DOMAIN` si nécessaire.

## Variables utiles
Exemples de variables utilisees par l'application :
- `OPENAI_API_KEY`
- `OPENAI_COMPONENT_LOOKUP_MODEL`
- `OPENAI_COMPONENT_LOOKUP_USE_WEB_SEARCH`
- `OPENAI_COMPONENT_LOOKUP_TIMEOUT`
- `OPENAI_COMPONENT_LOOKUP_SYSTEM_PROMPT`
- `APP_DATA_DIR`
- `APP_DB_URL`
- `APP_DOMAIN`

## Donnees persistantes
Le dossier `/app/data` contient notamment :
- `app.db`
- les images articles
- les images emplacements
- les miniatures
- les imports temporaires
- les presets de prompt
- le hash de mot de passe si l'auth est activee

## Images
Les images envoyees sont redimensionnees et compressees automatiquement en WEBP pour rester legeres sur Raspberry Pi.

## Remarque
Si tu modifies la structure de la base ou les services de sauvegarde/restauration, pense a regenerer une nouvelle archive de test avant de valider le flux complet.
