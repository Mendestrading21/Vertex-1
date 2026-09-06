# VERTEX_RUNBOOK — démarrage, arrêt, diagnostic, reprise, retour arrière

Valable pour la branche `ui/refonte-dashboards` (mission alimentation du
2026-09-06) sur Windows 11 avec Python 3.12 dans `.venv`. Aucun secret ici :
les valeurs vivent dans `.env` (gitignoré).

## 1. Démarrer

### Instance de travail (IBKR en direct, lecture seule)

Prérequis : TWS ouvert, API activée, **Read-Only API coché**, 127.0.0.1 en IP
de confiance (port 7496 réel, 7497 papier). `.env` avec `VERTEX_CODE` et
`VERTEX_SECRET`.

```bash
cd "C:\Users\<toi>\OneDrive\Desktop\Vertex 1" && .venv\Scripts\python.exe -m vertex
```

Ou double-clic `Lancer_VERTEX.bat` (crée `.venv` et installe
`requirements.txt` au premier lancement). Le navigateur s'ouvre sur
http://localhost:5002 ; le code d'accès est `VERTEX_CODE`.

Ce que le démarrage fait : boucles de fond (scan 30 min, options 120 s, news
60 s, calendrier 3 h, fondamentaux 6 h, edge 6 h, hebdo 5 min, alertes 60 s,
**références macro officielles 6 h**), workers IBKR (cotations, indices,
chaînes, radar) ouverts par la **session marché seulement**
(`vertex/data_sources/ibkr_session.py`) : poignée de main puis verrouillage,
aucune lecture de compte, positions, ordres ni exécutions.

### Instance de vérification (sans IBKR, sans code)

```bash
.venv\Scripts\python.exe tools\qa\run_qa_instance.py --port 5003
```

Copie le dépôt dans `%TEMP%\vertex-qa`, `NO_IBKR=1`, `DEMO=0`, écoute
127.0.0.1 seulement. Données différées yfinance ; sert aux captures et à la
console sans toucher aux caches de l'instance de travail.

### Démarrage automatique à l'ouverture de session

`Installer_Demarrage_Auto.bat` installe `_vertex_autostart.cmd` dans le
dossier Démarrage de Windows. Prérequis opérationnels non gérés par Vertex :
TWS doit être lancé et connecté avant (sinon Vertex démarre en différé et se
reconnecte quand TWS répond) ; l'ordinateur ne doit pas se mettre en veille
(réglage Windows, hors périmètre de Vertex).

## 2. Arrêter

- Fenêtre console : `Ctrl+C` (arrêt propre : les threads sont des démons, les
  caches JSON sont écrits à chaque publication, rien à finaliser).
- Depuis le navigateur intégré : `preview_stop`.
- Ne jamais fermer TWS pour arrêter Vertex : TWS est partagé avec l'humain.

## 3. Diagnostiquer

| Question | Où regarder |
|---|---|
| L'application répond ? | `GET /healthz` (200, `status: ok`, `read_only: true`) ; `GET /readyz` (vérifications passées) |
| IBKR connecté et vivant ? | Système › Connexions (preuve socket, `ibkr_connected` / `ibkr_live` posés par `vertex/app/ibkr_state.py` sur tick récent < 75 s) ; `/api/live/status` (`mode` = `live` seulement sur preuve) |
| Les boucles tournent ? | Système › Jobs (`/api/system/automations`) : ACTIF / ERREUR / SILENCIEUX (muet > 2 × cadence) / NON_IMPLEMENTE / EN_ATTENTE |
| Les références macro sont-elles publiées ? | `GET /api/macro/officiel` : `disponibles/total`, `as_of`, `etat.derniere_erreur` ; carte Marchés › Macro › Références officielles |
| Fraîcheur d'une carte | pied de carte : `Il y a N min · source · Différé/Live` ; « Âge inconnu » signifie que la route n'a pas fourni d'époque (jamais l'heure du navigateur) |
| Erreurs navigateur | console + `POST /api/client-log` (journal serveur) |
| Journal serveur | sortie console de `python -m vertex` (le bruit `ib_async` est condensé par `ibkr_link.calmer_le_journal_du_courtier`) |
| Frontière IBKR | `.venv\Scripts\python.exe .claude\skills\vertex-2-0\scripts\check_ibkr_boundary.py --enforce` ; `pytest tests\test_ibkr_session_marche_seule.py` ; preuve sur socket réelle : `VERTEX_TEST_IBKR_LIVE=1 pytest tests\test_ibkr_session_marche_seule.py -k vraie_socket` |

