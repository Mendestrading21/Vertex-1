# -*- coding: utf-8 -*-
"""Le badge des fondamentaux nomme l'état RÉEL, pas « cache » par défaut.

Mesure du 2026-09-06, navigateur réel sur un titre jamais demandé (instance
neuve, cache froid) : la carte « Financials — fondamentaux » affichait ses
DOUZE mesures à « — » sous un badge « cache ». Rien n'était en cache : la
collecte était en vol, et la même page l'écrivait pourtant ailleurs
(`meta.rafraichissement_en_cours`). Vingt secondes plus tard les valeurs
arrivaient, badge inchangé.

Un tiret sous un badge « cache » se lit « la donnée manque à la source » ; sous
« collecte en cours » il se lit « pas encore reçu ». Absence, collecte,
instantané précédent, source injoignable et cache sont cinq états DISTINCTS
(invariant 5), et la page disposait déjà de la mesure.

Lecture de la source : aucun réseau, aucun navigateur.
"""
import os
import re

_RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PAGE = os.path.join(_RACINE, 'vertex', 'ui', 'pages', 'analysis_page.py')


def _src() -> str:
    with open(_PAGE, encoding='utf-8') as f:
        return f.read()


def _bloc_badge() -> str:
    src = _src()
    debut = src.index("const srcEl=$('an-fin-src')")
    return src[debut:debut + 1400]


def test_le_badge_nest_plus_une_constante():
    bloc = _bloc_badge()
    assert "srcEl.textContent=demo?'DÉMO':'cache'" not in bloc, (
        'le badge annonce de nouveau « cache » dans tous les états non-démo')


def test_les_cinq_etats_sont_distincts():
    """Un vocabulaire qui confond deux états n'en nomme aucun."""
    bloc = _bloc_badge()
    attendus = ('DÉMO', 'collecte en cours', 'source injoignable',
                'scan précédent', 'cache')
    manquants = [e for e in attendus if e not in bloc]
    assert not manquants, manquants
    #  Les libellés doivent être DIFFÉRENTS entre eux, sinon deux états se
    #  lisent pareil à l'écran. On ne lit QUE l'affectation du texte du badge :
    #  les tons et les infobulles vivent dans deux autres ternaires, et les
    #  mélanger ferait comparer des pommes et des poires.
    debut = bloc.index('srcEl.textContent=')
    texte = bloc[debut:bloc.index(';', debut)]
    libelles = re.findall(r"'([^']+)'", texte)
    assert len(libelles) >= 5, libelles
    assert len(set(libelles)) == len(libelles), (
        'deux états rendent le même libellé : %s' % libelles)


def test_l_etat_vient_de_la_MESURE_servie_et_non_d_une_intuition():
    bloc = _bloc_badge()
    assert 't.meta' in bloc, (
        'le badge doit lire `t.meta`, la seule mesure d’état que le serveur sert')
    for champ in ('rafraichissement_en_cours', 'etat', 'qualite'):
        assert champ in bloc, champ


def test_le_tiret_est_EXPLIQUE_pendant_la_collecte():
    """Le point du défaut : un tiret pendant la collecte n'est pas un zéro."""
    bloc = _bloc_badge()
    assert 'srcEl.title' in bloc, 'le badge ne porte aucune explication au survol'
    assert 'pas encore reçu' in bloc, (
        'rien ne dit au lecteur qu’un tiret en cours de collecte n’est pas une '
        'valeur manquante à la source')


def test_la_page_lit_le_meme_vocabulaire_que_son_bandeau():
    """Deux vocabulaires pour un même état seraient deux autorités."""
    src = _src()
    for etat in ("'MISSING'", "'OFFLINE'", "'STALE'"):
        assert src.count(etat) >= 2, (
            'l’état %s n’est plus reconnu aux deux endroits qui le lisent' % etat)
