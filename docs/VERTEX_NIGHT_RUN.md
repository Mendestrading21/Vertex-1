# VERTEX_NIGHT_RUN — journal de la mission d'alimentation (nuit du 2026-09-05 → 06)

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
  IBKR réel en lecture seule, TWS 7496 ouvert) ; instance QA (port 5003, sans
  IBKR) relancée à la demande pour les vérifications navigateur.
- Accès réseau mesurés par requête HTTP : FRED CSV public 200, FRED API sans
  clé 400 (clé requise), BCE data API 200, BNS data API 200, SEC EDGAR 403
  sans User-Agent / 200 avec.
- `.env` ne contient que `VERTEX_CODE` et `VERTEX_SECRET` : pas de clé
  Anthropic, pas de `SEC_USER_AGENT` (la SEC exige un contact réel, à saisir
  par l'humain), pas de secret TradingView, pas de clé FRED.

## 2. Jalons

| # | Jalon | État | Preuve |
|---|---|---|---|
| A | Inventaire et état de référence | **fait** | 3 audits parallèles en lecture seule (pages Piloter/Explorer, pages Gérer/Options/IA/Système, sources + frontière IBKR) ; le 4ᵉ (circuit temps réel) a été interrompu par la limite d'usage et remplacé par une lecture directe (SSE 4 émetteurs, `VX.refresh` par page, registre des jobs). Résultats : `VERTEX_DATA_COVERAGE.md`, `VERTEX_SOURCE_REGISTRY.md` |
| B | Choix des sources et architecture minimale | **fait** | D1–D3 ci-dessous ; aucun nouveau système d'orchestration |
| C | Connecteur marché sécurisé (IBKR données seulement, requêtes prouvées) | **fait** | `dfa0247f` — `vertex/data_sources/ibkr_session.py`, 6 sites migrés, doublure + gardien statique + **preuve sur socket réelle TWS** (`VERTEX_TEST_IBKR_LIVE=1`, rôle `verification`, id 29 : aucune position ni valeur de compte détenue) |
| D | Première chaîne source → carte vérifiée | **fait** | `426c5184` — FRED/BCE/BNS → collecteur 6 h → `/api/macro/officiel` → carte Marchés › Macro « Références officielles », 11/11 séries publiées, vérifiée dans le navigateur, collecte réelle testée (`VERTEX_TEST_RESEAU=1`) |
| E | Extension à l'inventaire | **partiel** | étiquettes « live » sur preuve de socket (`31305b70`), fraîcheur servie sur 9 pages (`f8d6f150`), calendrier daté et étiqueté ; le reste est consigné dans `VERTEX_DATA_COVERAGE.md` §13 avec priorités |
| F | Actualités, fondamentaux, macro | **partiel** | macro officielle faite ; SEC bloquée par la configuration (contact humain) ; actualités et fondamentaux inchangés (chaînes existantes documentées) |
| G | Diagnostics, performances, reprises | **partiel** | registre des jobs (nouveau job avec battement, états ACTIF/SILENCIEUX), reprise espacée du collecteur, cache persisté ; runbook `VERTEX_RUNBOOK.md` |
| H | Tests finaux et lancement local vérifié | **fait** | suite complète relancée après chaque tranche (voir §5) ; relance de l'instance de travail avec le code de la nuit + observation de stabilité (voir `VERTEX_FINAL_REPORT.md`) |

## 3. Décisions

- D1. Pas de nouveau système d'orchestration (ni Docker, ni n8n, ni Prefect) :
  les boucles existantes de `terminal.py` + le registre `vertex/scheduler`
  + le diffuseur SSE `vertex/services/live_stream.py` sont réutilisés ; le
  nouveau collecteur vit dans le paquet et n'ajoute qu'une ligne de démarrage
  au monolithe.
- D2. Frontière IBKR : `ib_async 2.1.0` émet `reqPositions` **sans condition**
  au connect, et `reqAccountUpdates`/`reqAccountUpdatesMulti`/`reqExecutions`
  selon `fetchFields` (défaut ALL). `readonly=True` n'y change rien. La
  connexion passe par une session « marché seulement » (poignée de main au
  niveau client) verrouillée par **liste blanche** : tout ce qui n'est pas
  une méthode de marché lève avant toute requête. `ib_async` n'est pas épinglé
  à une version exacte dans `requirements.txt` (`>=1.0`) : à décider par
  l'humain (le comportement au connect dépend de la version).
- D3. Sources macro : FRED par CSV public (pas de clé), BCE et BNS sans clé ;
  fréquence déclarée par série, dates de la source, jamais « live ».
- D4. « Live » n'est écrit que sur preuve de socket (`ibkr_live` posé par
  `ibkr_state.sync`), plus sur la configuration.
