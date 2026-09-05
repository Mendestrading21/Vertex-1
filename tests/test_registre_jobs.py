"""Vertex Test 1.0 · #779/G1 — LE REGISTRE DE JOBS NE DÉCLARE PLUS CE QU'IL N'A PAS.

`RELEASE_GATES.md` G1 demande un propriétaire modulaire pour le scheduler. Il en
avait déjà un — `vertex/scheduler/registry.py` — et c'est précisément ce qui
rendait le défaut invisible : la case était cochée.

## Ce que la mesure a trouvé

`tools/mesures/mesurer_registre_jobs.py` énumère à l'AST **tous** les appels
`registry.beat('NOM')` du dépôt. Le registre ne reçoit d'information que par
là : un nom déclaré qu'aucun `beat` ne porte ne peut pas tourner, jamais.

```text
avant : 27 jobs déclarés · 7 émetteurs · 20 jobs sans exécutant
après : 27 jobs déclarés · 9 émetteurs · 18 marqués `implemente: False`
```

## Pourquoi c'était un défaut d'honnêteté, pas de cosmétique

`/api/system/automations` servait les 27 lignes à l'identique, et la page
Système affichait **« jamais exécuté »** pour toutes celles sans `last_run` —
le même mot pour un job en panne et pour un job qui n'existe pas. Le pied de
page allait plus loin et *expliquait* le silence : « dépendent d'intégrations
absentes dans cet environnement ». Ce diagnostic était faux. `NEWS_REFRESH`,
par exemple, tournait toutes les 60 s depuis toujours : sa boucle n'émettait
simplement aucun battement. Deux mensonges de sens opposé sur la même ligne.

C'est la règle 4 de `CLAUDE.md` — donnée absente → aveu honnête, jamais une
valeur inventée — appliquée à un état plutôt qu'à un chiffre.

## Le drapeau est confronté à la mesure DANS LES DEUX SENS

`implemente` serait sans valeur s'il n'était qu'une annotation : il dériverait au
premier ajout. Le test central le compare à ce que l'AST trouve, dans les deux
directions — marquer un job implémenté sans émetteur échoue, et poser un
émetteur sans lever le drapeau échoue aussi.
"""
import importlib
import pathlib
import sys

import pytest

RACINE = pathlib.Path(__file__).resolve().parents[1]
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

from tools.mesures import mesurer_registre_jobs as _mes  # noqa: E402

_reg = importlib.import_module('vertex.scheduler.registry')


@pytest.fixture(scope='module')
def mesure():
    return _mes.mesurer()


def test_le_drapeau_implemente_colle_a_la_mesure_dans_les_deux_sens(mesure):
    """LE CŒUR DU GARDIEN.

    Un job marqué implémenté doit avoir un émetteur ; un job qui a un émetteur
    doit être marqué implémenté. Les deux écarts sont des mensonges — de sens
    opposé, mais servis par la même API."""
    etat_mesure = {l['nom']: l['etat'] for l in mesure['jobs']}
    declare = {nom: bool(ok) for nom, _, _, ok in _reg._CANONICAL_4}

    menteurs_optimistes = sorted(
        n for n, ok in declare.items() if ok and etat_mesure[n] == 'SANS_EMETTEUR')
    assert not menteurs_optimistes, (
        'ces jobs se declarent implementes mais aucun appel beat() ne porte '
        'leur nom : /api/system/automations les affichera « en attente » pour '
        'toujours, ce qui se lit comme une panne — %s' % menteurs_optimistes)

    menteurs_pessimistes = sorted(
        n for n, ok in declare.items() if not ok and etat_mesure[n] == 'ACTIF')
    assert not menteurs_pessimistes, (
        'ces jobs ont un emetteur mais restent marques « non implemente » : '
        'l\'ecran nie un travail qui a bien lieu — %s' % menteurs_pessimistes)


def test_la_mesure_nest_pas_aveugle(mesure):
    """Un détecteur qui ne trouve rien ne prouve rien. Les deux témoins de
    l'outil sont rejoués ici : sans eux, ce fichier vérifierait seulement que
    « rien ne trouve rien »."""
    echecs = _mes._temoins(mesure)
    assert not echecs, 'les temoins de l\'instrument sont muets : %s' % echecs
    assert _mes.TEMOIN_ABSENT not in {l['nom'] for l in mesure['jobs']}, (
        'le temoin negatif a ete declare au registre : il ne temoigne plus')
    assert mesure['actifs'] >= 9, (
        'seulement %d jobs actifs : des emetteurs ont disparu du depot'
        % mesure['actifs'])


