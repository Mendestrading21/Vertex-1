"""tests/test_portfolio_stress.py — stress-scénarios du book : maths exactes + honnêteté."""
from vertex.engines import portfolio_stress as ps


def _pos():
    return [
        {'sym': 'AAPL', 'type': 'STK', 'qty': 10, 'cost': 1500},
        {'sym': 'MSFT', 'type': 'STK', 'qty': 5, 'cost': 2000},
        {'sym': 'NVDA', 'type': 'CALL', 'qty': 2, 'cost': 800, 'strike': 120},   # option → exclue
        {'sym': 'ZZZZ', 'type': 'STK', 'qty': 3, 'cost': 300},                    # sans prix → exclue
    ]


def _prices():
    return {'AAPL': 200.0, 'MSFT': 400.0}


def test_stress_math_exact():
    d = ps.build(_pos(), _prices())
    assert d['empty'] is False
    # valeur stressée = 10*200 + 5*400 = 4000
    assert d['stressed_value'] == 4000.0
    sc5 = next(s for s in d['scenarios'] if s['shock_pct'] == -5.0)
    assert sc5['impact'] == -200.0                       # 4000 × −5 %
    assert sc5['value_after'] == 3800.0
    # pire contributeur du choc −5 % : MSFT (2000×−5% = −100 > AAPL −100 ? égal…)
    imps = {r['sym']: r['impact'] for r in sc5['by_position']}
    assert imps == {'AAPL': -100.0, 'MSFT': -100.0}


def test_options_and_unpriced_excluded_honestly():
    d = ps.build(_pos(), _prices())
    reasons = {e['sym']: e['reason'] for e in d['excluded']}
    assert 'NVDA' in reasons and 'IBKR' in reasons['NVDA']       # option jamais estimée
    assert 'ZZZZ' in reasons and 'prix réel' in reasons['ZZZZ']
    # couverture = 4000 / (4000 + 800 + 300)
    assert d['coverage_pct'] == round(100 * 4000 / 5100)


def test_narrative_states_assumption_not_advice():
    d = ps.build(_pos(), _prices())
    assert 'beta 1' in d['narrative']
    assert 'pas une prévision' in d['narrative']


def test_beta_assumptions_expose_declared_and_defaulted_coverage():
    from vertex.portfolio.models import Position, PortfolioSnapshot
    snapshot = PortfolioSnapshot(positions=[Position('AAA', 1, last_price=100, beta=1.2),
                                            Position('BBB', 1, last_price=100)])
    from vertex.portfolio.stress_tests import run_stress_tests
    out = run_stress_tests(snapshot, type('Profile', (), {'portfolio_max_drawdown_pct': -25})())
    assert out['beta_assumptions']['declared_symbols'] == ['AAA']
    assert out['beta_assumptions']['defaulted_symbols'] == ['BBB']
    assert out['beta_assumptions']['declared_weight_pct'] == 50.0
    assert out['beta_assumptions']['read_only'] is True


# ── Constat 26 : le zéro inventé de l'IV crush, et le périmètre tu ──────────

def _snapshot_actions_et_cash():
    from vertex.portfolio.models import Position, PortfolioSnapshot
    return PortfolioSnapshot(positions=[
        Position('KO', 1, avg_cost=88.07, last_price=88.07, sector='Consumer Defensive')],
        cash=25000.0, provenance='REAL')


class _Profil:
    portfolio_max_drawdown_pct = -25.0


def test_iv_crush_avec_options_sans_greeks_nest_plus_un_zero_invente():
    """MESURE : avec 2 options déclarées et aucun greek broker, le bloc §26
    publiait « IV_CRUSH 0,0 % · contraction d'IV de 30 % sur les options
    longues détenues » et « VIX_PLUS_50 −0,0 % · choc actions modéré +
    gain/perte vega des options ». Preuve décisive : la même requête SANS
    `option_positions` rendait des scénarios BIT POUR BIT identiques — le vega
    ne changeait rien pendant que la note affirmait le contraire.
    `options_vega_value or 0.0` écrasait l'inconnu en zéro connu."""
    from vertex.portfolio.stress_tests import run_stress_tests
    out = run_stress_tests(_snapshot_actions_et_cash(), _Profil(),
                           options_vega_value=None, options_open=2)
    assert out['scenarios']['IV_CRUSH']['impact_pct'] is None       # valait 0.0
    assert 'non estimé' in out['scenarios']['IV_CRUSH']['note']
    vix = out['scenarios']['VIX_PLUS_50']
    assert vix['impact_pct'] is None                                # valait -0.0
    assert '2 option(s)' in vix['note'] and 'non estimé' in vix['note']
    assert 'gain/perte vega des options' not in vix['note']         # promesse retirée


