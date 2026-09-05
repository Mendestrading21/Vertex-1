"""Routes Strategy OS (§36-37) : hub, décision unique, diagnostics, mode dégradé."""
import pytest
from flask import Flask

from vertex.app.routes import strategy_os_api


@pytest.fixture()
def client():
    app = Flask(__name__)
    scan_state = {
        'source': 'stooq',
        'detail': {
            'NVDA': {'score': 78, 'rr': 2.3, 'rs': 70, 'st_fund': 72,
                     'st_timing': 65, 'ext_atr': 1.0, 'earnings_dte': 20,
                     'plan': {'entry': 490, 'stop': 465, 'tp1': 540},
                     'series': {'close': [400 + i for i in range(60)]}},
        },
        'market': {'regime': 'TREND', 'vix': 15.0, 'breadth': 68, 'risk': 'Risk-On'},
        'rows': [{'symbol': 'NVDA'}],
    }
    app.register_blueprint(strategy_os_api.make_blueprint(scan_state=scan_state))
    return app.test_client()


def test_profile_route(client):
    r = client.get('/api/strategy/profile')
    assert r.status_code == 200
    data = r.get_json()
    assert data['display_name'].startswith('Stratégie Vertex')
    assert data['strategy_id'].startswith('vertex_strategy_v')


def test_decision_route_uses_executive_engine(client):
    r = client.get('/api/strategy/decision/NVDA')
    data = r.get_json()
    assert data['final_decision'] in ('ACHETER', 'RENFORCER', 'ATTENDRE',
                                      'REDUIRE', 'REFUSER')
    assert data['audit_trail']
    assert set(data['scores']) == {'conviction', 'risk', 'timing', 'asymmetry',
                                   'data_quality'}


def test_decision_route_honest_when_symbol_unknown(client):
    r = client.get('/api/strategy/decision/ZZZZ')
    assert r.status_code == 200
    j = r.get_json()
    assert j['available'] is False
    # Hors scan, aucun verdict n'est fabriqué : null + état explicite.
    assert j['final_decision'] is None
    assert j['etat'] == 'NON_EVALUE'


def test_regime_route(client):
    data = client.get('/api/market/regime').get_json()
    assert data['regime'] in ('TREND_UP', 'RISK_ON', 'TRANSITION', 'UNKNOWN',
                              'VOLATILITY_COMPRESSION', 'CHOP')
    assert 'adjustments' in data


def test_anomalies_route_n_est_plus_declaree_ici(client):
    #  Lot 9 : la route etait MASQUEE par analysis_api (meme chemin, premier
    #  enregistre gagne) et sa forme {anomalies:[...]} ne servait que la page
    #  legacy /strategy-os, devenue une redirection 301. Retiree — le
    #  proprietaire unique est analysis_api.api_anomalies.
    r = client.get('/api/anomalies/NVDA')
    assert r.status_code == 404, (
        'la route a deux proprietaires est revenue dans strategy_os_api.')


def test_team_route_requires_explicit_positions(client):
    usage = client.get('/api/portfolio/team').get_json()
    assert 'positions réelles' in usage['usage'] or 'simulées explicites' in usage['usage']
    r = client.post('/api/portfolio/team', json={
        'positions': [{'symbol': 'NVDA', 'quantity': 10, 'avg_cost': 400,
                       'last_price': 500, 'sector': 'Technologie', 'beta': 1.6}],
        'cash': 5000, 'simulated': True})
    data = r.get_json()
    assert data['risk']['provenance'] == 'SIMULATED'
    assert 'stress' in data and 'guard' in data


def test_diagnostics_and_data_quality(client):
    d = client.get('/api/system/diagnostics').get_json()
    assert 'scan' in d and 'alerts' in d and 'tradingview' in d
    blob = str(d).lower()
    for secret_like in ('anthropic_api_key', 'vertex_secret', 'password'):
        assert secret_like not in blob
    dq = client.get('/api/data-quality').get_json()
    assert dq['total'] == 1 and 'by_quality' in dq


def test_hub_page_renders_without_personal_names():
    """Le hub Strategy OS (vertex/ui/strategy_os.py) est retiré (lot 37) :
    /strategy-os appartient à redesign et redirige vers Vertex IA."""
    import terminal
    r = terminal.app.test_client().get('/strategy-os')
    assert r.status_code == 301
    assert (r.headers.get('Location') or '').startswith('/intelligence')


def test_degraded_mode_empty_scan():
    """Sans scan, sans IBKR, sans IA : les routes répondent proprement."""
    app = Flask(__name__)
    app.register_blueprint(strategy_os_api.make_blueprint(scan_state={}))
    c = app.test_client()
    assert c.get('/api/strategy/profile').status_code == 200
    dec = c.get('/api/strategy/decision/NVDA')
    assert dec.status_code == 200 and dec.get_json()['available'] is False
    regime = c.get('/api/market/regime').get_json()
    assert regime['regime'] == 'UNKNOWN'
    assert c.get('/api/system/diagnostics').status_code == 200
    assert c.get('/api/data-quality').get_json()['total'] == 0


def test_decision_route_blocks_incomplete_packet(client):
    data = client.get('/api/strategy/decision/NVDA').get_json()
    assert data['final_decision'] == 'ATTENDRE'
    assert data['decision_packet']['complete'] is False
    assert 'DECISION_PACKET_INCOMPLETE' in data['blocking_rules']


def test_decision_route_uses_explicit_complete_packet():
    app = Flask(__name__)
    scan_state = {
        'source': 'ibkr_live',
        'detail': {
            'NVDA': {
                'score': 78, 'rr': 2.3, 'rs': 70, 'st_fund': 72,
                'st_timing': 65, 'ext_atr': 1.0, 'earnings_dte': 20,
                'plan': {'entry': 490, 'stop': 465, 'tp1': 540},
                'series': {'close': [400 + i for i in range(60)]},
                'data_quality': {'overall': 'FRESH', 'actionable_allowed': True},
                'reconciliation': {'actionable_allowed': True},
                'guard': {'blocking_rules': [], 'mandatory_reviews': []},
            },
        },
        'market': {'regime': 'TREND', 'vix': 15.0, 'breadth': 68, 'risk': 'Risk-On'},
    }
    app.register_blueprint(strategy_os_api.make_blueprint(scan_state=scan_state))
    data = app.test_client().get('/api/strategy/decision/NVDA').get_json()
    assert data['decision_packet']['complete'] is True
    assert 'DECISION_PACKET_INCOMPLETE' not in data['blocking_rules']
    assert data['final_decision'] in ('ACHETER', 'RENFORCER', 'ATTENDRE')
