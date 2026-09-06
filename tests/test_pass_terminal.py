"""
LOT 386 — LES 38 `except: pass` DE `terminal.py`, LUS UN PAR UN.

Le lot 379 avait fait ce travail pour les 46 de `vertex/`. Le lot 385 a montré
que le recensement s'arrêtait à cette frontière : `terminal.py` en porte 38 que
personne n'avait jamais ouverts. Ce lot les ouvre.

## Classement par ce que le `try` ENTOURE

```
nettoyage / fermeture        6   ← cancelMktData, disconnect, reqMarketDataType
journal / persistance       10   ← beats du scheduler, caches, track_record
import / config optionnel    2   ← dotenv, provider JSON
infra thread                 2   ← boucle asyncio, événement de re-scan
absence honnête             16   ← une donnée externe manque → clé/élément OMIS
examinés de près             2   ← L621 et L1342
```

Les 36 premiers sont sans danger pour l'invariant n°4 : un échec y produit une
**absence**, jamais une valeur inventée. Deux méritaient mieux qu'un coup d'œil.

## L621 — l'overlay IBKR : honnête au moteur, muet au produit

`_apply_ibkr_indices()` écrase les indices différés yfinance par les valeurs
IBKR **temps réel**, et marque chaque entrée touchée `src = 'ibkr'` — le
commentaire dit explicitement « provenance temps réel (honnêteté §4) ». Si
l'overlay échoue, les entrées restent **non marquées** : le mécanisme est
complet et correct côté moteur.

**Mais le marqueur n'atteint aucune surface servie.** Mesuré : les pages
servies (`markets_page.py`, `briefing.py`) lisent `.price`, `.change`, `.spark`
— jamais `.src`. Le seul endroit du dépôt qui rend « TEMPS RÉEL IBKR » vs
« yfinance différé » est `PAGE_ME` (L4741-5189), **l'une des 7 constantes
`PAGE_* mortes` du lot 374**, jamais renvoyée par une route. `indices_live`
part bien au client (`/scan` sérialise `{**scan_state}`) mais **aucun code
client ne le lit**.

Ce n'est pas une malhonnêteté — un cours différé reste un cours réel. C'est la
catégorie du lot 382 : **un énoncé du code plus large que ce que le produit
délivre.** Verdict : rien à corriger ici, mais la pièce fragile est la
**fenêtre de fraîcheur de 75 s** — si elle grandissait, des valeurs IBKR
périmées seraient présentées comme du temps réel. C'est elle que ce gardien
verrouille, avec le marqueur lui-même, pour qu'un affichage futur ait quelque
chose de vrai à lire.

## L1342 — `bret = 0.0` : mesuré, pas excusé

> DEPUIS : ce handler a suivi `edge_backtest` dans
> `vertex/engines/edge_validation.py` (strangler). Il n'a été ni supprimé ni
> corrigé, seulement déplacé, et le plafond de `vertex/` l'absorbe. Tout ce
> qui suit reste vrai : la caractérisation porte sur la formule de force
> relative et sur le chemin de scan vivant, pas sur l'emplacement du `pass`.
> Le backtest est en revanche désormais ÉPROUVÉ — voir
> `tests/test_edge_validation.py`, qui vérifie l'absence de look-ahead que
> personne ne pouvait mesurer tant que la fonction appelait le réseau.

Dans `edge_backtest`, l'échec du calcul du rendement de référence laisse
`bret = 0.0`, qui part dans `analyse(sub, bret)`. J'ai failli l'excuser en
disant que 0 est neutre. **La mesure dit le contraire** : dans
`analysis.py:54`, `rs = clip(50 + (sym_ret − bench_ret) × 200, 0, 100)`.

```
sym +0.10  bench réel +0.15 → rs 40    |  bench 0.0 → rs 70
sym −0.05  bench réel +0.12 → rs 16    |  bench 0.0 → rs 40
sym +0.20  bench réel +0.20 → rs 50    |  bench 0.0 → rs 90
```

La force relative devient une performance absolue. **Ce n'est donc PAS un
neutre** — exactement le piège du lot 378 avec `entry_quality`.

Trois faits l'empêchent d'être une faute : (1) `0.0` est le défaut **déclaré**
de la fonction, atteint aussi sans exception quand `bi <= 63` ; (2) le chemin
de scan **vivant** (L395) passe un `bench_ret` réel — le repli est confiné au
backtest ; (3) `scan_state['edge']` part au client via `/scan` mais **aucune
page servie ne le lit**.

**Caractérisation, pas correction** — jumelle du dossier `context()` du lot 379.
Le test ci-dessous fige la sensibilité mesurée pour qu'on ne puisse plus
l'innocenter par un raisonnement élégant.
"""
import ast
import time

