# -*- coding: utf-8 -*-
"""Un dossier incomplet ne laisse aucune carte vide SANS motif.

Mesure du 2026-09-06, audit navigateur sur `/analysis/NVDA` à 1600 px :
« an-scenarios : carte vide ». Quand le moteur rend `DATA_INSUFFICIENT`, la
fiche vidait à néant DEUX conteneurs — `SC.innerHTML=''` et `CO.innerHTML=''`.
Les sections gardaient leur en-tête (« Scénarios Bull / Base / Bear ») et leur
corps devenait une chaîne vide.

Le lecteur voyait donc une promesse suivie de rien, juste à côté d'une carte de
verdict qui, elle, explique parfaitement pourquoi elle ne tranche pas. Une carte
vide sans motif ne distingue pas « rien à montrer » de « le rendu a échoué » —
c'est le même défaut d'hôte muet que les vues Options portaient.

Lecture de la source : ni réseau, ni navigateur.
"""
import os
import re

_RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PAGE = os.path.join(_RACINE, 'vertex', 'ui', 'pages', 'analysis_page.py')


def _src():
    with open(_PAGE, encoding='utf-8') as f:
        return f.read()


def _branche_incomplete() -> str:
    src = _src()
    d = src.index("if(dec.final_decision==='DATA_INSUFFICIENT')")
    return src[d:src.index('\n    return;', d)]


def test_la_branche_existe_toujours():
    """Une garde qui n'inspecte rien est une garde qui ment."""
    b = _branche_incomplete()
    assert 'an-verdict' in _src() and len(b) > 200


def test_aucun_conteneur_n_est_vide_a_neant():
    b = _branche_incomplete()
    for vide in ("SC.innerHTML=''", "CO.innerHTML=''",
                 'SC.innerHTML = ""', 'CO.innerHTML = ""'):
        assert vide not in b.replace(' ', '').replace('"', "'") or vide.count("'") == 0, b[:300]
    assert "SC.innerHTML=''" not in b.replace(' ', ''), (
        'les scénarios sont de nouveau vidés à néant : la carte garde son '
        'en-tête et ne montre rien')
    assert "CO.innerHTML=''" not in b.replace(' ', ''), b[:300]


def test_les_deux_conteneurs_recoivent_le_MEME_motif_que_le_verdict():
    """Un second vocabulaire pour la même cause serait une seconde autorité."""
    b = _branche_incomplete()
    assert 'VX.states.empty' in b, 'aucun état vide nommé'
    assert 'esc(miss)' in b, (
        'le motif ne réutilise pas la cause que le verdict a déjà mesurée '
        '(`missing_fields`) : il en invente une autre')
    #  Un seul motif construit, employé deux fois.
    assert b.count('VX.states.empty') == 1, b.count('VX.states.empty')


def test_l_en_tete_de_la_carte_n_est_pas_ecrit_deux_fois():
    """`an-scenarios` porte déjà son en-tête dans le gabarit."""
    b = _branche_incomplete()
    assert 'data-body' in b, (
        'la branche remplace tout le contenu de la section au lieu de son seul '
        'corps : l’en-tête serait écrit deux fois')
    assert 'vx-card-title' not in b, b[:300]


def test_le_conteneur_sans_en_tete_n_en_recoit_pas_un_invente():
    """`an-committee` est un simple conteneur : on n'y invente pas de titre."""
    src = _src()
    assert re.search(r'<div id="an-committee"[^>]*></div>', src), (
        'an-committee n’est plus un conteneur nu : vérifier que la branche '
        'incomplète ne duplique pas son en-tête')
