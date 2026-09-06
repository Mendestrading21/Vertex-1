# VERTEX_FINAL_REPORT — bilan de la nuit du 2026-09-05 → 06

Branche `ui/refonte-dashboards`, PR brouillon #867 (aucune fusion). Aucun secret.

## 1. Statut par catégorie (ce qui est vrai, pas ce qui est souhaité)

| Catégorie | Contenu |
|---|---|
| **Inventorié** | 12 pages, toutes les cartes et champs importants → `VERTEX_DATA_COVERAGE.md` (état par carte, défauts P0–P2 avec fichier:ligne) ; 15 fournisseurs → `VERTEX_SOURCE_REGISTRY.md` (accès, droits, cadence, état) |
| **Implémenté** | session IBKR « marché seulement » (6 sites) ; collecteur macro officiel FRED/BCE/BNS + route + carte Marchés ; étiquettes « live » sur preuve de socket ; Simulateur sans IV inventée ; `scan_ts_h`, régime daté, calendrier daté et étiqueté ; fin des `Date.now()` comme âge (9 pages) ; gardiens statiques élargis ; cartes macro Marchés restaurées |
| **Testé avec simulation** | doublure d'`IB` (poignée de main seule, 47 méthodes refusées, refus par défaut) ; parseurs FRED/BCE/BNS sur fixtures réelles capturées ; collecteur (absence expliquée, jamais zéro, cache, battement) ; route sans réseau ; hôtes hors liste refusés ; calendrier `dte` recalculé ; moteur multi-jambes sans IV |
| **Vérifié sur une source réelle** | socket TWS 7496 (rôle `verification`, id 29) : connexion, `reqCurrentTime`, aucune position ni valeur de compte détenue, méthodes de compte refusées ; FRED, BCE, BNS : 11/11 séries publiées (collecte réelle, `VERTEX_TEST_RESEAU=1`) ; carte Marchés › Macro rendue dans le navigateur avec dates de la source |
| **Actuellement alimenté** (instance de travail relancée à 00:57 avec le code de la nuit) | IBKR en direct (`ibkr_live: true` dès 00:57:56, scan 513/517 titres à 00:59:53), overlay indices IBKR, board options, news, calendrier, fondamentaux, **références macro officielles** (collecteur de fond, cache seedé) ; `/healthz` `read_only: true` |
| **Bloqué par un accès, un droit ou une dépendance extérieure** | SEC EDGAR : `SEC_USER_AGENT` (contact réel) à saisir par l'humain ; FRED API JSON : clé optionnelle (le CSV public suffit) ; TradingView webhooks : secret non configuré ; Claude : clé absente (synthèse déterministe servie) ; 4ᵉ audit (circuit temps réel) interrompu par la limite d'usage, remplacé par une lecture directe |

## 2. Ce qui a été conservé du skill précédent

Toute la refonte des dashboards Options (commits `209c972f`, `3053a3cc`,
`90984dee`) : bases CSS restaurées, composition de la Vue d'ensemble, absence
≠ zéro, micro-barre partagée, instance QA, 42 gardiens. Aucun de ses fichiers
n'a été retravaillé visuellement cette nuit ; seules des étiquettes de données
ont changé (fraîcheur, « live »). Le thème Black Glass est intact.

## 3. Changements de cette mission (8 commits sur la branche)

| SHA | Objet | Rollback |
|---|---|---|
| `dfa0247f` | session IBKR marché seulement, lecteur racine sans compte, gardiens, preuve socket | `git revert` (réintroduirait la synchronisation de compte : déconseillé) |
| `426c5184` | macro officielle FRED/BCE/BNS → carte, registre des sources, matrice de couverture | `git revert` |
| `31305b70` | live sur preuve de socket, Simulateur sans IV inventée | `git revert` |
| `f8d6f150` | fraîcheur servie (`scan_ts_h`, régime, calendrier, `Date.now()`) | `git revert` |
| `fda07e70` | coque vx-shell-4, SW v291, cartes macro Marchés, runbook | `git revert` puis re-bump |
| `e5c1a042` | test desk aligné, journal de nuit | `git revert` |
| `240d23b7` | honnêteté : verdict hors scan non fabriqué, confirmation du calendrier servie, entonnoir Marchés, hôtes de la fiche Analyse (coque vx-shell-5, SW v292) | `git revert` puis re-bump |
| `08e0a79a` | risque du panier sur les positions déclarées (`POST /api/risk`), Portefeuille et Opportunités | `git revert` |
| `816e6f73` | réseau hors requête : analystes (cache + fond), cotations (worker en fond, `en_attente`), marque de contrat depuis le cache, blocs analystes visibles | `git revert` |
| `0b293dc5` | chaîne d'options hors requête (magasin non bloquant, `en_cours`, pages avec réessai ; coque vx-shell-6, SW v293) | `git revert` puis re-bump |
| `abd7df10` | composants alimentés : « Ce qui a changé », équité dérivée des clôtures, contribution (`plAbs`) | `git revert` |
| `d2722b4c` | verdict de structure côté serveur (`structure_verdict`), vue Structure qui peint (coque vx-shell-7, SW v294) | `git revert` puis re-bump |
| `9327ee42` | cotations LLM réconciliées avec le scan (Système), contrat du lot décision | `git revert` |
| `13b063e0` | `/api/company` et `/api/correlations` sans réseau dans la requête | `git revert` |
| `b58b6270` | delta du brief depuis le diff market_context | `git revert` |

