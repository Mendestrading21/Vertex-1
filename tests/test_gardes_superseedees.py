"""Vertex Test 1.0 — LE RECENSEMENT DES GARDES ÉCARTÉES.

## Le danger que ce fichier existe pour écarter

Écarter cent cinquante bancs est une opération dangereuse. Faite une fois, elle est
documentée ; faite deux fois sans compteur, elle devient une habitude, et la
suite finit verte parce qu'elle ne regarde plus rien.

`tests/_supersede.py` nomme chaque banc écarté et son motif. Ce fichier-ci
tient les quatre garanties qui rendent cette liste sûre :

1. **elle ne grossit pas en silence** — le nombre est épinglé ; un banc qui
   échoue demain n'y entre pas tout seul ;
2. **aucune entrée n'est morte** — un banc réécrit ou supprimé doit sortir de
   la liste, sinon on croirait couvert ce qui n'existe plus ;
3. **un banc hors liste n'est jamais écarté** — la contre-épreuve du
   mécanisme lui-même ;
4. **une perte de fond ne s'y cache pas** — le seul cas qui en avait l'air,
   la machine à états de thèse du Portefeuille, s'est révélé être un
   troisième nom fantôme (`thesisState` appelée, jamais définie). Il a été
   corrigé, pas classé. Le motif `REGLE_PERDUE` reste déclaré et inemployé :
   le jour où il servira, ce sera une décision, pas une dérive.

## Ce que la liste ne dit pas

Elle ne dit pas que ces 153 bancs avaient tort. Ils décrivaient fidèlement
l'interface de `main`. Elle dit que **cette interface n'est plus celle qui est
servie**, et qu'un banc qui décrit une page absente ne mesure plus rien.
"""
from __future__ import annotations

import importlib.util
import os
import re
import subprocess
import sys

import pytest

_ICI = os.path.dirname(os.path.abspath(__file__))
_RACINE = os.path.dirname(_ICI)


