# Maintenance de l'alimentation en données

Procédures **réellement testées** lors de la mission d'alimentation des 5–6
septembre 2026 (branche `ui/refonte-dashboards`, journal
`docs/VERTEX_NIGHT_RUN.md`). Ce document est la procédure de référence pour
toute tranche qui touche une source, un collecteur, une route servant des
données ou une carte qui les affiche. Il impose l'inventaire des champs, la
traçabilité, la frontière IBKR et les tests ; il n'ajoute aucune autorité :
le skill maître reste seul.

## 1. Avant de toucher une source ou une carte

1. Lire la ligne de la matrice `docs/VERTEX_DATA_COVERAGE.md`
   (page → carte → champ → source → cadence → droits → état → preuve) ; si le
   champ n'y est pas, l'ajouter d'abord avec son état honnête (`RÉEL`,
   `PARTIEL`, `DÉGRADÉ`, `ABSENT`, `NON_IMPLÉMENTÉ`).
2. Lire la fiche du fournisseur dans `docs/VERTEX_SOURCE_REGISTRY.md` :
   accès, droits d'affichage et d'archivage, cadence, quotas, résultat du
   dernier test réel. Une connexion validée ne prouve pas que toutes ses
   données sont accessibles.
3. Mesurer le runtime avant d'écrire : route, état partagé (`scan_state`,
   `news_state`, caches JSON), consommateurs JS (`grep` des URL), tests qui
   épinglent le comportement (`tests/test_*` — chercher la route et la carte).

## 2. Contrat de traçabilité d'une valeur servie

Toute valeur importante servie par une route porte, quand la source le permet :
`value`, `unit`/`currency`, `source` (fournisseur nommé, jamais « live » par
configuration), `observed_at` ou `published_at` (date de la SOURCE),
`received_at` ou `ts` (époque serveur), `mode` (`live` seulement sur preuve
de socket, sinon `delayed` / `PERIODIQUE` / `manual` / `calculated`),
`quality`, `error` (la panne est une donnée) et l'état d'une absence
(`etat: EN_COURS | CACHE | PERIME | NON_EVALUE | MISSING`).

Règles vérifiées par gardiens :

- jamais un zéro pour une absence (`test_etiquettes_live_honnetes`,
  `test_fraicheur_honnete`) ;
- jamais l'heure du navigateur comme âge d'une donnée
  (`test_fraicheur_serveur` interdit `Date.now()` dans les cartes) ;
- « live » uniquement sur `scan_state['ibkr_live']` (tick récent < 75 s) ;
- aucun verdict fabriqué hors scan (`final_decision: null`, `NON_EVALUE`) ;
- une valeur calculée est calculée par le serveur, la page peint
  (`test_structure_verdict`, `test_risque_panier_declare`).

## 3. Frontière IBKR — données de marché seulement

- Toute connexion passe par `vertex/data_sources/ibkr_session.connecter`
  (poignée de main au niveau client puis verrouillage par liste blanche) ;
  jamais `IB.connect` (`ib_async` émet `reqPositions` au connect, quel que
  soit `readonly`).
- Gardiens : `tests/test_ibkr_session_marche_seule.py` (doublure : 47
  méthodes refusées, refus par défaut), `check_ibkr_boundary.py --enforce`,
  `tests/test_no_orders.py`, `tests/test_strategy_os_final_guards.py`.
- Preuve réelle, à refaire après toute mise à jour d'`ib_async` :
  `VERTEX_TEST_IBKR_LIVE=1 pytest tests/test_ibkr_session_marche_seule.py -k vraie_socket`
  (TWS ouvert, rôle `verification`, id client 29) — aucune position ni valeur
  de compte ne doit être détenue par la session.
- Ne jamais fermer la session TWS d'un autre programme ; identifiants clients
  dans `vertex/data_sources/ibkr_link.py`.

## 4. Réseau hors requête

Aucune requête utilisateur ne tire un fournisseur. Motif validé :

1. la route sert le cache (même périmé, étiqueté `PERIME`/`stale`) ;
2. une absence lance une collecte en fond, dédoublonnée par clé, avec
   verrou et délai de relance ;
3. la réponse dit `EN_COURS` + `retry_s`, la page réessaie un nombre borné
   de fois hors cache client (`VX.fetch(url, {ttl: 0})`).

Exemples : `/api/analyst`, `/api/company`, `/api/correlations`,
`/api/pos-quotes` (`POSQ_ATTENTE_S`), `chaine_a_la_demande.board_avec`.
Gardien : `tests/test_reseau_hors_requete.py` (plus aucun `_od.board_with`
ni `_od.fetch` dans `vertex/app/routes`).

