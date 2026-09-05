# Refonte coordonnée des dashboards et widgets — suivi

Branche : `ui/refonte-dashboards` (depuis `main` `ed363d67`, 2026-09-05).
Aucun commit, aucun push : la validation humaine décide.

## Skills utilisés (lecture, pas autorité)

Installés dans `.claude/design-skills/` — provenance, commits et licences dans
[`.claude/design-skills/SOURCES.md`](../.claude/design-skills/SOURCES.md).
Le skill maître `/vertex-2-0` reste l'unique autorité ; les quatre skills sont
des expertises consultatives. Le thème conservé est **Vertex Black Glass —
Signal Light** (`design-system-final.md`, `.interface-design/system.md`) :
il n'existe aucun document « Titan Ledger » ni skill `vertex-titanium-ledger`
dans le dépôt ; la direction existante est celle qui a été suivie.

| Skill | Rôle dans ce lot | Mode d'usage |
|---|---|---|
| kpi-dashboard-design (wshobson/agents `a30778f`) | ordre de lecture, priorités, regroupements, synthèse → détails | lecture + agent d'analyse |
| interface-design (Dammyjay93 `2f9be32`) | anatomie des cartes, proportions, espacements, tokens | lecture + agent d'analyse |
| ui-ux-pro-max (nextlevelbuilder `f3ac195`, 2.13.0) | responsive, tables, filtres, clavier, états | moteur de recherche local + agent d'analyse |
| impeccable (pbakaus `4bee58d`, skill 4.2.0) | critique, audit, layout, clarify, harden, adapt, polish | lecture des références (moteur binaire non exécuté, hooks non installés) |

Quatre analyses ont été produites en parallèle par quatre sous-agents en
lecture seule (un par skill), puis fusionnées en un seul plan ; un seul
implémenteur (l'orchestrateur) a modifié les fichiers.

## Baseline (avant modification)

- Suite complète : `4280 passed, 179 skipped` (`python -m pytest -q`, 3 min 43 s).
- `tests/test_no_orders.py` : 3 passed. `compileall` : OK.
- Instance QA : `tools/qa/run_qa_instance.py` (miroir du dépôt dans le
  répertoire temporaire, `NO_IBKR=1`, `DEMO=0`, sans verrou, `127.0.0.1:5003`,
  données différées yfinance, 513/517 titres scannés). Sert aux captures et
  dumps sans saisir le code d'accès ni toucher aux caches de l'instance live.
  Configuration `vertex-qa` ajoutée à `.claude/launch.json`.
- Dumps runtime : HTML rendu des 9 vues Options + dossier AAPL, réponses
  `/api/options/*` réelles (scratchpad de session, non versionné).
- Aucune capture n'était jointe au message de mission : les captures « avant »
  ont été prises sur l'instance QA (1600 et 390 px).

### Cause racine trouvée par les quatre analyses

Plus de vingt classes émises par les pages Options n'avaient **aucune règle
CSS servie** : `.vx-opt-hero-grid`, `.vx-opt-dims`, `.vx-opt-dim*`,
`.vx-opt-pulse`, `.vx-opt-chip`, `.vx-demo-tag`, `.vx-explain`, `.vx-grid2`
(perdues avec `neon-glass.css`, lot 24, commit `9c0fe082`) ; `.vx-hero-grid`,
`.vx-hero-main`, `.vx-insight-rail` (base), `.vx-disclosure`, `.vx-stats-row`,
`.vx-table-primary`, `.vx-row-open`, `.vx-readonly-shield`, `.vx-section-stack`,
`.vx-card-foot`, `.vx-data-ledger` (présentes au commit `fcc41cd2`, perdues
ensuite) ; `.vx-empty`, `.vx-card-body` (jamais définies). Conséquences
mesurées : jauge seule au centre d'une carte pleine largeur, « Volatilité66 »
(libellé/valeur collés, barre invisible), hero et rail empilés à 1600 px,
dix tuiles GEX en colonne, `<details>` nus, « NVDACALL · 2027-03-19 » collé.

## Modifications, page par page

### Options — Vue d'ensemble (`/options?view=overview`)

- Composition : zone de décision (environnement `vx-col-8` + lecture dominante
  `vx-col-4`), bande de six indicateurs, table des meilleurs contrats. Quatre
  cartes identiques pleine largeur auparavant. Squelettes à la hauteur
  réservée par zone (200 / 100 / 280 px) au lieu d'un gabarit unique de 120 px.
- Carte d'environnement : jauge (sans halo) + libellé **moteur** (Porteur /
  Mitigé / Hostile, plus de relecture par seuils 40/60 côté client) + lecture
  `dominant_reading` du moteur + badge `partial` « 2/5 dimensions mesurées »
  + confiance. Cinq dimensions en lignes libellé | barre | valeur | note ; une
  dimension non mesurée n'a **aucune barre remplie** (absence ≠ zéro) et porte
  la note du moteur (« non mesuré · IV rank indisponible »). Sous 1440 px la
  note passe sous sa ligne ; sous 1180 px le hero et le rail s'empilent.
