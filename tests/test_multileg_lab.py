"""Vérification MATH du moteur multi-jambes (multileg_lab).

Valeurs attendues calculées à la main sur des stratégies canoniques : si un chiffre
dérive, un trader serait induit en erreur → ces tests sont un garde-fou produit.
Multiplicateur 100 (1 contrat = 100 actions).
"""
import pytest
from flask import Flask

from vertex.engines import multileg_lab as ml


@pytest.fixture()
def client():
    from vertex.app import state as app_state
    from vertex.app.routes import options_lab_api
    app = Flask(__name__)
    app.register_blueprint(options_lab_api.bp)
    saved_board = app_state.scan_state.get('options_board')
    saved_detail = (app_state.scan_state.get('detail') or {}).get('TEST')
    app_state.scan_state['options_board'] = [
        {'sym': 'TEST', 'type': 'CALL', 'strike': 100, 'exp': '2026-08-21', 'dte': 35, 'iv': 0.30, 'cost': 500},
        {'sym': 'TEST', 'type': 'PUT', 'strike': 100, 'exp': '2026-08-21', 'dte': 35, 'iv': 0.30, 'cost': 500},
        {'sym': 'TEST', 'type': 'CALL', 'strike': 106, 'exp': '2026-08-21', 'dte': 35, 'iv': 0.30, 'cost': 200},
        {'sym': 'TEST', 'type': 'PUT', 'strike': 94, 'exp': '2026-08-21', 'dte': 35, 'iv': 0.30, 'cost': 200},
    ]
    app_state.scan_state.setdefault('detail', {})['TEST'] = {'price': 100}
    yield app.test_client()
    # restauration pour ne pas polluer les autres tests
    if saved_board is None:
        app_state.scan_state.pop('options_board', None)
    else:
        app_state.scan_state['options_board'] = saved_board
    if saved_detail is None:
        (app_state.scan_state.get('detail') or {}).pop('TEST', None)
    else:
        app_state.scan_state['detail']['TEST'] = saved_detail


def test_long_call_math():
    r = ml.analyze_strategy([{'type': 'call', 'strike': 100, 'premium': 5, 'qty': 1}],
                            spot=100, iv=0.30, days_to_exp=30)
    assert r['available'] is True
    assert r['net_premium'] == 500.0          # débit 1×100×5
    assert r['is_credit'] is False
    assert r['max_loss'] == -500.0            # perte = prime payée
    assert r['max_profit_unbounded'] is True  # call long = gain illimité
    assert r['max_profit'] is None
    assert r['breakevens'] == [pytest.approx(105.0, abs=0.5)]  # strike + prime
    assert 0.0 <= r['probability_of_profit'] <= 100.0
    # ATM, breakeven au-dessus du spot → PoP < 50 %
    assert r['probability_of_profit'] < 50.0
    coverage = r['input_coverage']
    assert coverage['premium_covered_option_legs'] == 1
    assert coverage['bid_ask_coverage_pct'] == 0.0
    assert coverage['greeks_available'] is True


def test_bull_call_spread_math():
    legs = [{'type': 'call', 'strike': 100, 'premium': 5, 'qty': 1},
            {'type': 'call', 'strike': 110, 'premium': 2, 'qty': -1}]
    r = ml.analyze_strategy(legs, spot=100, iv=0.30, days_to_exp=30)
    assert r['net_premium'] == 300.0           # débit net (5-2)×100
    assert r['max_loss'] == -300.0             # = débit net
    assert r['max_profit_unbounded'] is False  # spread borné (call vendu couvre)
    assert r['max_profit'] == pytest.approx(700.0, abs=1.0)  # largeur 1000 - débit 300
    assert r['breakevens'] == [pytest.approx(103.0, abs=0.5)]  # strike bas + débit/action


def test_short_put_credit_math():
    r = ml.analyze_strategy([{'type': 'put', 'strike': 100, 'premium': 5, 'qty': -1}],
                            spot=105, iv=0.30, days_to_exp=30)
    assert r['net_premium'] == -500.0          # crédit encaissé
    assert r['is_credit'] is True
    assert r['max_profit'] == pytest.approx(500.0, abs=1.0)  # garde la prime
    assert r['max_profit_unbounded'] is False
    assert r['max_loss'] == pytest.approx(-9500.0, abs=50.0)  # ~ strike-prime à cours 0, ×100
    assert r['breakevens'] == [pytest.approx(95.0, abs=0.5)]  # strike - prime