import pytest

FICHIER = 'terminal.py'

# Recensement GELÉ des handlers, par famille. Une dérive réclame un examen.
#
# 38 -> 36 au lot #779/G1 : DEUX handlers ont quitté `terminal.py` avec la
# plomberie Flask, et aucun n'a été remplacé par un autre avaleur silencieux.
#   • celui qui gardait l'installation du fournisseur JSON sûr — un `try` autour
#     d'un import, famille « import/config optionnel » (2 -> 1) ; il est parti
#     avec le fournisseur dans `vertex/app/factory.py`, où l'import est
#     inconditionnel : un flask absent casse déjà l'application deux lignes plus
#     haut, le garder n'aurait protégé de rien ;
#   • celui de `_gzip_response`, devenu un `return resp` EXPLICITE dans la
#     fabrique — même comportement (rendre le corps non compressé, toujours
#     valide), intention lisible.
# 36 -> 35 : celui de `_to_naive` (normalisation des dates des séries de
# corrélation) est parti AVEC sa fonction dans
# `vertex/app/routes/correlations_api.py`. Famille « absence honnête » (15 -> 14) :
# un index sans fuseau n'a rien à retirer, l'échec est le cas nominal.
# 35 -> 32 au lot des trois dernieres routes LEGACY. Les TROIS sont partis avec
# le code qu'ils entouraient, aucun n'a ete supprime ni ajoute :
#   • deux dans `options_pack` -> `vertex/options/pack.py` (famille « absence
#     honnête » : un champ de chaine d'options absent reste absent) ;
#   • un dans la route `/desc` -> `vertex/app/routes/descriptions_api.py`
#     (famille « journal/persistance » : l'ecriture du cache disque ne doit
#     jamais couter la reponse).
# Familles : absence honnête 14 -> 12, journal/persistance 10 -> 9.
# HONNÊTETÉ SUR CETTE MISE À JOUR : le lot 386 n'a pas consigné la famille de
# chaque ligne, seulement les totaux et les deux cas « examinés de près ». La
# première baisse est donc CERTAINE (le `try` entourait un import) ; la seconde
# est RAISONNÉE — la compression ratée produisait une absence honnête, pas une
# valeur inventée — et non retrouvée dans la classification d'origine.
# MISE À JOUR (audit Vertex Test 1.0, portabilité Windows) : 32 -> 31.
# Le `pass` retiré est celui de `_weekly_loop`, dont le `try` entourait
# `weekly.get_or_build(...)`. Il était classé « absence honnête » — à tort :
# l'absence était honnête pour la SÉLECTION, mais sa RAISON n'existait nulle
# part, et le battement `WEEKLY_REVIEW` partait quand même à `ok=True`. Le
# domaine « hebdo » pouvait donc rester « jamais synchronisé » pendant que la
# page Système affichait le job en vert. La famille passe de 12 à 11 parce que
# ce cas n'en était pas un : l'erreur est désormais nommée, pas avalée.
#  MISE À JOUR (lot 42, publications atomiques) : 34 -> 33. Le `pass` retiré
#  est celui du tilt stratégie (`_strat_tilt(mctx)`), classé « absence
#  honnête » : son échec sautait l'écriture et l'état gardait la valeur
#  précédente PAR OMISSION. Le lot 42 publiant par blocs atomiques, l'omission
#  ne suffit plus — la reprise de la valeur précédente est désormais EXPLICITE
#  (`_tilt = scan_state.get('strat_tilt')`), même sémantique, dite au lieu
#  d'avalée. La famille passe de 11 à 10.
#  MISE À JOUR (strangler, extraction du backtest de l'edge) : 33 -> 32. Le
#  `pass` retiré est L1342, l'un des DEUX « examinés de près » : celui qui
#  laisse `bret = 0.0` quand le rendement de référence ne se calcule pas. Il
#  n'a pas disparu — il a suivi `edge_backtest` dans
#  `vertex/engines/edge_validation.py`, où le plafond de `vertex/`
#  (`test_pass_et_contexte.MAX_PASS`) l'absorbe sans dérive. Sa
#  caractérisation ci-dessous reste entièrement valable : elle porte sur la
#  formule de force relative (`analysis.py`) et sur le chemin de scan vivant,
#  pas sur l'emplacement du handler. La famille « examinés de près » passe de
#  2 à 1 pour `terminal.py` : il n'y reste que l'overlay IBKR (L621).
#  MISE À JOUR (battement manquant du calendrier) : 32 -> 33. Le `pass` AJOUTÉ
#  entoure l'import et l'émission du battement `CATALYST_REFRESH` dans
#  `_cal_loop`, à l'identique de celui de `_weekly_loop` — famille
#  « journal/persistance » (9 -> 10), celle des beats du scheduler.
#  Pourquoi il est admissible : ce `try` n'entoure aucune donnée financière. Un
#  registre indisponible ne doit pas coûter le rafraîchissement du calendrier ;
#  son échec produit une ABSENCE de diagnostic, jamais une valeur fausse.
#  Ce qu'il coûte, dit franchement : si l'émission échouait, la page Système
#  réafficherait « EN_ATTENTE » — le défaut même que ce lot corrige. Le risque
#  est borné à un import de module déjà chargé et à une écriture de
#  dictionnaire sous verrou ; il est accepté pour la même raison que chez son
#  voisin, et il est nommé ici plutôt que supposé inoffensif.
#  MISE À JOUR (les battements disent la vérité) : 33 -> 31. Quatre handlers
#  RETIRÉS, deux AJOUTÉS.
#
#  Retirés — chacun avalait un échec dont un job dépendait pour se déclarer :
#    · `_alerts_loop`   : le cycle entier d'évaluation des alertes ;
#    · `_fund_loop`     : la collecte des fondamentaux ;
#    · `_news_loop`     : le cycle du fil de nouvelles ;
#    · `_edge_loop`     : `_track.record`, la mise à jour de la fiabilité.
#  Les quatre nomment désormais leur motif et le transmettent au registre :
#  l'échec passe de « avalé » à « ERREUR, avec sa raison ». Les trois premiers
#  étaient classés « absence honnête » (10 -> 7) ; le quatrième
#  « journal/persistance », la famille des beats et de track_record.
#
#  Ajoutés — deux gardes autour d'une ÉMISSION de battement (`_edge_loop` et
#  la branche d'échec de `_news_loop`), à l'identique de celles de
#  `_weekly_loop` et `_cal_loop`. Famille « journal/persistance » :
#  10 - 1 + 2 = 11. Aucune donnée financière n'est entourée ; un registre
#  indisponible ne doit pas coûter le cycle qu'il observe.
#
#  HONNÊTETÉ SUR CE RECLASSEMENT : comme le note l'en-tête, le lot 386 n'a pas
#  consigné la famille de chaque ligne. L'attribution des trois « absence
#  honnête » retirés est donc RAISONNÉE — leur `try` entourait une collecte
#  dont l'échec laissait une donnée absente — et non retrouvée dans une
#  classification d'origine. Le total, lui, est mesuré.
#  MISE À JOUR (les deux dernières boucles muettes) : 31 -> 32.
#    · `_opt_loop` : son `except: pass` — qui avalait tout le cycle du board
#      d'options — nomme désormais son motif et le transmet au registre
#      (« absence honnête » 7 -> 6) ; une garde AJOUTÉE entoure l'émission du
#      battement, comme chez ses quatre voisines ;
#    · `_startup`  : une garde AJOUTÉE entoure le battement de repli, celui
#      qui manquait quand la séquence de démarrage elle-même casse — le job
#      restait « EN_ATTENTE » à jamais et la raison partait dans un `print`.
#  Famille « journal/persistance » : 11 + 2 = 13.
#  MISE À JOUR (le radar nomme ce qui manque) : 32 -> 31. Deux handlers
#  RETIRÉS dans `_radar_loop` — celui de la boucle des trois scanners et celui
#  du fil courtier. Ils étaient classés « absence honnête » (6 -> 4) à tort :
#  quand les quatre flux échouaient — le cas NOMINAL sans TWS — `out` restait
#  vide, le `if out` sautait l'écriture, et le radar gardait sa valeur
#  précédente PAR OMISSION, sans que la raison existe nulle part. Une absence
#  silencieuse ressemble à une absence de marché ; ce n'en est pas une. Les
#  motifs sont désormais retenus, servis dans `scan_state['radar_ecart']` et
#  transmis au registre. Une garde AJOUTÉE entoure l'émission du battement
#  (« journal/persistance » 13 -> 14), comme chez ses sept voisines.
#  MISE À JOUR (recensement du 2026-09-06, gardien ROUGE) : 31 -> 35. Le
#  détecteur mesurait 35 handlers pour 31 recensés — le banc était donc rouge,
#  et un banc rouge ne surveille plus rien. Les QUATRE ajoutés sont mesurés par
#  AST et lus un par un ; ils sont tous les quatre le MÊME geste, arrivé avec
#  le signal d'attente des boucles (`EN_ATTENTE_ENTREE`) :
#    · `_opt_loop`   L1638 : `_sched.attente('OPTIONS_BOARD_REFRESH', …)` ;
#    · `_fund_loop`  L2003 : `_sched.attente('FUNDAMENTALS_REFRESH', …)` ;
#    · `_edge_loop`  L2078 : `_sched.attente('TRACK_RECORD_UPDATE', …)` ;
#    · `_weekly_loop` L2133 : `_sched.attente('WEEKLY_REVIEW', …)`.
#  Famille « journal/persistance » (14 -> 18) : c'est celle des battements —
#  leur `try` n'entoure QU'un import de module déjà chargé et une écriture de
#  dictionnaire dans le registre. Aucune donnée financière n'est entourée ; un
#  registre indisponible ne doit pas coûter le cycle qu'il observe.
#  CE QU'ILS COÛTENT, dit plutôt que supposé inoffensif : si l'émission
#  échouait, la page Système réafficherait « JAMAIS_DEMARRE » au lieu de
#  « EN_ATTENTE_ENTREE » — un diagnostic moins précis, jamais un chiffre faux.
#  Ils ne sont PAS convertis en `contextlib.suppress` : le recensement ne voit
#  que `except: pass`, et faire disparaître quatre avaleurs d'un census qui
#  existe pour les compter serait masquer, pas corriger.
FAMILLES = {
    'nettoyage/fermeture': 6,
    'journal/persistance': 18,
    'import/config optionnel': 1,
    'infra thread': 2,
    'absence honnête': 4,
    'examinés de près': 1,
    #  Fusion Black Glass : arrivés de `vertex-live`, classés ici parce qu'une
    #  notification perdue ou un enrichissement absent ne rend AUCUNE donnée
    #  fausse — la valeur reste celle de la source, simplement sans le
    #  supplément. Distincts d'« absence honnête », qui décrit une donnée
    #  manquante ; ici la donnée est là, c'est le confort qui manque.
    'notification/enrichissement best-effort': 3,
}
#  31 -> 34 (fusion Black Glass) : six handlers arrives de `vertex-live`,
#  DEUX corriges sur place (TTL invalide avale, chaine large non
#  persistee laissant max-pain vide), quatre best-effort — chaine de
#  demo, deux notifications SSE, arrondi du spot. Classement complet en
#  tete de `test_pass_et_contexte.py`.
TOTAL_PASS = 35

