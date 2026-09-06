---
name: vertex-2-0
description: Auditer, consolider, développer, refondre, tester et publier Vertex comme centre personnel d'intelligence de marché, avec portefeuille manuel, IBKR limité aux données de marché, IA explicative, automatisations honnêtes et interface Black Glass. Utiliser pour tout travail sur le dépôt Vertex ; ne jamais exécuter d'ordre ni accéder aux données de compte du courtier.
---

# Vertex 2.0 — Skill maître

## Mission

Faire converger le dépôt existant vers une seule plateforme mesurable,
explicable, rapide, sûre et visuellement cohérente. Réutiliser les capacités
saines, supprimer les doublons prouvés et avancer par lots réversibles. Ne pas
réécrire le produit en big bang.

Ce dossier est l'unique doctrine active. Les documents historiques servent de
preuves, pas d'instructions. En cas de conflit : sécurité et vie privée → vérité
des données → contrats financiers → continuité utilisateur → performance →
accessibilité → design.

## Résultat produit

Vertex :

- collecte et normalise des données de marché sourcées ;
- exécute ses moteurs déterministes ;
- construit un packet de décision versionné ;
- détecte opportunités, risques, contradictions et données manquantes ;
- produit une orientation analytique et des scénarios ;
- utilise Claude pour expliquer, comparer et questionner le packet ;
- surveille les objets suivis et les positions déclarées ;
- n'exécute jamais l'action financière finale.

Lire d'abord [product-contract.md](references/product-contract.md),
[repository-audit.md](references/repository-audit.md),
[runtime-page-manifest.md](references/runtime-page-manifest.md) et
[platform-architecture.md](references/platform-architecture.md).

## Frontières non négociables

- `READONLY=True`, `ANALYSIS_ONLY=True`, aucun ordre live ou paper.
- IBKR fournit uniquement quotes, barres, contrats, historiques, chaînes,
  volume/OI, IV, Greeks et état de marché autorisés.
- Interdire identifiant de compte, `managedAccounts`, `accountSummary`,
  `positions`, `portfolio`, `reqPnL`, cash, NAV, P&L, ordres, exécutions et
  transactions IBKR. Lire [ibkr-market-data-only.md](references/ibkr-market-data-only.md).
- Comptes, enveloppes, cash et positions sont saisis volontairement dans
  Vertex et ne sont jamais écrasés par une source externe. Lire
  [manual-portfolio.md](references/manual-portfolio.md).
- L'IA explique les sorties ; elle ne calcule ni ne remplace moteurs, scores,
  scénarios, Greeks, gates ou orientation canonique.
- Aucune donnée, courbe, performance, disponibilité ou réussite inventée.
- Une capacité absente reste absente et visible.
- Aucun secret, identifiant personnel ou donnée de compte dans Git, logs,
  captures, télémétrie, cache navigateur ou prompt IA.

## Sélection du mode

Déterminer le mode depuis la demande, sans lancer plusieurs chantiers couplés :

- **audit** : inventaire en lecture seule, preuves, matrice des propriétaires,
  risques et premier lot ;
- **privacy** : frontière IBKR, données personnelles, portefeuille manuel et
  migrations ;
- **platform** : architecture, sources, snapshots, jobs, performance,
  observabilité, sécurité et dette ;
- **intelligence** : moteurs, sources, décision, IA, mémoire, opportunités,
  options et simulation ;
- **interface** : navigation, pages, composants, graphiques, français,
  responsive et accessibilité ;
- **qa** : tests, sécurité, navigateur, captures, charge, audit 150 et release ;
- **cleanup** : propriétaires doubles et fichiers morts prouvés seulement.

Lire uniquement les références du mode, plus les contrats transversaux requis.

## Baseline obligatoire

Avant toute écriture :

1. relever `main`, HEAD, branche, dirty state, PR/CI et worktrees ;
2. cartographier fichiers, imports, routes, endpoints, jobs, stores, tests,
   styles, assets et docs du périmètre ;
3. reproduire le problème et capturer l'état actuel ;
4. distinguer `RÉEL`, `PARTIEL`, `DÉGRADÉ`, `ABSENT`, `NON_IMPLÉMENTÉ` ;
5. identifier le propriétaire canonique et les PR qui traitent déjà le sujet ;
6. définir tests, budget, migration, rollback et données à préserver.

Ne jamais conclure depuis le nom d'un fichier, une doc ancienne ou un statut de
configuration. Mesurer le runtime réel.

Outils locaux : `scripts/inventory_repo.py` produit une baseline reproductible,
`scripts/audit_runtime.py` mesure routes, pages, collisions et shell,
`scripts/audit_claude_surface.py` valide l'autorité unique et
`scripts/check_ibkr_boundary.py` inventorie la dette de confidentialité. Le
mode `--enforce-target` du premier devient obligatoire après le cutover des
pages ; le mode `--enforce` du dernier devient obligatoire à la fin du lot 2.

