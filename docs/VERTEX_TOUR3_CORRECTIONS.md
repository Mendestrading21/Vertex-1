# VERTEX — troisième tour de correction et ses six régressions

Ce document couvre le tour de correction du 2026-09-06 qui a traité les fichiers
croisés laissés hors périmètre par les deux tours précédents, **et surtout** les
défauts que son propre contrôle adverse a trouvés. Il répond à une question
simple : *est-ce que ça se répare tout seul ?* Non. Chaque tour corrige
beaucoup et réintroduit quelque chose ; c'est pourquoi un contrôleur adverse
passe derrière chaque lot, et pourquoi ce qu'il trouve est réparé à la main.

## Méthode

Quatre lots taillés sur des périmètres de fichiers DISJOINTS (positions/desk,
pages croisées, options, terminal/commande), puis quatre contrôleurs adverses,
un par lot, chargés de **réfuter** les corrections plutôt que de les confirmer.

| Lot | Verdict du contrôle |
| --- | --- |
| terminal / commande | SOLIDE |
| positions / desk | PARTIEL — une régression de priorité 1 |
| pages croisées | PARTIEL — une régression |
| options | PARTIEL — une régression et deux défauts non déclarés |

## Les six défauts trouvés par le contrôle, et leur réparation

### 1. Le plan de travail franchissait une garde dure (priorité 1)

`vertex/positions/recalculator.py` construisait son propre paquet de décision.
Trois entrées critiques y étaient des **littéraux**, dont
`reconciliation: {'actionable_allowed': True}` — une autorisation affirmée sans
mesure. Or `scan_evidence.build_scan` pose le rapprochement réellement calculé
sur chaque titre scanné.

Mesure sur un `detail` dont le rapprochement INTERDIT d'agir : le plan de
travail rendait « RENFORCER » sans règle bloquante pendant que la route
canonique rendait « ATTENDRE » avec `SOURCE_DISAGREEMENT`. Deux autorités de
décision, sur des positions déclarées par l'utilisateur.

Ce contournement était **masqué** par un `REGIME_BLOCKS_NEW_RISK` fabriqué : en
réparant le régime, la correction précédente l'avait rendu atteignable.

**Réparé** : il n'y a plus de second constructeur. Le plan de travail appelle
`decision_packet.build`, qui possède le régime, le fondamental, les catalyseurs
et les trois preuves critiques. Il n'ajoute que ce que la position sait et que
le scan ignore — gain/risque restant, invalidation de thèse.

Le garde portefeuille, lui, n'existait nulle part sur cette surface : sans lui,
le paquet est déclaré incomplet et **toutes** les positions rendent ATTENDRE en
permanence — une garde toujours allumée ne distingue plus rien. Il est donc
calculé par son propriétaire canonique (`portfolio_guard.guard_rules` sur
`risk_engine.portfolio_risk`), et ce qu'il ne peut pas mesurer est **nommé** :
la trésorerie et le pic d'équité ne sont pas déclarés ici, donc le plafond de
drawdown portefeuille n'est pas évalué sur cette surface.

Preuve : `tests/test_desk_positions_une_seule_autorite.py` — les deux surfaces
portent les mêmes règles bloquantes, et attendent ou agissent ensemble, dans
les trois états du rapprochement (passant, en désaccord, absent).

### 2. La carte Alertes perdait son rafraîchissement instantané

Pour arrêter une amplification inter-pages, le rejeu du canal `jobs` avait été
restreint au seul label `jobs`. Mais la page Système enregistre ses tâches par
vue : `loadAlerts` est enregistrée sous `alertes` et lit pourtant
`/api/system/jobs`. Le cache était invalidé, la carte n'était repeinte que par
son intervalle de 60 s, contre environ 1,5 s auparavant.

**Réparé** en une ligne, et `tests/test_rejeu_canal_jobs.py` rapproche désormais
les deux sources : toute tâche qui lit l'endpoint des jobs doit être rejouée par
le canal des jobs — avec une contre-épreuve qui interdit de rejouer toute la
page.