# Fenêtre de fraîcheur de l'overlay IBKR. Au-delà, une valeur périmée serait
# présentée comme du temps réel : c'est la borne d'honnêteté du mécanisme.
FENETRE_FRAICHEUR_S = 75


def _pass_secs():
    arbre = ast.parse(open(FICHIER, encoding='utf-8').read())
    return [h.lineno for n in ast.walk(arbre) if isinstance(n, ast.Try)
            for h in n.handlers if all(isinstance(x, ast.Pass) for x in h.body)]


# ── 1. Le dénominateur ──────────────────────────────────────────────────────

def test_le_detecteur_voit_bien_les_trente_deux():
    """Sans dénominateur, la lecture « un par un » ne prouverait rien : si le
    détecteur cassait, le recensement passerait pour complet en couvrant zéro
    handler (leçon des lots 375-377)."""
    n = len(_pass_secs())
    assert n == TOTAL_PASS, (
        '%d `except: pass` dans terminal.py, %d recensés au lot 386 — la '
        'population a changé : reclasser les nouveaux cas par ce que leur '
        '`try` ENTOURE avant de mettre ce chiffre à jour' % (n, TOTAL_PASS))


def test_le_recensement_par_famille_est_complet():
    assert sum(FAMILLES.values()) == TOTAL_PASS, (
        'le classement par famille (%d) ne couvre plus les %d handlers'
        % (sum(FAMILLES.values()), TOTAL_PASS))


