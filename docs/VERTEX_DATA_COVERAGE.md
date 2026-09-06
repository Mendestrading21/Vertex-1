# VERTEX_DATA_COVERAGE — page → carte → champ → source → cadence → statut → preuve

Version 1 (2026-09-06, branche `ui/refonte-dashboards`). Construit à partir de
deux inventaires en lecture seule (un par moitié du produit) et des chaînes
remontées jusqu'aux sources. Les matrices complètes champ par champ vivent
dans les rapports d'inventaire ; ce fichier consigne, par carte, la source
réelle, la cadence réelle et l'état, puis les défauts d'alimentation avec leur
statut de traitement dans cette mission.

Légende état : **RÉEL** (source identifiée, chaîne complète) · **PARTIEL**
(données réelles mais étiquette, âge ou unité incomplets) · **DÉGRADÉ**
(valeur fausse, badge non fondé ou calcul au mauvais endroit) · **ABSENT**
(composant jamais alimenté) · **NON_IMPLÉMENTÉ** (déclaré tel quel) ·
**DÉMO** (données synthétiques). Statut mission : **corrigé** · **en cours** ·
**consigné** (non traité dans cette mission, motif donné).

## 0. Colonne vertébrale commune

| Maillon | Source réelle | Cadence | État | Preuve |
|---|---|---|---|---|
| Barres quotidiennes de l'univers (~517 titres) | IBKR historique (barres EOD) → yfinance (lots de 50) → Stooq (filet) ; `source = ibkr+yfinance+stooq` | boucle scan 30 min (`REFRESH_SEC`) | RÉEL (différé, EOD) | `terminal.py:360-465`, `constants.py:34` |
| Indices, matières, macro (^IRX ^FVX ^TNX ^TYX DX-Y) | yfinance, même téléchargement ; `macro_cache.json` | 30 min | RÉEL (différé) | `terminal.py:662-720` |
| Overlay temps réel indices (SPX/VIX/Dow CFD) | IBKR `reqMktData`, appliqué si tick < 75 s, `src:'ibkr'` par tuile | worker 15 s | RÉEL (live, prouvé par socket) | `terminal.py:2362-2394` |
| Cours des positions déclarées | worker IBKR `reqTickers`/`reqMktData` (cache 45 s) → repli clôture scan étiqueté | à la demande | PARTIEL | `desk.py:118-219, 386-500` |
| Board options | `_opt_loop` : IBKR ou yfinance (`options_source`), Greeks IBKR `modelGreeks` sinon IV seule | 120 s | RÉEL (source écrite sur la grille, pas sur la vue d'ensemble) | `terminal.py:1489-1555` |
| Session IBKR | **marché seulement** : poignée de main client, verrouillage par liste blanche, aucune synchronisation de compte | par worker | **corrigé (P0)** | `vertex/data_sources/ibkr_session.py`, `tests/test_ibkr_session_marche_seule.py` |
| Références macro officielles (Fed funds, Trésor 2/10 ans, pente, BCE refi/dépôt, IPCH, EUR/USD, EUR/CHF, SARON, Confédération 10 ans) | **FRED CSV public, BCE SDMX, BNS cube** — collecteur de fond, dates de la source | 6 h (`VERTEX_MACRO_OFFICIEL_MIN`) | **RÉEL, ajouté** (11/11 séries publiées le 2026-09-06) | `vertex/services/macro_officiel.py`, `/api/macro/officiel`, `tests/test_macro_officiel.py` |
| Diffusion vers les cartes | SSE `/api/live/events` (canaux market/options/alerts/system) + `VX.refresh` par page (polling TTL) | événementiel + TTL | PARTIEL (4 émetteurs seulement, la plupart des cartes pollent) | `terminal.py:933,1482,2574,2667`, `live-updates.js` |
| Horodatage du scan | `scan_ts` epoch + `updated` HH:MM:SS ; **`scan_ts_h` lu par 23 consommateurs, jamais écrit** | — | DÉGRADÉ | `terminal.py:748-749, 872-873` — consigné (lot fraîcheur) |

## 1. Aujourd'hui (`/`)

| Carte | Champs | Source → cadence | État | Statut mission |
|---|---|---|---|---|
| Hero DecisionTrace | source, horodatage, régime, comité, positions | scan (30 min) + desk | PARTIEL (`scan_ts_h` absent → HH:MM:SS) | consigné |
| L'essentiel (12 tuiles) | dernier close, Δ % | scan 120 s client / 30 min serveur ; overlay IBKR 15 s | PARTIEL : SMI, USD/CHF, ETH sans source (« n/d » permanent) ; « temps réel » affiché sur des barres EOD | consigné (retirer les tuiles sans source ou ajouter ^SSMI/CHF=X/ETH-USD) |
| Lecture en clair | tendance, ambiance, VIX, participation, secteur fort | `/api/market/summary` 60 s | RÉEL (seuils UI ±0,15 %, 15/25) | consigné |
| Opportunités actions / options | verdict, p_win, edge, R:R ; strike, prime, PoP | `/api/command` 60 s (comité, Black-Scholes) | RÉEL / PARTIEL (unité prime) | consigné |
| Entonnoir | Univers → Achats | calculé côté client (2e propriétaire) | DÉGRADÉ | consigné → propriétaire unique `/api/opportunities/funnel` |
| Portefeuille | valeur, P&L, poids | `VXEntities` + `/api/pos-quotes` ; **calcul financier dans l'UI** ; badge « IBKR temps réel » déduit | DÉGRADÉ | consigné (P1) |
| Alertes | règles marché + alertes perso + déclenchées | `/api/command`, `/api/alerts/status` 30–60 s | RÉEL | — |
| Brief | lignes, narratif, « ce qui a changé » | `/api/briefing/editorial` 60 s ; `as_of = now` quand aucun scan | PARTIEL | consigné |
| « Ce qui a changé » / « Depuis hier » | `market_ctx.changes_since_prev`, `daily_changes` | **jamais produits** | ABSENT | consigné (P1) |
| Régime | verdict, confiance, barres de « forces » | `/api/market/regime` 120 s ; **aucun `as_of`** ; barres 85/18/50/82/72 **codées** | DÉGRADÉ | consigné (P0 horodatage) |
| Calendrier du jour | items, macro | `/cal-feed` 300 s (yfinance 3 h ; **démo non signalée** ; `dte` figé) | DÉGRADÉ | consigné (P0) |
| Actus | titre, éditeur, heure, sentiment lexical | `/news-feed` 60 s (IBKR → yfinance → Google News RSS) | PARTIEL (source/âge non affichés) | consigné |
| Marchés (replié), Pouls, Top 10, Secteurs | indices, breadth, santé | `/scan` 120 s | PARTIEL (`||0`, `score||50`) | consigné |

## 2. Calendrier (`/calendar`)

| Carte | Source → cadence | État | Statut |
|---|---|---|---|
| Résultats (items) | yfinance `.calendar` 280 titres, 3 h ; cache réhydraté sans `ts` ni recalcul `dte` ; badge « Confirmé » systématique ; DÉMO synthétique non signalée | DÉGRADÉ | consigné (P0 : `source`, `approx`, `demo` par item) |
| Macro | liste FOMC 2026 codée + règles NFP/CPI | RÉEL (expire 2026-12-09) | consigné (flux officiel Fed/BLS à brancher) |
| Fraîcheur | `/cal-feed.ts` | RÉEL après première publication | — |
| Portefeuille, Options (échéances) | localStorage | RÉEL | — |
| Dividendes, catalyseurs, revues, heure/fuseau, consensus/réel | — | NON_IMPLÉMENTÉ (déclaré) | — |

## 3. Marchés (`/markets`)

| Carte | Source → cadence | État | Statut |
|---|---|---|---|
| Synthèse (régime, risque, S&P, leadership) | `/api/market/regime`, `/scan` 120 s ; `(confidence||0)*100` ; deux logiques de série S&P | PARTIEL | consigné |
| Indices (4 cartes, comparaison, Top/Flop) | scan ; overlay IBKR par tuile ignoré | PARTIEL | consigné |
| Macro · KPI, courbe des taux, appétit, calendrier | scan macro (`prev` = valeur du jour si absent) ; `cal.ts||Date.now()` | DÉGRADÉ (âge inventé, fausse séance précédente) | consigné |
| **Macro · Références officielles** (nouvelle carte) | `/api/macro/officiel` 60 s (collecteur 6 h) — valeur, unité, **date d'observation de la source**, fréquence, précédent, source, état d'erreur | **RÉEL, vérifié dans le navigateur** | **corrigé (ajout)** |
| Secteurs (heatmap, RRG) | scan | PARTIEL (`score||50`) | consigné |
| Participation · entonnoir | client ; « Achats » = 0 structurel (`ACHETER` vs `BUY`) | DÉGRADÉ | consigné (P1) |
| Volatilité | summary + regime | PARTIEL | consigné |

## 4. Opportunités (`/opportunities`)

| Carte | Source → cadence | État | Statut |
|---|---|---|---|
| Radar / Actions / ETF | `/scan` rows + detail 120 s ; buckets recalculés côté client sans gate régime | RÉEL / DÉGRADÉ (2e vérité) | consigné |
| Entonnoir serveur | `/api/opportunities/funnel` 60 s ; 2 étages cliquables inexistants | PARTIEL | consigné |
| Options (board, comparateur, contrat ouvert) | `/scan.options_board` ; `/api/options/simulate` ; 4 cartes `Date.now()` | RÉEL / DÉGRADÉ (âge) | consigné |
| Positions × moteur, risque du panier | `POST /api/risk {symbols}` sur les positions **déclarées** ; titres non mesurables nommés | RÉEL / PARTIEL | corrigé (`/api/command.risk` reste le panier du comité pour Aujourd'hui) |
| Anomalies, catalyseurs | `/scan`, `/cal-feed` | RÉEL / PARTIEL | consigné |

## 5. Analyse (`/analysis`, `/analysis/<sym>`)

| Carte | Source → cadence | État | Statut |
|---|---|---|---|
| Hero, puce fraîcheur prix | `/api/ticker` 60 s ; **`priceDomain` non déclaré** (puce jamais rendue) ; `status` = `window.status` | ABSENT / DÉGRADÉ | consigné (P1, fiche) |
| Verdict canonique, scénarios | `/api/decision` 60 s | RÉEL | — |
| Rail ExecutiveEngine / Skyler | `/api/strategy/decision` (**`ATTENDRE` fabriqué hors scan**), `/api/skyler` | DÉGRADÉ (3 autorités) | consigné (P0 programme) |
| Raisonnement du comité | `#an-committee` absent du DOM | ABSENT | consigné |
| Profil, physique, graphique, RSI, volume | `/api/ticker.detail` 180 s ; `Date.now()` sur RSI/volume | PARTIEL | consigné |
| Fondamentaux, financiers, valorisation | yfinance hebdo (fond) ; `meta.source` littéral | PARTIEL | consigné |
| Fondamentaux datés SEC EDGAR | route `/api/sec/fondamentaux/<sym>` existante, **non consommée** ; source bloquée par `SEC_USER_AGENT` absent | NON_IMPLÉMENTÉ côté page | consigné (action humaine : contact SEC) |
| TradingView | `/api/tradingview/signals` 60 s ; confluence recalculée en UI | PARTIEL (non configuré) | consigné |
| Plan & dimensionnement | `localStorage.vxAccountValue` (patrimoine en cache navigateur) | PARTIEL | consigné (P1) |

## 6. Options (`/options`, `/options/dossier/<sym>`)

| Vue / carte | Source → cadence | État | Statut |
|---|---|---|---|
| Vue d'ensemble (environnement, lecture, indicateurs, meilleurs contrats) | `/api/options/overview` (board 120 s, `as_of` scan) ; `source:'SCAN'` constant | RÉEL (source réelle IBKR/yfinance non nommée) | consigné |
| Structure (verdict, payoff, Greeks) | `/api/options/strategies` + **`expectedMove`, `computeVerdict`, `liqState` calculés en JS** | DÉGRADÉ | consigné (P1 moteur) |
| Volatilité, Scénarios, Événements, Positionnement, Scanner | `/api/options/*` ; `Date.now()` sur scénarios ; GEX enregistre l'historique sur GET | RÉEL / PARTIEL | consigné |
| Dossier titre : verdict volatilité | `/api/options/volatility/<sym>` (corrigé lors de la refonte UI) | RÉEL | corrigé (mission précédente) |
| Dossier : chaîne, grille, surface, max pain | `on_demand.fetch` **dans la requête** ; blocs IBKR vides sans TWS (dit) | PARTIEL | consigné (P1 réseau dans requête) |

## 7. Simulateur (`/simulator`)

| Carte | Source | État | Statut |
|---|---|---|---|
| Option (matrice, décroissance, IV) | `/api/options/simulate` : spot = clôture scan, IV inversée du mid (`FALLBACK_ESTIMATE`), taux courbe/4,5 % repli, dividende fondamentaux | PARTIEL (`entrees` non affichées) | consigné |
| Action/ETF · PoP et Greeks | **`iv: 0.25` codé en dur** dans `simulator.js` → probabilité et sensibilités fabriquées | DÉGRADÉ (P0) | consigné (lot moteur : refuser PoP/Greeks sans IV cotée) |
| Impact portefeuille (7 contrôles) | `/api/pretrade/check` | RÉEL | — |
| Forex, look-through ETF | — | NON_IMPLÉMENTÉ (déclaré) | — |

## 8. Portefeuille manuel (`/portfolio`)

| Carte | Source | État | Statut |
|---|---|---|---|
| Positions, marques | desk déclaré + `/api/pos-quotes` (IBKR marché, repli clôture scan) ; **jamais compte/positions IBKR** | RÉEL / PARTIEL | vérifié |
| Badge « marques live » | `live = bool(ibkr_enabled)` (config, pas socket) | DÉGRADÉ | consigné (P1 : `scan_state.ibkr_live`) |
| Valeur, P&L, poids | calculés dans le JS | PARTIEL | consigné |
| Diversification / dépendances cachées | `POST /api/risk {symbols}` = positions déclarées (jamais le panier du scan) ; `non_mesures` et `as_of` servis | RÉEL / PARTIEL | corrigé |
| Allocation, stress, Greeks agrégés | `/api/portfolio/context`, `/stress`, `/greeks` | RÉEL / PARTIEL | — |
| Performance (équité, contribution) | `myTradesEquity` jamais alimenté ; `t.plAbs` jamais produit | ABSENT | consigné |
| Devise, pays, thème | — | ABSENT (déclaré) | — |

## 9. Suivi (`/follow-up`)

| Carte | Source | État | Statut |
|---|---|---|---|
| Résumé, référence, actuel, alpha | `/api/tracking` (tracking.json), clôture scan, SPY | RÉEL (hypothétique, étiqueté) | — |
| MFE / MAE actions | 2 points seulement : `TRACKING_SNAPSHOT` non implémenté | DÉGRADÉ | consigné |
| Fraîcheur | `/api/tracking` sans horodatage | ABSENT (avoué) | consigné |

## 10. Performance (`/performance`)

| Carte | Source | État | Statut |
|---|---|---|---|
| KPI, équité, discipline | journal déclaré agrégé en JS ; `Date.now()` | RÉEL (déclaratif) / PARTIEL | consigné |
| Post-mortem, distribution | `/api/journal/postmortem` (autre magasin) | RÉEL (deux vérités) | consigné |
| Signaux théoriques, calibration, mémoire | `/api/track-record`, `/api/skyler/*` ; GET avec écriture | RÉEL (honnête) | consigné (GET à effet de bord) |
| « Positions IBKR · source IBKR » | aucune source ne produit de positions IBKR | ABSENT (libellé promet l'interdit) | consigné (P1 texte) |

## 11. Vertex IA (`/intelligence`)

| Carte | Source | État | Statut |
|---|---|---|---|
| Décision finale | `/api/strategy/decision` + `/api/decision` (deux moteurs) ; `'ATTENDRE'` par défaut | PARTIEL / DÉGRADÉ | consigné (P0 programme) |
| Interprétation IA | `/api/ai/analyst` ; sans clé : synthèse déterministe | RÉEL (dégradé sans clé) | — |
| Comité, brief, décisions, doctrine, mémoire, impacts SSE | routes dédiées | RÉEL | — |
| Recherche (validateur) | backtest paper de la watchlist présenté comme « équité réelle » | DÉGRADÉ (population) | consigné |
| Fraîcheur (barre) | 6 vues sur 8 en « Lecture… » | ABSENT | consigné |

## 12. Système (`/system`)

| Carte | Source | État | Statut |
|---|---|---|---|
| Connexions (IBKR, TradingView, Claude, stockage, scheduler, SSE) | preuve socket pour IBKR ; présence de variables pour TV/Claude | RÉEL / PARTIEL (configuré ≠ testé) | — |
| Jobs | registre + battements ; `NON_IMPLEMENTE` / `SILENCIEUX` distingués ; **`MACRO_OFFICIEL_REFRESH` ajouté (13 exécutables / 18 sans exécutant)** | RÉEL | corrigé (ajout) |
| Synchronisation, hero, `/healthz.engines` | `mode='live' si IBKR_ENABLED` ; `readonly=True` littéral ; moteurs en dur | DÉGRADÉ / PARTIEL | consigné (P1) |
| Cerveau Claude · cotations trouvées | prix par recherche web LLM, non réconciliés | DÉGRADÉ | consigné (retirer la surface `quotes`) |
| Qualité des données | classe unique par scan ; `last_scan_ts` jamais posé | DÉGRADÉ | consigné |

## 13. Défauts d'alimentation classés (synthèse) et statut

| # | Sév. | Défaut | Statut |
|---|---|---|---|
| 1 | P0 | Session IBKR synchronisait positions/compte/exécutions au connect | **corrigé** (session marché seulement, prouvée) |
| 2 | P0 | Verdict `ATTENDRE` fabriqué hors scan ; trois autorités de décision | **partiel** : plus aucun verdict fabriqué hors scan (`final_decision: null`, `etat: NON_EVALUE`, rail « NON ÉVALUÉ » avec la raison servie ; Vertex IA idem ; carte du comité : vocabulaire inconnu → « Non classé », plus « Attente ») — les trois autorités de décision restent (programme lot décision) |
| 3 | P0 | Calendrier : démo non signalée, `dte` figé, « Confirmé » systématique | **corrigé** : `dte` recalculé et items étiquetés par `/cal-feed` (`f8d6f150`) ; le niveau de confirmation est SERVI (résultats : « non confirmée par l’émetteur » ; macro : dérivé de la source, Fed publiée = confirmée, règle BLS = non confirmée) et l'écran ne décide plus « Confirmé » ; démo signalée par `cal.demo` |
| 4 | P0 | `Date.now()` posé comme âge de donnée (≈ 25 emplacements, 7 pages) ; `/api/market/regime` sans `as_of` ; `scan_ts_h` jamais écrit | **corrigé** (`f8d6f150` : `scan_ts_h` écrit, régime daté, 28 `Date.now()` retirés, gardien `test_fraicheur_serveur`) |
| 5 | P0 | Simulateur actions : IV 25 % codée → PoP/Greeks fabriqués | **corrigé** (`31305b70` : `iv: null`, PoP et Greeks absents sans IV cotée) |
| 6 | P1 | Badges « live » fondés sur la configuration (`ibkr_enabled`) | **corrigé** (`31305b70` : « live » sur preuve de socket `ibkr_live` seulement) |
| 7 | P1 | Risque du panier ≠ portefeuille déclaré | **corrigé** : `/api/risk` accepte en POST les symboles déclarés par la page (Portefeuille › Dépendances cachées, Opportunités › Risque du panier) et dit `panier: declare`, `non_mesures`, `as_of` ; le GET (panier du comité) reste pour Aujourd'hui |
| 8 | P1 | Réseau dans les requêtes UI (corrélations, descriptions, analystes, dossier options, pos-quotes) | **partiel** : `/api/analyst` sert le cache (CACHE / PERIME + `stale`) et collecte en fond (EN_COURS + `retry_s`, une collecte par symbole), la fiche réessaie 3× ; `/api/pos-quotes` n'attend plus que 1,5 s (`POSQ_ATTENTE_S`) et nomme `en_attente`, son repli lit la marque de contrat depuis le cache (`contract_mark(reseau=False)`, lecture en fond). Restent : `on_demand.fetch`/`board_with` dans les routes du dossier options (strategies, options-for, decision), `/api/correlations` (sans consommateur UI) et `/api/company` (sans consommateur UI) |
| 9 | P1 | Composants jamais alimentés (changes_since_prev, daily_changes, #an-committee, priceDomain, équité portefeuille) | **partiel** : `#an-committee` et `#an-catalyst-strip` ont leur hôte (le raisonnement du comité s'affiche dans la fiche), `priceDomain`/`status` déclarés (âge réel de la cotation) ; les blocs analystes de la fiche (surprises, révisions, notes, détenteurs, initiés) étaient peints à 1 s puis EFFACÉS à 2 s par la réécriture du corps de carte (mesuré) — ajout idempotent `data-analyst` ; restent `changes_since_prev`, `daily_changes`, équité portefeuille |
| 10 | P2 | Sources officielles macro absentes (FRED, BCE, BNS) | **corrigé** (nouvelle chaîne source → carte) |
| 11 | P2 | SEC EDGAR branchée mais inactive et non consommée | consigné (action humaine : `SEC_USER_AGENT`) |
| 12 | P1 | Entonnoir Marchés « Achats = 0 » structurel (vocabulaire français seul alors que le scan parle anglais) | **corrigé** : même vocabulaire que l'entonnoir d'Aujourd'hui (gardien d'égalité) ; mesuré sur l'instance QA : 513 → 513 → 294 → 94 au lieu de 0 |
