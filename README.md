[🇫🇷 Version française](#version-française) | [🇬🇧 English version](#english-version)

---

# Version Française

# Trello Board Init 🗂️

Importe automatiquement une todo list au format Markdown dans un board Trello, en créant le board, les listes, les labels et les cartes via l'API Trello.

---

## Fonctionnalités

- Création automatique du board et des 4 listes par défaut (`📥 Backlog`, `📅 Cette semaine`, `🔄 En cours`, `✅ Done`)
- Création des labels avec couleurs (explicites ou assignées automatiquement depuis la palette Trello)
- Toutes les cartes sont créées dans `📥 Backlog`
- Dry-run automatique avant toute action réelle, avec confirmation interactive
- Vérification de cohérence des labels (auto-correction du fichier si un label manque dans le header)
- Idempotence : bloque si des cartes existent déjà dans le Backlog
- Suppression des labels vides créés par défaut par Trello sur les nouveaux boards
- Logging horodaté dans `logs/`
- Support d'un board existant via `--board-id`

---

## Installation

**Prérequis** : Python 3.9+

```bash
# Cloner le projet
git clone https://github.com/ton-user/trelloBoardInit.git
cd trelloBoardInit

# Créer et activer un environnement virtuel
uv venv --python 3.9
source .venv/bin/activate

# Installer les dépendances
uv pip install -r requirements.txt
```

---

## Configuration

Créer un fichier `.env` à la racine du projet (ne jamais le committer) :

```bash
TRELLO_API_KEY=ta_clé_api
TRELLO_TOKEN=ton_token
```

**Obtenir les credentials Trello :**

1. Clé API : https://trello.com/app-key
2. Token : générer depuis l'URL suivante (remplacer `{TA_API_KEY}`) :

```
https://trello.com/1/authorize?expiration=never&scope=read,write&response_type=token&key={TA_API_KEY}
```

Un fichier `.env.example` est fourni comme modèle :
```bash
cp .env.example .env
```

---

## Format du fichier Markdown

Le fichier est composé d'un **header global** suivi des **cartes individuelles**, chacune séparée par un bloc YAML front matter.

### Header global

```yaml
---
board: Nom du Board
labels:
  - backend                  # couleur assignée automatiquement
  - name: urgent             # couleur assignée automatiquement
  - name: design
    color: purple            # couleur explicite
---
```

**Couleurs disponibles :**
`green` `yellow` `orange` `red` `purple` `blue` `sky` `lime` `pink` `black`

### Cartes

```markdown
---
title: Titre de la carte
labels: [backend, urgent]
---
Description longue et libre en Markdown.

On peut écrire des listes, du **gras**, des liens, des blocs de code, etc.
```

### Exemple complet

```markdown
---
board: Mon Projet
labels:
  - name: backend
    color: blue
  - name: urgent
    color: red
  - frontend
---

---
title: Mettre en place l'authentification
labels: [backend, urgent]
---
Implémenter le système de login/logout avec JWT.

- Endpoint `/auth/login`
- Endpoint `/auth/logout`

---
title: Créer la page d'accueil
labels: [frontend]
---
Concevoir et développer la landing page principale.
```

---

## Utilisation

```bash
# Dry-run uniquement (validation sans rien créer)
python tbi.py tasks.md --dry-run

# Dry-run automatique puis confirmation interactive
python tbi.py tasks.md

# Dry-run automatique puis lancement sans confirmation
python tbi.py tasks.md --force

# Cibler un board existant plutôt qu'en créer un nouveau
python tbi.py tasks.md --board-id ABC123XYZ
```

---

## Déroulement du script

Le script s'exécute toujours en **4 passes**, précédées d'un dry-run automatique :

| Passe | Action |
|-------|--------|
| 0 — Validation | Parsing du fichier, cohérence des labels, détection de doublons |
| 1 — Board | Création ou réutilisation du board + listes par défaut |
| 1.5 — Nettoyage | Suppression des labels vides Trello (board neuf uniquement) |
| 2 — Labels | Création des labels manquants avec leurs couleurs |
| 3 — Cartes | Création des cartes dans `📥 Backlog` avec leurs labels |

---

## Logs

Un fichier de log horodaté est créé dans `logs/` à chaque exécution :

```
logs/tbi_20260303_143000.log
```

Exemple de sortie :

```
2026-03-03 14:30:01  INFO     >>> Running dry-run first...
2026-03-03 14:30:01  INFO     Passe 0 — Parsing & validation
2026-03-03 14:30:01  INFO        Board   : Mon Projet
2026-03-03 14:30:01  INFO        Labels  : ['backend', 'urgent', 'frontend']
2026-03-03 14:30:01  INFO        Cards   : 12 found
2026-03-03 14:30:01  INFO     ✅ Label coherence OK
2026-03-03 14:30:01  INFO     ✅ No duplicate card titles in file.
...
2026-03-03 14:30:04  INFO     ============================================================
2026-03-03 14:30:04  INFO     RÉSUMÉ
2026-03-03 14:30:04  INFO       Board             : created
2026-03-03 14:30:04  INFO       Labels créés      : 3
2026-03-03 14:30:04  INFO       Cartes créées     : 12
2026-03-03 14:30:04  INFO       Erreurs           : 0
2026-03-03 14:30:04  INFO       Durée             : 4.21s
```

---

## Structure du projet

```
trelloBoardInit/
├── tbi.py                 # Script principal
├── requirements.txt       # Dépendances Python
├── .env.example           # Modèle de configuration
├── .env                   # Credentials (non versionné)
├── .gitignore
├── logs/                  # Fichiers de log (non versionnés)
└── src/                   # Répertoire recommandé pour vos fichiers .md
    └── example_tasks.md   # Fichier exemple (seul fichier src versionné)
```

Le dossier `src/` est la convention adoptée dans ce projet pour centraliser les fichiers `.md` à traiter. Il n'a aucune valeur fonctionnelle — le script accepte n'importe quel chemin en argument. Vous pouvez stocker vos fichiers ailleurs.

### `.gitignore` recommandé

```
.env
.venv/
logs/
__pycache__/
*.pyc
src/*
!src/example_tasks.md
```

---

## Dépendances

```
requests
pyyaml
python-dotenv
```

---

## Limites connues

- Toutes les cartes atterrissent dans `📥 Backlog` (pas de ciblage d'une autre liste depuis le `.md`)
- L'API Trello est limitée à 300 requêtes / 10 secondes — largement suffisant pour un usage normal
- Le plan gratuit Trello est limité à 10 boards actifs par workspace

---

## 📋 Licence

Ce projet est sous licence MIT - voir le fichier [LICENSE](LICENSE) pour plus de détails.

---
---

# English Version

# Trello Board Init 🗂️

Automatically imports a Markdown todo list into a Trello board, creating the board, lists, labels and cards via the Trello API.

---

## Features

- Automatic board creation with 4 default lists (`📥 Backlog`, `📅 This week`, `🔄 In progress`, `✅ Done`)
- Label creation with colors (explicit or auto-assigned from the Trello palette)
- All cards are created in `📥 Backlog`
- Automatic dry-run before any real action, with interactive confirmation
- Label coherence check (auto-fixes the file if a label is missing from the header)
- Idempotence: aborts if cards already exist in the Backlog
- Removes empty default labels created by Trello on new boards
- Timestamped logging in `logs/`
- Support for an existing board via `--board-id`

---

## Installation

**Requirements**: Python 3.9+

```bash
# Clone the project
git clone https://github.com/your-user/trelloBoardInit.git
cd trelloBoardInit

# Create and activate a virtual environment
uv venv --python 3.9
source .venv/bin/activate

# Install dependencies
uv pip install -r requirements.txt
```

---

## Configuration

Create a `.env` file at the project root (never commit this file):

```bash
TRELLO_API_KEY=your_api_key
TRELLO_TOKEN=your_token
```

**Getting Trello credentials:**

1. API Key: https://trello.com/app-key
2. Token: generate from the following URL (replace `{YOUR_API_KEY}`):

```
https://trello.com/1/authorize?expiration=never&scope=read,write&response_type=token&key={YOUR_API_KEY}
```

A `.env.example` file is provided as a template:
```bash
cp .env.example .env
```

---

## Markdown file format

The file consists of a **global header** followed by **individual cards**, each separated by a YAML front matter block.

### Global header

```yaml
---
board: My Board Name
labels:
  - backend                  # auto-assigned color
  - name: urgent             # auto-assigned color
  - name: design
    color: purple            # explicit color
---
```

**Available colors:**
`green` `yellow` `orange` `red` `purple` `blue` `sky` `lime` `pink` `black`

### Cards

```markdown
---
title: Card title
labels: [backend, urgent]
---
Free-form description in Markdown.

You can write lists, **bold text**, links, code blocks, etc.
```

### Full example

```markdown
---
board: My Project
labels:
  - name: backend
    color: blue
  - name: urgent
    color: red
  - frontend
---

---
title: Set up authentication
labels: [backend, urgent]
---
Implement JWT-based login/logout system.

- Endpoint `/auth/login`
- Endpoint `/auth/logout`

---
title: Create home page
labels: [frontend]
---
Design and develop the main landing page.
```

---

## Usage

```bash
# Dry-run only (validation without creating anything)
python tbi.py tasks.md --dry-run

# Automatic dry-run then interactive confirmation
python tbi.py tasks.md

# Automatic dry-run then run without confirmation
python tbi.py tasks.md --force

# Target an existing board instead of creating a new one
python tbi.py tasks.md --board-id ABC123XYZ
```

---

## How the script works

The script always runs in **4 passes**, preceded by an automatic dry-run:

| Pass | Action |
|------|--------|
| 0 — Validation | File parsing, label coherence check, duplicate detection |
| 1 — Board | Create or reuse board + default lists |
| 1.5 — Cleanup | Remove empty default Trello labels (new boards only) |
| 2 — Labels | Create missing labels with their colors |
| 3 — Cards | Create cards in `📥 Backlog` with their labels |

---

## Logs

A timestamped log file is created in `logs/` on each run:

```
logs/tbi_20260303_143000.log
```

Sample output:

```
2026-03-03 14:30:01  INFO     >>> Running dry-run first...
2026-03-03 14:30:01  INFO     Pass 0 — Parsing & validation
2026-03-03 14:30:01  INFO        Board   : My Project
2026-03-03 14:30:01  INFO        Labels  : ['backend', 'urgent', 'frontend']
2026-03-03 14:30:01  INFO        Cards   : 12 found
2026-03-03 14:30:01  INFO     ✅ Label coherence OK
2026-03-03 14:30:01  INFO     ✅ No duplicate card titles in file.
...
2026-03-03 14:30:04  INFO     ============================================================
2026-03-03 14:30:04  INFO     SUMMARY
2026-03-03 14:30:04  INFO       Board             : created
2026-03-03 14:30:04  INFO       Labels created    : 3
2026-03-03 14:30:04  INFO       Cards created     : 12
2026-03-03 14:30:04  INFO       Errors            : 0
2026-03-03 14:30:04  INFO       Duration          : 4.21s
```

---

## Project structure

```
trelloBoardInit/
├── tbi.py                 # Main script
├── requirements.txt       # Python dependencies
├── .env.example           # Configuration template
├── .env                   # Credentials (not versioned)
├── .gitignore
├── logs/                  # Log files (not versioned)
└── src/                   # Recommended directory for your .md files
    └── example_tasks.md   # Example file (the only versioned src file)
```

The `src/` directory is the convention used in this project to centralize `.md` files to be processed. It has no functional significance — the script accepts any path as an argument. You are free to store your files elsewhere.

### Recommended `.gitignore`

```
.env
.venv/
logs/
__pycache__/
*.pyc
src/*
!src/example_tasks.md
```

---

## Dependencies

```
requests
pyyaml
python-dotenv
```

---

## Known limitations

- All cards land in `📥 Backlog` (no per-card list targeting from the `.md`)
- Trello API is rate-limited to 300 requests / 10 seconds — well within limits for normal use
- The Trello free plan is limited to 10 active boards per workspace

---

## 📋 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.