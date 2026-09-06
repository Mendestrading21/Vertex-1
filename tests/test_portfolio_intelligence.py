"""tests/test_portfolio_intelligence.py — SKYLER LOT 7 : Portfolio Intelligence.

PortfolioContext canonique (provenance, poids, HHI, bornes 8-15), sizing
S+/S/A/B = plafonds ANALYTIQUES de la V2 (jamais un ordre), impact marginal et
concentration, garde-fou « jamais renforcer un perdant » branché dans les hard
gates Skyler, quota options, budget de risque honnêtement absent sans stops.
"""
import pytest

from vertex.engines import portfolio_context as PC


def _positions():
    def stk(sym, qty, cost):
        return {'symbol': sym, 'asset_type': 'STOCK', 'quantity': qty,
                'cost_basis': cost, 'average_cost': cost / qty, 'source': 'MANUAL',
                'is_real': True, 'status': 'OPEN'}
    return [stk('AAA', 10, 1000.0),     # avg 100
            stk('BBB', 5, 2000.0),      # avg 400
            stk('CCC', 20, 1000.0)]     # avg 50


def _quotes():
    return {'AAA': 90.0, 'BBB': 500.0, 'CCC': 50.0}
    # valeurs: AAA 900 (perdant -10%), BBB 2500 (gagnant +25%), CCC 1000 (flat)


# ─── Contexte canonique ─────────────────────────────────────────────────────────

def test_context_weights_and_hhi_hand_computed():
    ctx = PC.build(_positions(), quotes=_quotes())
    assert ctx['available'] is True
    assert ctx['n_positions'] == 3
    assert ctx['total_value'] == pytest.approx(4400.0)
    w = ctx['weights']
    assert w['AAA'] == pytest.approx(900 / 4400 * 100, abs=0.01)
    assert w['BBB'] == pytest.approx(2500 / 4400 * 100, abs=0.01)
    # HHI sur fractions : (900/4400)² + (2500/4400)² + (1000/4400)²
    hhi = (900 / 4400) ** 2 + (2500 / 4400) ** 2 + (1000 / 4400) ** 2
    assert ctx['hhi'] == pytest.approx(hhi, abs=1e-4)
    assert ctx['top_weight_pct'] == pytest.approx(2500 / 4400 * 100, abs=0.01)


def test_les_deux_hhi_du_produit_portent_chacun_sa_base():
    """CONSTAT 24 — deux « HHI » cohabitent et ne mesurent pas la même chose.

    MESURE : sur KO (88,07 $) + 25 000 $ de cash, `risk_engine` rend 1.0
    (compartiment actions renormalisé) pendant que `portfolio_context` rend
    1.0 sur une base différente (toutes les lignes valorisées, cash absent du
    dénominateur parce qu'il n'est pas une ligne). Les deux sont affichés sous
    le même libellé avec des seuils différents (0,33/0,66 contre 0,18/0,25) :
    seule la base publiée permet de savoir lequel répond à quoi. `risk_engine`
    la publiait déjà ; `portfolio_context` ne la publiait pas.
    """
    from vertex.portfolio.risk_engine import portfolio_risk
    from vertex.portfolio.models import Position, PortfolioSnapshot

    class _P:
        max_stock_weight_pct = 15.0
        portfolio_max_drawdown_pct = -25.0
        stock_max_drawdown_pct = -20.0
        max_simultaneous_options = 3

    ctx = PC.build(_positions(), quotes=_quotes())
    assert 'toutes les lignes valorisées' in ctx['hhi_basis']
    assert 'cash' in ctx['hhi_basis']
    risque = portfolio_risk(PortfolioSnapshot(
        positions=[Position('KO', 1, avg_cost=88.07, last_price=88.07)],
        cash=25000.0, provenance='REAL'), _P())
    #  Deux bases DIFFÉRENTES, donc deux phrases différentes : c'est le point.
    assert risque['hhi_basis'] != ctx['hhi_basis']


