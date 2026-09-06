# -*- coding: utf-8 -*-
"""tests/test_refonte_dashboards.py — refonte coordonnée des dashboards (pilote Options).

Mesuré avant le lot, au navigateur (instance QA, 1600 px) : la carte
« Environnement pour l'achat d'options » rendait une jauge seule au centre
d'une carte pleine largeur et des dimensions « Volatilité66 » (libellé et
valeur collés, barre invisible). Cause : plus de vingt classes émises par les
pages Options (`.vx-opt-hero-grid`, `.vx-opt-dim*`, `.vx-hero-grid`,
`.vx-disclosure`, `.vx-stats-row`, `.vx-table-primary`, `.vx-empty`…) n'avaient
plus AUCUNE règle dans les feuilles servies depuis la suppression de
`neon-glass.css` (lot 24) et un nettoyage ultérieur de layout/components.

Ces gardiens sont nés ROUGES sur `main` (ed363d67) et empêchent le retour de
ce défaut : une classe posée dans le HTML ou le JS des pages Options doit
avoir un propriétaire dans la cascade servie.
"""
import os
import re

import pytest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSS_DIR = os.path.join(RACINE, 'vertex', 'static', 'vertex', 'css')
JS_DIR = os.path.join(RACINE, 'vertex', 'static', 'vertex', 'js')


@pytest.fixture(scope='module')
def client():
    import terminal
    return terminal.app.test_client()


def _lire(*parts):
    with open(os.path.join(RACINE, *parts), encoding='utf-8') as fh:
        return fh.read()


def _css_servi():
    from vertex.ui.shell import CSS_ORDER
    return '\n'.join(_lire('vertex', 'static', 'vertex', 'css', nom) for nom in CSS_ORDER)


# ── 1. Aucune classe orpheline sur les pages Options ────────────────────────
CLASSES_OPTIONS = [
    'vx-opt-hero-grid', 'vx-opt-gauge', 'vx-opt-dims', 'vx-opt-dim', 'vx-opt-dim-l',
    'vx-opt-dim-bar', 'vx-opt-dim-v', 'vx-opt-dim-n', 'vx-opt-coverage', 'vx-opt-kpis',
    'vx-hero-grid', 'vx-insight-rail', 'vx-disclosure', 'vx-disclosure__body',
    'vx-stats-row', 'vx-table-primary', 'vx-row-open', 'vx-empty', 'vx-demo-tag',
    'vx-readonly-shield', 'vx-card-foot', 'vx-microbar', 'vx-table-stamp',
    'vx-verdict-evidence', 'vx-metric-meta', 'vx-stackbar--options',
]


@pytest.mark.parametrize('classe', CLASSES_OPTIONS)
def test_chaque_classe_des_pages_options_a_une_regle_servie(classe):
    css = _css_servi()
    assert re.search(r'\.' + re.escape(classe) + r'(?![\w-])', css), (
        'classe émise par les pages Options sans aucune règle CSS servie : .%s' % classe)


def test_les_bases_de_composition_perdues_sont_restaurees():
    """`.vx-hero-grid` n'avait que sa surcharge responsive : sans base, hero et
    rail s'empilaient à 1600 px sur Structure, Volatilité et Positionnement."""
    layout = _lire('vertex', 'static', 'vertex', 'css', 'layout.css')
    assert re.search(r'\.vx-hero-grid\{display:grid', layout)
    assert re.search(r'\.vx-insight-rail\{display:flex', layout)
    components = _lire('vertex', 'static', 'vertex', 'css', 'components.css')
    assert re.search(r'\.vx-disclosure>summary\{[^}]*min-height:44px', components), \
        'le résumé repliable doit offrir une cible tactile de 44 px'
    cockpit = _lire('vertex', 'static', 'vertex', 'css', 'cockpit.css')
    assert re.search(r'\.vx-stats-row\{display:grid', cockpit)