### 3. La sélection de récence des dépêches classait par FORME de date

La déduplication départageait deux dépêches du même événement en comparant
`ev['time']` en **chaîne brute**. Ce champ arrive sous au moins trois formes :
`2026-09-05 08:00:00+00:00` (courtier), `2026-09-05T07:00:00Z` (ISO),
`Sat, 06 Sep 2026 07:00:00 GMT` (RSS).

Le `T` bat l'espace dès le 11ᵉ caractère, et une lettre bat tout. Mesuré : une
dépêche de 07:00 gagnait contre une de 08:00. L'événement fusionné héritait de
la source, de la date, du lien et du sentiment du plus **ancien**.

**Réparé** : `news_dedup.instant()` rend un instant normalisé, employé aussi par
le tri final du fil — une seule clé de récence. Le cas RSS, cassé avant ce tour,
est fermé au passage. Preuve : `tests/test_recence_depeches.py`, qui mesure les
deux ordres d'arrivée.

### 4. et 5. Des hôtes de graphique restaient littéralement vides

Vue Structure : quatre hôtes sont vidés au chargement, les branches dégradées
n'en remplissaient que deux. `vx-os-scenarios` et `vx-os-compare` restaient
vides **dans tous les états**, y compris la panne réseau où seul l'hôte du
verdict était servi. Le gardien s'appelait « aucun hôte muet » et n'en vérifiait
que deux sur quatre.

Vue Scénarios : le second hôte, `vx-opt-strategies`, gardait son texte de départ
à l'identique dans les deux états — consigne inapplicable quand le tableau est
vide, panne muette quand la lecture échoue.

**Réparé** : un seul endroit nomme l'absence sur tous les hôtes, et chaque
chemin dégradé y passe. Une panne se dit avec un état d'erreur, une absence avec
un état vide. Preuve : `tests/test_hotes_options_nommes.py`, qui lit le gabarit
de chaque vue et vérifie que **chaque** hôte déclaré est nommé.

### 6. Une route dont la documentation contredisait sa propre sortie

La docstring de `/news-feed` affirmait que l'attestation du vendeur valait
`NON_IMPLÉMENTÉ` faute de producteur. Mesuré par appel direct : la même fonction
sert `attestation_vendeur: ACTIF` depuis qu'un producteur a été branché.

Aucune valeur servie n'était fausse — c'est la prose qui l'était, et c'est la
façon la plus discrète de rendre une garde inutile : un lecteur qui croit le
commentaire ne va pas vérifier la réponse. Preuve :
`tests/test_prose_route_actualites.py`.

## Un septième défaut, trouvé par l'audit navigateur

Sur un titre jamais demandé (instance neuve, cache froid), la carte
« Financials — fondamentaux » affichait ses **douze** mesures à « — » sous un
badge annonçant « cache ». Rien n'était en cache : la collecte était en vol, et
la même page l'écrivait pourtant ailleurs.

Un tiret sous « cache » se lit « la donnée manque à la source » ; sous
« collecte en cours » il se lit « pas encore reçu ». Le badge lit désormais la
mesure servie et distingue cinq états. Preuve :
`tests/test_fondamentaux_etat_annonce.py`.

## Hygiène : les fins de ligne

Un outil d'édition avait réécrit dix-huit fichiers en CRLF, dont `terminal.py`
en entier. Le changement réel valait quelques dizaines de lignes ;
`git diff` en annonçait 2883, et une revue humaine devenait impossible.

`tools/qa/normaliser_fins_de_ligne.py` ne retient qu'une conversion
**accidentelle** — version indexée en LF, copie de travail en CRLF — et épargne
donc les compétences vendues et les fixtures capturées, commises en CRLF à
juste titre. `tests/test_fins_de_ligne.py` juge ce qui est **commis**, c'est-à-dire
ce qu'un relecteur verra.
