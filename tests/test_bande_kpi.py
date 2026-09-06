"""LOT 626 — UN SPAN DIMENSIONNÉ POUR UNE GRILLE, PLACÉ DANS UNE AUTRE.

Le lot 625 a trouvé le défaut : les tuiles KPI du Portefeuille portent
`style="grid-column:span 3"`, dimensionné pour la grille historique à **12**
colonnes. La bande `vx-kpi-strip` de la refonte visuelle n'en déclare que **4** :
`span 3` sur 4 ne laisse tenir qu'**une** tuile par rangée.

Mesuré à 1440 px : **4 tuiles de 860 px empilées** au lieu de 276 côte à côte.
**3005 tests étaient verts sur cette page empilée** — aucun ne regardait où les
tuiles atterrissent.

## Pourquoi la correction porte sur la BANDE et non sur les tuiles

Le même helper alimente aussi des conteneurs `.vx-grid` à 12 colonnes, où
`span 3` est **juste** (4 tuiles par rangée). Retirer le style en ligne aurait
réparé un endroit et cassé l'autre. La bande, elle, sait combien de colonnes
elle a : c'est à elle de neutraliser un span qui ne la concerne pas.

## Ce que le balayage du 626 a établi

Instrument : pour chaque conteneur `display:grid` des **8 pages × 2 largeurs**,
nombre réel de colonnes, span de chaque enfant, et rangées reconstituées par
**chevauchement vertical** (grouper par `top` est faux dès que les éléments sont
centrés). Signalé uniquement le cas `1 < span < colonnes` — un `span 12` sur 12
est le repli mobile **voulu**, un `span 1` est le défaut normal.

| | résultat |
| --- | --- |
| grilles à span hétérogène | **2** |
| dont légitimes *(span 7+5 = 12 ; 3 × 4 = 12, rangées pleines)* | **2** |
| **défauts réels restants** | **0** |
| débordement horizontal, 8 pages × 2 largeurs | **0** |

**La bande KPI était le seul cas du produit.**
"""

import io
import os
import re

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_COMPONENTS = os.path.join(_ROOT, 'vertex', 'static', 'vertex', 'css', 'components.css')
_PORTFOLIO = os.path.join(_ROOT, 'vertex', 'ui', 'pages', 'portfolio_page.py')

# Colonnes déclarées par la bande, mesurées au lot 625.
_COLONNES_BANDE = 4


def _lire(p):
    return io.open(p, encoding='utf-8').read()


def test_la_bande_kpi_neutralise_les_spans_qui_ne_la_concernent_pas():
    """LE CORRECTIF DU 625, ET LA RAISON DE SON `!important`.

    Un style en ligne ne peut être battu que par `!important` : ce n'est pas une
    facilité, c'est la seule mécanique disponible. Le retirer réempile les
    quatre tuiles sans qu'aucun autre test ne bouge.
    """
    src = _lire(_COMPONENTS)
    m = re.search(r'\.vx-kpi-strip\s*>\s*\*\s*\{([^}]*)\}', src)
    assert m, (
        'la règle qui neutralise les spans hérités dans `.vx-kpi-strip` a '
        'disparu. Sans elle, les tuiles du Portefeuille reprennent leur '
        '`grid-column:span 3` en ligne dans une grille à %d colonnes, et se '
        'réempilent (4 × 860 px au lieu de 4 × 276 px à 1440 px).'
        % _COLONNES_BANDE)
    decl = m.group(1).replace(' ', '')
    assert 'grid-column:span1' in decl, (
        'la règle existe mais ne force plus `span 1` : %s' % m.group(1).strip())
    assert '!important' in decl, (
        'le `!important` a été retiré. Les tuiles portent un style EN LIGNE — '
        'rien d\'autre ne le bat. La règle redevient décorative.')


def test_la_bande_declare_toujours_moins_de_colonnes_que_le_span_herite():
    """La règle ci-dessus n'a de sens que tant que le conflit existe.

    Si la bande passait à 12 colonnes, `span 3` redeviendrait juste et le
    `!important` masquerait alors une intention légitime. Ce test dit quand la
    neutralisation cesse d'être nécessaire.
    """
    src = _lire(_COMPONENTS)
    m = re.search(r'\.vx-kpi-strip\s*\{[^}]*grid-template-columns:\s*repeat\((\d+)', src)
    assert m, '`.vx-kpi-strip` ne déclare plus un nombre fixe de colonnes'
    n = int(m.group(1))
    assert n == _COLONNES_BANDE, (
        'la bande déclare %d colonnes, mesurée à %d au lot 625. Re-mesurer au '
        'navigateur : la neutralisation du span est peut-être devenue inutile, '
        'ou insuffisante.' % (n, _COLONNES_BANDE))


def test_les_tuiles_portent_toujours_le_span_herite():
    """Audit complet du 2026-09-06 : le style EN LIGNE `grid-column:span 3`
    ignorait les règles mobiles (quatre tuiles de 81 px à 390 px, débordement
    mesuré). Il est remplacé par la classe `vx-col-3` — même span dans la
    grille à douze colonnes, mais les règles responsive s'appliquent. La
    neutralisation `.vx-kpi-strip > *` garde son objet : la classe spannerait
    encore 3 dans la bande à 4 colonnes."""
    src = _lire(_PORTFOLIO)
    assert 'grid-column:span 3' not in src, (
        "le style en ligne est revenu : les règles mobiles ne s'appliqueraient plus")
    n = len(re.findall(r'vx-kpi vx-col-3"|vx-card--compact vx-col-3"', src))
    assert n >= 1, (
        "plus aucune tuile ne porte `vx-col-3` : la règle `.vx-kpi-strip > *` "
        "du lot 625 n'a plus d'objet. La retirer, et retirer ce test avec elle.")


def test_le_meme_helper_sert_encore_une_grille_a_douze_colonnes():
    """POURQUOI ON N'A PAS SIMPLEMENT RETIRÉ LE STYLE EN LIGNE.

    Le helper alimente aussi un conteneur `.vx-grid` (12 colonnes) où `span 3`
    donne les 4 tuiles par rangée attendues. Si ce second usage disparaissait,
    retirer le style en ligne redeviendrait la correction la plus simple — et ce
    test le signalerait.
    """
    src = _lire(_PORTFOLIO)
    grilles_simples = re.findall(r'<div class="vx-grid(?! vx-kpi-strip)[^"]*"', src)
    assert grilles_simples, (
        'plus aucun conteneur `.vx-grid` sans `vx-kpi-strip` dans '
        'portfolio_page.py : le span en ligne n\'a plus d\'usage légitime, on '
        'peut le supprimer à la source plutôt que de le neutraliser.')