- Lecture dominante : badge de statut, confiance, phrase, impact, **preuves
  pour/contre inline** (+ / −), estampille source · heure.
- Indicateurs clés : six tuiles `VX.tile.metric` avec ligne de contexte
  (`meta`) — Contrats (titres, OI moyen), CALLS / PUTS (ratio), IV moyenne
  (médiane, min–max, état), Qualité moyenne (bande moteur), Spread moyen
  (« non disponible sur ce scan » quand nul), DTE moyen (theta moyen en %/j de
  prime). Les neuf pastilles dupliquées du hero ont disparu. Barre CALL/PUT :
  CALL = argent, PUT = violet (un type de contrat n'est ni un gain ni une
  perte) ; la consigne « biais de la Stratégie Vertex » sort de la légende.
- Meilleurs contrats : six lignes (au lieu de quatre), colonnes numériques
  `vx-num` alignées à droite en mono, échéance en date française + horizon,
  coût, micro-barre partagée, `th scope="col"`, en-tête d'action nommé,
  bouton « Suivre » avec `aria-label` complet (comportement conservé),
  population et source sous la table (« 6 contrats affichés sur 126 »),
  cartes-lignes à ≤ 720 px via `data-label`.
- Actions : « Comprendre ce score » / « Comprendre cette lecture » sur la bonne
  carte (plus de « Comprendre ce graphique » sur des cartes sans graphique) ;
  le tiroir canonique `VX.shell.openDrawer` remplace la modale de repli.
- Scénarios (vue Scénarios) : libellés STOP/BEAR/FLAT/BASE/TP1-3 rendus en
  français, colonne « Gain J+N » datée sur l'horizon réellement présent.

### Options — autres vues

- Structure / Volatilité / Positionnement : hero 7 col + rail 5 col
  (`.vx-hero-grid` restaurée), disclosures avec résumé de 44 px, dimensions
  LEAPS lisibles ; « Insufficient » → « Insuffisant », « DELAYED » → « Différé ».
- Positionnement : radar GEX activable au clavier (Entrée/Espace, nom
  accessible « Analyser le positionnement de NVDA »), `data-label` pour les
  cartes mobiles, unité $ en en-tête, montants en fr-FR (« 5,65 M$ »),
  légende du spot exacte (cyan analytique, plus « orange »), défilement doux
  respectant `prefers-reduced-motion`, tuiles en grille (`.vx-stats-row`).
  Erreur console préexistante corrigée (`insertBefore` sur un parent qui
  n'était pas celui de la cible, vue entière en erreur).
- Scanner LEAPS : nombres en fr-FR, raisons hors-mandat lisibles sous le badge
  (depuis `mandate_reasons` du moteur quand présent), `aria-pressed` sur les
  univers, « n/a » → « — » / « non disponible », cause de P(doubler) affichée.

### Dossier titre (`/options/dossier/<sym>`)

- Trois anneaux lumineux remplacés par trois tuiles (« Meilleure qualité »,
  « Meilleure PoP », « IV médiane ») avec leur population (« N contrats au
  tableau ») ; mêmes chiffres, aucun calcul nouveau.
- « Les options sont-elles chères ? » lit désormais l'interprétation
  volatilité du moteur (`/api/options/volatility/<sym>`) : statut, confiance,
  lecture, impact, incertitudes — au lieu d'une regex sur le texte de la
  structure par terme. Un statut INCONNU s'affiche avec ses causes.
- Emplacements de graphiques vides → carte d'état avec cause (« Une seule
  échéance dans le tableau ») au lieu d'un rectangle blanc.
- Chaîne : en-têtes nommés, « pourquoi » du moteur lisible sous le type (plus
  seulement au survol), tri annoncé, boutons « Suivre » nommés.
- Faux bouton `<span aria-current>` remplacé par un badge « Mode : options ».

## Composants partagés créés ou améliorés

| Composant | Fichier | Changement |
|---|---|---|
| `VX.tile.microbar` | `vx-core.js` | nouvelle micro-barre (chiffre porteur, barre `aria-hidden`), remplace deux copies inline |
| `VX.tile.metric` | `vx-core.js` | option `meta` (ligne de contexte, échappée) |
| `VXCharts.gauge` | `chart-core.js` | plus de `drop-shadow` permanent, bille en jeton d'encre |
| `.vx-hero-grid`, `.vx-insight-rail`, `.vx-section-stack` | `layout.css` | bases restaurées (7/5) |
| `.vx-disclosure`, `.vx-readonly-shield`, `.vx-card-body/-foot`, `.vx-demo-tag`, `.vx-data-ledger` | `components.css` | restaurées / définies |
| `.vx-table-primary`, `.vx-row-open`, `.vx-microbar` | `tables.css` | restaurées / nouvelle |
| `.vx-stats-row` | `cockpit.css` | restaurée |
| `.vx-empty` | `states.css` | définie |
| §32 `.vx-opt-*`, `.vx-explain`, `.vx-grid2`, `.vx-scenario*` (options), `.vx-table-stamp`, `.vx-verdict-evidence`, focus visible unifié, unités en `--vx-smoke`, `.vx-btn-sm` ≥ 32 px, libellés de tuile sur deux lignes | `vertex-2-0.css` | nouvelle section |