def test_iron_condor_bounded_and_credit():
    legs = [{'type': 'put', 'strike': 90, 'premium': 1, 'qty': 1},
            {'type': 'put', 'strike': 95, 'premium': 2, 'qty': -1},
            {'type': 'call', 'strike': 105, 'premium': 2, 'qty': -1},
            {'type': 'call', 'strike': 110, 'premium': 1, 'qty': 1}]
    r = ml.analyze_strategy(legs, spot=100, iv=0.30, days_to_exp=30)
    assert r['is_credit'] is True               # net crédit (on encaisse)
    assert r['max_profit_unbounded'] is False   # ailes longues bornent tout
    # crédit net = (2+2-1-1)×100 = 200 = gain max
    assert r['max_profit'] == pytest.approx(200.0, abs=1.0)
    # perte max = largeur d'aile (5) ×100 - crédit 200 = 300
    assert r['max_loss'] == pytest.approx(-300.0, abs=1.0)
    assert len(r['breakevens']) == 2            # deux breakevens (bas et haut)
    assert r['breakevens'][0] == pytest.approx(93.0, abs=0.5)
    assert r['breakevens'][1] == pytest.approx(107.0, abs=0.5)


def test_greeks_signs():
    # Long call : delta>0, gamma>0, vega>0, theta<0 (le temps nuit au long).
    r = ml.analyze_strategy([{'type': 'call', 'strike': 100, 'premium': 5, 'qty': 1}],
                            spot=100, iv=0.30, days_to_exp=30)
    g = r['greeks']
    assert g is not None
    assert g['delta'] > 0 and g['gamma'] > 0 and g['vega'] > 0 and g['theta'] < 0
    # Short put : delta>0 (haussier), theta>0 (le temps profite au vendeur).
    r2 = ml.analyze_strategy([{'type': 'put', 'strike': 100, 'premium': 5, 'qty': -1}],
                             spot=100, iv=0.30, days_to_exp=30)
    assert r2['greeks']['delta'] > 0 and r2['greeks']['theta'] > 0


def test_higher_order_greeks():
    # Call OTM : vanna>0 et vomma>0 (d1,d2 < 0 → d1*d2 > 0, -d2 > 0).
    g = ml.analyze_strategy([{'type': 'call', 'strike': 120, 'premium': 1, 'qty': 1}],
                            spot=100, iv=0.30, days_to_exp=30)['greeks']
    assert 'vanna' in g and 'vomma' in g
    assert g['vomma'] > 0 and g['vanna'] > 0
    # Parité call/put : vega, vanna, vomma IDENTIQUES au même strike/qty (garde-fou math).
    gc = ml.analyze_strategy([{'type': 'call', 'strike': 110, 'premium': 2, 'qty': 1}],
                             spot=100, iv=0.30, days_to_exp=30)['greeks']
    gp = ml.analyze_strategy([{'type': 'put', 'strike': 110, 'premium': 2, 'qty': 1}],
                             spot=100, iv=0.30, days_to_exp=30)['greeks']
    assert abs(gc['vega'] - gp['vega']) < 1e-6
    assert abs(gc['vanna'] - gp['vanna']) < 1e-6
    assert abs(gc['vomma'] - gp['vomma']) < 1e-6


def test_honest_refusals():
    # Prime manquante → refus honnête, pas de P&L inventé.
    bad = ml.analyze_strategy([{'type': 'call', 'strike': 100, 'premium': None, 'qty': 1}],
                              spot=100, iv=0.30, days_to_exp=30)
    assert bad['available'] is False
    # Aucune jambe → refus.
    assert ml.analyze_strategy([], spot=100, iv=0.3, days_to_exp=30)['available'] is False
    # Spot invalide → refus.
    assert ml.analyze_strategy([{'type': 'call', 'strike': 100, 'premium': 5, 'qty': 1}],
                               spot=0, iv=0.3, days_to_exp=30)['available'] is False


def test_preset_builds_iron_condor():
    ref = {'atm': {'strike': 100, 'call': 3, 'put': 3},
           'otm_call': {'strike': 110, 'call': 1}, 'otm_put': {'strike': 90, 'put': 1}}
    legs = ml.build_preset('iron_condor', 100, ref)
    assert legs is not None and len(legs) == 4
    r = ml.analyze_strategy(legs, spot=100, iv=0.30, days_to_exp=30)
    assert r['available'] is True and r['is_credit'] is True
    # Preset incomplet (pas de otm_call) → None honnête.
    assert ml.build_preset('iron_condor', 100, {'atm': {'strike': 100, 'call': 3, 'put': 3}}) is None