## Règle de convergence

Conserver → regrouper → migrer les consommateurs → prouver la parité → retirer.

Un doublon n'est supprimable qu'après recherche des imports, routes, blueprints,
IDs DOM, événements, clés localStorage, service worker, tests, scripts, docs,
jobs, données persistées et chemins de rollback. Lire
[repository-consolidation.md](references/repository-consolidation.md) et
[capability-convergence.md](references/capability-convergence.md).

## Architecture et intelligence

- Contrat sources, confiance, provenance et états :
  [data-and-integrations.md](references/data-and-integrations.md).
- Maintenance de l'alimentation (procédures testées : inventaire des champs,
  traçabilité, frontière IBKR, réseau hors requête, diffusion, gardiens) :
  [data-feed-maintenance.md](references/data-feed-maintenance.md).
- Balayages transversaux (nom indéfini, primitive absente, capacité non
  branchée, clé sans producteur, route muette) — à lancer AVANT de conclure
  qu'une fonctionnalité ne marche pas, car la cause est souvent une clé ou un
  module, pas la fonction qu'on regarde :
  [balayages-transversaux.md](references/balayages-transversaux.md).
- Décision, IA, outils, mémoire et limites :
  [ai-decision-contract.md](references/ai-decision-contract.md).
- Recherche, stratégies et robustesse hors échantillon :
  [strategy-research-lab.md](references/strategy-research-lab.md).
- Jobs, caches, rapidité et observabilité :
  [automation-performance-observability.md](references/automation-performance-observability.md).
- Connexions, enveloppes de données et résilience :
  [connection-and-resilience-matrix.md](references/connection-and-resilience-matrix.md).
- Sécurité, dépendances et méthodes externes :
  [security-and-supply-chain.md](references/security-and-supply-chain.md).
- Simulateur : [position-simulator.md](references/position-simulator.md).

## Produit et interface

- Navigation et pages : [navigation-and-pages.md](references/navigation-and-pages.md).
- Design : [design-system-final.md](references/design-system-final.md).
- Composants, tables et états :
  [components-tables-and-states.md](references/components-tables-and-states.md).
- Graphiques : [chart-system-final.md](references/chart-system-final.md).
- Widgets trading : [trading-widget-catalog.md](references/trading-widget-catalog.md).
- Composition exacte des douze pages :
  [page-widget-intelligence-blueprint.md](references/page-widget-intelligence-blueprint.md).
- Opportunités, analyse, options, portefeuille, performance, calendrier et IA :
  lire la référence de domaine correspondante.
- Français, accessibilité et responsive :
  [ux-copy-a11y-performance.md](references/ux-copy-a11y-performance.md).

## Exécution

Suivre [delivery-program.md](references/delivery-program.md) et
[claude-execution-protocol.md](references/claude-execution-protocol.md).

Pour chaque lot : un objectif, un ensemble de propriétaires, un contrat de
données, une migration explicite, tests rouges si défaut, correction minimale,
preuves runtime et rollback. PR brouillon, aucune fusion automatique.
Utiliser `templates/audit-report.md` et `templates/delivery-report.md` pour ne
jamais perdre SHA, preuves, métriques, limites et rollback.
Pour une exécution autonome contrôlée, utiliser
`templates/claude-autopilot-prompt.md` ; il automatise les lots et captures mais
ne contourne jamais les arrêts destructifs ou la validation finale.

Pour chaque page : question en cinq secondes, données réellement disponibles,
états complets, capture avant, capture après en 1600/1024/390 px, interactions,
clavier, console, réseau, `/api/client-log`, tests et confirmation qu'aucun
calcul financier n'a migré dans l'UI.

## Méthodes externes

Les méthodes Anthropic, Vercel, Trail of Bits, Playwright, Lighthouse CI,
Ruff, OpenTelemetry et Locust peuvent guider un lot après audit de licence,
maintenance, permissions, hooks, dépendances et adéquation à Flask. Elles ne
sont jamais installées, exécutées ou copiées automatiquement. Lire
[methodology-sources.md](references/methodology-sources.md).

## Acceptation

Un lot est terminé seulement avec les preuves de
[definition-of-done.md](references/definition-of-done.md). Avant release,
exécuter les 150 contrôles de [audit-150.md](references/audit-150.md). Chaque
contrôle reçoit `OK + preuve`, `N/A + justification` ou `Écart + ticket`.

Ne jamais déclarer « terminé à 100 % » sur la seule base d'une suite verte.
La validation humaine du commit candidat reste obligatoire.