def test_sans_aucune_option_le_zero_de_liv_crush_est_un_fait():
    """`options_open=0` : il n'y a rien à écraser, donc 0,0 % est vrai — et le
    dire n'est pas la même chose que le supposer."""
    from vertex.portfolio.stress_tests import run_stress_tests
    out = run_stress_tests(_snapshot_actions_et_cash(), _Profil(),
                           options_vega_value=None, options_open=0)
    assert out['scenarios']['IV_CRUSH']['impact_pct'] == 0.0
    assert 'aucune option' in out['scenarios']['IV_CRUSH']['note']
    assert out['scenarios']['VIX_PLUS_50']['impact_pct'] is not None
    assert out['warnings'] == []


def test_perimetre_options_non_transmis_reste_inconnu_jamais_zero():
    """Appelant qui ne dit rien du book options : le moteur ne peut pas
    distinguer « aucune option » de « options sans greeks ». Il refuse donc de
    chiffrer, et `coverage` publie l'ignorance au lieu de la cacher."""
    from vertex.portfolio.stress_tests import run_stress_tests
    out = run_stress_tests(_snapshot_actions_et_cash(), _Profil())
    assert out['scenarios']['IV_CRUSH']['impact_pct'] is None
    assert out['coverage']['options_open'] is None
    assert out['coverage']['options_vega_known'] is False
    assert out['coverage']['options_in_equity'] is False


def test_couverture_du_stress_est_publiee_avec_les_chiffres():
    """MESURE : 14 100 $ d'options sur 39 188 $ de capital déclaré (36 %)
    restaient hors base ET hors impact, sous « pire scénario −0,1 % » sans
    aucune mention de périmètre — alors que la carte voisine le disait."""
    from vertex.portfolio.stress_tests import run_stress_tests
    out = run_stress_tests(_snapshot_actions_et_cash(), _Profil(),
                           options_vega_value=None, options_open=2)
    assert out['coverage']['options_in_equity'] is False
    assert 'hors base' in out['coverage']['note']
    assert any('hors base de stress' in w for w in out['warnings'])


def test_vega_connu_chiffre_toujours_liv_crush():
    """Non-régression : un vega broker RÉEL reste chiffré, sans note d'absence."""
    from vertex.portfolio.stress_tests import run_stress_tests
    out = run_stress_tests(_snapshot_actions_et_cash(), _Profil(),
                           options_vega_value=500.0, options_open=2)
    assert out['scenarios']['IV_CRUSH']['impact_pct'] == -0.6      # 500 × 0,3 / 25 088
    assert out['scenarios']['VIX_PLUS_50']['impact_pct'] is not None
    assert out['coverage']['options_vega_known'] is True


def test_no_stock_positions_is_honest():
    d = ps.build([{'sym': 'NVDA', 'type': 'CALL', 'qty': 2, 'cost': 800}], {})
    assert d['empty'] is True
    assert d['reason'] and 'IBKR' in d['reason']


def test_empty_book():
    d = ps.build([], {})
    assert d['empty'] is True and d['excluded'] == []


def test_stress_route_reads_desk_and_scan(tmp_path, monkeypatch):
    import json
    import terminal
    from vertex.services import persist
    from vertex.app.state import scan_state
    monkeypatch.setattr(persist, 'cache_path', lambda name: str(tmp_path / name))
    persist.save_json('desk_data.json', {'ts': 1, 'data': {'myTrades': json.dumps([
        {'id': 1, 'sym': 'AAPL', 'type': 'STK', 'qty': 10, 'cost': 1500}])}})
    scan_state.setdefault('detail', {})['AAPL'] = {'price': 200.0}
    client = terminal.app.test_client()
    d = client.get('/api/portfolio/stress').get_json()
    assert d['empty'] is False
    assert d['stressed_value'] == 2000.0
    sc = next(s for s in d['scenarios'] if s['shock_pct'] == -5.0)
    assert sc['impact'] == -100.0


def test_risk_view_mentions_stress():
    import terminal
    body = terminal.app.test_client().get('/portfolio?view=risk').get_data(as_text=True)
    assert 'renderStress' in body                     # loader câblé dans la vue Risque
