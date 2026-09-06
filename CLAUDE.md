# CLAUDE.md — Vertex

## Autorité unique

Pour tout travail sur Vertex — audit, architecture, données, IA, marché,
options, portefeuille, automatisations, performance, sécurité, interface,
tests ou publication — utiliser exclusivement :

```text
/vertex-2-0
```

Skill maître : `.claude/skills/vertex-2-0/SKILL.md`.

Il n'existe aucun second skill actif, aucun alias de compatibilité et aucune
doctrine de page indépendante. Les anciens documents et noms de branches sont
des preuves historiques, jamais des instructions concurrentes.

## Produit

Vertex est un centre personnel d'intelligence de marché et d'aide à la
décision. Il collecte, vérifie, analyse, note, compare et explique. L'humain
reste le seul décideur et agit hors de Vertex.

Boucle canonique :

```text
OBSERVER → COMPRENDRE → DÉTECTER → ÉVALUER → ORIENTER
→ SURVEILLER → MESURER → APPRENDRE
```

Les moteurs déterministes produisent les calculs, scores, scénarios, gates et
orientations analytiques. Claude explique le packet existant, nomme les
contradictions et les inconnues ; il ne devient jamais le calculateur ou le
propriétaire du verdict.

## Invariants absolus

1. `READONLY=True` et `ANALYSIS_ONLY=True` restent vrais.
2. Aucun ordre live ou paper, transfert, exercice, ticket transmissible,
   bouton achat/vente ou automatisation d'exécution.
3. **IBKR est une source de données de marché uniquement.** Vertex ne lit,
   n'importe, n'affiche ni ne rapproche jamais identifiant de compte, solde,
   cash, NAV, positions, portefeuille, P&L, ordres, exécutions ou historique
   IBKR.
4. Les comptes et positions Vertex proviennent exclusivement des déclarations
   volontaires de l'utilisateur. Une source externe ne les écrase jamais.
5. Aucune donnée financière inventée. Absence, zéro, estimation, retard,
   fallback, démo et erreur restent distincts.
6. Toute valeur critique conserve source, timestamp, fraîcheur, qualité,
   unité et limites.
7. L'IA n'invente ni prix, prime, Greek, probabilité, score ou source ; elle ne
   contourne jamais un hard gate.
8. Une capacité non implémentée est nommée `NON_IMPLÉMENTÉE`, jamais présentée
   comme une automatisation en attente.
9. Aucun nettoyage par nom ou ancienneté : supprimer seulement après preuve
   d'absence d'import, route, test, consommateur, donnée ou rollback utile.
10. Une PR reste brouillon et n'est jamais fusionnée automatiquement.

## Architecture de travail

Le runtime ne respecte pas encore tous ces invariants. La règle reste
entière : ne jamais prétendre qu'un défaut est corrigé parce que ce contrat
l'interdit — il faut une MESURE. Symétriquement, un défaut mesuré comme fermé
ne doit plus être décrit comme ouvert : une doctrine périmée envoie chercher
des fantômes et fait perdre la confiance dans le reste du texte.

État MESURÉ au 2026-09-06, chaque ligne reproductible :

| P0 du programme | État | Preuve |
| --- | --- | --- |
| lectures de compte / positions IBKR | fermé | `check_ibkr_boundary.py --enforce` OK ; verrou vérifié sur un objet `IB` réel, façade ET client bas niveau, zéro méthode interdite appelable |
| collisions de routes | fermé | `tools/qa/exercer_routes.py` : 0 sur 184 règles, groupées par (chemin, méthode) ; gardé par `tests/test_routes_sans_collision.py` |
| plusieurs autorités de décision | en cours | le plan de travail des positions passe par `decision_packet.build` ; d'autres doublons restent à chercher |
| jobs déclaratifs | en cours | les capacités sans exécuteur trouvées à ce jour portent `ETAT = NON_IMPLÉMENTÉ` (`scanner/stages.py`, `ai/tool_registry.py`) |

Ce tableau se met à jour avec une mesure, jamais avec une intention.

- Entrée locale : `python -m vertex`.
- WSGI : `vertex.runtime:app`.
- `terminal.py` reste un adaptateur historique à réduire par strangler pattern ;
  ne pas y ajouter une nouvelle capacité sauf correctif bloquant avant
  extraction.
- Une page sert des snapshots bornés ; elle ne lance pas une collecte réseau
  lente dans la requête utilisateur.
- Un propriétaire canonique par capacité, route, métrique, composant et job.
- Une PR cohérente par lot : ne pas mélanger frontière IBKR, migration de
  données, moteur financier, refonte globale et nettoyage sans rapport.

## Identité visuelle

Direction unique : **Vertex Black Glass — Signal Light**.

- obsidienne et graphite, verre noir, argent et blanc cassé ;
- Geist pour l'interface, Geist Mono pour tickers, prix et mesures ;
- vert = positif, rouge = risque/négatif, ambre = prudence ou dégradation ;
- violet = options, cyan = focus technique exceptionnel ;
- une lumière dominante maximum par carte, deux par écran hors rouge/vert ;
- bordures presque invisibles, aucun glow permanent, aucun arc-en-ciel,
  aucun template SaaS ou esthétique casino ;
- tout le texte visible en français clair.

## Navigation cible

- **Piloter** : Aujourd'hui, Calendrier.
- **Explorer** : Marchés, Opportunités, Analyse, Options, Simulateur.
- **Gérer** : Portefeuille, Suivi, Performance.
- **Intelligence** : Vertex IA.
- **Utilitaire** : Système.

Une page cible n'est activée que lorsque ses routes, données, états et tests
existent réellement. Sinon Claude conserve l'accès existant et documente le
manque sans fabriquer de façade.

## Workflow obligatoire

1. Partir du dernier `main`, relever SHA, état Git, PR ouvertes, CI et dette
   déjà prise en charge.
2. Lire le code, les tests et les consommateurs avant le document historique.
3. Établir une baseline reproductible avant de modifier.
4. Choisir le premier lot canonique non terminé dans le skill maître.
5. Écrire le contrat du lot : problème, propriétaires, données, risques,
   tests, preuves visuelles et rollback.
6. Implémenter le changement minimal cohérent.
7. Vérifier compile, tests ciblés, suite complète, sécurité, navigateur,
   états dégradés, performance et données.
8. Pour chaque page modifiée, produire captures avant/après en 1600, 1024 et
   390 px, avec console et `/api/client-log` contrôlés.
9. Ouvrir ou mettre à jour une PR brouillon ; attendre la décision humaine.

## Validation minimale

```bash
python -m compileall -q terminal.py vertex
python -m pytest -q
python -m pytest tests/test_no_orders.py -q
```

Ajouter les contrôles du domaine modifié et les 150 contrôles finaux du skill.
Une suite verte ne remplace ni la preuve navigateur, ni la preuve des données,
ni l'acceptation humaine.
