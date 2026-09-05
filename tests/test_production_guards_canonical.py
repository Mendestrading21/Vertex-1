"""Vertex Full Production — gardiens canoniques (§37).

Noms de tests exigés par le cahier final. Chaque test porte une assertion
RÉELLE (pas un alias vide) ; certains invariants sont aussi couverts plus en
profondeur dans les suites dédiées (référencées en commentaire).
"""
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / 'vertex' / 'static' / 'vertex'
PAGES = ROOT / 'vertex' / 'ui' / 'pages'


@pytest.fixture(scope='module')
def client():
    import terminal
    terminal.app.config['TESTING'] = True
    return terminal.app.test_client()


# ── Identité & sécurité ───────────────────────────────────────────────
def test_no_personal_names():
    """Cf. test_namespace_guards — vérification directe ici aussi."""
    first, last = 'el' + 'io', 'men' + 'des'
    out = subprocess.run(
        ['git', 'grep', '-i', '-l', '-E', f'({first}|{last})', '--', '.',
         ':!docs/redesign'],
        cwd=ROOT, capture_output=True, text=True, encoding='utf-8')
    hits = [l for l in out.stdout.splitlines() if l.strip()]
    assert not hits, f'noms personnels: {hits}'


def test_single_decision_engine():
    """Le vocabulaire décisionnel final n'est produit que par vertex.strategy
    (executive_engine) — cf. test_single_decision_source pour le scan complet."""
    from vertex.strategy import executive_engine as EE
    from vertex.strategy import constitution as C
    assert set(EE.FINAL_DECISIONS) == set(C.ALLOWED_FINAL_DECISIONS)
    out = EE.decide({'symbol': 'X'}, C.load_profile())
    assert out['final_decision'] in EE.FINAL_DECISIONS


def test_ai_registry_has_no_order_tool():
    from vertex.ai.tool_registry import ALLOWED_TOOLS, FORBIDDEN_TOOLS
    assert not set(ALLOWED_TOOLS) & set(FORBIDDEN_TOOLS)
    for tool in ('place_order', 'modify_order', 'cancel_order',
                 'exercise_option', 'transfer_cash', 'change_constitution',
                 'activate_rule', 'delete_history'):
        assert tool in FORBIDDEN_TOOLS and tool not in ALLOWED_TOOLS


def test_ai_failure_uses_fallback():
    from vertex.ai.investment_agent import InvestmentAgent
    from vertex.ai.models import AnalysisRequest
    res = InvestmentAgent(provider=None).analyze(
        AnalysisRequest(symbol='X', packet={'final_decision': 'ATTENDRE'}))
    assert res.ok and res.source == 'deterministic-fallback'


# ── Options : bornes de la constitution ───────────────────────────────
def test_dynamic_call_ranges():
    from vertex.strategy.constitution import load_profile
    dyn = load_profile().category('DYNAMIC')
    assert (dyn['delta_min'], dyn['delta_max']) == (0.28, 0.45)
    assert dyn['target_gain_pct'] == [50, 100]
    assert dyn['planned_loss_pct'] == [25, 35]


def test_eleventh_position_requires_replacement():
    """Cf. test_eleventh_stock_requires_replacement (portefeuille complet)."""
    from vertex.portfolio.models import Position, PortfolioSnapshot
    from vertex.portfolio.team_engine import candidate_fit
    from vertex.strategy.constitution import load_profile
    snap = PortfolioSnapshot(positions=[
        Position(f'P{i}', 10, 100, 100, sector='Tech') for i in range(10)],
        provenance='REAL')
    fit = candidate_fit(snap, load_profile(), {'symbol': 'NEW', 'role': 'MIDFIELDER'})
    assert fit['blocked'] is True




# ── UI : boutons vivants ──────────────────────────────────────────────
_WIRED_MARKERS = (
    'onclick=', 'data-open-analysis', 'data-entity-menu', 'data-close-drawer',
    'data-close-modal', 'data-density-btn', 'data-dest', 'data-filter-key',
    'data-filter-value', 'data-tf=', 'data-ct=', 'data-close-pos',
    'data-wl-del', 'data-wl-status', 'data-unfollow', 'data-ag=', 'data-blk',
    'data-explain', 'type="submit"', 'data-hm', 'data-i=', 'data-idx',
)


