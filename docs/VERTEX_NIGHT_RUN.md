# VERTEX_NIGHT_RUN — journal de la mission d'alimentation (nuit du 2026-09-05)

Branche : `ui/refonte-dashboards` (base `main` `ed363d67`). Aucun secret ici.

## 0. Passation de la mission précédente (refonte des dashboards)

- Terminée et vérifiée : suite complète `4322 passed, 179 skipped, 0 failed`,
  captures 1600/1280/1024/390 px, console propre. Suivi détaillé dans
  `docs/ui-refonte-vertex.md`.
- Préservée par trois commits ciblés (examinés fichier par fichier) :
  `209c972f` (skills consultatifs), `3053a3cc` (refonte UI Options + bases CSS
  restaurées), `90984dee` (tests, instance QA, suivi).
- Rien d'autre n'était modifié dans l'arbre de travail avant cette mission.

## 1. Environnement vérifié

- Dépôt : `Vertex-1` (origin GitHub), branche `ui/refonte-dashboards`.
- Windows 11, PowerShell/Git Bash, Python 3.12 dans `.venv`, Node portable
  hors dépôt pour les contrôles de syntaxe. Flask 3 + HTML rendu serveur + JS
  vanilla + CSS custom, `ib_async 2.1.0`, `yfinance`, `pandas`.
- Processus actifs au début : instance live `python -m vertex` (port 5002,
  IBKR réel en lecture seule, TWS 7496 ouvert), instance QA (port 5003,
  sans IBKR) arrêtée à la fin de la mission précédente.
- Accès réseau depuis cette machine (mesuré par requête HTTP) :
  FRED CSV public 200, FRED API sans clé 400 (clé requise), BCE data API 200,
  BNS data API 200, SEC EDGAR 403 sans User-Agent / 200 avec, Stooq : voir
  `vertex/data_sources/stooq.py` (format d'URL propre).
- `.env` ne contient que `VERTEX_CODE` et `VERTEX_SECRET` : pas de clé
  Anthropic, pas de `SEC_USER_AGENT` (la SEC exige un contact réel, à saisir
  par l'humain), pas de secret TradingView, pas de clé FRED.

## 2. Jalons

| # | Jalon | État | Preuve |
|---|---|---|---|
| A | Inventaire et état de référence (4 audits parallèles en lecture seule) | en cours | rapports fusionnés dans `VERTEX_DATA_COVERAGE.md`, `VERTEX_SOURCE_REGISTRY.md` |
| B | Choix des sources et architecture minimale | à faire | |
| C | Connecteur marché sécurisé (IBKR données seulement, requêtes prouvées) | en cours | `vertex/data_sources/ibkr_session.py`, tests |
| D | Première chaîne source → carte vérifiée | à faire | |
| E | Extension à l'inventaire | à faire | |
| F | Actualités, fondamentaux, macro (SEC, FRED, BCE, BNS) | à faire | |
| G | Diagnostics, performances, reprises | à faire | |
| H | Tests finaux et lancement local vérifié | à faire | |

## 3. Décisions

- D1. Pas de nouveau système d'orchestration (ni Docker, ni n8n, ni Prefect) :
  les boucles existantes de `terminal.py` + le registre `vertex/scheduler`
  + le diffuseur SSE `vertex/services/live_stream.py` sont réutilisés.
- D2. Frontière IBKR : `ib_async 2.1.0` émet `reqPositions` **sans condition**
  au connect, et `reqAccountUpdates`/`reqAccountUpdatesMulti`/`reqExecutions`
  selon `fetchFields` (défaut ALL). `readonly=True` n'y change rien. La
  connexion passe donc par une session « marché seulement » qui n'appelle que
  la couche client (handshake) et verrouille les méthodes de compte.

## 4. Checkpoint de reprise

- Dernier commit : voir `git log --oneline -1` ; état de l'arbre : `git status`.
- Reprendre au premier jalon « en cours » du tableau ci-dessus.