def test_strategies_from_board_synthetic():
    board = [
        {'sym': 'TEST', 'type': 'CALL', 'strike': 100, 'exp': '2026-08-21', 'dte': 35, 'iv': 0.30, 'cost': 500},
        {'sym': 'TEST', 'type': 'PUT', 'strike': 100, 'exp': '2026-08-21', 'dte': 35, 'iv': 0.30, 'cost': 500},
        {'sym': 'TEST', 'type': 'CALL', 'strike': 106, 'exp': '2026-08-21', 'dte': 35, 'iv': 0.30, 'cost': 200},
        {'sym': 'TEST', 'type': 'PUT', 'strike': 94, 'exp': '2026-08-21', 'dte': 35, 'iv': 0.30, 'cost': 200},
        {'sym': 'OTHER', 'type': 'CALL', 'strike': 50, 'exp': '2026-08-21', 'dte': 35, 'iv': 0.30, 'cost': 300},
    ]
    res = ml.strategies_for_symbol(board, 'TEST', 100)
    assert res['available'] is True
    kinds = {s['kind'] for s in res['strategies']}
    # avec ATM call+put et OTM call+put, tous les presets se construisent
    assert {'iron_condor', 'straddle', 'strangle', 'bull_call_spread'} <= kinds
    for s in res['strategies']:
        assert 'payoff' in s and 'max_loss' in s and 'breakevens' in s and 'label' in s
    # symbole absent → refus honnête
    assert ml.strategies_for_symbol(board, 'ZZZ', 100)['available'] is False


def _board():
    return [
        {'sym': 'TEST', 'type': 'CALL', 'strike': 100, 'exp': '2026-08-21', 'dte': 35, 'iv': 0.30, 'cost': 500},
        {'sym': 'TEST', 'type': 'PUT', 'strike': 100, 'exp': '2026-08-21', 'dte': 35, 'iv': 0.30, 'cost': 500},
        {'sym': 'TEST', 'type': 'CALL', 'strike': 106, 'exp': '2026-08-21', 'dte': 35, 'iv': 0.30, 'cost': 220},
        {'sym': 'TEST', 'type': 'PUT', 'strike': 94, 'exp': '2026-08-21', 'dte': 35, 'iv': 0.30, 'cost': 210},
    ]


def test_ranking_recommends_by_bias():
    # exactement une recommandée, alignée sur le biais
    rb = ml.strategies_for_symbol(_board(), 'TEST', 100, bias='bullish')
    reco = [s for s in rb['strategies'] if s['recommended']]
    assert len(reco) == 1 and reco[0]['kind'] in ('long_call', 'bull_call_spread')
    rx = ml.strategies_for_symbol(_board(), 'TEST', 100, bias='bearish')
    assert [s for s in rx['strategies'] if s['recommended']][0]['kind'] in ('long_put', 'bear_put_spread')
    rn = ml.strategies_for_symbol(_board(), 'TEST', 100, bias='neutral')
    assert [s for s in rn['strategies'] if s['recommended']][0]['kind'] in ('iron_condor', 'straddle', 'strangle')
    # tri décroissant par fit_score + reason présente
    scores = [s['fit_score'] for s in rb['strategies']]
    assert scores == sorted(scores, reverse=True)
    assert all(s.get('fit_reason') for s in rb['strategies'])


def test_strategies_route_real_and_honest(client):
    # symbole présent dans le board → 200 + stratégies analysées
    r = client.get('/api/options/strategies/TEST')
    assert r.status_code == 200
    d = r.get_json()
    assert d['available'] is True
    assert isinstance(d['strategies'], list) and len(d['strategies']) >= 3
    s0 = d['strategies'][0]
    assert 'payoff' in s0 and 'breakevens' in s0 and 'max_loss' in s0 and 'label' in s0
    # symbole absent → 200 + refus honnête (jamais 404 ni chiffre inventé)
    r2 = client.get('/api/options/strategies/ZZZZ')
    assert r2.status_code == 200
    assert r2.get_json()['available'] is False


def test_analyze_route_post(client):
    # stratégie arbitraire (spread haussier) via POST → analyse cohérente
    r = client.post('/api/options/analyze', json={
        'legs': [{'type': 'call', 'strike': 100, 'premium': 5, 'qty': 1},
                 {'type': 'call', 'strike': 110, 'premium': 2, 'qty': -1}],
        'spot': 100, 'iv': 0.30, 'days': 30})
    assert r.status_code == 200
    d = r.get_json()
    assert d['available'] is True
    assert d['max_loss'] == -300.0
    assert d['max_profit'] == pytest.approx(700.0, abs=1.0)
    assert 'payoff' in d
    # entrée vide → refus honnête, jamais 500
    r2 = client.post('/api/options/analyze', json={'legs': [], 'spot': 100})
    assert r2.status_code == 200 and r2.get_json()['available'] is False


