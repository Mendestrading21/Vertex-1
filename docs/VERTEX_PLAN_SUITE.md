# VERTEX_PLAN_SUITE — plan d'exécution des parties restantes de la mission « alimentation »

Base : branche `ui/refonte-dashboards` (PR brouillon #867, CI verte, suite
4474/180/0). Chaque tranche = un commit revertible, tests ciblés + suite
complète, preuve navigateur sur l'instance QA (port 5003, sans IBKR), puis
consignation dans `VERTEX_NIGHT_RUN.md` / `VERTEX_DATA_COVERAGE.md` /
`VERTEX_FINAL_REPORT.md`. Aucun secret. Aucune fusion automatique : la PR
sera passée « prête à relire », la fusion reste un clic humain
(CLAUDE.md, invariant 10).

| # | Tranche | Section mission | Problème mesuré | Livrable | Preuve | Rollback |
|---|---|---|---|---|---|---|
| P1 | **Diffusion réelle** | §13 | Le diffuseur SSE (`vertex/services/live_stream.py`, 9 canaux) n'a qu'un émetteur (macro officielle) ; toutes les autres cartes sondent (`VX.refresh`). | Émission SSE depuis les boucles du monolithe (scan → `market`, options → `options`, news → `market`/`news`, alertes → `alerts`, jobs → `jobs`), écoute côté pages (Aujourd'hui, Marchés, Analyse, Options, Système) : invalidation du cache client + rechargement des cartes concernées sans reload, états préservés (filtres, symbole, onglet). | test du courtier (événements émis par canal), test source des pages (écouteurs), QA : mise à jour observée sans rechargement après un scan | revert (les pages retombent sur le sondage) |
| P2 | **Actualités** | §11 | Chaîne existante (IBKR news + RSS Google) avec `dedupe_news` ; pas d'horodatage source uniforme ni de canal de diffusion ; provenance à vérifier carte par carte. | Horodatage source + réception + provenance sur chaque item, déduplication vérifiée par test (reprises d'une même dépêche), rattachement instrument, diffusion P1. | tests dédup/hors ordre, QA carte Actualités | revert |
| P3 | **Skill de maintenance** | §16 A | Aucune procédure de maintenance de l'alimentation dans le skill maître. | `.claude/skills/vertex-2-0/references/data-feed-maintenance.md` (inventaire des champs, traçabilité, frontière IBKR, tests obligatoires, checklists de tranche) + gardien qui exige la référence ; pas de second skill actif. | `audit_claude_surface.py` OK, gardien | revert |
| P4 | **Composants** | §6 | Aucun candidat évalué formellement. | Décision documentée par composant (`VERTEX_SOURCE_REGISTRY.md` §composants) ; installation seulement sur besoin prouvé : Playwright + Chromium dans `.venv` pour activer les tests navigateur aujourd'hui ignorés (preuve réelle), `feedparser` seulement si `parse_rss` maison échoue sur un flux réel. Versions épinglées. | tests navigateur non ignorés, journal d'installation | désinstallation, revert de `requirements-dev` |
| P5 | **Sources Suisse/Europe** | §11 | Couverture macro FRED/BCE/BNS faite ; aucune publication européenne (communiqués BCE/BNS) dans la page Publications. | Collecteur RSS des communiqués BCE et BNS (droits : réutilisation avec attribution), dédup P2, carte Publications datée par la source. | test fixtures réelles capturées, collecte réelle (`VERTEX_TEST_RESEAU=1`) | revert |
| P6 | **Stabilité** | §17 | Observations courtes (10 + 5 min). | Observation 60 min de l'instance de travail : mémoire, threads, files, reconnexions, erreurs ; consignée. | journal horodaté | — |
| P7 | **PR prête à relire** | §19 | PR brouillon. | Corps de PR à jour, `gh pr ready` (sortie du brouillon, pas de fusion), bilan final. | CI verte | `gh pr ready --undo` |

Hors plan (décision humaine) : `SEC_USER_AGENT`, secret TradingView, clé
Anthropic, épinglage `ib_async`, lot décision (contrat
`VERTEX_LOT_DECISION_CONTRAT.md`), regroupement des onglets Options, fusion.

Ordre : P1 → P2 → P3 → P4 → P5 → P6 → P7. Une tranche bloquée n'arrête pas
la suivante ; le blocage est consigné.
