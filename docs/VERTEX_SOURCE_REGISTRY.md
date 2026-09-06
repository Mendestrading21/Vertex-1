# VERTEX_SOURCE_REGISTRY — accès, droits, limites et configuration des fournisseurs

Mesuré le 2026-09-06 (branche `ui/refonte-dashboards`) par lecture du code et
requêtes HTTP réelles depuis cette machine. Aucun secret ici. Droits : d'après
les conditions publiques connues ; « à confirmer » quand aucun contrat n'a été
lu. Un accès validé ne prouve pas que toutes ses données sont accessibles.

Légende état : **RÉEL** = appelé au runtime · **FIXTURE** = seulement rejoué
en test · **DÉCLARATIF** = configuré/affiché sans lecteur · **ABSENT** ·
**BLOQUÉ (config)** = adaptateur présent, clé/contact manquant.

| Fournisseur | Accès / configuration | Couverture | Données | Latence | Historique | Quotas / coûts | Droits (à confirmer sauf mention) | Cadence dans le code | État | Test réel |
|---|---|---|---|---|---|---|---|---|---|---|
| **IBKR (TWS/Gateway, ib_async 2.1.0)** | socket local 127.0.0.1, ports 7496/7497/4001/4002, `IBKR_HOST`/`IBKR_PORT`/`IBKR_CLIENT_ID` optionnels, `NO_IBKR=1` désactive ; **session « marché seulement »** `vertex/data_sources/ibkr_session.py` | actions US SMART/USD, options US, indices CBOE (SPX/VIX), CFD Dow, scanners `STK.US.MAJOR` | contrats, tickers, `reqMktData` (ticks 100/101/106/258), type de données 1→4, barres daily, chaînes (`reqSecDefOptParams`), dépêches (BRFG, DJ-N, DJ-RT, BRFUPDN), scanners, heure | live / différé / figé selon abonnement (`ECHELLE_DONNEES`) | `reqHistoricalData` 1 Y / 6 M / 2 Y daily RTH | pacing IBKR ; lignes de marché bornées ; tick 258 refusé sans abonnement (10358) ; news 321 sur fournisseurs non souscrits | usage personnel du titulaire, affichage et calcul ; **redistribution interdite** (Market Data Subscriber Agreement) | cotations continu (lots de 20, pause 15 s) ; indices stream + poll 12 s ; options 120 s ; radar 240 s ; news 60 s ; barres univers en tête du scan 30 min | **RÉEL** | 2026-09-06 : poignée de main sur 7496 (rôle `verification`, id 29), `reqCurrentTime` OK, aucune position ni valeur de compte détenue (`tests/test_ibkr_session_marche_seule.py`, niveau 4) |
| **Frontière IBKR** | `readonly=True` sur chaque site + verrouillage par liste blanche (`METHODES_MARCHE`) ; `IB.connect` n'a plus de site | — | interdits : compte, cash, NAV, positions, portefeuille, P&L, ordres, exécutions, `managedAccounts` | — | — | — | invariant produit | — | **PROUVÉ** (doublure + statique + socket réelle) | idem |
| **yfinance (Yahoo Finance, non officiel)** | aucune clé | actions, ETF, indices `^…`, futures `=F`, crypto `-USD`, monde partiel | barres daily, `.info` fondamentaux, `.calendar` résultats, chaînes d'options (repli), news, révisions, détenteurs, initiés | différé ~15 min | multi-années | throttle 429 mesuré ; backoff 3 lots vides → abandon (`terminal.py:400-413`) | **usage personnel, pas de redistribution ni usage commercial** (Yahoo ToS) | scan 30 min (repli après IBKR) ; calendrier 3 h ; fondamentaux 45 s puis 6 h ; news 60 s ; **à la requête** : corrélations, descriptions, profil, analystes, marques d'options (à corriger : réseau dans la requête UI) | **RÉEL** | instance QA 2026-09-05/06 : 513/517 titres scannés en différé |
| **Stooq** | aucune clé, CSV public (`vertex/data_sources/stooq.py`) | actions US `.us`, indices, or/argent/pétrole, BTC | barres daily (~1100 jours) | EOD | 3 ans | 6 threads max ; TTL 6 h | usage personnel, pas de redistribution | filet du scan uniquement | **RÉEL** | URL générique testée à la main : 404 (le module construit ses propres URL ; budget `stooq_budget` = UNKNOWN sur `/healthz`) |
| **SEC EDGAR** | `SEC_USER_AGENT` **obligatoire** (contact réel exigé par le fair-access) + `VERTEX_ENABLE_SEC=1` | émetteurs US (ticker → CIK) | faits XBRL `companyfacts` datés (`end`, `filed`), point-in-time | EOD | complet | fair-access 10 req/s ; code borné à 30/min ; TTL 6 h / table 24 h | domaine public, UA de contact exigé | route `/api/sec/fondamentaux/<sym>` servie par magasin (fond, `attendre=False`) | **BLOQUÉ (config)** : `SEC_USER_AGENT` absent du `.env` (l'humain doit saisir son propre contact) ; `VERTEX_ENABLE_SEC` absent de `.env.example` | 2026-09-06 : 403 sans UA, 200 avec UA de test → l'API répond ; non consommé par la page Analyse |
| **FRED (Federal Reserve Bank of St. Louis)** | API : `FRED_API_KEY` requise (400 sans clé) ; **CSV public `fredgraph.csv?id=<série>` sans clé** | séries macro US et internationales | observations datées, révisions via ALFRED | quotidien/mensuel selon série | complet | fair use | FRED Terms of Use : affichage et usage personnel OK, attribution ; redistribution limitée | **aucune** (adaptateur ABSENT au 2026-09-06 ; à créer) | **ABSENT → à implémenter** | 2026-09-06 : `fredgraph.csv?id=DGS10` 200 (268 Ko) ; API sans clé 400 |
| **BCE (ECB Data Portal, API SDMX)** | aucune clé ; `data-api.ecb.europa.eu/service/data/<flux>/<clé>?lastNObservations=N&format=jsondata` | zone euro : taux directeurs, EURIBOR, change, inflation | observations datées SDMX | quotidien/mensuel | complet | fair use | licence BCE : réutilisation libre avec attribution | aucune (ABSENT) | **ABSENT → à implémenter** | 2026-09-06 : `FM/B.U2.EUR.4F.KR.MRR_FR.LEV` 200 (3,9 Ko) |
| **BNS (data.snb.ch, API cube)** | aucune clé ; `data.snb.ch/api/cube/<id>/data/json/en` | Suisse : taux directeur, courbes, change, inflation | cubes JSON datés | quotidien/mensuel | complet | fair use | conditions BNS : réutilisation avec mention de la source | aucune (ABSENT) | **ABSENT → à implémenter** | 2026-09-06 : cube `snbgwdzid` 200 (656 Ko) |
| **Courbe de taux (dérivée)** | aucune ; dérivée du scan yfinance `^IRX/^FVX/^TNX/^TYX` (`courbe_taux.py`, `rates.py`) | Trésor US | 4 points + interpolation ; **repli plat 4,5 % marqué `fallback_used`** | EOD | — | — | — | lue depuis `scan_state['macro']` | **RÉEL (dérivé)** | — |
| **TradingView (webhooks signés)** | `TRADINGVIEW_WEBHOOK_SECRET` (ou `TRADINGVIEW_SECRET`) | symboles libres | signaux typés `ALLOWED_SIGNALS`, payload borné 12 champs / 256 car. | événementiel | mémoire (500 max) | 30/min ; anti-replay 15 min ; dédup 10 min | signaux de l'utilisateur ; aucune API générale supposée ; aucun scraping | push entrant ; `/api/tradingview/signals` | **RÉEL, non configuré** (secret absent → 503 honnête) | — |
| **TradingView (widgets d'affichage)** | client-side sur `/titre/<sym>` | — | graphique widget | — | — | — | conditions des widgets TradingView (affichage seulement) | — | RÉEL (affichage) | — |
| **Google News RSS** | aucune | tout ticker | titres, liens, éditeur | différé | — | timeout 6 s ; taille bornée | affichage titres + liens ; pas de redistribution | repli news 60 s après IBKR puis yfinance | **RÉEL** | — |
| **Google Translate (endpoint non officiel `translate_a/single`)** | aucune | — | traduction EN→FR de titres | — | — | timeout 8 s | **hors API officielle** ; sortie de texte externe non déclarée dans `.env.example` | à chaque titre non caché sans clé Anthropic | **RÉEL (à documenter ou remplacer)** | — |
| **Wikipedia (constituants S&P/NDX/Dow)** | aucune | listes d'indices | tickers | hebdo | — | UA navigateur | CC BY-SA (attribution) | cache fichier | RÉEL | — |
| **Anthropic (Claude)** | `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL` / `VERTEX_AI_MODEL` | — | briefs, copilote, traduction, `web_search` avec citations | — | — | budget interne `gateway.allow` ; facturé | conditions API Anthropic ; positions déclarées seulement sur consentement | à la demande | **RÉEL, non configuré** (clé absente : synthèse déterministe servie, enrichissement « indisponible ») | — |
| **Portefeuille déclaré** | `desk_data.json` local (gitignoré) | — | positions, capital, journal, alertes, notes | — | — | — | propriété de l'utilisateur ; jamais écrasé par une source externe | à la saisie | **RÉEL, saisie seule** | — |

## Écarts de configuration et de droits relevés

- `IBKR_ACCOUNT_ID` et `IBKR_MARKET_DATA_MODE` sont proposés dans
  `.env.example` et validés par `config_validation.py` mais lus nulle part ;
  le texte « compte détecté automatiquement » promet une lecture de compte
  contraire à l'invariant. À retirer.
- `.env.example` propose `IBKR_CLIENT_ID=41`, identifiant du worker options :
  collision garantie avec la passerelle si copié tel quel.
- Rôles `ibkr_link.CLIENT_IDS['compte']` (preuve de socket seulement) et
  `['pnl']` (aucun consommateur) : à renommer / retirer après preuve d'absence
  de consommateur.
- Réseau dans des requêtes utilisateur : **corrigé** (tranches réseau hors
  requête) — `/api/analyst`, `/api/company`, `/api/correlations`,
  `/api/pos-quotes`, dossier options (`chaine_a_la_demande.board_avec`) servent
  le cache et collectent en fond (`EN_COURS`/`CACHE`/`PERIME`) ; gardien
  `tests/test_reseau_hors_requete.py`.
- Aucun masque d'identifiant de compte sur les journaux `ib_async`
  (métadonnées de protocole) : les identifiants sont désormais effacés de la
  session à la connexion ; un filtre de journal reste à ajouter.

## Composants candidats évalués (mission §6, plan P4)

Décision par composant, sur besoin mesuré ; rien n'est installé « par
principe ». Versions retenues épinglées dans `requirements*.txt`.

| Composant | Besoin couvert ? | Décision |
|---|---|---|
| Playwright (`playwright==1.62.0`, déjà en `requirements-dev.txt`) + Chromium | Les gardiens navigateur (`tests/test_qa_espaces.py`, `test_couche_visuelle.py`, `test_boutons_morts_temoins.py`) s'abstenaient : binaire Chromium absent (`BINAIRE_ABSENT`). | **Installé** : `python -m playwright install chromium` dans le cache utilisateur Playwright (hors dépôt) ; les gardiens mesurent désormais réellement. CI : `ci.yml` installe `requirements-dev.txt` mais pas le navigateur — à décider (coût de téléchargement par exécution). |
| feedparser | RSS Google News parsé par `news_plus.parse_rss` (maison, testé sur fixtures, assainissement au point de sortie). | **Non installé** : aucun flux réel en échec ; à reconsidérer si un flux Atom/RSS non conforme apparaît (P5 le vérifie sur les communiqués BCE/BNS). |
| trafilatura | Extraction de texte d'articles : Vertex résume des titres/descriptions, ne recopie pas d'articles entiers (mission §11). | **Non installé** : pas de besoin ; l'extraction pleine page poserait la question des droits. |
| firecrawl, changedetection.io | Surveillance de pages : les sources retenues sont des API/RSS/CSV officiels ; aucune page HTML à surveiller n'est au contrat. | **Non installés** ; service externe/conteneur non nécessaire. |
| OpenBB | Agrégateur multi-sources : redondant avec les connecteurs directs (IBKR, yfinance, FRED, BCE, BNS) et ajoute une couche de droits opaque. | **Non installé**. |
| Prefect, n8n (+ skills n8n, n8n-mcp) | Orchestration : les boucles du monolithe + registre des jobs + diffuseur SSE suffisent (décision D1 de la nuit) ; un second orchestrateur créerait deux autorités. | **Non installés**. |
| OpenTelemetry | Observabilité : Système › Jobs, `/healthz`, `/readyz`, battements et journaux bornés couvrent le besoin local. | **Non installé** ; à reconsidérer pour un déploiement serveur. |
| ib_async | Déjà en production (`>=1.0`, 2.1.0 installé) ; session marché seulement prouvée sur socket. | Épinglage exact `==2.1.0` : **décision humaine** (le comportement au connect dépend de la version). |
| lightweight-charts (TradingView) | Graphiques : `chart-core.js` + Chart.js/SVG maison couvrent les 72 cartes ; une bibliothèque n'est pas une source de données. | **Non installé**. |
| playwright-cli / playwright-mcp / skills webapp-testing, superpowers, firecrawl skills | Outils d'agent : le skill maître interdit un second skill actif ; les quatre skills de design restent consultatifs. | **Non installés** (documenté dans `.claude/design-skills/SOURCES.md`). |

## Configuration d'exemple (sans valeurs)

```
SEC_USER_AGENT="Vertex <prenom.nom@domaine>"   # contact réel exigé par la SEC
VERTEX_ENABLE_SEC=1
FRED_API_KEY=                                   # optionnel : sans clé, CSV public fredgraph
TRADINGVIEW_WEBHOOK_SECRET=                     # optionnel
ANTHROPIC_API_KEY=                              # optionnel (facturé)
```