Ces bases servent toutes les pages qui émettaient déjà ces classes (Analyse,
Marchés, Portefeuille, Performance, Aujourd'hui…) : c'est la généralisation
naturelle du pilote.

## Décisions de design (arbitrages entre les quatre analyses)

1. Jauge demi-lune conservée (composant partagé), halo retiré, une seule
   bande colorée par le libellé moteur — plutôt qu'une jauge linéaire nouvelle.
2. Ordre de lecture : décision (score + lecture) → indicateurs → table, comme
   demandé (« synthèse → indicateurs clés → analyses → tableaux »).
3. Cartes `.vx-card` conservées (IDs, tests) plutôt que migrées vers
   `vx2.surface` ; titres de carte en capitales conservés (règle globale,
   hors périmètre d'un lot Options).
4. CALL = argent, PUT = violet partout sur la Vue d'ensemble et le dossier ;
   vert/rouge réservés aux valeurs signées (net GEX, gains).
5. « Suivre » garde sa redirection vers le suivi après succès (comportement
   réel conservé) ; seuls le nom accessible et l'état de chargement changent.
6. Les onglets (10 + Chaîne) ne sont pas regroupés dans ce lot (changement
   de navigation, pas de refonte visuelle) ; consigné ci-dessous.
7. Aucun seuil recodé côté client n'a été ajouté ; les seuils préexistants
   (66/45 des micro-barres) restent inchangés, dans un helper unique.

## Tests

- Nouveau : `tests/test_refonte_dashboards.py` (42 contrôles : classes
  orphelines, bases restaurées, composition de la Vue d'ensemble, absence
  ≠ zéro, lecture moteur, couleurs CALL/PUT, table nommée, micro-barre
  partagée, jauge sans halo, formats fr-FR, clavier GEX, dossier, versions).
- Mis à jour : pins de version du service worker (`td-shell-v290`) dans
  `test_redesign_ui`, `test_design_system_page`, `test_production_guards_canonical`,
  `test_ui_v3` ; empreinte des assets et version dans `test_sw_cache_scope` ;
  `test_options_structure_06` (« Insuffisant » en français).
- Résultats exacts : baseline `4280 passed, 179 skipped` → après refonte
  `4322 passed, 179 skipped, 0 failed` (42 tests ajoutés, aucun retiré).

## Limites, anomalies préexistantes, blocages

- **Anomalies métier (non corrigées, hors refonte visuelle)** : l'API
  n'appelle jamais `score_environment` avec `iv_rank` (`options_intel_api.py:94`,
  `overview.py:75`) → la dimension « IV rank » est structurellement absente
  (`NON_IMPLÉMENTÉE`), pas seulement indisponible ; `options-structure.js`
  calcule verdict, liquidité, mouvement attendu et score LEAPS côté client
  (`computeVerdict`, `liqState`, `expectedMove`, `leapsScore`) ; `paintScorecard`
  agrège côté client ; `vol-charts.spot` est nul alors que `chain.spot` est
  renseigné ; les trois blocs IBKR du dossier restent vides sans TWS.
- Fraîcheur de la barre de contexte : sur Vue d'ensemble / Radar / Positions
  elle affiche « Aucune donnée datée sur cette vue » car `as_of` du scan est
  une heure sans date ; la source et l'heure sont désormais écrites sous les
  tables et la lecture dominante.
- Onglets : dix onglets + Chaîne ; le dernier peut sortir de l'écran entre
  ~770 et ~1040 px (barre défilante).
- Captures : prises sur l'instance QA (données différées yfinance, pas IBKR
  live) ; le bundle CSS est immuable par version — un navigateur ayant déjà
  chargé `vx-shell-3` pendant le développement doit vider son cache HTTP
  (fait pour les vérifications).
- Le moteur binaire d'Impeccable n'a pas été exécuté (téléchargement d'un
  binaire) ; ses commandes ont été appliquées par lecture des références.

## Avancement

- [x] Installation et lecture des quatre skills
- [x] Baseline tests + instance QA + captures avant
- [x] Quatre analyses (KPI, Interface, UI/UX, Impeccable)
- [x] Plan commun et arbitrage des contradictions
- [x] Implémentation pilote Options (9 vues + dossier)
- [x] Généralisation des bases CSS partagées
- [x] Tests ciblés + nouveaux tests de non-régression
- [x] Vérification navigateur 1600 / 1280 / 1024 / 390, console contrôlée
- [x] Suite complète finale : `4322 passed, 179 skipped, 0 failed` (4 min 02 s) ; `tests/test_no_orders.py` : 3 passed ; `compileall` OK

## Points restants (prochaines actions)

1. Regrouper les onglets Options (niveau univers / niveau titre) — lot de
   navigation distinct.
2. Remonter les anomalies métier ci-dessus au propriétaire des moteurs.
3. Étendre la bande KPI avec `meta` aux pages Marchés / Portefeuille /
   Performance (les bases CSS sont déjà servies).
4. Grille strikes × échéances : `label` associé au `select`, colonne Strike
   collante en mobile.
