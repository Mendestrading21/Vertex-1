# VERTEX_AUDIT_CARTES — audit navigateur complet, page par page, carte par carte

Outil : `tools/qa/audit_cartes.py` (Chromium via Playwright, instance QA sans
IBKR ni code d'accès, 59 pages et sous-vues énumérées depuis les modules de
page, 1600 et 390 px). Relevé par page : statut HTTP, requêtes en échec,
erreurs console, exceptions, squelettes perpétuels, états d'erreur, cartes
vides, débordement horizontal, `/api/client-log`.

## Passage 1 (2026-09-06, 118 relevés)

- Aucune erreur console, aucune exception de page, aucune requête en échec,
  aucun squelette perpétuel, aucun état d'erreur, journal client vide.
- Trois débordements réels à 390 px, corrigés dans le commit `be7a2f2a` :
  Marchés › Indices (bande d'indicateurs à 4 colonnes sur mobile), Options ›
  Vue d'ensemble (règle ≤1440 px battant la règle ≤900 px), Portefeuille ›
  Options / Performance (tuiles KPI avec `grid-column` en style inline).
- « Cartes vides » signalées au premier passage : faux positifs (cartes à
  contenu graphique ou hors écran, `innerText` vide) ; l'outil compare
  désormais `textContent` et ignore les cartes à SVG/canvas/table.

## Passage à 1024 px

59 relevés (une largeur), **0 problème** — même mesure que les passages à
1600 et 390 px.

## Passage APRÈS les corrections de la vérification en direct (2026-09-06)

Les 45 corrections issues de la vérification en direct
(`VERTEX_VERIFICATION_DIRECTE.md`) touchent des dizaines de cartes. Les deux
audits ont donc été rejoués sur une instance de contrôle reconstruite à partir
du code corrigé :

| Audit | Portée | Résultat |
|---|---|---|
| Affichage | 59 pages × 1600 et 390 px = 118 relevés | **0 problème** |
| Interactions | 59 pages, 593 clics | **0 problème** |
| Gardiens navigateur (Chromium) | 5 bancs | **53 réussis** |

## Graphiques et widgets (`tools/qa/audit_graphiques.py`, 1600 px)

Les deux premiers outils mesurent la PAGE (statut, erreurs, squelettes,
débordements) et les COMMANDES (clics). Aucun ne répondait à la question de
l’utilisateur : *le graphique trace-t-il une courbe, le widget montre-t-il un
chiffre ?* Une carte peut être présente, sans erreur, sans squelette — et vide.

`audit_graphiques.py` ouvre les 59 vues, fait défiler la page (les cartes en
`content-visibility` ne dessinent pas hors écran), puis mesure :

- les **canevas** par les pixels réellement peints (`getImageData`) : un canevas
  monté mais jamais dessiné est le défaut invisible par excellence ;
- les **SVG** par leur nombre de tracés, jugés PAR FAMILLE ;
- les **widgets de valeur**, et pour chaque tiret : la carte hôte
  explique-t-elle l’absence ?

### Deux défauts de l’outil, corrigés avant de conclure

Le premier relevé annonçait « 40 SVG sans tracé » et « 319 widgets creux ».
Les deux chiffres étaient faux, et le vérifier valait mieux que les publier.

1. **Seuil unique sur les SVG.** La règle « moins de 3 tracés = vide » accusait
   124 widgets sains : une jauge de score (anneau 78 × 78) porte exactement DEUX
   cercles — piste et arc — et c’est sa forme complète ; un treemap de deux
   contrats porte deux rectangles. Le seuil est désormais donné par famille
   (`jauge`, `aires`, `graphique`), et un SVG dont la carte annonce un gabarit
   (le tracé « fantôme » de Performance) n’est plus compté.
2. **`innerText` sur du contenu replié.** `innerText` est calculé sur le RENDU :
   dans un `<details>` fermé il rend `''` alors que `textContent` porte
   « 513 » — et Chromium donne quand même une boîte non nulle à ces éléments.
   L’audit comptait donc chaque valeur repliée comme creuse : 19 sur 19 pour
   « Système › données », dont **pas une seule** ne l’était. L’outil écarte
   maintenant ce qui n’est pas affiché, au lieu de le déclarer vide.

### Relevé après correction de la mesure

| Mesure | Valeur |
| --- | --- |
| Vues ouvertes | 59 |
| Canevas mesurés | 38 |
| Canevas jamais dessinés | 0 |
| SVG de graphique mesurés | 188 |
| SVG sans tracé | 0 |
| Cartes-graphiques muettes | 0 |
| Widgets de valeur | 2089 |
| Widgets affichant un tiret | 195 |
| Tirets SANS explication sur leur carte | 2 |

Un tiret n’est pas un défaut : c’est la représentation honnête d’une absence,
et l’instance de mesure tourne sans IBKR, sans portefeuille déclaré et sans
journal de trades. Le défaut est le tiret MUET. Il en reste deux, tous deux sur
Portefeuille :

- `?view=options` — KPI « Risque événementiel » : `—` ne distingue pas « aucune
  échéance de résultats proche » de « date de résultats inconnue » ;
- `?view=risk` — KPI « Bêta » : `—` ne dit pas si le bêta est incalculable
  (série de référence absente) ou simplement non déclaré.

## Interactions (`tools/qa/audit_interactions.py`, 1280 px)

Sur chaque page et sous-vue, clic sur chaque bouton, onglet, puce et lien de
filtre visible (hors commandes qui modifient le desk ou lancent une collecte :
clôturer, supprimer, importer, exporter, enregistrer, déclarer, lancer un
scan, mettre à jour avec Claude), tiroirs et modales refermés. Résultat du
2026-09-06 : **59 pages, 630 clics, 0 problème** (aucune exception, aucune
erreur console, aucune requête en échec, aucun état d'erreur déclenché).

## Passage 2 (après corrections) — rapport brut

Base : `http://127.0.0.1:5003` · 2026-09-06T11:12:56Z → 2026-09-06T11:26:20Z · largeurs [1600, 390] · 118 relevés (59 pages × 2 largeurs).

## Relevés avec un problème (0)

| Page | Largeur | Problèmes |
|---|---|---|

## Tous les relevés

| Page | Largeur | Statut | Cartes | Squelettes | Erreurs | Vides | « Aucune donnée » | n/d | Durée |
|---|---|---|---|---|---|---|---|---|---|
| Aujourd’hui | 1600 | 200 | 28 | 0 | 0 | 0 | 1 | 6 | 7.4 s |
| Calendrier › today | 1600 | 200 | 2 | 0 | 0 | 0 | 0 | 0 | 6.7 s |
| Calendrier › week | 1600 | 200 | 3 | 0 | 0 | 0 | 0 | 0 | 6.7 s |
| Calendrier › month | 1600 | 200 | 3 | 0 | 0 | 0 | 0 | 0 | 6.7 s |
| Calendrier › agenda | 1600 | 200 | 3 | 0 | 0 | 0 | 0 | 0 | 6.7 s |
| Calendrier › portfolio | 1600 | 200 | 3 | 0 | 0 | 0 | 0 | 0 | 6.7 s |
| Calendrier › macro | 1600 | 200 | 3 | 0 | 0 | 0 | 0 | 0 | 6.7 s |
| Calendrier › options | 1600 | 200 | 2 | 0 | 0 | 0 | 0 | 0 | 6.6 s |
| Marchés › overview | 1600 | 200 | 4 | 0 | 0 | 0 | 0 | 0 | 7.2 s |
| Marchés › macro | 1600 | 200 | 7 | 0 | 0 | 0 | 0 | 4 | 7.2 s |
| Marchés › indices | 1600 | 200 | 3 | 0 | 0 | 0 | 0 | 0 | 7.2 s |
| Marchés › sectors | 1600 | 200 | 3 | 0 | 0 | 0 | 0 | 0 | 7.2 s |
| Marchés › breadth | 1600 | 200 | 8 | 0 | 0 | 0 | 1 | 0 | 7.2 s |
| Marchés › volatility | 1600 | 200 | 3 | 0 | 0 | 0 | 0 | 0 | 7.3 s |
| Opportunités › screener | 1600 | 200 | 62 | 0 | 0 | 0 | 0 | 0 | 7.5 s |
| Opportunités › stocks | 1600 | 200 | 62 | 0 | 0 | 0 | 0 | 0 | 7.4 s |
| Opportunités › etf | 1600 | 200 | 0 | 0 | 0 | 0 | 0 | 0 | 7.3 s |
| Opportunités › options | 1600 | 200 | 53 | 0 | 0 | 0 | 0 | 0 | 7.2 s |
| Opportunités › anomalies | 1600 | 200 | 1 | 0 | 0 | 0 | 0 | 0 | 7.4 s |
| Opportunités › calendar | 1600 | 200 | 1 | 0 | 0 | 0 | 0 | 3 | 7.2 s |
| Opportunités › portfolio | 1600 | 200 | 9 | 0 | 0 | 0 | 0 | 0 | 7.2 s |
| Options › overview | 1600 | 200 | 4 | 0 | 0 | 0 | 1 | 0 | 6.6 s |
| Options › structure | 1600 | 200 | 6 | 0 | 0 | 0 | 1 | 0 | 6.6 s |
| Options › volatility | 1600 | 200 | 6 | 0 | 0 | 0 | 1 | 0 | 6.6 s |
| Options › radar | 1600 | 200 | 1 | 0 | 0 | 0 | 1 | 0 | 6.6 s |
| Options › scenarios | 1600 | 200 | 7 | 0 | 0 | 0 | 1 | 0 | 6.7 s |
| Options › positions | 1600 | 200 | 2 | 0 | 0 | 0 | 1 | 5 | 6.6 s |
| Options › events | 1600 | 200 | 2 | 0 | 0 | 0 | 1 | 1 | 6.6 s |
| Options › positioning | 1600 | 200 | 6 | 0 | 0 | 0 | 1 | 30 | 6.6 s |
| Options › leaps | 1600 | 200 | 3 | 0 | 0 | 0 | 1 | 1 | 6.7 s |
| Simulateur › simple | 1600 | 200 | 2 | 0 | 0 | 0 | 0 | 0 | 6.6 s |
| Simulateur › avance | 1600 | 200 | 2 | 0 | 0 | 0 | 0 | 0 | 6.6 s |
| Simulateur › comparer | 1600 | 200 | 2 | 0 | 0 | 0 | 0 | 0 | 6.6 s |
| Portefeuille › team | 1600 | 200 | 8 | 0 | 0 | 0 | 0 | 5 | 7.2 s |
| Portefeuille › positions | 1600 | 200 | 4 | 0 | 0 | 0 | 0 | 6 | 6.6 s |
| Portefeuille › allocation | 1600 | 200 | 6 | 0 | 0 | 0 | 1 | 0 | 6.7 s |
| Portefeuille › options | 1600 | 200 | 15 | 0 | 0 | 0 | 0 | 8 | 6.7 s |
| Portefeuille › risk | 1600 | 200 | 15 | 0 | 0 | 0 | 2 | 5 | 7.2 s |
| Portefeuille › theses | 1600 | 200 | 3 | 0 | 0 | 0 | 1 | 0 | 7.1 s |
| Portefeuille › performance | 1600 | 200 | 5 | 0 | 0 | 0 | 3 | 1 | 6.6 s |
| Suivi › attention | 1600 | 200 | 7 | 0 | 0 | 0 | 0 | 0 | 6.7 s |
| Suivi › active | 1600 | 200 | 7 | 0 | 0 | 0 | 0 | 0 | 6.6 s |
| Suivi › archives | 1600 | 200 | 6 | 0 | 0 | 0 | 0 | 0 | 6.6 s |
| Performance › overview | 1600 | 200 | 9 | 0 | 0 | 0 | 3 | 0 | 6.7 s |
| Performance › journal | 1600 | 200 | 2 | 0 | 0 | 0 | 2 | 0 | 6.6 s |
| Performance › real | 1600 | 200 | 1 | 0 | 0 | 0 | 1 | 0 | 6.6 s |
| Performance › track-record | 1600 | 200 | 1 | 0 | 0 | 0 | 1 | 0 | 6.6 s |
| Performance › progression | 1600 | 200 | 1 | 0 | 0 | 0 | 0 | 0 | 6.6 s |
| Performance › learnings | 1600 | 200 | 3 | 0 | 0 | 0 | 3 | 0 | 6.6 s |
| Système › connections | 1600 | 200 | 16 | 0 | 0 | 0 | 0 | 0 | 6.7 s |
| Système › data | 1600 | 200 | 5 | 0 | 0 | 0 | 1 | 0 | 6.6 s |
| Système › jobs | 1600 | 200 | 2 | 0 | 0 | 0 | 1 | 0 | 6.7 s |
| Système › alerts | 1600 | 200 | 2 | 0 | 0 | 0 | 0 | 0 | 6.6 s |
| Système › preferences | 1600 | 200 | 4 | 0 | 0 | 0 | 0 | 0 | 6.6 s |
| Système › security | 1600 | 200 | 3 | 0 | 0 | 0 | 1 | 0 | 6.6 s |
| Système › archives | 1600 | 200 | 1 | 0 | 0 | 0 | 1 | 0 | 6.6 s |
| Analyse NVDA | 1600 | 200 | 33 | 0 | 0 | 0 | 5 | 0 | 6.9 s |
| Options › dossier NVDA | 1600 | 200 | 16 | 0 | 0 | 0 | 7 | 0 | 6.8 s |
| Vertex IA | 1600 | 200 | 4 | 0 | 0 | 0 | 3 | 0 | 6.6 s |
| Aujourd’hui | 390 | 200 | 28 | 0 | 0 | 0 | 1 | 6 | 7.3 s |
| Calendrier › today | 390 | 200 | 2 | 0 | 0 | 0 | 0 | 0 | 6.6 s |
| Calendrier › week | 390 | 200 | 3 | 0 | 0 | 0 | 0 | 0 | 6.6 s |
| Calendrier › month | 390 | 200 | 3 | 0 | 0 | 0 | 0 | 0 | 6.6 s |
| Calendrier › agenda | 390 | 200 | 3 | 0 | 0 | 0 | 0 | 0 | 6.7 s |
| Calendrier › portfolio | 390 | 200 | 2 | 0 | 0 | 0 | 0 | 0 | 6.6 s |
| Calendrier › macro | 390 | 200 | 3 | 0 | 0 | 0 | 0 | 0 | 6.6 s |
| Calendrier › options | 390 | 200 | 2 | 0 | 0 | 0 | 0 | 0 | 6.6 s |
| Marchés › overview | 390 | 200 | 4 | 0 | 0 | 0 | 0 | 0 | 7.1 s |
| Marchés › macro | 390 | 200 | 7 | 0 | 0 | 0 | 0 | 4 | 7.1 s |
| Marchés › indices | 390 | 200 | 3 | 0 | 0 | 0 | 0 | 0 | 7.1 s |
| Marchés › sectors | 390 | 200 | 3 | 0 | 0 | 0 | 0 | 0 | 7.1 s |
| Marchés › breadth | 390 | 200 | 8 | 0 | 0 | 0 | 1 | 0 | 7.1 s |
| Marchés › volatility | 390 | 200 | 3 | 0 | 0 | 0 | 0 | 0 | 7.1 s |
| Opportunités › screener | 390 | 200 | 62 | 0 | 0 | 0 | 0 | 0 | 7.3 s |
| Opportunités › stocks | 390 | 200 | 62 | 0 | 0 | 0 | 0 | 0 | 7.3 s |
| Opportunités › etf | 390 | 200 | 0 | 0 | 0 | 0 | 0 | 0 | 7.1 s |
| Opportunités › options | 390 | 200 | 53 | 0 | 0 | 0 | 0 | 0 | 7.1 s |
| Opportunités › anomalies | 390 | 200 | 1 | 0 | 0 | 0 | 0 | 0 | 7.1 s |
| Opportunités › calendar | 390 | 200 | 1 | 0 | 0 | 0 | 0 | 3 | 7.1 s |
| Opportunités › portfolio | 390 | 200 | 9 | 0 | 0 | 0 | 0 | 0 | 7.1 s |
| Options › overview | 390 | 200 | 4 | 0 | 0 | 0 | 1 | 0 | 6.6 s |
| Options › structure | 390 | 200 | 6 | 0 | 0 | 0 | 1 | 0 | 6.7 s |
| Options › volatility | 390 | 200 | 6 | 0 | 0 | 0 | 1 | 0 | 6.6 s |
| Options › radar | 390 | 200 | 1 | 0 | 0 | 0 | 1 | 0 | 6.6 s |
| Options › scenarios | 390 | 200 | 7 | 0 | 0 | 0 | 1 | 0 | 6.7 s |
| Options › positions | 390 | 200 | 2 | 0 | 0 | 0 | 1 | 5 | 6.6 s |
| Options › events | 390 | 200 | 2 | 0 | 0 | 0 | 1 | 1 | 6.6 s |
| Options › positioning | 390 | 200 | 6 | 0 | 0 | 0 | 1 | 30 | 6.6 s |
| Options › leaps | 390 | 200 | 3 | 0 | 0 | 0 | 1 | 1 | 6.7 s |
| Simulateur › simple | 390 | 200 | 2 | 0 | 0 | 0 | 0 | 0 | 6.6 s |
| Simulateur › avance | 390 | 200 | 2 | 0 | 0 | 0 | 0 | 0 | 6.6 s |
| Simulateur › comparer | 390 | 200 | 2 | 0 | 0 | 0 | 0 | 0 | 6.6 s |
| Portefeuille › team | 390 | 200 | 8 | 0 | 0 | 0 | 0 | 5 | 7.1 s |
| Portefeuille › positions | 390 | 200 | 4 | 0 | 0 | 0 | 0 | 6 | 6.6 s |
| Portefeuille › allocation | 390 | 200 | 6 | 0 | 0 | 0 | 1 | 0 | 6.6 s |
| Portefeuille › options | 390 | 200 | 15 | 0 | 0 | 0 | 0 | 8 | 6.6 s |
| Portefeuille › risk | 390 | 200 | 15 | 0 | 0 | 0 | 2 | 5 | 7.2 s |
| Portefeuille › theses | 390 | 200 | 3 | 0 | 0 | 0 | 1 | 0 | 7.1 s |
| Portefeuille › performance | 390 | 200 | 5 | 0 | 0 | 0 | 3 | 1 | 6.7 s |
| Suivi › attention | 390 | 200 | 7 | 0 | 0 | 0 | 0 | 0 | 6.6 s |
| Suivi › active | 390 | 200 | 7 | 0 | 0 | 0 | 0 | 0 | 6.6 s |
| Suivi › archives | 390 | 200 | 6 | 0 | 0 | 0 | 0 | 0 | 6.6 s |
| Performance › overview | 390 | 200 | 9 | 0 | 0 | 0 | 3 | 0 | 6.6 s |
| Performance › journal | 390 | 200 | 2 | 0 | 0 | 0 | 2 | 0 | 6.6 s |
| Performance › real | 390 | 200 | 1 | 0 | 0 | 0 | 1 | 0 | 6.6 s |
| Performance › track-record | 390 | 200 | 1 | 0 | 0 | 0 | 1 | 0 | 6.6 s |
| Performance › progression | 390 | 200 | 1 | 0 | 0 | 0 | 0 | 0 | 6.6 s |
| Performance › learnings | 390 | 200 | 3 | 0 | 0 | 0 | 3 | 0 | 6.6 s |
| Système › connections | 390 | 200 | 16 | 0 | 0 | 0 | 0 | 0 | 6.6 s |
| Système › data | 390 | 200 | 5 | 0 | 0 | 0 | 1 | 0 | 6.6 s |
| Système › jobs | 390 | 200 | 2 | 0 | 0 | 0 | 1 | 0 | 6.6 s |
| Système › alerts | 390 | 200 | 2 | 0 | 0 | 0 | 0 | 0 | 6.6 s |
| Système › preferences | 390 | 200 | 4 | 0 | 0 | 0 | 0 | 0 | 6.6 s |
| Système › security | 390 | 200 | 3 | 0 | 0 | 0 | 1 | 0 | 6.6 s |
| Système › archives | 390 | 200 | 1 | 0 | 0 | 0 | 1 | 0 | 6.6 s |
| Analyse NVDA | 390 | 200 | 33 | 0 | 0 | 0 | 2 | 0 | 6.9 s |
| Options › dossier NVDA | 390 | 200 | 16 | 0 | 0 | 0 | 7 | 0 | 6.7 s |
| Vertex IA | 390 | 200 | 4 | 0 | 0 | 0 | 3 | 0 | 6.6 s |

`/api/client-log` : 0 entrée(s) pendant l’audit.