def test_no_order_paths_in_module():
    """Garde-fou READONLY : le module ne contient aucun chemin d'ordre."""
    import inspect
    src = inspect.getsource(ml).lower()
    for bad in ('place_order', 'placeorder', 'submit_order', 'reqmarketorder', 'buy(', 'sell('):
        assert bad not in src


# ── Constat 44 : le carnet du board ne doit plus mourir entre le board et la jambe ──

def _contrat_cote(typ, strike, cost, bid, ask, quoted=True):
    """Ligne de board RÉELLE : `cost` est PAR CONTRAT, `bid`/`ask` PAR ACTION."""
    return {'sym': 'NVDA', 'type': typ, 'strike': strike, 'exp': '2026-10-16',
            'dte': 35, 'iv': 0.30, 'cost': cost, 'bid': bid, 'ask': ask,
            'liquidity_coverage': {'quoted_bid_ask': quoted, 'volume_present': True}}


def test_le_carnet_du_board_arrive_jusqu_a_la_jambe_et_chiffre_le_rempli_defavorable():
    """MESURE : `/api/options/strategies/NVDA` servait
    `bid_ask_coverage_pct: 0.0` et `net_premium_adverse: null` sur 100 % des
    stratégies, avec la note « le rendement exécutable dépend du spread
    bid/ask, non fourni ici » — alors que le board portait bid ET ask sur les
    mêmes contrats. Le nœud `ref` de `strategies_for_symbol` ne transportait
    que `strike` et la prime : le carnet mourait là, et l'honnêteté
    d'exécution du moteur tombait sur une absence FABRIQUÉE par le câblage.

    Attendu : call ATM bid 6,00 / ask 6,40, prime déclarée 6,20 (cost 620/100).
    Achat à l'ask → 1 × 100 × 6,40 = 640,00 $ contre 620,00 $ déclarés."""
    board = [_contrat_cote('CALL', 230, 620, 6.0, 6.4),
             _contrat_cote('PUT', 230, 600, 5.8, 6.2)]
    res = ml.strategies_for_symbol(board, 'NVDA', 230.0)
    par_kind = {s['kind']: s for s in res['strategies']}

    lc = par_kind['long_call']
    assert lc['legs'][0]['bid'] == 6.0 and lc['legs'][0]['ask'] == 6.4
    assert lc['input_coverage']['bid_ask_coverage_pct'] == 100.0
    assert lc['execution']['spread_slippage_included'] is True
    assert lc['execution']['net_premium_declared'] == 620.0
    assert lc['execution']['net_premium_adverse'] == 640.0
    #  PIÈGE D'UNITÉ : `premium` vient de cost/100, `bid`/`ask` sont déjà par
    #  action. Une division de trop rendrait 6,40 $ au lieu de 640,00 $.
    assert lc['execution']['net_premium_adverse'] == round(100 * 6.4, 2)

    #  Deux jambes : achat à l'ask ET vente au bid dans le même chiffre.
    st = par_kind['straddle']
    assert st['execution']['net_premium_adverse'] == 1260.0     # 100 × (6,40 + 6,20)
    assert st['input_coverage']['bid_ask_covered_option_legs'] == 2


def test_un_contrat_non_cote_ne_fabrique_aucun_carnet():
    """`legacy_engine._f(None)` rend 0.0 : un contrat sans carnet porte
    `bid: 0.0, ask: 0.0` dans le board. Les recopier chiffrerait un rempli
    défavorable de 0 $ sur un carnet inexistant — une donnée inventée, pire
    que l'absence qu'elle remplacerait. L'absence reste une absence."""
    board = [_contrat_cote('CALL', 230, 620, 0.0, 0.0, quoted=False),
             _contrat_cote('PUT', 230, 600, 0.0, 0.0, quoted=False)]
    res = ml.strategies_for_symbol(board, 'NVDA', 230.0)
    lc = {s['kind']: s for s in res['strategies']}['long_call']
    assert lc['legs'][0]['bid'] is None and lc['legs'][0]['ask'] is None
    assert lc['input_coverage']['bid_ask_coverage_pct'] == 0.0
    assert lc['execution']['net_premium_adverse'] is None
    assert 'non fourni' in lc['execution']['note']
    #  Un carnet CROISÉ (ask < bid) n'est pas un carnet non plus.
    croise = [_contrat_cote('CALL', 230, 620, 6.4, 6.0),
              _contrat_cote('PUT', 230, 600, 5.8, 6.2)]
    lc2 = {s['kind']: s for s in ml.strategies_for_symbol(croise, 'NVDA', 230.0)['strategies']}['long_call']
    assert lc2['legs'][0]['bid'] is None