- D5. Aucune donnée inventée pour compenser une absence : le Simulateur
  n'envoie plus d'IV constante ; PoP et Greeks deviennent absents.
- D6. L'heure du navigateur n'est jamais un âge de donnée : les routes datent
  (`scan_ts_h`, `as_of`, `ts`), le client transmet ou rend « Âge inconnu ».
- D7. Non traité cette nuit, consigné avec priorité : verdict `ATTENDRE`
  fabriqué hors scan et trois autorités de décision (programme lot décision) ;
  réseau dans les requêtes UI ; risque du panier ≠ portefeuille ; composants
  jamais alimentés ; SEC (contact humain requis).

## 4. Commits de la nuit (poussés sur la branche dédiée, PR brouillon #867, aucune fusion)

| SHA | Objet |
|---|---|
| `dfa0247f` | fix(ibkr) : session marché seulement, gardiens, preuve socket |
| `426c5184` | feat(macro) : FRED/BCE/BNS → carte Marchés, registre des sources, matrice de couverture |
| `31305b70` | fix(honnêteté) : live sur preuve de socket, Simulateur sans IV inventée |
| `f8d6f150` | fix(fraîcheur) : scan_ts_h, régime daté, calendrier daté, fin des `Date.now()` |
| `fda07e70` | chore(assets) : coque vx-shell-4, SW v291, cartes macro Marchés, runbook |
| `240d23b7` | fix(honnêteté) : aucun verdict fabriqué hors scan, confirmation du calendrier servie, entonnoir Marchés au vocabulaire du scan, hôtes morts de la fiche Analyse (coque vx-shell-5, SW v292) |
| `08e0a79a` | fix(risque) : le risque du panier mesure les positions déclarées (`POST /api/risk {symbols}`), Portefeuille et Opportunités branchés, titres non mesurables nommés |
| `816e6f73` | fix(réseau) : analystes servis du cache et collectés en fond, cotations sans attente de 12 s (worker en fond, `en_attente`), marque de contrat depuis le cache, blocs analystes de la fiche enfin visibles |
| `0b293dc5` | fix(réseau) : chaîne d'options hors requête (`chaine_a_la_demande.board_avec`, `en_cours`, pages Options avec réessai borné ; coque vx-shell-6, SW v293) |
| `abd7df10` | fix(composants) : « Ce qui a changé » sur /api/market/context (`changes_base`, `prev_as_of`), équité Portefeuille dérivée des clôtures déclarées, `plAbs` produit (contribution) |

## 5. Tests (résultats exacts)

