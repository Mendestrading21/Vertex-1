"""Tests canoniques Vertex Experience OS (§39).

Chaque nom de test exigé par le cahier des charges V3 existe ici (ou dans
les suites historiques référencées en commentaire). Vérifications statiques
sur le HTML rendu + les assets ; les vérifications purement navigateur
(console, overflow réel) sont doublées par les runs Chromium documentés
dans le rapport de refonte UI V3 (archive, retiree du depot).
"""
#  `/performance` RETIRE des listes d'espaces : Performance est repliee
#  dans le Journal (301). La constitution enumere Journal, pas
#  Performance — c'est la liste de ce banc qui s'en ecartait.
import os
import re

import pytest

import terminal

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VXJS = os.path.join(ROOT, 'vertex', 'static', 'vertex', 'js')
VXCSS = os.path.join(ROOT, 'vertex', 'static', 'vertex', 'css')

PAGES = ['/', '/opportunities', '/portfolio', '/analysis',
         '/analysis/NVDA', '/intelligence', '/system']


@pytest.fixture(scope='module')
def client():
    terminal.app.config['TESTING'] = True
    return terminal.app.test_client()


@pytest.fixture(scope='module')
def rendered(client):
    return {p: client.get(p).get_data(as_text=True) for p in PAGES}


def _read(*parts):
    return open(os.path.join(*parts), encoding='utf-8').read()


def _all_js():
    out = []
    for base, _, files in os.walk(VXJS):
        for f in files:
            if f.endswith('.js'):
                out.append(_read(base, f))
    return '\n'.join(out)


# ── Routes & navigation ──────────────────────────────────────────────────

def test_every_primary_route_returns_200(client):
    for p in PAGES:
        r = client.get(p)
        assert r.status_code == 200, f'{p} → {r.status_code}'


def test_no_dead_links(client, rendered):
    """Tout href interne rendu doit répondre 200 ou rediriger (301/302)."""
    seen = set()
    for page, html in rendered.items():
        for m in re.finditer(r'href="(/[a-z0-9\-/]*?)(\?[^"]*)?"', html):
            path = m.group(1)
            if path in seen or path.startswith('/static'):
                continue
            seen.add(path)
            r = client.get(path)
            assert r.status_code in (200, 301, 302), f'{page} → lien mort {path} ({r.status_code})'


def test_no_dead_buttons(rendered):
    """Chaque bouton rendu est câblé — délégation data-*, id référencé ou inline.
    (Généralisation : test_every_button_has_handler couvre le même invariant.)"""
    js_all = _all_js()
    for page, html in rendered.items():
        page_js = '\n'.join(re.findall(r'<script[^>]*>(.*?)</script>', html, re.S))
        for m in re.finditer(r'<button([^>]*)>', html):
            attrs = m.group(1)
            if 'onclick=' in attrs or 'data-' in attrs or 'type="submit"' in attrs:
                continue
            idm = re.search(r'id="([^"]+)"', attrs)
            assert idm, f'{page} : bouton sans identifiant ni handler : {attrs[:90]}'
            bid = idm.group(1)
            assert bid in page_js or bid in js_all, f'{page} : bouton mort #{bid}'


# ── Valeurs invalides ────────────────────────────────────────────────────

def _no_literal(rendered, literal):
    for page, html in rendered.items():
        text = re.sub(r'<script.*?</script>', '', html, flags=re.S)
        assert literal not in text, f'{page} affiche {literal!r}'


def test_no_object_object_visible(rendered):
    _no_literal(rendered, '[object Object]')


def test_no_undefined_visible(rendered):
    _no_literal(rendered, '>undefined<')


def test_no_nan_visible(rendered):
    _no_literal(rendered, '>NaN<')


def test_no_infinity_visible(rendered):
    _no_literal(rendered, '>Infinity<')


# ── Contrat graphique ────────────────────────────────────────────────────

def test_every_chart_has_title():
    core = _read(VXJS, 'charts', 'chart-core.js')
    assert 'vx-chart-title' in core and 'opts.title' in core


def test_every_chart_has_source():
    core = _read(VXJS, 'charts', 'chart-core.js')
    assert 'opts.source' in core and 'updateIndicator' in core
    # chaque appel *Card( dans les pages fournit source:
    pages_dir = os.path.join(ROOT, 'vertex', 'ui', 'pages')
    for f in os.listdir(pages_dir):
        if not f.endswith('.py'):
            continue
        src = _read(pages_dir, f)
        for m in re.finditer(r'VXCharts\.\w+Card\((.{0,600}?)\}\)\;', src, re.S):
            call = m.group(1)
            assert 'source' in call, f'{f} : carte graphique sans source'


def test_every_chart_has_timestamp():
    core = _read(VXJS, 'charts', 'chart-core.js')
    assert 'opts.timestamp' in core


def test_chart_theme_is_single():
    theme = _read(VXJS, 'charts', 'chart-theme-black-glass.js')
    assert 'VXChartTheme' in theme
    core = _read(VXJS, 'charts', 'chart-core.js')
    assert 'VXChartTheme' in core


# ── États de widgets ─────────────────────────────────────────────────────

def test_every_widget_has_loading_state(rendered):
    for page, html in rendered.items():
        assert 'vx-skeleton' in html, f'{page} : aucun skeleton de chargement'