# ── 2. Vue d'ensemble : synthèse → indicateurs clés → tableau ───────────────
def test_vue_d_ensemble_composee_en_decision_puis_indicateurs_puis_table(client):
    html = client.get('/options?view=overview').get_data(as_text=True)
    hero = html.index('id="vx-opt-hero"')
    verdict = html.index('id="vx-opt-verdict"')
    counters = html.index('id="vx-opt-counters"')
    radar = html.index('id="vx-opt-radar-lite"')
    assert hero < verdict < counters < radar, 'ordre de lecture : décision, indicateurs, table'
    assert 'vx-card vx-col-8 vx-opt-hero' in html, 'la carte d’environnement occupe 8 colonnes'
    assert re.search(r'vx-card vx-col-4"[^>]*id="vx-opt-verdict"', html), 'la lecture dominante est un rail de 4 colonnes'
    # les IDs remplis par options-intel.js sont intacts
    for ident in ('vx-opt-hero-body', 'vx-opt-counters-body', 'vx-opt-verdict-body', 'vx-opt-radar-lite-body'):
        assert 'id="%s"' % ident in html, ident
    # plus de « Comprendre ce graphique » sur des cartes qui ne sont pas des graphiques
    assert 'Comprendre ce score' in html and 'Comprendre cette lecture' in html
    assert html.count('Comprendre ce graphique') == 0


def test_squelettes_a_la_hauteur_reservee():
    src = _lire('vertex', 'ui', 'pages', 'options_intel_page.py')
    assert '%%LOADING_200%%' in src and '%%LOADING_280%%' in src, \
        'chaque zone de la vue d’ensemble réserve sa hauteur (CLS)'


# ── 3. Rendus JS : honnêteté des absences, formats, accessibilité ───────────
def test_dimension_non_mesuree_sans_barre_remplie():
    src = _lire('vertex', 'static', 'vertex', 'js', 'pages', 'options-intel.js')
    assert 'data-state="\' + (w == null ? \'missing\' : \'known\')' in src
    assert "(w == null ? '' : '<i style=\"width:' + w + '%\"></i>')" in src, \
        'une dimension inconnue n’émet AUCUNE barre (absence ≠ zéro)'
    assert 'dimensions mesurées</span>' in src, 'la couverture partielle est un badge, pas une note grise'
    assert "width:' + (w == null ? 0 : w) + '%'" not in src, 'l’ancien rendu 0 % pour n/d a disparu'


def test_lecture_et_ton_viennent_du_moteur_pas_de_seuils_client():
    src = _lire('vertex', 'static', 'vertex', 'js', 'pages', 'options-intel.js')
    assert 'reading: it.dominant_reading' in src
    assert "s >= 60 ? 'Environnement porteur" not in src, 'plus de lecture par seuils recodés'
    assert 'MITIGE: { tone' in src and "label: 'Mitigé'" in src, 'le libellé moteur MITIGE est rendu tel quel'


def test_call_put_argent_violet_et_sans_doctrine():
    src = _lire('vertex', 'static', 'vertex', 'js', 'pages', 'options-intel.js')
    assert 'vx-stackbar--options' in src and 'data-side="call"' in src and 'data-side="put"' in src
    assert 'biais de la Stratégie Vertex' not in src, 'aucune consigne de stratégie dans une légende de donnée'
    assert "mCell('CALLS', VXf.nd(c.calls), '', (c.calls >= c.puts ? 'pos'" not in src, \
        'un comptage de CALLS n’est pas une valeur positive'


def test_table_radar_numerique_nommee_et_datee():
    src = _lire('vertex', 'static', 'vertex', 'js', 'pages', 'options-intel.js')
    assert src.count('<th scope="col"') >= 10
    assert 'aria-label="Suivre ' in src, 'chaque bouton Suivre est nommé avec son contrat'
    assert 'contrats affichés sur' in src, 'la population de la table est écrite'
    assert 'PoP (est.)' in src
    assert 'window.__optFollow(this)' in src, 'le comportement réel de « Suivre » est conservé'


def test_micro_barre_partagee_remplace_les_deux_copies_inline():
    core = _lire('vertex', 'static', 'vertex', 'js', 'vx-core.js')
    assert 'microbar: function (o)' in core
    assert '<i aria-hidden="true">' in core, 'la barre est décorative, le chiffre porte le sens'
    for page in ('options-intel.js', 'options-symbol.js'):
        src = _lire('vertex', 'static', 'vertex', 'js', 'pages', page)
        assert 'VX.tile.microbar' in src, page
        assert 'flex:0 0 34px;height:5px' not in src, page + ' porte encore la micro-barre inline'