# ── 2. L'overlay IBKR : le mécanisme d'honnêteté doit survivre ──────────────

def _seed(monkeypatch, terminal, age_s):
    monkeypatch.setitem(terminal.scan_state, 'indices',
                        [{'name': 'S&P 500', 'price': 100.0, 'change': 0.5}])
    monkeypatch.setitem(terminal.scan_state, 'indices_live', None)
    monkeypatch.setattr(terminal, '_IDX_IBKR', {
        'S&P 500': {'price': 4321.0, 'change': 1.25, 'ts': time.time() - age_s}})


def test_l_overlay_marque_la_provenance_des_valeurs_temps_reel(monkeypatch):
    """Le marqueur `src='ibkr'` est la SEULE trace qui distingue une valeur
    IBKR temps réel d'un cours yfinance différé. Aucune page ne la lit encore
    (mesuré au lot 386), mais la supprimer rendrait la distinction
    définitivement impossible à afficher."""
    import terminal
    _seed(monkeypatch, terminal, age_s=1)
    terminal._apply_ibkr_indices()
    e = terminal.scan_state['indices'][0]
    assert e['price'] == 4321.0, 'la valeur temps réel n\'a pas été appliquée'
    assert e.get('src') == 'ibkr', (
        'marqueur de provenance perdu : plus rien ne distingue le temps réel '
        'IBKR du différé yfinance (invariant n°4)')
    live = terminal.scan_state.get('indices_live')
    assert isinstance(live, dict) and live.get('source') == 'ibkr'