| Moment | Résultat |
|---|---|
| Baseline (fin de la mission précédente) | `4322 passed, 179 skipped, 0 failed` |
| Après la session IBKR | `4376 passed, 180 skipped, 2 failed` → les 2 (population des `except: pass`) corrigés dans la même tranche |
| Après macro + honnêteté | `4385 passed, 181 skipped, 8 failed` → pins de versions, fingerprint, import orphelin, 3 tests fournisseur (passés au rejeu isolé) corrigés |
| Après fraîcheur | `4420 passed, 181 skipped, 2 failed` (fingerprint + import orphelin, corrigés dans `fda07e70`) |
| Final (après `e5c1a042`) | `4422 passed, 181 skipped, 0 failed` ; CI PR #867 : safety pass, test pass |
| Tranche honnêteté (`240d23b7`) | `4435 passed, 180 skipped, 0 failed` ; une garde « écartée » (`test_future_catalyst_is_not_backdated_on_last_historical_candle`) repasse au vert grâce à l'hôte restauré et sort du registre des gardes supplantées (131 au lieu de 132) |
| Tranche risque du panier (`08e0a79a`) | `4442 passed, 180 skipped, 0 failed` |
| Tranche réseau hors requête (`816e6f73`) | `4452 passed, 180 skipped, 0 failed` (gardien `test_pos_quotes` réaligné sur le contrat hors requête) |
| Tranche chaîne hors requête (`0b293dc5`) | `4455 passed, 180 skipped, 1 failed` (import orphelin) → corrigé avant le commit, gardien vert ; suite complète relancée après : `4456 passed, 180 skipped, 0 failed` |
| Tranche composants alimentés (`abd7df10`) | `4460 passed, 180 skipped, 0 failed` |

Preuves réelles hors suite : socket TWS (session marché seulement),
collecte FRED/BCE/BNS (11/11), carte Marchés dans le navigateur.

## 6. Checkpoint de reprise

- Dernier commit : `git log --oneline -1` ; arbre : `git status` (doit être
  propre hors caches gitignorés).
- Instance de travail : relancer `python -m vertex` avec TWS ouvert ; vérifier
  `/healthz` (`ibkr_live`), Système › Jobs (`MACRO_OFFICIEL_REFRESH` ACTIF
  après la première collecte), Marchés › Macro.
- Tranche « honnêteté » faite (`240d23b7`) : §13 #2 (partiel), #3, #9 (partiel),
  #12. Vérifié sur l'instance QA (port 5003, sans IBKR) : calendrier 120 j —
  badges « Confirmée » (Fed publiée), « Approx. » (règle BLS), « Non
  confirmée » (résultats, titre = texte du serveur) ; fiche `/analysis/ZZZZ`
  — rail « NON ÉVALUÉ · titre hors scan courant — aucun verdict calculé » ;
  fiche AAPL — « Raisonnement du comité » enfin rendu ; Marchés › Largeur —
  entonnoir 513 → 513 → 294 → 94 ; console sans erreur, 375 px sans
  débordement.
- Tranche « risque du panier » faite (`08e0a79a`) : §13 #7. Vérifié sur
  l'instance QA avec des positions de test (copie QA seulement) : Portefeuille ›
  Risque › Dépendances cachées « sur 3 titre(s) déclaré(s) · 1 non mesurable »,
  Opportunités › Positions × moteur › Risque du panier (diversification,
  corrélations, secteur, non mesurable, pied daté « positions déclarées »),
  console sans erreur.
- Tranche « réseau hors requête » faite (`816e6f73`) : §13 #8 partiel (analystes,
  cotations, marque de contrat), #9 partiel (blocs analystes). Vérifié sur
  l'instance QA : `/api/analyst/ORCL` EN_COURS en 4 ms, CACHE après la
  collecte de fond, fiche Analyse › Catalyseurs avec surprises, révisions et
  notes stables 12 s, console sans erreur.
- Tranche « chaîne hors requête » faite (`0b293dc5`) : §13 #8 clos pour les
  routes consommées par l'interface (restent `/api/correlations` et
  `/api/company`, sans consommateur UI). Vérifié sur l'instance QA :
  `/api/options/strategies/KHC` → `en_cours` en 356 ms, dossier Options KHC
  avec réessai (3 appels), console sans erreur.
- Tranche « composants alimentés » faite (`abd7df10`) : §13 #9 clos (reste
  `daily_changes`, hors interface). Vérifié sur l'instance QA : « Ce qui a
  changé » dans ses trois états (base absente → base posée → « rien de notable
  depuis … »), contribution au P&L rendue, équité honnêtement vide sans
  clôture, console sans erreur.
- Prochaine action si reprise : §13 #2 (trois autorités de décision, programme
  lot décision), puis #11 (SEC, action humaine).