## 4. Pages et champs effectivement couverts

- **Marchés › Macro** : nouvelle carte de 11 références officielles (valeur,
  unité, date d'observation de la source, fréquence, précédent, source,
  erreur éventuelle) ; cartes d'actifs macro à nouveau lisibles.
- **Toutes les pages** : plus aucune carte n'affiche l'heure du navigateur
  comme âge ; le régime et le calendrier sont datés ; le calendrier recalcule
  les jours restants et dit sa source et son niveau de confirmation.
- **Portefeuille / Aujourd'hui / Système** : « live » n'apparaît que si des
  cotations IBKR récentes ont été servies.
- **Simulateur (actions/ETF)** : probabilité de gain et sensibilités absentes
  sans IV cotée, au lieu de chiffres fabriqués.
- **Frontière IBKR** : toutes les sessions (passerelle, options, cotations,
  indices, preuve de socket, lecteur racine).

## 5. Tests exécutés et résultats exacts

| Exécution | Résultat |
|---|---|
| Suite complète finale (`python -m pytest -q`) | **4422 passed, 181 skipped, 0 failed** (3 min 10 s) ; après la tranche honnêteté : **4435 passed, 180 skipped, 0 failed** ; après la tranche risque du panier : **4442 passed, 180 skipped, 0 failed** ; après la tranche réseau hors requête : **4452 passed, 180 skipped, 0 failed** |
| CI GitHub sur la PR #867 | `safety` pass (12 s), `test` pass (2 min 12 s) |
| `tests/test_no_orders.py` | 3 passed |
| `check_ibkr_boundary.py --enforce` (racine entière) | OK, aucun appel sensible |
| Socket réelle TWS (`VERTEX_TEST_IBKR_LIVE=1`) | 1 passed |
| Collecte réelle FRED/BCE/BNS (`VERTEX_TEST_RESEAU=1`) | 1 passed (11/11 séries) |
| Nouveaux tests | `test_ibkr_session_marche_seule` (63), `test_macro_officiel` (12), `test_etiquettes_live_honnetes` (4), `test_fraicheur_serveur` (29), `test_honnetete_verdict_et_calendrier` (12), `test_risque_panier_declare` (7), `test_reseau_hors_requete` (14), `test_composants_alimentes` (4), `test_structure_verdict` (8), `test_cerveau_claude_reconcilie` (3), `test_reseau_hors_requete` porté à 16 |

Tests simulés, contractuels, connexion réelle et observation de fonctionnement
sont distingués dans chaque fichier (docstring et marqueurs `skipif`).

## 6. Sources réellement connectées

IBKR (données de marché, session verrouillée, prouvée), yfinance (différé),
Stooq (filet), FRED, BCE, BNS (nouveau), Google News RSS, Wikipedia
(constituants), portefeuille déclaré. Non connectées : SEC (contact requis),
TradingView (secret absent), Anthropic (clé absente).

## 7. Services démarrés et contrôles de santé

- Instance de travail `python -m vertex` (pid 33684, seul processus à
  écouter 0.0.0.0:5002 derrière `VERTEX_CODE`), relancée à 00:57:15 avec le
  code de la nuit.
