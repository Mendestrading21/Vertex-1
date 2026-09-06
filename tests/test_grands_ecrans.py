# -*- coding: utf-8 -*-
"""Sur un écran très large, Vertex utilise la place — sans devenir illisible.

MESURÉ le 2026-09-06 sur le poste de travail, deux écrans 5120 × 1440 (32:9) :
la page « Marchés » n'occupait que 34,4 % de l'écran, ne formait jamais plus de
DEUX colonnes, et 44 % de ses lignes ne portaient qu'une seule carte. Plus de
trois mille pixels — les deux tiers — restaient vides pendant qu'on faisait
défiler.

Sur un 32:9, la ressource RARE est la HAUTEUR : 1440 px, pas plus qu'un écran
ordinaire. Élargir sans réorganiser ne ferait qu'étirer les cartes et allonger
les lignes ; ce qui aide, c'est de mettre plus de choses côte à côte, pour
acheter de la hauteur avec de la largeur.

Après : 70,3 % d'écran utilisé, jusqu'à six colonnes, et la ligne de texte
bridée. Aucun débordement à 1024 ni à 390 px.

Ce banc lit les RÈGLES. La mesure au rendu, elle, vit dans
`tools/qa/mesurer_grand_ecran.py`, qui compare largeur occupée, colonnes
formées et longueur de ligne à plusieurs largeurs de fenêtre.
"""
import os
import re

_RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CSS = os.path.join(_RACINE, 'vertex', 'static', 'vertex', 'css')


def _lire(nom: str) -> str:
    with open(os.path.join(_CSS, nom), encoding='utf-8') as f:
        return f.read()


def _paliers(css: str) -> list[tuple[int, int]]:
    """(largeur de fenêtre, plafond de contenu) pour chaque palier déclaré."""
    out = []
    for m in re.finditer(r'@media\s*\(min-width:(\d+)px\)\s*\{[^}]*?'
                         r'\.vx-content\{max-width:(\d+)px\}', css):
        out.append((int(m.group(1)), int(m.group(2))))
    return sorted(out)


def test_les_paliers_de_largeur_montent_avec_la_fenetre():
    paliers = _paliers(_lire('layout.css'))
    assert len(paliers) >= 3, (
        'un seul palier : au-delà, tout écran plus large ne fait qu’ajouter du '
        'vide — %s' % paliers)
    largeurs = [p[0] for p in paliers]
    plafonds = [p[1] for p in paliers]
    assert largeurs == sorted(largeurs) and plafonds == sorted(plafonds), paliers
    assert max(largeurs) >= 4400, (
        'aucun palier ne couvre un écran 5120 : celui du poste de travail')


def test_le_plafond_garde_toujours_une_marge():
    """Un tableau de bord collé aux deux bords force des mouvements de tête."""
    for fenetre, plafond in _paliers(_lire('layout.css')):
        assert plafond < fenetre, (fenetre, plafond)
        #  La barre latérale occupe déjà 240 px : la marge restante doit être
        #  visible, pas symbolique.
        assert fenetre - plafond >= 140, (
            'palier %d px → contenu %d px : il ne reste rien autour'
            % (fenetre, plafond))


def test_une_carte_pleine_largeur_se_coupe_en_deux_sur_un_ecran_large():
    css = _lire('layout.css')
    m = re.search(r'@media\s*\(min-width:2400px\)\s*\{(.*?)\n\}', css, re.S)
    assert m, 'plus de palier de recomposition : les lignes à une carte reviennent'
    bloc = m.group(1)
    for portee in ('.vx-col-12', '.vx-col-11', '.vx-col-10'):
        assert portee in bloc, portee
    assert 'grid-column:span 6' in bloc, (
        'les cartes pleine largeur ne sont plus redécoupées')


def test_une_carte_peut_REFUSER_le_decoupage():
    """Un tableau large ou une chaîne d'options perd son sens coupé en deux."""
    css = _lire('layout.css')
    assert '[data-pleine-largeur]' in css, (
        'aucune échappatoire : une pièce qui a besoin de toute la largeur ne '
        'peut plus le dire')
    m = re.search(r'\[data-pleine-largeur\]\{grid-column:span 12\}', css)
    assert m, css[css.index('[data-pleine-largeur]'):][:120]


def test_les_petites_portees_ne_sont_pas_redecoupees():
    """`col-4` et `col-6` étaient déjà côte à côte : les couper les rendrait
    illisibles, et c'est le contraire du but."""
    css = _lire('layout.css')
    m = re.search(r'@media\s*\(min-width:2400px\)\s*\{(.*?)\n\}', css, re.S)
    bloc = m.group(1)
    for portee in ('.vx-col-4,', '.vx-col-6,', '.vx-col-3,'):
        assert portee not in bloc, ('%s est redécoupée' % portee, bloc[:200])


def test_le_texte_courant_garde_une_mesure_lisible():
    css = _lire('utilities.css')
    assert '--vx-mesure-texte' in css
    m = re.search(r'--vx-mesure-texte:(\d+)ch', css)
    assert m, 'la mesure n’est plus exprimée en caractères'
    assert 60 <= int(m.group(1)) <= 100, (
        'au-delà d’environ 90 caractères, l’œil ne retrouve plus le début de la '
        'ligne suivante : %sch' % m.group(1))
    for classe in ('#vx-content p', '#vx-content .vx-help', '#vx-content .vx-meta'):
        assert classe in css, classe


def test_la_mesure_epargne_ce_dont_la_largeur_EST_l_information():
    """Une cellule de tableau se compare de gauche à droite ; la brider
    laisserait du vide à droite de données qu'on lit en balayant."""
    css = _lire('utilities.css')
    bloc = css[css.index('--vx-mesure-texte'):]
    for exception in ('td .vx-meta', '.vx-table .vx-meta', '.vx-card-footer .vx-meta'):
        assert exception in bloc, exception
    assert 'max-width:none' in bloc


def test_les_largeurs_etroites_ne_sont_pas_touchees():
    """Le gain sur grand écran ne doit rien coûter au téléphone."""
    css = _lire('layout.css')
    for m in re.finditer(r'@media\s*\(min-width:(\d+)px\)', css):
        assert int(m.group(1)) >= 1025, (
            'une règle de recomposition descend à %s px : elle atteint les '
            'tailles où la place manque déjà' % m.group(1))
