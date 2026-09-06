# VERTEX — audit complet, page par page, et ce qu'il a réparé

Nuit du 2026-09-06. Ce document répond à trois questions, dans cet ordre :
qu'est-ce qui ne marchait pas, comment on le sait, et qu'est-ce qui reste.

Il ne contient aucun chiffre qui n'ait été mesuré. Quand une mesure a démenti
une hypothèse — la mienne comprise — c'est la mesure qui est écrite.

## 1. Ce qui a été fait

Deux campagnes se sont succédé.

**Un troisième tour de correction** sur les fichiers croisés laissés hors
périmètre par les tours précédents : quatre lots, quatre contrôleurs adverses.
Verdicts : un SOLIDE, trois PARTIELS. Les six défauts trouvés par les
contrôleurs sont détaillés dans
[VERTEX_TOUR3_CORRECTIONS.md](VERTEX_TOUR3_CORRECTIONS.md) ; le plus grave
laissait le plan de travail des positions franchir une garde dure au moyen
d'une autorisation qu'il s'accordait à lui-même.

**Un audit complet** ensuite : douze lots taillés sur des périmètres de
fichiers disjoints — cinq groupes de pages, la coque, les routes, les moteurs,
les sources — chacun suivi d'un contrôleur chargé de *réfuter* son travail,
pas de le confirmer. Les contrôleurs ont trouvé, dans presque chaque lot, une
régression que le lot avait introduite, et l'ont corrigée avec sa mesure.

En parallèle, cinq balayages transversaux ont cherché la famille de défauts
qu'aucun test unitaire ne voit : ceux qui vivent **entre** les modules.

## 2. La forme des défauts trouvés

Aucun des défauts majeurs n'était un calcul faux. Tous étaient des **absences
silencieuses** — quelque chose qui manque sans le dire, et qui se lit donc
comme une réponse.

| Forme | Exemple mesuré |
| --- | --- |
| une garde qui s'autorise elle-même | le plan de travail des positions posait `reconciliation: {'actionable_allowed': True}` en dur ; sur un rapprochement qui INTERDIT d'agir, il rendait « RENFORCER » quand la route canonique rendait « ATTENDRE » |
| un zéro imputé lu comme une observation | un intérêt ouvert absent devenait `0`, donc « liquidité insuffisante », donc un contrat écarté par le scanner pour une raison jamais mesurée |
| une capacité annoncée et non branchée | 15 détections d'anomalies sur 42 ne pouvaient pas se déclencher ; le pipeline du scanner et le registre d'outils Claude ne sont appelés par aucun chemin |
| un nom qui n'existe pas | `_POS_TTL_S`, lu par le memo des cotations, défini nulle part — un plantage en attente, invisible sans IBKR |
| une carte vide sans motif | quatre hôtes de graphique restaient littéralement vides dans TOUS les états dégradés, panne réseau comprise |
| une prose qui contredit sa sortie | la documentation d'une route déclarait `NON_IMPLÉMENTÉ` un canal que la même fonction sert `ACTIF` |
| une comparaison qui classe par forme | la récence des dépêches comparait des chaînes brutes : le `T` d'une date ISO battait l'espace d'une date courtier, donc l'événement fusionné héritait du plus ANCIEN |

## 3. Ce qui a été gagné, en chiffres

| Mesure | Avant | Après |
| --- | --- | --- |
| Actifs de première partie servis au navigateur | 791 ko en clair | 265 ko compressés (−67 %) |
| Routes exercées en échec, lentes ou muettes | 5 muettes, 1 « lente » | 0 |
| Collisions de routes | annoncées « deux » par la doctrine | 0 mesurée sur 184 règles |
| Modules jamais exécutés | inconnu | 4 sur 323, tous étiquetés |
| Noms indéfinis dans le paquet | 1 (plantage en attente) | 0 |
| Cartes-graphiques muettes | 1 exception, 1 carte vide | 0 |
| Canevas jamais dessinés | 0 | 0 |