def test_every_widget_has_empty_state():
    js = _read(VXJS, 'vx-core.js')
    assert 'empty' in js and 'states' in js
    pages_dir = os.path.join(ROOT, 'vertex', 'ui', 'pages')
    for f in ('briefing.py', 'opportunities_page.py',
              'portfolio_page.py', 'performance_page.py'):
        assert 'states.empty' in _read(pages_dir, f), f'{f} sans état vide'


def test_every_widget_has_error_state():
    pages_dir = os.path.join(ROOT, 'vertex', 'ui', 'pages')
    for f in ('briefing.py', 'portfolio_page.py', 'intelligence_page.py'):
        assert 'states.error' in _read(pages_dir, f), f'{f} sans état erreur'


def test_demo_mode_is_clear():
    css = _read(VXCSS, 'states.css')
    assert 'vx-demo-banner' in css and 'vx-badge-demo' in css
    assert 'vx-demo-banner' in _read(ROOT, 'vertex', 'ui', 'pages', 'briefing.py')


def test_live_state_is_clear():
    css = _read(VXCSS, 'states.css')
    for state in ('live', 'delayed', 'frozen', 'fallback', 'offline'):
        assert f'data-live="{state}"' in css, f'état {state} absent'


# ── Shell & interactions ─────────────────────────────────────────────────

def test_sidebar_collapses(rendered):
    js = _read(VXJS, 'vx-shell.js')
    assert 'vxSidebarState' in js and 'vx-collapse-btn' in rendered['/']


def test_mobile_navigation_exists(rendered):
    assert 'vx-mobile-bar' in rendered['/']
    assert 'vx-mobile-nav-btn' in rendered['/']


def test_drawer_closes_with_escape():
    js = _read(VXJS, 'vx-shell.js')
    assert 'Escape' in js and 'closeAll' in js


def test_modal_traps_focus():
    js = _read(VXJS, 'vx-shell.js')
    assert 'trapFocus' in js


def test_command_palette_keyboard():
    js = _read(VXJS, 'vx-shell.js')
    assert 'ArrowDown' in js and 'ArrowUp' in js and 'Enter' in js


# ── Responsive / accessibilité / perfs ───────────────────────────────────

def test_no_horizontal_overflow():
    """Statique : tout tableau vit dans un conteneur à défilement propre et
    la grille passe en colonnes aux points de rupture (run Chromium en plus)."""
    tables = _read(VXCSS, 'tables.css')
    assert 'overflow-x:auto' in tables
    resp = _read(VXCSS, 'responsive.css')
    assert '@media' in resp and '640px' in resp or '768px' in resp


def test_reduced_motion():
    base = _read(VXCSS, 'base.css')
    assert 'prefers-reduced-motion' in base


def test_no_console_errors():
    """La télémétrie 0-erreur est branchée : toute erreur navigateur remonte
    à /api/client-log (les runs Chromium vérifient le zéro effectif)."""
    core = _read(VXJS, 'vx-core.js')
    assert "'/api/client-log'" in core or '"/api/client-log"' in core
    assert 'unhandledrejection' in core


def test_service_worker_version_bumped(client):
    body = client.get('/sw.js').get_data(as_text=True)
    assert 'td-shell-v293' in body
    assert 'td-shell-v49' not in body


# ── Sécurité produit ─────────────────────────────────────────────────────

def test_no_order_execution_path():
    """Aucun APPEL ni DÉFINITION d'exécution d'ordre — les listes d'interdits
    (deny-lists des gardes) citent légitimement les noms sans les appeler."""
    words = ('place_order', 'submit_order', 'transmit_order', 'modify_order',
             'cancel_order', 'exercise_option', 'transfer_cash',
             'withdraw_cash', 'rebalance_automatically', 'auto_execute')
    pat = re.compile(r'(?:\.|\bdef\s+|\bfunction\s+)(?:' + '|'.join(words) + r')\s*\(')
    hits = []
    for base, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in ('.git', '__pycache__', 'node_modules')]
        for f in files:
            if not f.endswith(('.py', '.js')) or f.startswith('test_'):
                continue
            src = _read(base, f)
            for m in pat.finditer(src):
                hits.append(os.path.join(base, f) + ' : ' + m.group(0))
    assert not hits, 'Chemin d\'ordre détecté :\n' + '\n'.join(hits)


def test_v3_tokens_are_canonical():
    """Palette Vertex OBSIDIAN COPPER — canonique et centralisée.
    Marque = cuivre #D28A54 (accent d'interface, jamais « hausse ») · émeraude
    = positif · corail = risque · jaune = attente · violet = options · cyan =
    comparaison. Le token de marque reste `--vx-ember-*` pour compatibilité."""
    tokens = _read(VXCSS, 'tokens.css')
    for var in ('--vx-canvas:#060707', '--vx-ember-500:#D28A54',
                '--vx-brand:var(--vx-ember-500)', '--vx-positive:#2BBE90',
                '--vx-negative:#E9555F', '--vx-warning:#D9BE3C',
                '--vx-option:#9B7BFF', '--vx-neutral-chart:#BABABA'):
        assert var in tokens, f'token manquant : {var}'
    # Garde-fou anti-régression : le vert Signal ne doit plus être la marque.
    assert '--vx-brand:var(--vx-signal-500)' not in tokens, \
        'la marque ne doit plus pointer sur le vert Signal'
    assert '#84aa31' not in tokens, 'aucun littéral vert Signal résiduel dans les tokens'