def test_tuile_metrique_supporte_une_ligne_de_contexte():
    core = _lire('vertex', 'static', 'vertex', 'js', 'vx-core.js')
    assert "o.meta ? '<span class=\"vx-metric-meta\">' + VX.esc(o.meta)" in core, \
        '`meta` est échappé : jamais de HTML injecté par un appelant'


def test_jauge_sans_halo_permanent():
    core = _lire('vertex', 'static', 'vertex', 'js', 'charts', 'chart-core.js')
    debut = core.index('C.gauge = function')
    fin = core.index('function tetePrimitive')
    assert 'drop-shadow' not in core[debut:fin], 'aucun glow permanent sur la jauge partagée'


def test_formats_fr_dans_gex_et_scanner():
    gex = _lire('vertex', 'static', 'vertex', 'js', 'pages', 'options-gex.js')
    assert "(a / 1e6).toFixed(2)" not in gex, 'le montant GEX suit le format fr-FR'
    scanner = _lire('vertex', 'static', 'vertex', 'js', 'pages', 'options-scanner.js')
    assert 'VX.fmt.num(v, d == null ? 2 : d)' in scanner
    assert "'n/a'" not in scanner, 'plus de « n/a » anglais'
    assert "setAttribute('aria-pressed'" in scanner, 'l’univers actif est exposé au clavier'


def test_radar_gex_activable_au_clavier_et_lisible_en_cartes():
    gex = _lire('vertex', 'static', 'vertex', 'js', 'pages', 'options-gex.js')
    assert 'data-clickable tabindex="0" aria-label="Analyser le positionnement de' in gex
    assert "ev.key === 'Enter' || ev.key === ' '" in gex
    assert 'data-label="Net GEX"' in gex, 'les cartes mobiles gardent leur libellé'
    assert 'out.parentNode.insertBefore(priv, out)' in gex, \
        'la case vie privée s’insère sous le parent de `out` (NotFoundError corrigée)'


def test_dossier_titre_sans_anneaux_decoratifs_et_verdict_moteur():
    src = _lire('vertex', 'static', 'vertex', 'js', 'pages', 'options-symbol.js')
    assert 'VXCharts.scoreGaugeSVG' not in src, 'trois anneaux lumineux pour un contrat : retirés'
    assert "get('/api/options/volatility/'" in src, \
        '« Les options sont-elles chères ? » lit l’interprétation volatilité du moteur'
    assert 'function emptyChart' in src and "innerHTML = '';" not in src.split('function paintStrats')[0], \
        'aucun emplacement de graphique vidé en silence'
    assert 'Survole une ligne pour lire' not in src, 'le « pourquoi » ne dépend plus du survol'


def test_dossier_titre_page_sans_faux_bouton(client):
    html = client.get('/options/dossier/AAPL').get_data(as_text=True)
    assert 'aria-current="true" title="Mode actuel' not in html, 'un span habillé en bouton n’est pas un bouton'
    assert 'data-state="option" title="Mode actuel : dossier options">Mode : options' in html


def test_francais_dans_structure():
    src = _lire('vertex', 'static', 'vertex', 'js', 'pages', 'options-structure.js')
    assert 'Insufficient' not in src and "'DELAYED'" not in src


# ── 4. Versions de cache : bundle immuable et service worker ────────────────
def test_la_coque_et_le_service_worker_suivent_le_lot(client):
    from vertex.ui.shell import SHELL_VERSION
    assert int(SHELL_VERSION.rsplit('-', 1)[1]) >= 3, SHELL_VERSION   # numérique : 'vx-shell-10' < 'vx-shell-3' en texte
    html = client.get('/options').get_data(as_text=True)
    assert '/asset/css/bundle.css?v=' + SHELL_VERSION in html
    sw = client.get('/sw.js').get_data(as_text=True)
    m = re.search(r"td-shell-v(\d+)", sw)
    assert m and int(m.group(1)) >= 290