def test_une_valeur_ibkr_perimee_n_est_pas_presentee_comme_temps_reel(monkeypatch):
    """LA propriété d'honnêteté du mécanisme. Si la fenêtre de fraîcheur
    grandissait, un cours vieux de plusieurs minutes serait servi comme du
    temps réel, sans que rien ne le signale."""
    import terminal
    _seed(monkeypatch, terminal, age_s=FENETRE_FRAICHEUR_S + 5)
    terminal._apply_ibkr_indices()
    e = terminal.scan_state['indices'][0]
    assert e['price'] == 100.0, (
        'une valeur IBKR périmée (> %d s) a écrasé le cours différé : elle '
        'serait servie comme du temps réel' % FENETRE_FRAICHEUR_S)
    assert 'src' not in e, 'une valeur périmée a été marquée temps réel'


def test_la_fenetre_de_fraicheur_ne_s_elargit_pas():
    """Anti-dérive de la borne elle-même.

    Première version : `'< 75' in src`. **Creuse** — la preuve ROUGE l'a
    démasquée : la chaîne apparaît 4 fois dans `terminal.py` (deux autres
    fraîcheurs `_live_meta`, plus la docstring), donc élargir la fenêtre de
    l'overlay laissait le test vert. On lit désormais la constante DANS le
    corps de la fonction, par AST.
    """
    arbre = ast.parse(open(FICHIER, encoding='utf-8').read())
    fn = next(n for n in ast.walk(arbre)
              if isinstance(n, ast.FunctionDef) and n.name == '_apply_ibkr_indices')
    bornes = [c.value for n in ast.walk(fn) if isinstance(n, ast.Compare)
              for c in n.comparators
              if isinstance(c, ast.Constant) and isinstance(c.value, (int, float))
              and not isinstance(c.value, bool)]
    assert FENETRE_FRAICHEUR_S in bornes, (
        'la fenêtre de fraîcheur de %d s a disparu du corps de '
        '_apply_ibkr_indices (bornes trouvées : %s) — l\'élargir revient à '
        'présenter des valeurs périmées comme du temps réel'
        % (FENETRE_FRAICHEUR_S, bornes))