## 4. Comment c'est vérifié

Cinq outils neufs, tous en lecture seule, tous documentés dans le
[runbook](VERTEX_RUNBOOK.md) et la
[doctrine](../.claude/skills/vertex-2-0/references/balayages-transversaux.md) :

- `balayage_statique` — nom indéfini, import mort, redéfinition silencieuse ;
- `primitives_manquantes` — une page appelle un graphique qu'elle ne charge pas ;
- `modules_non_atteints` — une capacité qu'aucun chemin n'exécute ;
- `cles_sans_producteur` — une clé lue que personne n'écrit ;
- `exercer_routes` — route en échec, lente, muette, ou à deux propriétaires.

Plus trois audits navigateur qui ouvrent les 59 vues dans Chromium et mesurent
l'affichage, les commandes et les graphiques.

### La leçon qui vaut pour la suite

Chacun de ces outils a d'abord accusé à tort, et chaque correction est
consignée à côté de son effet :

- ignorer `terminal.py` faisait accuser cinq clés de l'entonnoir Opportunités —
  **81 suspects devenus 63** ;
- ignorer les imports par chaîne et les imports relatifs faisait passer la
  moitié de la surface HTTP et tout le paquet IA pour morts — **74 modules
  « morts » devenus 4** ;
- un seuil unique sur les SVG accusait 121 jauges saines, et `innerText` rend
  `''` dans un `<details>` replié — **19 valeurs creuses sur 19 pour « Système ›
  données », dont aucune ne l'était** ;
- juger le texte plutôt que le code faisait accuser trois gardes de leur propre
  documentation ;
- mesurer un premier appel faisait passer un coût de démarrage payé une fois
  (2226 ms puis 245 ms) pour une page lente.

**Un détecteur incomplet ne détecte pas : il calomnie.** Avant de publier un
chiffre d'accusation, chercher le contre-exemple sain.

## 5. Ce qui reste ouvert

Rien de tout cela n'est caché derrière une suite verte.

- **28 appels de graphique** dont la garde ne nomme pas la primitive attendue.
  Latent : l'ordre d'arrivée des scripts les rend inoffensifs aujourd'hui, et
  un seul cas s'est manifesté (corrigé). Le compte est figé et ne peut que
  baisser.
- **Deux capacités étiquetées `NON_IMPLÉMENTÉ`** : le pipeline de notation du
  scanner et le registre d'outils Claude. Conservées, nommées, gardées dans les
  deux sens — si un appelant apparaît, le banc tombe.
- **Deux clés sans producteur** : `quality_flags` et `eps_revision_pct`. Les
  détections correspondantes sont mortes par construction, pas seulement par
  contexte manquant.
- **Le contrôle croisé broker/modèle** des Greeks ne s'exécute pas : un seul jeu
  est servi. La couverture est publiée à côté du verdict.
- **Deux P0 de doctrine encore ouverts** : la consolidation des autorités de
  décision et les jobs déclaratifs restants.

## 6. Ce qui demande une décision humaine

Ces points ne sont pas des oublis : ils engagent au-delà d'un correctif.

- **Fusionner la branche.** Aucune fusion automatique vers `main` n'est faite,
  c'est la règle du dépôt.
- **Installer le chien de garde en tâche planifiée.** Il tourne pour la session
  en cours ; l'inscrire au démarrage est un changement durable de la machine.
- **Le job `navigateur` en intégration continue.** La proposition est prête
  dans `docs/propositions/` ; l'appliquer demande un jeton avec la portée
  `workflow`.
- **Les cinq routes sans consommateur.** `/api/comite`, `/api/portefeuille`,
  `/api/search`, `/api/strategie`, `/api/weekly` ne sont lues par aucune page
  du dépôt. Elles disent maintenant leur état ; les garder, les documenter ou
  les retirer est un choix de produit.