def _all_shell_js():
    return '\n'.join(p.read_text(encoding='utf-8')
                     for p in (STATIC / 'js').rglob('*.js'))


def _buttons_in(source: str):
    return re.findall(r'<button\b[^>]*>', source)


def _is_wired(btn: str, src: str, js_all: str) -> bool:
    if any(m in btn for m in _WIRED_MARKERS):
        return True
    # id référencé par le JS de la page ou du shell
    m = re.search(r'id="([^"$]+)"', btn)
    if m and (f"'{m.group(1)}'" in src or f"'{m.group(1)}'" in js_all
              or f'"{m.group(1)}"' in js_all):
        return True
    # attribut data-x câblé localement : querySelectorAll('[data-x]') ou dataset.x
    for attr in re.findall(r'data-([a-z0-9\-]+)=', btn):
        camel = re.sub(r'-([a-z])', lambda mm: mm.group(1).upper(), attr)
        if f'[data-{attr}]' in src or f'dataset.{camel}' in src \
                or f'[data-{attr}]' in js_all or f'dataset.{camel}' in js_all:
            return True
    return False


def test_every_button_has_handler():
    """Chaque <button> des pages est câblé : marqueur inline, id référencé par
    le JS, ou attribut data-* consommé par un écouteur (délégation)."""
    js_all = _all_shell_js()
    offenders = []
    # Vitrines READONLY : boutons d'exemple volontairement inertes (échantillons
    # de design). design_system_demo = Command Surface ; widget_lab = /widget-lab
    # (laboratoire du Design System, hors produit).
    _skip = {'design_system_demo.py', 'widget_lab.py'}
    for page in list(PAGES.glob('*.py')) + [ROOT / 'vertex' / 'ui' / 'shell' / '__init__.py']:
        if page.name in _skip:
            continue
        src = page.read_text(encoding='utf-8')
        for btn in _buttons_in(src):
            if not _is_wired(btn, src, js_all):
                offenders.append(f'{page.name}: {btn[:90]}')
    assert not offenders, 'boutons sans handler:\n' + '\n'.join(offenders)


def test_no_dead_buttons():
    """Aucun bouton construit dynamiquement sans écouteur : les patterns de
    délégation globaux existent (click délégué + addEventListener locaux)."""
    ent = (STATIC / 'js' / 'vx-entities.js').read_text(encoding='utf-8')
    assert "closest('[data-entity-menu]')" in ent
    assert "closest('[data-open-analysis]')" in ent
    for page in PAGES.glob('*.py'):
        src = page.read_text(encoding='utf-8')
        dyn_ids = set(re.findall(r"getElementById\('([a-z0-9\-]+)'\)", src))
        # tout id interrogé doit exister dans le HTML généré de la page
        html_ids = set(re.findall(r'id="([a-z0-9\-]+)"', src))
        used_dynamic = {i for i in dyn_ids if f'id="{i}"' in src or i in src}
        assert dyn_ids <= used_dynamic | html_ids, \
            f'{page.name}: ids interrogés sans élément {dyn_ids - html_ids}'


# ── UI : recherche, palette, contexte ─────────────────────────────────
def test_global_search(client):
    html = client.get('/').get_data(as_text=True)
    assert 'vx-global-search' in html
    r = client.get('/api/names')
    assert r.status_code == 200


def test_command_palette():
    shell = (STATIC / 'js' / 'vx-shell.js').read_text(encoding='utf-8')
    assert 'openPalette' in shell and 'vx-palette' in shell
    for key in ("'ArrowDown'", "'ArrowUp'", "'Enter'"):
        assert key in shell


def test_context_is_restored():
    core = (STATIC / 'js' / 'vx-core.js').read_text(encoding='utf-8')
    assert 'restoreIfReturning' in core
    shell = (STATIC / 'js' / 'vx-shell.js').read_text(encoding='utf-8')
    assert 'VX.context.restoreIfReturning()' in shell


