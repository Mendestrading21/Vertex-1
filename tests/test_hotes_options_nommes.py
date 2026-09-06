# -*- coding: utf-8 -*-
"""Aucun hôte de contenu des vues Options ne reste MUET dans un état dégradé.

Mesure du 2026-09-06 (contrôle adverse) : sur `/options?view=scenarios`, la
branche « aucun titre dans le tableau » ne nommait qu'UN hôte sur deux. Le
second, `vx-opt-strategies`, gardait son texte de départ — « Choisis un symbole
pour construire les stratégies depuis le board » — à l'identique dans les DEUX
états mesurés : board vide (consigne inapplicable, puisqu'il n'y a aucun
symbole à choisir) et lecture en échec HTTP 503 (panne tue). C'est la même
confusion entre absence et panne qu'un correctif venait de fermer sur le rail
voisin de la même vue.

Ce banc lit les DEUX sources et les rapproche : tout hôte de contenu déclaré
dans le gabarit d'une vue doit être nommé par la branche dégradée de cette vue.
Aucun réseau, aucun navigateur.
"""
import os
import re

_RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PAGE = os.path.join(_RACINE, 'vertex', 'ui', 'pages', 'options_intel_page.py')
_JS = os.path.join(_RACINE, 'vertex', 'static', 'vertex', 'js', 'pages', 'options-intel.js')

#: Les vues dont la branche dégradée passe par `nommerAbsenceDeTableau`.
_VUES = ('volatility', 'scenarios', 'events')
#: Un hôte de CONTENU est un conteneur rempli par le JS. Le pont local (champ
#: de saisie et bouton, `hidden`) et les sections englobantes n'en sont pas.
_PONT = re.compile(r'vx-opt-\w+-(sym|go)$')


def _lire(p):
    with open(p, encoding='utf-8') as f:
        return f.read()


def _gabarit(vue: str) -> str:
    src = _lire(_PAGE)
    debut = src.index("    '%s': \"\"\"" % vue)
    fin = src.index('\n"""', debut)
    return src[debut:fin]


def _hotes_de_contenu(vue: str) -> set[str]:
    """Les `<div id="…">` que le JS doit remplir, hors pont et hors sections."""
    gab = _gabarit(vue)
    #  Un hôte porte souvent une classe de grille AVANT son identifiant
    #  (`<div class="vx-col-4" id="vx-opt-cone">`) : chercher `<div id=` seul
    #  n'en voyait qu'un sur cinq — une garde qui ne mesure presque rien.
    ids = set(re.findall(r'<div[^>]*\bid="(vx-opt-[\w-]+)"', gab))
    return {i for i in ids if not _PONT.search(i)}


def _hotes_nommes(vue: str) -> set[str]:
    """Les identifiants passés à `nommerAbsenceDeTableau` pour cette vue."""
    js = _lire(_JS)
    charnieres = {'volatility': 'vx-opt-vol-out-body',
                  'scenarios': 'vx-opt-sc-out-body',
                  'events': 'vx-opt-ev-out-body'}
    rail = charnieres[vue]
    m = re.search(r"nommerAbsenceDeTableau\(\s*'%s'\s*,\s*\[([^\]]*)\]" % re.escape(rail), js)
    assert m, 'la vue %s n’appelle plus nommerAbsenceDeTableau' % vue
    return {rail} | set(re.findall(r"'([^']+)'", m.group(1)))


def test_le_banc_mesure_bien_quelque_chose():
    """Une garde qui n'inspecte rien est une garde qui ment."""
    for vue in _VUES:
        assert _hotes_de_contenu(vue), vue
    assert 'vx-opt-strategies' in _hotes_de_contenu('scenarios')
    assert len(_hotes_de_contenu('volatility')) >= 4


def test_chaque_hote_de_contenu_est_nomme_dans_l_etat_degrade():
    manquants = {}
    for vue in _VUES:
        oublies = _hotes_de_contenu(vue) - _hotes_nommes(vue)
        if oublies:
            manquants[vue] = sorted(oublies)
    assert not manquants, (
        'ces hôtes gardent leur texte de départ dans les DEUX états dégradés — '
        'une consigne inapplicable quand le tableau est vide, une panne muette '
        'quand la lecture échoue : %s' % manquants)


def test_l_etat_de_PANNE_est_distinct_de_l_etat_d_ABSENCE():
    """Un hôte qui dit la même chose dans les deux états ne dit rien."""
    js = _lire(_JS)
    m = re.search(r'function nommerAbsenceDeTableau\([^)]*\)\s*\{(.*?)\n  \}', js, re.S)
    assert m, 'nommerAbsenceDeTableau introuvable'
    corps = m.group(1)
    assert 'lecture en échec' in corps, 'la panne doit être nommée comme telle'
    assert 'VX.states.error' in corps and 'VX.states.empty' in corps, (
        'les deux états doivent employer deux rendus DISTINCTS')


def test_la_vue_structure_nomme_ses_quatre_hotes():
    """Même défaut, autre fichier : `options-structure.js` en vidait deux."""
    src = _lire(os.path.join(_RACINE, 'vertex', 'static', 'vertex', 'js',
                             'pages', 'options-structure.js'))
    m = re.search(r'var HOTES_STRUCTURE = \[(.*?)\];', src, re.S)
    assert m, 'la liste des hôtes de la vue Structure a disparu'
    hotes = set(re.findall(r"\['([\w-]+)'", m.group(1)))
    assert hotes == {'vx-os-scenarios', 'vx-os-compare', 'vx-os-payoff', 'vx-os-greeks'}, hotes
    #  Les trois chemins dégradés (aucune structure, analyse absente, panne)
    #  passent tous par le même endroit : aucun ne peut en oublier un.
    assert src.count('nommerAbsenceStructure(') >= 4, (
        'un chemin dégradé ne passe pas par le nommage commun')