def test_bounds_from_profile_8_15():
    ctx = PC.build(_positions(), quotes=_quotes())
    assert ctx['bounds']['min'] == 8 and ctx['bounds']['max'] == 15
    assert ctx['in_bounds'] is False           # 3 < 8 : sous la cible, dit honnêtement
    assert ctx['free_slots'] == 12


def test_empty_portfolio_honest():
    ctx = PC.build([], quotes={})
    assert ctx['available'] is False and 'reason' in ctx


def test_simulated_positions_excluded():
    pos = _positions() + [{'symbol': 'SIM', 'asset_type': 'STOCK', 'quantity': 1,
                           'cost_basis': 100.0, 'average_cost': 100.0,
                           'source': 'SIMULATED', 'is_real': False, 'status': 'OPEN'}]
    ctx = PC.build(pos, quotes=_quotes())
    assert 'SIM' not in ctx['weights']


def test_valuation_fallback_labeled():
    """Sans cote : valorisation au coût, étiquetée — jamais un prix inventé."""
    ctx = PC.build(_positions(), quotes=None)
    assert ctx['total_value'] == pytest.approx(4000.0)
    assert ctx['valuation_note'] and 'coût' in ctx['valuation_note']


def test_sector_coverage_never_assigns_unknown_symbol_by_default():
    positions = [
        {'symbol': 'AAPL', 'asset_type': 'STOCK', 'quantity': 10, 'cost_basis': 1000.0,
         'source': 'MANUAL'},
        {'symbol': 'UNKNOWNX', 'asset_type': 'STOCK', 'quantity': 10, 'cost_basis': 1000.0,
         'source': 'MANUAL'},
    ]
    ctx = PC.build(positions, quotes={'AAPL': 100.0, 'UNKNOWNX': 100.0})
    coverage = ctx['sector_coverage']
    assert 'AAPL' in coverage['classified_symbols']
    assert coverage['unclassified_symbols'] == ['UNKNOWNX']
    assert coverage['classified_value_pct'] == 50.0
    assert coverage['unclassified_value_pct'] == 50.0


# ─── Candidat : gagnant/perdant, impact marginal ───────────────────────────────

def test_candidate_loser_reinforcement_forbidden():
    ctx = PC.build(_positions(), quotes=_quotes(), sym='AAA')
    c = ctx['candidate']
    assert c['held'] is True
    assert c['pnl_pct'] == pytest.approx(-10.0, abs=0.01)
    assert c['is_loser'] is True
    assert c['reinforcement_allowed'] is False
    assert 'confirmation' in ' '.join(c['reinforcement_conditions']).lower() or \
           c['reinforcement_conditions']       # conditions V2 échues


def test_candidate_winner_needs_confirmation_not_blanket_yes():
    ctx = PC.build(_positions(), quotes=_quotes(), sym='BBB')
    c = ctx['candidate']
    assert c['is_loser'] is False
    assert c['reinforcement_allowed'] == 'AFTER_CONFIRMATION'   # jamais un oui aveugle
    assert c['reinforcement_conditions']        # cassure/retest/résultats/révisions/tendance


def test_candidate_unknown_pnl_honest():
    ctx = PC.build(_positions(), quotes={}, sym='AAA')   # pas de cote
    c = ctx['candidate']
    assert c['pnl_pct'] is None and c['is_loser'] is None
    assert c['reinforcement_allowed'] is None    # inconnu ≠ autorisé


def test_candidate_not_held():
    ctx = PC.build(_positions(), quotes=_quotes(), sym='NEW')
    assert ctx['candidate']['held'] is False
    assert ctx['candidate']['weight_pct'] == 0.0


# ─── Sizing S+/S/A/B : plafonds analytiques, jamais un ordre ────────────────────

def test_sizing_analytical_caps_from_v2():
    ctx = PC.build(_positions(), quotes=_quotes(), sym='NEW', capital=10000.0)
    sz = ctx['sizing']
    assert sz['never_triggers_orders'] is True
    assert sz['base'] == 10000.0
    s = sz['levels']['S_PLUS']
    assert s['allocation_pct'] == [10, 15]
    assert s['amount_range'] == [1000.0, 1500.0]
    b = sz['levels']['B']
    assert b['amount_range'] == [100.0, 200.0]