def test_les_deux_emetteurs_poses_battent_reellement():
    """`NEWS_REFRESH` et `POSITION_REFRESH` ont été câblés dans ce lot. Vérifier
    la seule présence de la chaîne dans la source serait creux : c'est
    l'effet sur le registre qui compte."""
    src_terminal = RACINE.joinpath('terminal.py').read_text(encoding='utf-8')
    assert "_sched.beat('NEWS_REFRESH'" in src_terminal, (
        'la boucle de nouvelles n\'emet plus de battement : NEWS_REFRESH '
        'redevient invisible alors qu\'elle tourne toutes les 60 s')
    src_desk = RACINE.joinpath('vertex/app/routes/desk.py').read_text(encoding='utf-8')
    assert "_sched.beat('POSITION_REFRESH'" in src_desk, (
        '/api/pos-quotes n\'emet plus de battement : POSITION_REFRESH '
        'redevient invisible')

    #  L'EFFET, pas la chaine : on bat, et on regarde ce que sert `jobs()`.
    _reg.beat('NEWS_REFRESH', ok=True)
    ligne = next(j for j in _reg.jobs() if j['name'] == 'NEWS_REFRESH')
    assert ligne['etat'] == 'ACTIF' and ligne['last_run'], (
        'un battement ne fait plus passer le job a ACTIF : %s' % ligne)


def test_letat_distingue_les_trois_situations():
    """`last_run: null` confondait « non implémenté », « en attente » et
    « en panne ». Trois causes, trois conduites à tenir."""
    lignes = {j['name']: j for j in _reg.jobs()}
    #  Non implémenté : le registre le sait AVANT tout battement.
    assert lignes['THESIS_HEALTH_REVIEW']['etat'] == 'NON_IMPLEMENTE'
    #  En panne : un battement en échec ne doit pas se lire « OK ».
    _reg.beat('CATALYST_REFRESH', ok=False, error='reseau')
    assert next(j for j in _reg.jobs()
                if j['name'] == 'CATALYST_REFRESH')['etat'] == 'ERREUR'
    _reg.beat('CATALYST_REFRESH', ok=True)


def test_lecran_ne_dit_plus_jamais_execute_ni_ne_l_explique_a_tort():
    """La sortie compte autant que le registre : c'est elle que l'utilisateur
    lit. L'ancien pied de page *expliquait* le silence par des « intégrations
    absentes » — une affirmation invérifiable sur 20 lignes dont la plupart
    n'avaient aucun exécutant."""
    src = RACINE.joinpath('vertex/ui/pages/system_page.py').read_text(encoding='utf-8')
    assert 'jamais exécuté' not in src, (
        'la page Systeme accuse de nouveau un job de n\'avoir jamais tourne '
        'alors qu\'il n\'a peut-etre aucun executant')
    assert 'dépendent d\'intégrations absentes' not in src, (
        'le pied de page rediagnostique le silence des jobs : cette phrase '
        'etait fausse pour 18 des 27 lignes')
    assert 'NON_IMPLEMENTE:' in src and 'non implémenté' in src, (
        'l\'ecran ne distingue plus « non implemente » des autres etats')


def test_la_colonne_prochaine_ne_promet_rien_a_un_job_sans_executant():
    """TROUVÉ À LA CAPTURE, PAS À L'API.

    Le statut corrigé, la ligne continuait d'annoncer **« sur événement »** dans
    la colonne « Prochaine (est.) » pour sept jobs sans exécutant. C'est une
    promesse : aucun événement ne déclenchera jamais un job que rien n'exécute.
    La même invention que le statut, une colonne plus loin — invisible depuis
    `/api/system/automations`, qui sert un JSON sans cette colonne."""
    src = RACINE.joinpath('vertex/ui/pages/system_page.py').read_text(encoding='utf-8')
    assert "j.etat==='NON_IMPLEMENTE'?'—':" in src, (
        'la colonne « Prochaine » ne court-circuite plus les jobs sans '
        'executant : elle leur promet de nouveau un declenchement')