def _module():
    spec = importlib.util.spec_from_file_location(
        '_vx_supersede_banc', os.path.join(_ICI, '_supersede.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope='module')
def sup():
    return _module()


#: Mesure du 27 août 2026, à la fusion. **Ne pas relever ce nombre sans avoir
#: lu les nouveaux cas** : c'est exactement la discipline que les recensements
#: `except: pass` imposent depuis le lot 378, et pour la même raison.
#  PISTE OUVERTE, non exploitee ici : `test_parallel_scan_is_byte_identical_to_serial`
#  est ecarte sous le motif MARQUAGE, qui est INEXACT — il garde une invariance
#  FONCTIONNELLE (scan parallele == scan serie), pas du balisage. L invariant
#  a ete verifie hors pytest et TIENT : 392 326 octets identiques, une fois
#  l horloge figee pour neutraliser les champs derives du temps (`age_s`). Le
#  banc echoue parce qu il colle l invariant et son anti-vide dans un seul
#  `and`, et parce que les deux scans ne tournent pas au meme instant. Le
#  remettre en service demande de figer l horloge ET de comprendre pourquoi il
#  reste rouge a froid sous pytest alors qu il passe hors pytest. Non fait.
#  153 a la fusion, puis 148, puis 140, puis 132 : huit gardes PASSAIENT
#  aujourd hui et dormaient ecartees — leur couverture etait retablie sans que
#  personne le sache, parce que le banc cense le voir ne faisait que COLLECTER.
#  153 a la fusion, puis 148, puis 140 : six entrees designaient des bancs
#  supprimes avec le code injoignable qu ils gardaient, et deux nommaient
#  une fonction qui n a jamais existe (orphelines depuis l origine).
#  153 a la fusion, puis 148 : sept bancs du garde-fou de these sont SORTIS
#  de la liste (la regle a ete portee, ils mesurent de nouveau quelque chose)
#  et deux y sont entres pour la propriete deplacee de la courbe de resultats.
#  Une liste qui DIMINUE est le signe qu'on la relit.
#  130 depuis le 2026-09-06 : `test_fraicheur_garde_type::
#  test_les_cinq_sites_appellent_bien_assess` est SORTIE du registre. Elle
#  passe de nouveau — un lot a rétabli les cinq appels à `assess` qu'elle
#  surveille. Laisser une garde écartée alors que sa couverture est revenue,
#  c'est éteindre une protection sans que personne ne le sache : le registre
#  doit rétrécir dès qu'il le peut.
TOTAL_ECARTES = 130


#  ═══════════  1. la liste ne grossit pas  ════════════════════════════════════

def test_le_nombre_de_gardes_ecartees_est_EPINGLE(sup):
    """Un banc qui échoue demain doit échouer, pas rejoindre la liste."""
    assert len(sup.REGISTRE) == TOTAL_ECARTES, (
        'la liste des gardes ecartees a change (%d au lieu de %d) — lire les '
        'nouveaux cas AVANT de mettre ce nombre a jour'
        % (len(sup.REGISTRE), TOTAL_ECARTES))


def test_chaque_entree_porte_un_motif_CONNU(sup):
    """Un motif libre deviendrait vite « divers », et « divers » ne se relit
    pas."""
    connus = {sup.PALETTE, sup.MARQUAGE, sup.REGLE_PERDUE,
              sup.PROPRIETE_DEPLACEE}
    inconnus = {t: m for t, m in sup.REGISTRE.items() if m not in connus}
    assert inconnus == {}, inconnus


def test_les_motifs_EMPLOYES_sont_ceux_qu_on_croit(sup):
    """`REGLE_PERDUE` est déclaré et volontairement INEMPLOYÉ.

    La seule perte de fond que la fusion semblait avoir produite — la machine
    à états de thèse du Portefeuille — s'est révélée être un troisième nom
    fantôme : la page appelait `thesisState`, donc la refonte la voulait, et
    la fonction n'était définie nulle part. Elle a été portée.

    Ce banc fige cet état. Le jour où `REGLE_PERDUE` servira, il faudra le
    décider explicitement — pas le laisser arriver.
    """
    employes = set(sup.REGISTRE.values())
    assert sup.PALETTE in employes
    assert sup.MARQUAGE in employes
    assert sup.PROPRIETE_DEPLACEE in employes
    assert sup.REGLE_PERDUE not in employes, (
        'une garde est desormais ecartee pour REGLE PERDUE : une regle '
        'produit ne s applique plus, et cela demande une decision humaine')


def test_la_liste_reste_une_affaire_de_PIXELS(sup):
    """Si le gros de la liste cessait d'être palette et balisage, la fusion
    aurait coûté des fonctionnalités et non des pixels — et ce banc doit le
    crier avant qu'on s'y habitue."""
    pixels = sum(1 for m in sup.REGISTRE.values()
                 if m in (sup.PALETTE, sup.MARQUAGE))
    assert pixels >= len(sup.REGISTRE) - 5, (
        'seules %d entrees sur %d relevent du visuel : le reste est du fond'
        % (pixels, len(sup.REGISTRE)))


#  ═══════════  2. aucune entrée n'est morte  ══════════════════════════════════

def test_chaque_entree_designe_un_fichier_QUI_EXISTE(sup):
    """Un banc supprimé qui resterait listé ferait croire à une couverture
    écartée alors qu'elle a simplement disparu."""
    manquants = sorted({t.split('::')[0] for t in sup.REGISTRE
                        if not os.path.exists(os.path.join(_RACINE, t.split('::')[0]))})
    assert manquants == [], (
        'entrees mortes — le fichier n existe plus : %s' % manquants)


#: Gardes dont le VERDICT DEPEND DE L ENVIRONNEMENT, et que le banc ci-dessous
#: ne peut donc pas juger. Nommees une par une, avec leur raison — jamais une
#: regle large. Une entree ici est un aveu, pas un classement : elle dit « ce
#: banc n est ni fiablement rouge ni fiablement vert », ce qui est une
#: information, pas une exemption.
ETAT_DEPENDANT = {
    #  Invariance FONCTIONNELLE (scan parallele == scan serie), ecartee a tort
    #  sous un motif VISUEL. Elle est VRAIE : verifiee hors pytest, 392 326
    #  octets identiques, horloge figee pour neutraliser les champs derives du
    #  temps (`age_s`). Mais le banc colle l invariant et son anti-vide
    #  (`len > 1000`) dans un seul `and` : il passe quand des caches existent
    #  sur disque, echoue sur un arbre froid. Le rallumer demande de separer
    #  les deux assertions ET de figer l horloge — non fait, lot a part.
    'tests/test_scan_parallel.py::test_parallel_scan_is_byte_identical_to_serial',
}


def test_aucune_entree_ne_designe_un_banc_QUI_PASSE(sup):
    """La garantie la plus utile : un banc redevenu vert doit SORTIR de la
    liste. Sinon on croit avoir renonce a une couverture qu on a en realite
    retablie — et on ne la remet jamais en service.

    CE BANC NE TENAIT PAS SON NOM. Il lancait pytest avec `--co` : la
    COLLECTE seule. Il prouvait que les identifiants existent encore, jamais
    qu ils echouent encore. Huit gardes etaient donc vertes et ecartees en
    silence, dont `test_journal_hero_is_honest_no_fabricated_percent` — un
    controle d honnetete. Le nom promettait « QUI PASSE », le corps mesurait
    « QUI EXISTE ».

    Il les EXECUTE desormais, avec le registre neutralise. Cout mesure ~27 s.
    C est le prix de la garantie : un echantillon laisserait dormir la majorite
    des cas, et c est exactement ce qui s est produit.

    LIMITE ASSUMEE. Les entrees de `ETAT_DEPENDANT` sont exclues : leur verdict
    depend de l etat du disque, donc ce banc ne peut rien en conclure. Sans
    cette exclusion il etait lui-meme CAPRICIEUX — vert sur un arbre froid,
    rouge apres une suite complete qui a rempli les caches. Un gardien qui
    change d avis selon ce qui a tourne avant ne garde rien.
    """
    ids = sorted(set(sup.REGISTRE) - ETAT_DEPENDANT)
    assert ids, 'registre vide : ce banc n aurait plus rien a prouver'

    #  Le registre doit etre neutralise, sinon le hook de `conftest` ecarte
    #  les bancs qu on vient justement demander a executer.
    env = dict(os.environ, VERTEX_SUPERSEDE_OFF='1')
    r = subprocess.run(
        [sys.executable, '-m', 'pytest', '-p', 'no:cacheprovider',
         '--no-header', '--tb=no', '-v'] + ids,
        capture_output=True, text=True, errors='replace', cwd=_RACINE, env=env)

    #  Temoin : si RIEN n a ete execute, l absence de vert ne prouve rien.
    assert re.search(r'\d+ (failed|passed)', r.stdout or ''), (
        'aucun banc execute — la mesure serait vide de sens :\n%s'
        % (r.stdout or '')[-800:])

    #  On NOMME les gardes vertes. Un compte seul obligerait a refaire la
    #  mesure a la main pour savoir lesquelles sortir.
    verts = sorted(l.split(' ')[0] for l in (r.stdout or '').splitlines()
                   if ' PASSED' in l)
    assert verts == [], (
        '%d garde(s) ecartee(s) passe(nt) aujourd hui : leur couverture est '
        'retablie mais reste eteinte. Les SORTIR du registre :\n  %s'
        % (len(verts), '\n  '.join(verts)))


def test_les_exceptions_d_etat_restent_NOMMEES_et_rares(sup):
    """Une liste d exceptions qui grossit finit par vider le gardien. Chaque
    entree doit encore etre ecartee — sinon elle n a plus rien a y faire — et
    leur nombre est epingle."""
    hors_registre = sorted(ETAT_DEPENDANT - set(sup.REGISTRE))
    assert hors_registre == [], (
        'exception d etat sur un banc qui n est plus ecarte : %s' % hors_registre)
    assert len(ETAT_DEPENDANT) <= 1, (
        '%d exceptions d etat : au-dela d une, ce n est plus un aveu ponctuel '
        'mais une porte de sortie' % len(ETAT_DEPENDANT))


#  ═══════════  3. le mécanisme n'écarte que ce qui est listé  ═════════════════

def test_un_banc_HORS_liste_n_est_jamais_ecarte(sup):
    """Contre-épreuve du mécanisme. Une règle large — « tous les bancs
    visuels » — écarterait demain des bancs neufs sans que personne ne le
    voie. Le hook lit un dictionnaire, et rien d'autre."""
    assert 'tests/test_gardes_superseedees.py' not in {
        t.split('::')[0] for t in sup.REGISTRE}
    #  Ce banc-ci tourne : la preuve vivante que le hook ne ratisse pas large.


def test_le_hook_lit_bien_le_REGISTRE_et_pas_un_motif(sup):
    conftest = open(os.path.join(_ICI, 'conftest.py'), encoding='utf-8').read()
    assert 'REGISTRE.get(' in conftest, (
        'le hook n interroge plus le registre nominatif')
    for large in ('visual', 'startswith', 'endswith(', 'fnmatch', 're.match'):
        assert large not in conftest.split('pytest_collection_modifyitems')[1], (
            'le hook ecarte par MOTIF (%r) et non par nom : de nouveaux bancs '
            'seraient emportes sans qu on le voie' % large)


#  ═══════════  4. la perte réelle reste lisible  ══════════════════════════════

def test_la_perte_relevee_a_ete_CORRIGEE(sup):
    """Le releve initial concluait a une perte de fond. La contre-epreuve de
    ce recensement a montre le contraire : la page APPELAIT `thesisState`,
    donc la refonte la voulait ; elle n'etait definie nulle part. Le bloc
    levait `ReferenceError` et la regle « ne jamais renforcer un perdant sans
    confirmation positive » ne s'appliquait plus. Les quatre fonctions ont ete
    portees."""
    assert sup.PERTE_REELLE['decision'] == 'CLOSE'
    assert 'PORTEE' in sup.PERTE_REELLE['quoi']


def test_la_regle_PORTEE_est_reellement_servie(sup):
    """Contre-epreuve : une note qui declare la correction faite alors que le
    code ne la porte pas serait le pire des deux mondes."""
    src = open(os.path.join(_RACINE, sup.PERTE_REELLE['ou']),
               encoding='utf-8').read()
    for fn in ('function hasPositiveConfirmation', 'function thesisState',
               'function winnerRule', 'function nextAction'):
        assert fn in src, 'la note declare portee une fonction absente : %s' % fn
    assert 'Renforcement interdit' in src, (
        'le garde-fou des perdants n est plus dans la page')
    #  Et elles sont APPELEES, pas seulement definies — c'est ce defaut-la
    #  qu'on vient de corriger.
    for appel in ('thesisState(', 'nextAction(', 'winnerRule('):
        assert src.count(appel) >= 2, 'definie mais jamais appelee : %s' % appel