def test_sizing_marginal_impact_and_concentration_breach():
    """BBB pèse déjà 56.8 % — tout ajout dépasse le plafond 15 % par titre."""
    ctx = PC.build(_positions(), quotes=_quotes(), sym='BBB', capital=4400.0)
    s = ctx['sizing']['levels']['A']
    assert s['resulting_weight_pct'] > 15.0
    assert s['concentration_breach'] is True
    new = PC.build(_positions(), quotes=_quotes(), sym='NEW', capital=4400.0)
    a = new['sizing']['levels']['B']            # 1-2 % sur titre neuf : pas de brèche
    assert a['concentration_breach'] is False


def test_risk_budget_honestly_absent_without_stops():
    ctx = PC.build(_positions(), quotes=_quotes())
    assert ctx['risk_budget']['available'] is False
    assert 'stop' in ctx['risk_budget']['reason']


def test_risk_budget_measures_only_positions_with_declared_stop():
    positions = [
        {'symbol': 'AAA', 'quantity': 10, 'cost_basis': 900, 'stop': 80,
         'asset_type': 'STOCK', 'source': 'MANUAL'},
        {'symbol': 'BBB', 'quantity': 5, 'cost_basis': 500,
         'asset_type': 'STOCK', 'source': 'MANUAL'},
    ]
    ctx = PC.build(positions, quotes={'AAA': 100, 'BBB': 120})
    budget = ctx['risk_budget']
    assert budget['available'] is True
    assert budget['known_risk_to_stop'] == 200.0
    assert budget['coverage_pct'] == 50.0
    assert budget['unmeasured'][0]['symbol'] == 'BBB'


def test_correlation_requires_explicitly_dated_overlapping_series():
    series = {}
    for offset, symbol in enumerate(('AAA', 'BBB', 'CCC')):
        closes = [100 + offset + day * (1 + offset * 0.1) for day in range(40)]
        series[symbol] = {'dates': [f'03-{day:02d}' for day in range(1, 41)], 'close': closes}
    ctx = PC.build(_positions(), quotes=_quotes(), series_by_symbol=series)
    assert ctx['correlations']['available'] is True
    assert len(ctx['correlations']['pairs']) == 3
    absent = PC.build(_positions(), quotes=_quotes())
    assert absent['correlations']['available'] is False


# ─── Branchement Skyler : gates portefeuille ────────────────────────────────────

def _detail(verdict='RENFORCER'):
    return {'score': 70, 'verdict': verdict,
            'plan': {'entry': 100, 'stop': 94, 'tp1': 106, 'tp2': 112,
                     'tp3': 118, 'rr_res': 3.0}}


def test_gate_loser_reinforcement_triggers():
    from vertex.engines import skyler_core as SK
    pctx = PC.build(_positions(), quotes=_quotes(), sym='AAA')
    p = SK.build_packet('AAA', _detail('RENFORCER'), portfolio_ctx=pctx, as_of='10:00')
    gates = SK.hard_gates(p, SK.score40(p))
    g = next(g for g in gates if g['id'] == 'LOSER_REINFORCEMENT')
    assert g['triggered'] is True


def test_gate_loser_not_triggered_for_winner_or_absent():
    from vertex.engines import skyler_core as SK
    pctx = PC.build(_positions(), quotes=_quotes(), sym='BBB')
    p = SK.build_packet('BBB', _detail('RENFORCER'), portfolio_ctx=pctx, as_of='10:00')
    g = next(g for g in SK.hard_gates(p, SK.score40(p)) if g['id'] == 'LOSER_REINFORCEMENT')
    assert g['triggered'] is False
    p2 = SK.build_packet('AAA', _detail(), as_of='10:00')   # sans portefeuille
    g2 = next(g for g in SK.hard_gates(p2, SK.score40(p2)) if g['id'] == 'LOSER_REINFORCEMENT')
    assert g2['triggered'] is None               # inconnu honnête