## 4. Reprendre après incident

- **TWS fermé puis rouvert** : les workers réessaient les ports partagés
  (`ibkr_link.ordre_des_ports`) ; le port qui répond est mémorisé et oublié
  dès qu'il cesse de répondre. Aucune action.
- **Réseau coupé** : le scan garde le dernier instantané (`radar_cache.json`,
  `macro_cache.json`, `options_cache.json`, `cal_cache.json`,
  `macro_officiel_cache.json`) et les cartes affichent l'âge réel ; le
  collecteur macro reprend avec un délai croissant (5 min × 2ⁿ, plafonné à la
  cadence).
- **Redémarrage de l'ordinateur** : relancer TWS puis Vertex (ou démarrage
  automatique). Les caches sont réhydratés ; le calendrier recalcule `dte` à
  la lecture ; les trous non récupérables (par exemple un scan manqué)
  restent visibles comme âge.
- **Quota fournisseur (yfinance 429, IBKR pacing)** : les boucles ralentissent
  d'elles-mêmes (`refus_fournisseur`, backoff) ; ne pas relancer en boucle.

## 5. Revenir en arrière

Chaque tranche de la mission est un commit revertible sur
`ui/refonte-dashboards` :

| Tranche | Commit | `git revert` isolé possible |
|---|---|---|
| Session IBKR marché seulement | `dfa0247f` | oui (les six sites reprennent `IB.connect` — à éviter : réintroduit la synchronisation de compte) |
| Références macro officielles | `426c5184` | oui (retire le job, la route et la carte) |
| Étiquettes « live » et Simulateur sans IV inventée | `31305b70` | oui |
| Fraîcheur servie (scan_ts_h, régime, calendrier, `Date.now()`) | `f8d6f150` | oui |
| Honnêteté (verdict hors scan, confirmation du calendrier, entonnoir, hôtes de la fiche) | `240d23b7` | oui (touche `vertex/static` : re-bump requis, voir ci-dessous) |
| Risque du panier sur les positions déclarées | `08e0a79a` | oui |
| Réseau hors requête (analystes, cotations, marque de contrat) | `816e6f73` | oui |
| Chaîne d'options hors requête | `0b293dc5` | oui (touche `vertex/static` : re-bump requis) |
| Composants alimentés (« Ce qui a changé », équité, contribution) | `abd7df10` | oui |
| Verdict de structure côté serveur | `d2722b4c` | oui (touche `vertex/static` : re-bump requis) |
| Cerveau Claude réconcilié, contrat du lot décision | `9327ee42` | oui |
| `/api/company` et `/api/correlations` hors requête | `13b063e0` | oui |

Après un revert touchant `vertex/static`, bumper `td-shell-vN`
(`vertex/app/routes/system.py`), `SHELL_VERSION` (`vertex/ui/shell/__init__.py`)
et rafraîchir `tests/test_sw_cache_scope.py` (empreinte), sinon les
navigateurs gardent l'ancien bundle immuable.

## 6. Validation minimale avant toute livraison

```bash
.venv\Scripts\python.exe -m compileall -q terminal.py vertex
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m pytest tests\test_no_orders.py -q
.venv\Scripts\python.exe .claude\skills\vertex-2-0\scripts\check_ibkr_boundary.py --enforce
```

Une suite verte ne remplace ni la preuve navigateur (captures 1600 / 1280 /
1024 / 390 px, console et `/api/client-log` propres), ni la preuve de
données (source, date, fraîcheur visibles), ni l'acceptation humaine.
