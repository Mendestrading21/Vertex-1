# Balayages transversaux — les défauts qui vivent ENTRE les modules

Un test unitaire vérifie une fonction ; une suite verte ne dit rien de ce qui se
perd aux jointures. Les défauts les plus coûteux de Vertex n'ont jamais été des
calculs faux : ce sont des **absences silencieuses**. Une clé lue que personne
n'écrit rend `None` sans lever. Une capacité entière n'est appelée par aucun
chemin, mais son test passe. Une page appelle un graphique qu'elle ne charge
pas, et la carte disparaît sans message.

Cinq outils cherchent exactement ces formes. Les lancer avant de conclure un lot
coûte quelques secondes et évite de chercher un défaut à l'endroit où il se
manifeste plutôt qu'à l'endroit où il naît.

```bash
.venv\Scripts\python.exe tools\qa\balayage_statique.py --racine vertex
.venv\Scripts\python.exe tools\qa\primitives_manquantes.py
.venv\Scripts\python.exe tools\qa\modules_non_atteints.py
.venv\Scripts\python.exe tools\qa\cles_sans_producteur.py --racine vertex
.venv\Scripts\python.exe tools\qa\exercer_routes.py
```

## Ce que chacun cherche, et ce qu'il a trouvé

| Outil | Forme cherchée | Trouvé le 2026-09-06 |
| --- | --- | --- |
| `balayage_statique` | nom indéfini, import mort, redéfinition silencieuse, défaut mutable | `_POS_TTL_S`, un `NameError` en attente dans le memo des cotations — invisible sans IBKR et sans second appel |
| `primitives_manquantes` | une page appelle `VXCharts.x` sans charger le module qui définit `x` | une carte perdue sur Système, plus 28 appels dont la garde ne nomme pas la primitive |
| `modules_non_atteints` | un module qu'aucun chemin de production n'importe | `scanner/stages.py` et `ai/tool_registry.py`, deux capacités annoncées et non branchées |
| `cles_sans_producteur` | une clé lue et jamais écrite | `quality_flags` — l'anomalie `QUALITY_DETERIORATION` ne pouvait pas se déclencher |
| `exercer_routes` | route en échec, lente, muette, ou à deux propriétaires | 0 collision sur 184 règles, 5 charges vides sans motif |

Les quatre premiers sont tenus par des bancs (`test_balayage_statique`,
`test_primitives_graphiques`, `test_modules_atteints`,
`test_routes_sans_collision`). Les lancer à la main sert à LIRE le détail, pas à
savoir s'ils passent. Le dernier fait de vraies requêtes : il a sa place dans un
rapport, jamais dans un banc.

## La leçon commune : un détecteur incomplet CALOMNIE

Chacun de ces outils a d'abord accusé à tort, et chaque correction vaut d'être
retenue avant d'en écrire un nouveau :

- `cles_sans_producteur` ne lisait que `vertex/` et accusait cinq clés de
  l'entonnoir Opportunités. Elles sont posées dans `terminal.py`, le plus gros
  producteur de clés du produit. **81 suspects sont devenus 63.**
- `modules_non_atteints` ne suivait que les `import` de l'arbre. Les blueprints
  sont chargés depuis des **littéraux de chaîne** dans `app/factory.py` (22
  modules de routes accusés), et `vertex/ai` s'importe en **relatif** (tout le
  paquet accusé). **De 74 modules « morts » à 4.**
- `audit_graphiques` jugeait les SVG à un seuil unique : une jauge d'anneau
  porte deux cercles et c'est sa forme complète. Et `innerText` rend `''` dans
  un `<details>` replié alors que la boîte a une taille — **19 valeurs sur 19
  comptées creuses pour « Système › données », dont aucune ne l'était.**

Règle : avant de publier un chiffre d'accusation, chercher le **contre-exemple
sain**. Un outil qui rend « 0 défaut » sur un dépôt qu'on sait imparfait est
aussi suspect qu'un outil qui en rend mille.

## Quand les lancer

- **Avant** de conclure qu'une fonctionnalité « ne marche pas » : la cause est
  souvent une clé ou un module, pas la fonction qu'on regarde.
- **Après** un lot qui supprime ou renomme : c'est là que naissent les noms
  orphelins et les capacités débranchées.
- **Avant** une livraison, avec la validation minimale du runbook.

## Ce qu'ils ne font pas

Ils ne disent pas si une valeur est JUSTE. Un module atteint peut calculer faux,
une clé produite peut porter un chiffre absurde, une route qui répond peut
mentir. Ces outils réduisent l'espace de recherche ; ils ne remplacent ni la
mesure du domaine, ni la preuve navigateur, ni l'acceptation humaine.