## 5. Diffusion sans rechargement

- Les boucles publient sur `vertex/services/live_stream.BROKER`
  (canaux `market`, `options`, `news`, `alerts`, `jobs`, `system`, …) des
  comptes et horodatages, jamais de contenu ni de donnée personnelle.
- `live-updates.js` invalide le cache client par canal puis rejoue les tâches
  de la page (`VX.refresh.runTasks`), regroupé 1,5 s, jamais en onglet
  masqué ; `vx:data-refreshed` part APRÈS l'invalidation.
- Une page qui saisit des filtres (screener) ne se rejoue pas.
- Un écouteur `VX.bus.on` reçoit un `CustomEvent` : lire `ev.detail`.
- Gardien : `tests/test_diffusion_live.py`.

## 6. Collecteurs de fond (modèle `vertex/services/macro_officiel.py`)

- réseau injectable (`fetch(url, accept) -> str`), hôtes en liste blanche,
  taille de réponse bornée, User-Agent explicite ;
- parseurs purs testés sur **fixtures réelles capturées**
  (`tests/fixtures/<source>/`) ;
- cache JSON persisté et réhydraté au démarrage, `as_of` de la collecte,
  `observed_at` de la source ;
- battement au registre (`_sched.beat('<JOB>', ok=…)`, nom LITTÉRAL, sinon le
  registre le déclare sans exécutant) et entrée dans
  `vertex/scheduler/registry.py` (pins de comptes dans
  `tests/test_registre_jobs.py`, `tests/test_factory_parity.py`) ;
- reprise espacée (délai croissant plafonné), la panne est une donnée ;
- un test de collecte réelle derrière un drapeau
  (`VERTEX_TEST_RESEAU=1`), jamais dans la suite par défaut.

## 7. Assets statiques et cache navigateur

Tout changement sous `vertex/static` exige, dans le même commit :
`const CACHE='td-shell-vN'` (`vertex/app/routes/system.py`), `SHELL_VERSION`
(`vertex/ui/shell/__init__.py`), l'empreinte `_EMPREINTE` et `_SW_VERSION`
de `tests/test_sw_cache_scope.py`, et les quatre pins de version
(`test_design_system_page`, `test_production_guards_canonical`,
`test_redesign_ui`, `test_ui_v3`). Sinon un visiteur garde l'ancien bundle
immuable.

## 8. Gardiens qui surprennent

- `tests/test_pass_terminal.py` compte les `except: pass` de `terminal.py`
  (population épinglée) et `tests/test_replis_exception.py` refuse un repli
  numérique dans un `except` : utiliser `contextlib.suppress` et une valeur
  initialisée avant le `try`.
- `tests/test_terminal_imports.py` : aucun import orphelin.
- `tests/test_gardes_superseedees.py` : une garde écartée qui repasse au
  vert doit sortir de `tests/_supersede.py` (compte `TOTAL_ECARTES`).
- `tests/test_namespace_guards.py` : aucun nom personnel ni chemin
  utilisateur dans l'arbre.
- `tests/test_strategy_os_final_guards.py` : `client_id` sur la même ligne
  que `.connecter(`.

## 9. Preuve d'une tranche

1. tests ciblés puis suite complète (`python -m pytest -q`), résultat exact
   consigné ;
2. instance QA (`tools/qa/run_qa_instance.py`, port 5003, sans IBKR) :
   route lue, carte lue dans le DOM, console sans erreur ; le volet
   navigateur intégré est `document.hidden` (SSE et tâches coupés) : forcer
   la visibilité pour un test de réaction, lire le flux SSE directement ;
3. données de test seulement dans la copie QA (`%TEMP%\vertex-qa`), jamais
   dans le desk réel ;
4. consignation : `VERTEX_NIGHT_RUN.md` (commit, suite), `VERTEX_DATA_COVERAGE.md`
   (statut du défaut), `VERTEX_FINAL_REPORT.md` (rollback), `VERTEX_RUNBOOK.md` ;
5. commit ciblé revertible, PR brouillon, aucune fusion automatique.

## 10. Ce que cette procédure interdit

Un chiffre inventé pour compenser une absence ; un badge « live » sans
preuve de socket ; une lecture de compte, positions ou P&L IBKR ; un
collecteur lancé depuis une requête utilisateur ; un secret dans Git, une
capture, un journal ou un prompt ; l'affaiblissement d'un gardien pour
obtenir du vert.