def test_l_overlay_ne_reassigne_pas_l_etat_partage():
    """`scan_state` est muté EN PLACE, jamais réassigné (règle d'architecture).
    L'overlay est l'un des rares écrivains directs."""
    arbre = ast.parse(open(FICHIER, encoding='utf-8').read())
    fn = next(n for n in ast.walk(arbre)
              if isinstance(n, ast.FunctionDef) and n.name == '_apply_ibkr_indices')
    for n in ast.walk(fn):
        if isinstance(n, ast.Assign):
            for c in n.targets:
                assert not (isinstance(c, ast.Name) and c.id == 'scan_state'), (
                    'scan_state réassigné dans _apply_ibkr_indices (L%d)' % n.lineno)


# ── 3. `bret = 0.0` : la sensibilité mesurée, figée ─────────────────────────

def test_le_repli_du_rendement_de_reference_n_est_pas_neutre():
    """Fige la mesure qui interdit d'innocenter ce repli par le raisonnement.
    `rs` est une force RELATIVE ; avec `bench_ret = 0`, elle devient une
    performance ABSOLUE — un score très différent, pas un milieu d'échelle.
    """
    import numpy as np

    def rs(sym_ret, bench_ret):
        return float(np.clip(50 + (sym_ret - bench_ret) * 200, 0, 100))

    assert rs(0.10, 0.15) == 40.0 and rs(0.10, 0.0) == 70.0
    assert rs(-0.05, 0.12) == 16.0 and rs(-0.05, 0.0) == 40.0
    ecarts = [abs(rs(s, b) - rs(s, 0.0)) for s, b in
              ((0.10, 0.15), (-0.05, 0.12), (0.20, 0.20))]
    assert min(ecarts) >= 20, (
        'le repli bench_ret=0 serait devenu indolore (écarts %s) — si la '
        'formule de force relative a changé, refaire la caractérisation'
        % ecarts)


def test_la_formule_de_force_relative_est_bien_celle_mesuree():
    """Anti-péremption : la caractérisation ci-dessus ne vaut que tant que la
    formule est celle-là. Si elle change, le lot 386 doit être rejoué."""
    src = open('vertex/engines/analysis.py', encoding='utf-8').read()
    assert '(sym_ret - bench_ret) * 200' in src, (
        'la formule de force relative a changé : la caractérisation du repli '
        'bench_ret=0 (lot 386) doit être refaite sur la nouvelle formule')


def test_le_chemin_de_scan_vivant_passe_un_rendement_reel():
    """Ce qui confine le repli au backtest. Si le scan vivant se mettait à
    appeler `analyse` sans rendement de référence réel, la distorsion mesurée
    ci-dessus atteindrait les scores SERVIS."""
    src = open(FICHIER, encoding='utf-8').read()
    assert 'analyse(df, bench_ret' in src, (
        'le chemin de scan vivant n\'appelle plus analyse() avec un rendement '
        'de référence réel : la distorsion du repli 0.0 atteindrait les '
        'scores servis')


@pytest.mark.parametrize('cle', ['edge', 'indices_live'])
def test_les_cles_non_lues_partent_quand_meme_au_client(cle):
    """Constat figé, pas un reproche : `/scan` sérialise `{**scan_state}`, donc
    ces clés voyagent. Aucune page servie ne les lit (mesuré au lot 386) — si
    l'une gagnait un lecteur, sa caractérisation ci-dessus deviendrait un
    enjeu d'affichage et devrait être revue."""
    #  #779/G1 — `/scan` a quitte terminal.py pour
    #  `vertex/app/routes/scan_api.py`. LE CONSTAT EST INCHANGE : la route
    #  serialise toujours `{**scan_state}`, donc ces cles voyagent toujours.
    #  Seul le fichier a change ; le pointer ici garde le constat vivant.
    src = open('vertex/app/routes/scan_api.py', encoding='utf-8').read()
    assert '**scan_state' in src, (
        '/scan ne sérialise plus scan_state en bloc : revoir ce que la clé '
        '« %s » atteint désormais' % cle)
