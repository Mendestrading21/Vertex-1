# VERTEX_LOT_DECISION_CONTRAT — contrat du lot « autorité de décision unique » (à valider par l'humain)

Défaut consigné : `docs/VERTEX_DATA_COVERAGE.md` §13 #2 — *trois autorités de
décision*. Lot canonique du skill maître : **Lot 10 — AdviceEngine unique**
(`.claude/skills/vertex-2-0/references/delivery-program.md`, phase C), contrat
cible dans `references/ai-decision-contract.md` (« Autorité unique »).

Ce document est un **contrat de lot**, pas une implémentation : le chantier
touche les moteurs de décision et exige une validation humaine avant tout
code. Rien ici n'est déjà corrigé.

## 1. Problème (mesuré au SHA `d2722b4c`)

Quatre vocabulaires de « verdict » coexistent dans le runtime et sont servis
aux pages ; aucun ne projette l'objet cible `AdviceResult`.

| Autorité | Propriétaire | Vocabulaire | Route | Pages qui l'affichent |
|---|---|---|---|---|
| A. Verdict quant du scan | `vertex/engines/quant_engine.py` (`verdict`, `action`) + noyau `vx_verdict` (`terminal.py` : « VERTEX BUY / S+ ») | `BUY / WATCH / WAIT / AVOID …` (anglais) | `/scan` (rows, detail) | Marchés (verdicts, entonnoir), Opportunités (radar, positions × moteur), Aujourd'hui (cockpit), Calendrier (verdict par item) |
| B. Décision stack | `vertex/engines/decision_stack.py` (« la vérité unique ») | `STRONG_BUY / BUY / BUY_PULLBACK / WATCH_BREAKOUT / WAIT / TOO_LATE / AVOID / NO_NEW_RISK / DATA_INSUFFICIENT` | `/api/decision/<sym>`, `/api/brief`, carte du comité | Analyse (carte-verdict, scénarios, comité), Vertex IA (decision stack, carte conviction × accord) |
| C. Moteur exécutif | `vertex/strategy/executive_engine.py` (« LA seule couche de décision finale ») | `ACHETER / RENFORCER / ATTENDRE / REDUIRE / REFUSER` (constitution) | `/api/strategy/decision/<sym>`, `/api/portfolio/team` | Analyse (rail décisionnel), Vertex IA (verdict), Portefeuille (conformité de l'équipe) |
| D. Décision du jour du comité | `vertex/app/routes/command.py` | `ATTAQUER / ATTENDRE-SÉLECTIF / RÉDUIRE-DÉFENSIF` + alertes | `/api/command` | Aujourd'hui (décision du jour, alertes), Portefeuille |

Contradictions observées :

- un même titre peut porter `BUY` (A), `WATCH_BREAKOUT` (B) et `ATTENDRE` (C)
  sur la même page (Analyse : hero, carte-verdict, rail) ;
- les entonnoirs comptent « achats » sur A, le comité (D) raisonne sur C, la
  carte conviction × accord (Vertex IA) range B par groupes ;
- `final_decision` est aussi produit par `vertex/tracking/repository.py`
  (suivi) et lu par `vertex/ai/fallback.py` (synthèse déterministe) ;
- la mission de nuit a retiré le `ATTENDRE` fabriqué hors scan (`NON_EVALUE`)
  mais n'a pas touché aux trois moteurs.

## 2. Cible (contrat du skill)

```text
AdviceEngine.evaluate(snapshot) -> AdviceResult
```

`AdviceResult` : orientation (`ACHETER / RENFORCER / ATTENDRE / RÉDUIRE /
REFUSER` — sorties analytiques, jamais des actes), horizon, confiance
décomposée, preuves, contradictions, inconnues, bloqueurs, invalidation,
scénarios, couverture, versions, audit. **Toutes** les routes et pages
projettent cet objet ; les autres moteurs deviennent des producteurs de
preuves, métriques ou contexte.

## 3. Propriétaires proposés

- Propriétaire du conseil : `vertex/strategy/executive_engine.py` (déjà le
  vocabulaire constitutionnel et les hard gates) → renommé/enveloppé en
  `AdviceEngine` (nouveau module `vertex/advice/engine.py`, façade, sans
  réécriture du calcul au premier lot).
- Producteurs de preuves : `decision_stack` (raisonnement, comité, pros/cons,
  unknowns), `quant_engine` (scores, verdict quant → **preuve**, plus un
  verdict affiché), `command` (contexte marché, alertes de risque → contexte).
- Lecture : une seule route `/api/advice/<sym>` (+ `/api/advice/batch` pour les
  tableaux) ; les routes existantes deviennent des projections de
  `AdviceResult` pendant la période de parité, puis sont retirées.

## 4. Données et invariants

- Entrées : le packet de décision existant (`build_executive_decision`) —
  aucune nouvelle collecte ; `snapshot_id`, versions de profil/moteurs,
  empreinte des intrants.
- Un hard gate inconnu échoue fermé (`ATTENDRE` + bloqueur nommé), `UNKNOWN`
  n'est jamais neutre ; un titre hors scan reste `NON_EVALUE` (fait cette nuit).
- Aucune probabilité publiée sans calibration hors échantillon versionnée ;
  sinon « estimation de modèle ».
- Aucun ordre, aucune allocation ; portefeuille déclaré seulement ; IBKR
  marché seulement.

## 5. Étapes (chacune un commit revertible, PR brouillon)

1. **Façade sans changement de calcul** : `AdviceEngine.evaluate` enveloppe
   `executive_engine` et joint les preuves de `decision_stack` ; tests de
   parité byte-à-byte sur un corpus de packets capturés (fixtures).
2. **Projection** : `/api/decision`, `/api/strategy/decision`, `/api/brief`,
   `/api/command.decision` servent `AdviceResult` + leurs anciens champs
   (période de parité mesurée par un compteur d'usage par route).
3. **Pages** : Analyse, Vertex IA, Aujourd'hui, Opportunités, Marchés,
   Calendrier affichent l'`Orientation Vertex` (date, horizon, confiance,
   preuves, bloqueurs, invalidation, limites) ; les verdicts quant deviennent
   des preuves (« score quant », « verdict du scan ») sous l'orientation, plus
   des verdicts concurrents. Entonnoirs et comptes sur l'orientation.
4. **Retrait** : après parité prouvée et usage nul mesuré, retrait des anciens
   champs `final_decision`/`verdict` affichés (gardien : un seul vocabulaire
   d'orientation servi aux pages).

## 6. Risques

- Changer le sens d'un verdict affiché (le vocabulaire quant anglais est aussi
  celui du calendrier et des entonnoirs) — mitigé par la période de parité et
  les fixtures.
- Perte d'explicabilité si le comité (B) est réduit à une preuve — mitigé :
  `AdviceResult.preuves` porte pros/cons/unknowns/accord.
- Régression de performance (`/api/advice/batch` sur 500 titres) — snapshot
  borné, calcul en fond au scan, jamais dans la requête.

## 7. Tests et preuves exigés

- Parité : corpus de packets (≥ 30 titres, démo et réel capturé) → orientation
  identique à `executive_engine` avant/après façade.
- Contrat : chaque `AdviceResult` porte toutes les sections ; hard gate inconnu
  → `ATTENDRE` + bloqueur ; hors scan → `NON_EVALUE`.
- Gardiens : aucune page n'affiche deux orientations différentes pour un même
  titre ; aucun `||'ATTENDRE'` ; entonnoirs sur l'orientation.
- Navigateur : captures 1600/1024/390 des six pages, console et
  `/api/client-log` propres ; états hors scan, données insuffisantes, gate
  inconnu.

## 8. Rollback

Chaque étape est un commit ; la façade (étape 1) ne modifie aucun calcul, son
revert est neutre. Les projections (étape 2) conservent les anciens champs
jusqu'au retrait (étape 4), lui-même revertible tant que les fixtures de
parité existent.

## 9. Décision humaine attendue

- Valider le propriétaire (`executive_engine` enveloppé) ou choisir
  `decision_stack` comme socle.
- Valider le vocabulaire public (`ACHETER / RENFORCER / ATTENDRE / RÉDUIRE /
  REFUSER`) et le libellé « Orientation Vertex ».
- Autoriser l'étape 1 (façade sans changement de calcul) sur une branche
  dédiée.
