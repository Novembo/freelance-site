# Site vitrine — Obed VODOUHE

[![CI](https://github.com/Novembo/freelance-site/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/Novembo/freelance-site/actions/workflows/ci.yml)
[![GitHub Pages](https://github.com/Novembo/freelance-site/actions/workflows/deploy-pages.yml/badge.svg?branch=main)](https://github.com/Novembo/freelance-site/actions/workflows/deploy-pages.yml)

Site vitrine freelance full-stack : interface en **HTML, CSS et JavaScript** (Vue 3 et Bootstrap, sans compilation) et API REST en **Python** (FastAPI, SQLite). Le projet couvre les demandes de devis, les commandes, les témoignages et l’intégration Kkiapay, avec vérification des transactions côté serveur.

Ce projet est pensé pour montrer trois choses :
- que je conçois et livre des API backend fiables,
- que je peux intégrer une maquette ou un cahier des charges en interface web / mobile,
- que je travaille avec une logique de livraison plus proche d’un service client professionnel que d’une simple démo technique.

- **Langages :** HTML · CSS · JavaScript · Python
- **Technologies :** Vue 3 · Bootstrap · FastAPI · SQLite · Kkiapay · pytest · Docker · GitHub Actions

## Démo déployée

- **Site :** [novembo.github.io/freelance-site](https://novembo.github.io/freelance-site/)
- **API :** [freelance-site-api.onrender.com](https://freelance-site-api.onrender.com/docs)
- **Vérification API :** [`GET /api/testimonials`](https://freelance-site-api.onrender.com/api/testimonials)

GitHub Pages injecte l’URL de l’API via la variable Actions `API_BASE`; l’API autorise l’origine du site dans `ALLOWED_ORIGINS`. La configuration Render actuelle utilise Kkiapay en mode sandbox et SQLite : cette démo n’est pas destinée à recevoir de vrais paiements ni des commandes à conserver.

GitHub Pages est l’hébergement principal du frontend statique. Le service Render sert l’API et, actuellement, sert aussi le même fichier `public/index.html` à la racine (`/`). Ce doublon n’ajoute pas un second service Render — l’API reste nécessaire — mais duplique la livraison de la page. Pour un hébergement strictement séparé, Pages peut rester le frontend unique et Render être limité à l’API.

## Pourquoi ce projet est crédible

- processus de commande et de paiement vérifié côté serveur,
- logique de 70 % à la réservation et 30 % à la livraison,
- flux de devis sur mesure avec validation manuelle,
- messages de contact et témoignages gérés par l’API,
- structure orientée “client + livraison + preuve de qualité”.

## Méthodologie de travail

1. Diagnostic du besoin et des contraintes.
2. Proposition d’architecture claire, coûts et livrables.
3. Développement avec tests, validation et sécurisation.
4. Livraison, suivi et correction des défauts identifiés.

Ce projet sert donc à présenter une vraie logique de service numérique : clarifier, sécuriser, livrer, puis soutenir le client après mise en production.

## Structure

```
├── public/
│   └── index.html            → le site (seul dossier servi au public)
├── backend/
│   ├── main.py               → API FastAPI (contact, commandes, devis, témoignages, paiement, facture, admin)
│   ├── database.py           → base SQLite (contacts, orders, testimonials)
│   ├── requirements.txt
│   └── .env.example          → variables d'environnement à renseigner
├── tests/                    → 17 tests pytest (commandes, paiement, sécurité)
├── .github/workflows/
│   ├── ci.yml                → lance les tests à chaque push
│   └── deploy-pages.yml      → publie public/index.html sur GitHub Pages
├── Dockerfile
├── requirements-dev.txt      → dépendances + pytest
└── README.md
```

## 1. Voir le site sans backend

Ouvre `public/index.html` dans ton navigateur. Services, tarifs et animations fonctionnent ; contact, commandes, témoignages et paiement nécessitent le backend.

## 2. Lancer en local

### Windows (PowerShell)

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
Copy-Item backend\.env.example backend\.env
Set-Location backend
python -m uvicorn main:app --reload
```

### Linux / macOS (Bash)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp backend/.env.example backend/.env     # puis renseigne ADMIN_TOKEN au minimum
cd backend
python -m uvicorn main:app --reload
```

Ouvre http://127.0.0.1:8000/ — le backend sert le site (`public/`) et l'API ensemble, et crée `backend/data/site.db` au premier lancement. La documentation interactive de l'API est sur http://127.0.0.1:8000/docs.

## 3. Tests

Depuis la racine du dépôt (après avoir démarré ou arrêté le serveur local) :

```bash
python -m pytest -q
```

Les tests couvrent : calcul de l'acompte côté serveur, refus des prix envoyés par le client, flux devis sur mesure, modération des témoignages, vérification du paiement (montant, rejeu de transaction, nouvelle tentative), jeton admin, CORS, échappement HTML de la facture, et absence de fuite de fichiers privés (`.env`, base, code source).

## CI/CD

`ci.yml` exécute les tests Python sur chaque push et pull request. `deploy-pages.yml` publie `public/index.html` sur GitHub Pages après un push sur `main`; il remplace `__API_BASE__` avec la variable Actions `API_BASE`. Le backend reste déployé séparément sur Render. Vérifie que cette variable et `ALLOWED_ORIGINS` correspondent aux URL de production après tout changement de domaine.

## 4. Paiement — acompte de 70 %

Toute commande suit la même règle : **70 % du total à la réservation, le solde (30 %) à la livraison.**

1. Le client choisit un forfait → il saisit son nom et son email.
2. Le frontend crée une **commande** (`POST /api/orders`, statut `pending`) ; l'acompte est calculé côté serveur.
3. Le widget Kkiapay s'ouvre pour le montant de l'acompte.
4. Après paiement, le frontend appelle `POST /api/kkiapay/confirm`.
5. **Le serveur revérifie la transaction auprès de Kkiapay** avec la clé privée et compare le montant à l'acompte attendu. Une même transaction ne peut valider qu'**une seule** commande (index unique + contrôle, `409` sinon). Seule cette vérification fait passer la commande à `deposit_paid`.

## 5. Projets sur mesure, facture, administration

- **Devis :** `POST /api/quote-request` crée une commande `awaiting_price`. Tu fixes le prix :
  ```bash
  curl -X POST https://TON-API/api/admin/orders/42/set-price \
    -H "X-Admin-Token: $ADMIN_TOKEN" -H "Content-Type: application/json" \
    -d '{"total_amount": 500000}'
  ```
  Puis envoie au client `https://TON-SITE/?order=SA_REFERENCE`.
- **Facture :** `GET /invoice/<référence>` dès que l'acompte est confirmé (page imprimable en PDF).
  `POST /api/admin/orders/42/complete` attribue le numéro définitif (`FAC-2026-0001`).
- **Témoignages :** `GET /api/admin/testimonials`, puis `POST /api/admin/testimonials/<id>/approve`.

Tous les endpoints `/api/admin/...` exigent l'en-tête `X-Admin-Token`.

## 6. Configuration (variables d'environnement)

| Variable | Rôle |
|----------|------|
| `KKIAPAY_PUBLIC_KEY`, `KKIAPAY_PRIVATE_KEY`, `KKIAPAY_SECRET_KEY` | clés de https://app.kkiapay.me/dashboard (menu Développeurs) |
| `KKIAPAY_SANDBOX` | `true` pour tester, `false` en production |
| `ADMIN_TOKEN` | secret des endpoints admin (`python -c "import secrets; print(secrets.token_urlsafe(32))"`) |
| `ALLOWED_ORIGINS` | URL(s) du site autorisées à appeler l'API, ex. `https://TON-COMPTE.github.io` |
| `DB_PATH` | emplacement de la base SQLite (volume persistant en production) |

Avant la mise en production réelle, dans `public/index.html` : remplace `REMPLACE_PAR_TA_CLE_PUBLIQUE_KKIAPAY` par ta clé publique et passe `sandbox: true` à `false`. Ajuste aussi les tarifs (`plans` dans `index.html`, `PRICING` dans `backend/main.py`).

## 7. Déploiement

### Backend (Render, Railway…)

**Important :** SQLite est un fichier. Sur un disque éphémère (plan gratuit sans volume), **les commandes peuvent être perdues lors d’un redéploiement**. Monte un volume/disque persistant (ex. `/data`) et définis `DB_PATH=/data/site.db` avant tout usage réel. La configuration de démo actuelle garde Kkiapay en sandbox; ne l’utilise pas pour accepter de vrais paiements.

Sur Render (Web Service lié au dépôt GitHub), au choix :
- **Runtime Docker :** Render utilise le `Dockerfile` du dépôt.
- **Runtime Python :** *Build* `pip install -r backend/requirements.txt` — *Start* `cd backend && uvicorn main:app --host 0.0.0.0 --port $PORT`.

Renseigne ensuite les variables du §6 (`ALLOWED_ORIGINS` = l'URL de ton site GitHub Pages) et teste `https://TON-SERVICE.onrender.com/docs`. Le plan gratuit s'endort après inactivité : le premier appel peut prendre environ une minute.

### Avec Docker

```bash
docker build -t site-obed .
docker run -p 8000:8000 -v site-data:/data \
  -e ADMIN_TOKEN=... -e KKIAPAY_SANDBOX=true site-obed
```

### Frontend (GitHub Pages)

GitHub Pages est configuré pour publier avec GitHub Actions. La variable de dépôt `API_BASE` pointe actuellement vers `https://freelance-site-api.onrender.com`; le workflow remplace `__API_BASE__` dans la page et publie le site à chaque push sur `main`. Si l'URL de l'API change, mettez à jour cette variable dans **Settings → Secrets and variables → Actions → Variables**.

### Première publication sur GitHub

```bash
git init
git add .
git status          # vérifie qu'aucun .env ni *.db n'apparaît
git commit -m "Premier envoi du site"
git branch -M main
git remote add origin https://github.com/TON-COMPTE/TON-DEPOT.git
git push -u origin main
```

Si une clé secrète a déjà été commitée par erreur, **régénère-la** : la supprimer du dépôt ne suffit pas.

## 8. Choix volontairement simples

- SQLite plutôt qu'un serveur de base de données séparé.
- Un jeton partagé (`ADMIN_TOKEN`) plutôt qu'un système de comptes admin : l'authentification JWT/RBAC est démontrée dans un projet séparé.
- Services et tarifs dupliqués (frontend + backend) pour que le site s'affiche même si le backend est indisponible.

## 9. Améliorations possibles

- Interface admin graphique (prix, témoignages)
- Notification email à chaque message, commande ou devis
- Limitation du débit (rate limiting) sur les formulaires publics
- Migration vers PostgreSQL