def test_gate_concentration_triggers_on_overweight():
    from vertex.engines import skyler_core as SK
    pctx = PC.build(_positions(), quotes=_quotes(), sym='BBB')   # 56.8 % > 15 %
    p = SK.build_packet('BBB', _detail('ACHETER'), portfolio_ctx=pctx, as_of='10:00')
    g = next(g for g in SK.hard_gates(p, SK.score40(p)) if g['id'] == 'CONCENTRATION_EXCESSIVE')
    assert g['triggered'] is True
    d = SK.decide('BBB', _detail('ACHETER'), portfolio_ctx=pctx, as_of='10:00')
    assert d['decision'] in ('ATTENDRE', 'REFUSER')   # le score ne contourne pas la porte


def test_decision_carries_sizing_when_available():
    from vertex.engines import skyler_core as SK
    pctx = PC.build(_positions(), quotes=_quotes(), sym='NEW', capital=10000.0)
    d = SK.decide('NEW', _detail('ACHETER'), portfolio_ctx=pctx, as_of='10:00')
    assert d['sizing'] is not None
    assert d['sizing']['never_triggers_orders'] is True


# ─── Route ──────────────────────────────────────────────────────────────────────

def test_skyler_route_includes_portfolio_context(tmp_path, monkeypatch):
    import json as _json
    import terminal
    from vertex.services import persist
    from vertex.app.state import scan_state
    monkeypatch.setattr(persist, 'cache_path', lambda name: str(tmp_path / name))
    persist.save_json('desk_data.json', {
        'data': {'myTrades': _json.dumps([{'id': 'T1', 'sym': 'PFX', 'type': 'STK',
                                           'qty': 10, 'cost': 1000.0}])}})
    scan_state.setdefault('detail', {})['PFX'] = _detail('ACHETER')
    scan_state['detail']['PFX']['price'] = 90.0
    try:
        d = terminal.app.test_client().get('/api/skyler/PFX').get_json()
        pctx = d['packet']['contexts']['portfolio']
        assert pctx['available'] is True
        assert pctx['candidate']['held'] is True
        assert pctx['candidate']['is_loser'] is True      # 90 < 100 (coût moyen)
    finally:
        scan_state['detail'].pop('PFX', None)


def test_portfolio_context_route(tmp_path, monkeypatch):
    """Route LOT 8d : /api/portfolio/context sert le contexte canonique du desk."""
    import json as _json
    import terminal
    from vertex.services import persist
    monkeypatch.setattr(persist, 'cache_path', lambda name: str(tmp_path / name))
    persist.save_json('desk_data.json', {
        'data': {'myTrades': _json.dumps([
            {'id': 'T1', 'sym': 'PCX', 'type': 'STK', 'qty': 10, 'cost': 1000.0},
            {'id': 'T2', 'sym': 'PCY', 'type': 'STK', 'qty': 5, 'cost': 500.0}])}})
    d = terminal.app.test_client().get('/api/portfolio/context').get_json()
    assert d['available'] is True
    assert d['n_positions'] == 2
    assert d['bounds'] == {'min': 8, 'max': 15}
    assert 'PCX' in d['weights']


def test_portfolio_context_route_empty_honest(tmp_path, monkeypatch):
    import terminal
    from vertex.services import persist
    monkeypatch.setattr(persist, 'cache_path', lambda name: str(tmp_path / name))
    d = terminal.app.test_client().get('/api/portfolio/context').get_json()
    assert d['available'] is False and 'reason' in d


def test_portfolio_risk_view_has_discipline_card():
    """Gardien LOT 8d : la vue Risque expose la carte Discipline V2."""
    import terminal
    body = terminal.app.test_client().get('/portfolio?view=risk').get_data(as_text=True)
    assert 'renderDiscipline' in body
    assert '/api/portfolio/context' in body
    assert 'Discipline du portefeuille' in body