def test_le_bilan_du_scheduler_ne_compte_plus_les_jobs_sans_executant():
    """Deuxième récidive, dans le panneau Démarrage : « 27 jobs enregistrés »
    présenté comme un état de santé READY. Le total flattait en comptant 18
    lignes qu'aucun code n'exécute."""
    from vertex.services import connections as _cx
    src = pathlib.Path(_cx.__file__).read_text(encoding='utf-8')
    #  ON VISE LA CHAINE SERVIE, pas le mot : « jobs enregistrés » vivait aussi
    #  dans un commentaire deux lignes plus haut — le chercher tel quel faisait
    #  echouer le test sur une prose sans effet.
    assert "%d jobs enregistrés" not in src, (
        'le bilan du scheduler recompte tous les jobs declares, executables ou '
        'non : le total redevient flatteur')
    assert 'jobs exécutables' in src and 'déclarés sans exécutant' in src, (
        'le bilan ne distingue plus executable et declare')

    instantane = _cx.snapshot({}, ibkr_enabled=False, demo_mode=True)
    ligne = next(c for c in instantane['connections'] if c['name'] == 'Scheduler')
    #  9 -> 10 : `FUNDAMENTALS_REFRESH` est DÉCLARÉ. La boucle des
    #  fondamentaux tournait déjà — elle empruntait le battement de
    #  `TRACK_RECORD_UPDATE`, le job d'une autre boucle. Le total des
    #  10 -> 12 : `OPTIONS_BOARD_REFRESH` (board d'options, 120 s) et
    #  `MARKET_RADAR_REFRESH` (scanners du marché entier + fil courtier,
    #  240 s), qui tournaient sans aucune ligne. Le total des
    #  exécutables monte parce qu'une capacité réelle cesse d'être invisible,
    #  pas parce qu'on a ajouté une ligne décorative : « 18 déclarés sans
    #  exécutant » ne bouge pas, et `test_le_drapeau_implemente_suit_la_mesure`
    #  refuserait le drapeau sans émetteur.
    assert '13 jobs exécutables' in ligne['detail'], (
        'le detail servi ne reflete pas la mesure : %s' % ligne['detail'])
    assert '18 déclarés sans exécutant' in ligne['detail'], (
        'les jobs sans executant ne sont plus nommes : %s' % ligne['detail'])


def test_les_intervalles_annonces_ne_sont_pas_inventes():
    """Deux cadences déclarées ne correspondaient à aucune boucle réelle.

    `NEWS_REFRESH` annonçait 900 s pour une boucle à 60 s, et `POSITION_REFRESH`
    annonçait 45 s pour une route **à la demande**. `next_run_eta_s` en dérive :
    l'écran affichait « prochaine dans ~15 min » pour un job qui repasse dans la
    minute, et un compte à rebours pour un job qui ne repasse que si on le
    demande."""
    par_nom = {n: i for n, _, i, _ in _reg._CANONICAL_4}
    assert par_nom['NEWS_REFRESH'] == 60, (
        'la cadence de NEWS_REFRESH ne suit plus la boucle ; verifier '
        '`_live.wait_force(\'news\', N)` dans terminal.py')
    src = RACINE.joinpath('terminal.py').read_text(encoding='utf-8')
    assert "_live.wait_force('news', 60)" in src, (
        'la boucle de nouvelles a change de cadence : mettre a jour '
        'NEWS_REFRESH dans le registre, sinon l\'ETA servi est faux')
    assert par_nom['POSITION_REFRESH'] is None, (
        'POSITION_REFRESH annonce de nouveau une cadence : la cotation des '
        'positions est declenchee par /api/pos-quotes, pas par un minuteur')


def test_la_forme_a_trois_colonnes_reste_servie():
    """`_CANONICAL` est lu ailleurs dans le dépôt. Ajouter une quatrième colonne
    ne doit pas casser ces appelants."""
    assert all(len(t) == 3 for t in _reg._CANONICAL)
    #  27 -> 30 : `FUNDAMENTALS_REFRESH`, `OPTIONS_BOARD_REFRESH` et
    #  `MARKET_RADAR_REFRESH` (cf. ci-dessus). Trois boucles cadencées
    #  qui tournaient sans aucune ligne à l'écran, chacune empruntant le
    #  job d'une autre ou n'en ayant aucun. Toutes les boucles de fond
    #  du produit sont désormais déclarées.
    assert len(_reg._CANONICAL) == len(_reg._CANONICAL_4) == 31
    assert _reg.NON_IMPLEMENTES and 'NEWS_REFRESH' not in _reg.NON_IMPLEMENTES