- Observation de stabilité : 10 minutes (00:57 → 01:11), `/healthz` sondé
  toutes les 30 s : `ibkr_live: true` sur toutes les sondes après 00:57:56,
  premier scan complet à 00:59:53 (513/517 titres), aucun `Traceback` dans le
  journal serveur (seules des erreurs IBKR de contrats non résolus AVB/EA/EQR
  et deux champs d'options invalides, préexistantes). Mémoire du processus :
  231 → 233 Mo, 32 threads, stables. Aucune reconnexion observée.
- Les autres processus Python de la machine appartiennent au monorepo
  « Vertex 1.0 Beta » (`~/.vertex/app`, ports 8000/8001) : non touchés.
- Relance du 2026-09-06 à 02:49 avec le code de la branche (`659aec4a`) :
  `/healthz` `status: ok` en 45 s, premier scan à 02:49:34 ; TWS était fermé
  à cet instant (« injoignable sur 7496/7497/4001/4002 », état normal sans
  session courtier) → données différées yfinance, étiquetées ; les workers
  réessaieront les ports à la réouverture de TWS. Observation 5 min :
  mémoire 262 → 271 Mo, aucun `Traceback` (une 404 yfinance sur un titre,
  préexistante). L'instance précédente (00:57) était montée à 368 Mo en
  1 h 40 avec IBKR actif : à surveiller sur la durée.
- Instance QA (port 5003) arrêtée après les vérifications.
- Le fonctionnement ne dépend pas de Claude : les boucles sont des threads du
  processus Vertex ; `VERTEX_RUNBOOK.md` décrit démarrage, arrêt, reprise.

## 8. Branche, commits, pull request

- Branche `ui/refonte-dashboards` poussée sur `origin` ; PR brouillon
  **#867** vers `main`, CI verte. Aucune fusion, aucun force-push, aucun
  déploiement.

## 9. Actions humaines restantes (indispensables)

1. Saisir `SEC_USER_AGENT="Vertex <contact réel>"` et `VERTEX_ENABLE_SEC=1`
   dans `.env` pour activer SEC EDGAR (l'adaptateur existe et se refuse sans
   contact).
2. Décider d'épingler `ib_async==2.1.0` dans `requirements.txt` (le
   comportement au connect dépend de la version ; la session marché seulement
   protège, mais une version future pourrait déplacer la poignée de main).
3. Relire et fusionner (ou non) la PR #867.
4. Lot décision (autorité unique) : valider `VERTEX_LOT_DECISION_CONTRAT.md`
   (§9) avant tout code moteur.
5. Onglets Options : le contrat cible sept sous-vues (Vue d'ensemble, Chaîne,
   Volatilité, Scanner, Scénarios, Positions, Événements) ; la page en sert
   neuf, chacune son onglet, par décision antérieure explicite (lot 38 :
   « plus aucune vue orpheline », gardiens `test_options_visual`). Proposition
   à valider : Radar + Scanner LEAPS → **Scanner** (bascule interne),
   Structure → **Scénarios** (verdict + scénarios + payoff), Positionnement →
   **Chaîne** (OI, murs, GEX avec la table), les autres inchangées ; chaque
   ancienne URL `?view=` redirigée vers son nouvel onglet + ancre. Non
   implémenté : c'est un choix d'architecture d'information qui inverse une
   décision documentée.

## 10. Défauts consignés, non traités cette nuit (par priorité)

Voir `VERTEX_DATA_COVERAGE.md` §13. Traités depuis (commit `240d23b7`) : plus
aucun verdict fabriqué hors scan (`NON_EVALUE`), niveau de confirmation du
calendrier servi et affiché tel quel, entonnoir Marchés au vocabulaire du scan,
`#an-committee`/`#an-catalyst-strip`/`priceDomain` de la fiche Analyse.
Traité aussi (`08e0a79a`) : risque du panier mesuré sur les positions déclarées ;
(`816e6f73`) : analystes et cotations sans réseau lent dans la requête, blocs
analystes de la fiche visibles.
(`0b293dc5`) : chaîne d'options chargée en fond, jamais dans la requête ;
(`abd7df10`) : « Ce qui a changé », équité et contribution du Portefeuille alimentés ;
(`d2722b4c`) : verdict, liquidité, mouvement attendu et scénarios de la vue
Structure calculés par le serveur.
(`9327ee42`) : cotations LLM réconciliées avec le prix du scan (Système).
Restent : trois autorités de décision — contrat écrit
(`VERTEX_LOT_DECISION_CONTRAT.md`), décision humaine attendue ; onglets
Options non regroupés.

Une information indisponible n'est pas un succès ; une PR n'est pas un
déploiement ; une donnée simulée n'est pas une source connectée. Ce bilan les
distingue.