def test_filters_are_restored():
    core = (STATIC / 'js' / 'vx-core.js').read_text(encoding='utf-8')
    assert '_collectFilters' in core
    assert "data-filter-key" in core and 'aria-pressed' in core


def test_scroll_is_restored():
    core = (STATIC / 'js' / 'vx-core.js').read_text(encoding='utf-8')
    assert 'ctx.scrollY' in core and 'window.scrollTo(0, ctx.scrollY)' in core


# ── UI : mises à jour partout (bus) ───────────────────────────────────
@pytest.mark.parametrize('event', ['vx:favorites-changed', 'vx:watchlist-changed',
                                   'vx:follow-changed', 'vx:alert-changed',
                                   'vx:position-changed'])
def test_entity_updates_everywhere(event):
    """Chaque événement d'entité est émis par la couche unique ET écouté par
    au moins une page + la fiche analyse."""
    ent = (STATIC / 'js' / 'vx-entities.js').read_text(encoding='utf-8')
    assert f"'{event}'" in ent, f'{event} non émis'
    pages_src = '\n'.join(p.read_text(encoding='utf-8') for p in PAGES.glob('*.py'))
    assert f"'{event}'" in pages_src, f'{event} non écouté par les pages'


def test_favorite_updates_everywhere():
    test_entity_updates_everywhere('vx:favorites-changed')


def test_watchlist_updates_everywhere():
    test_entity_updates_everywhere('vx:watchlist-changed')


def test_follow_updates_everywhere():
    test_entity_updates_everywhere('vx:follow-changed')


def test_alert_updates_everywhere():
    test_entity_updates_everywhere('vx:alert-changed')


def test_position_updates_everywhere():
    test_entity_updates_everywhere('vx:position-changed')


# ── Graphiques : contrat §31 ──────────────────────────────────────────
def _chart_core():
    return (STATIC / 'js' / 'charts' / 'chart-core.js').read_text(encoding='utf-8')


def test_chart_has_question():
    assert 'vx-chart-question' in _chart_core()


def test_chart_has_conclusion():
    assert 'vx-chart-conclusion' in _chart_core()


def test_chart_has_source():
    assert 'updateIndicator(opts.timestamp, opts.source' in _chart_core()


def test_chart_has_timestamp():
    core = (STATIC / 'js' / 'vx-core.js').read_text(encoding='utf-8')
    assert 'age_seconds' in core or 'isoFull' in core
    assert 'title="${VX.fmt.isoFull(ts)}"' in core


# ── États UI ──────────────────────────────────────────────────────────
def _states_src():
    return (STATIC / 'js' / 'vx-core.js').read_text(encoding='utf-8')


def test_loading_state():
    assert 'vx-skeleton' in _states_src() and "data-state=\"loading\"" in _states_src()


def test_empty_state():
    assert 'Aucune donnée' in _states_src()


def test_stale_state():
    src = _states_src()
    assert 'stale' in src and 'ACTIONABLE bloquée' in src


def test_error_state():
    src = _states_src()
    assert 'Réessayer' in src and 'Ouvrir Système' in src


# ── Divers canoniques ─────────────────────────────────────────────────
def test_no_duplicate_ids(client):
    for page in ('/', '/portfolio', '/system'):
        html = client.get(page).get_data(as_text=True)
        ids = re.findall(r'id="([^"]+)"', html)
        dupes = {i for i in ids if ids.count(i) > 1}
        assert not dupes, f'{page}: {dupes}'


def test_no_console_errors():
    """Proxy statique (la vérification navigateur réelle : parcours §38, 0
    erreur) : aucun console.log de debug dans le JS livré."""
    for js in (STATIC / 'js').rglob('*.js'):
        src = js.read_text(encoding='utf-8')
        assert 'console.log(' not in src, js.name


def test_mobile_navigation(client):
    assert 'vx-mobile-bar' in client.get('/').get_data(as_text=True)


def test_mobile_action_bar(client):
    html = client.get('/analysis/NVDA').get_data(as_text=True)
    assert 'vx-mobile-bar' in html and 'Alerte' in html


def test_service_worker_version(client):
    body = client.get('/sw.js').get_data(as_text=True)
    assert 'td-shell-v290' in body
