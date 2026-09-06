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
            #  La forme du detail est celle que le SCAN produit réellement : la
            #  note fondamentale vit dans `sub` (analysis.analyse → 'sub': sc).
            #  Ces fixtures posaient `st_fund`/`st_timing`, deux clés qu'aucun
            #  producteur du dépôt n'écrit sur le detail — elles fabriquaient une
            #  forme que le scan ne sert jamais, ce qui expliquait que la suite
            #  reste verte alors que le paquet lisait à vide en production.
            'NVDA': {'score': 78, 'rr': 2.3, 'rs': 70,
                     'sub': {'fundamental': 72, 'fundamental_is_proxy': False},
                     'ext_atr': 1.0, 'earnings_dte': 20,
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
                'score': 78, 'rr': 2.3, 'rs': 70,
                'sub': {'fundamental': 72, 'fundamental_is_proxy': False},
                'ext_atr': 1.0, 'earnings_dte': 20,
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


# ═══════════════════════════════════════════════════════════════════════════
# Lot C — le paquet décisionnel lit ses producteurs RÉELS (constats 5, 7, 41)
# ═══════════════════════════════════════════════════════════════════════════

def test_fondamental_mesure_n_est_plus_declare_inconnu(client):
    """CONSTAT 5 — une note fondamentale MESURÉE était servie comme une absence.

    MESURE d'origine (scan réel 513 titres, source yfinance) : /api/ticker/NVDA
    servait `sub = {'fundamental': 100, 'fundamental_is_proxy': False, ...}`
    pendant que /api/strategy/decision/NVDA rendait `fundamental.score = None`.
    Le paquet lisait `detail['st_fund'] or detail['fund_score']` : `fund_score`
    n'a AUCUNE assignation dans le dépôt et `st_fund` n'est posée que sur la
    ligne de tableau (terminal.py:609), jamais sur le `detail`. Conséquence
    mesurée sur un balayage de 40 titres : 40/40 avec 'fundamental' dans
    `unknowns`, décisions {ATTENDRE: 21, REFUSER: 19}, ACHETER + RENFORCER = 0 —
    `unknowns_critical` rendait la branche haute inatteignable pour TOUT
    l'univers, en permanence, et la conviction publiée était fausse (73.0 au
    lieu de 82.0 sur NVDA).
    """
    data = client.get('/api/strategy/decision/NVDA').get_json()
    assert data['fundamental']['score'] == 72
    assert 'fundamental' not in data['unknowns']
    # Le lignage voyage avec la note (invariant 6) : proxy ≠ mesure directe.
    assert data['fundamental']['is_proxy'] is False
    # conviction = moyenne(fondamental 72, technique 78, sentiment 70) = 73.3.
    # Sans le fondamental elle valait (78 + 70) / 2 = 74.0 — un chiffre faux,
    # pas seulement incomplet.
    assert data['scores']['conviction'] == 73.3


def test_fondamental_zero_reste_absent_jamais_mauvais():
    """CONSTAT 5 — sémantique 0 préservée (tests/test_evidence_edges.py:40).

    Une note fondamentale à 0 signifie « fondamentaux non branchés », pas
    « fondamentaux mauvais » : elle doit rester une inconnue déclarée et ne
    jamais entrer dans la conviction comme un zéro punitif.
    """
    from vertex.strategy import decision_packet as _dp
    from vertex.strategy import executive_engine as _ex
    pkt = _dp.build('ZZ', {'score': 78, 'sub': {'fundamental': 0}}, {'source': 'stooq'})
    assert pkt['fundamental'] == {'score': None, 'is_proxy': None}
    assert 'fundamental' in _ex.decide(pkt)['unknowns']


def test_regime_de_la_decision_est_celui_de_la_route_regime(client):
    """CONSTAT 7 — REGIME_BLOCKS_NEW_RISK s'allumait sur 15/15 des titres.

    MESURE d'origine : `build_executive_decision` écrasait le régime du paquet
    avec un mapping inline lisant `scan_state['market'].{regime,spy_trend,
    breadth,vix}`. Or cette clé est l'HORLOGE de séance (market_status) —
    mesurée à {'et': '08:54 ET', 'open': False, 'session': 'closed'}, donc
    aucune dimension de régime. Entrées toutes None → regime UNKNOWN,
    confidence 0.0, dimensions [] → blocking_rules
    {'REGIME_BLOCKS_NEW_RISK': 15} et audit « régime UNKNOWN — nouveau risque
    bloqué » sur 15/15, pendant que /api/market/regime rendait CHOP,
    confidence 0.6, 4 dimensions et new_risk_allowed True sur le MÊME
    scan_state, à la MÊME seconde. Le mapping canonique est
    `market_context.regime_inputs` : une seule autorité, donc
    /api/strategy/decision et /api/market/regime concordent.
    """
    regime = client.get('/api/market/regime').get_json()['regime']
    assert regime != 'UNKNOWN', 'le scan porte les dimensions : régime calculable'
    data = client.get('/api/strategy/decision/NVDA').get_json()
    assert 'REGIME_BLOCKS_NEW_RISK' not in data['blocking_rules']
    assert not any('UNKNOWN' in line for line in data['audit_trail'])


def test_regime_absent_bloque_toujours_le_risque_neuf():
    """CONSTAT 7 — la garde reste fail-closed quand le régime est VRAIMENT absent.

    Le correctif ne desserre pas la règle : sans aucune dimension dans le scan,
    le classifieur dégrade en UNKNOWN et la garde doit se déclencher. C'est
    précisément ce qui la rend informative — allumée en permanence, elle ne
    distinguait plus un marché en PANIC d'un câblage rompu.
    """
    app = Flask(__name__)
    scan_state = {'source': 'stooq',
                  'detail': {'NVDA': {'score': 78, 'rr': 2.3, 'rs': 70,
                                      'sub': {'fundamental': 72}}},
                  'market': {'et': '08:54 ET', 'open': False, 'session': 'closed'}}
    app.register_blueprint(strategy_os_api.make_blueprint(scan_state=scan_state))
    data = app.test_client().get('/api/strategy/decision/NVDA').get_json()
    assert 'REGIME_BLOCKS_NEW_RISK' in data['blocking_rules']
    assert data['final_decision'] == 'ATTENDRE'


def test_branche_acheter_redevient_atteignable():
    """CONSTATS 5 + 7 — preuve que la branche haute n'est plus morte.

    MESURE d'origine : sur 40 titres balayés, ACHETER + RENFORCER = 0, non par
    prudence mais par construction (fondamental toujours inconnu + régime
    toujours UNKNOWN). Sur un dossier dont TOUTES les gardes réelles passent
    (paquet complet, R:R 2.3, régime calculable autorisant le risque neuf), la
    décision doit pouvoir atteindre ACHETER — sinon la doctrine n'est plus
    appliquée, elle est simplement inatteignable.
    """
    app = Flask(__name__)
    scan_state = {
        'source': 'ibkr_live',
        'detail': {'NVDA': {
            'score': 78, 'rr': 2.3, 'rs': 70, 'ext_atr': 1.0,
            'sub': {'fundamental': 72, 'fundamental_is_proxy': False},
            'data_quality': {'overall': 'FRESH', 'actionable_allowed': True},
            'reconciliation': {'actionable_allowed': True},
            'guard': {'blocking_rules': [], 'mandatory_reviews': []}}},
        'market': {'regime': 'TREND', 'vix': 15.0, 'breadth': 68, 'risk': 'Risk-On'},
    }
    app.register_blueprint(strategy_os_api.make_blueprint(scan_state=scan_state))
    data = app.test_client().get('/api/strategy/decision/NVDA').get_json()
    assert data['blocking_rules'] == []
    assert data['final_decision'] == 'ACHETER'


def test_catalyseur_n_invente_plus_de_note_60(client):
    """CONSTAT 41 — un 60 constant notait identiquement J-400 et J+9999.

    MESURE d'origine, par la vraie route : earnings_dte ∈ {20, -400, 9999}
    rendait tous `catalysts={'score': 60}` et `unknowns=[]`, contre
    `{'score': None}` / `unknowns=['catalysts']` quand le champ était absent.
    Le vrai dégât n'était pas le 60 mais qu'il RETIRE 'catalysts' de
    `unknowns` : l'application cessait d'avouer son ignorance dès qu'une date
    de résultats était mise en relation (le calendrier /cal-feed la sert déjà,
    réelle et datée). Le scanner écarte les titres à J-0/J-7 pour le risque de
    gap : une note plate aurait inversé un risque que le reste du code
    respecte.
    """
    data = client.get('/api/strategy/decision/NVDA').get_json()
    assert data['catalysts']['score'] is None
    assert 'catalysts' in data['unknowns']
    # L'échéance reste une métadonnée DESCRIPTIVE datée, jamais une note.
    assert data['catalysts']['earnings_dte'] == 20
    assert data['catalysts']['derived'] is True and data['catalysts']['warning']


def test_timing_non_mesure_est_nomme_pas_masque(client):
    """CONSTAT 5 (nuance) — le neutre 50.0 du timing passait pour une mesure.

    MESURE d'origine : `scores.timing = 50.0` était publié pour TOUS les titres
    alors que `st_timing`, la seule clé lue, n'a aucun producteur (0
    assignation, 2 lectures ; absente des 66 clés du detail d'un scan réel).
    Aucun seuil n'est déplacé — la substitution reste — mais l'absence est
    désormais NOMMÉE dans `unknowns` et dans l'audit, le canal d'ignorance déjà
    servi à l'utilisateur.
    """
    data = client.get('/api/strategy/decision/NVDA').get_json()
    assert data['technical']['timing_score'] is None
    assert data['technical']['timing_status'] == 'NON_IMPLEMENTE'
    assert 'timing' in data['unknowns']
    assert any('timing non mesuré' in line for line in data['audit_trail'])


def test_correlations_team_disent_leur_cause(client):
    """CONSTAT 28 — matrice de corrélations vide SANS cause nommée.

    MESURE d'origine : POST /api/portfolio/team avec 1 position PUIS avec 3
    (KO, AAPL, MSFT) rendait le MÊME
    {'average': None, 'pairs': {}, 'symbols_covered': []}. `symbols_covered`
    restait vide à 3 titres : la cause n'était donc pas « moins de deux
    titres » mais l'absence de `returns_by_symbol` dans le seul appelant de
    production (strategy_os_api). Le moteur fonctionne quand on le nourrit
    (mesuré : average 0.946 sur AAPL/KO). Une capacité non branchée doit être
    nommée NON_IMPLÉMENTÉ, jamais laissée passer pour une automatisation en
    attente (invariant 8).
    """
    r = client.post('/api/portfolio/team', json={
        'positions': [{'symbol': 'KO', 'quantity': 10, 'avg_cost': 60,
                       'last_price': 62, 'sector': 'Consumer'},
                      {'symbol': 'AAPL', 'quantity': 5, 'avg_cost': 180,
                       'last_price': 200, 'sector': 'Technology'},
                      {'symbol': 'MSFT', 'quantity': 3, 'avg_cost': 380,
                       'last_price': 400, 'sector': 'Technology'}],
        'cash': 1000, 'simulated': True})
    corr = r.get_json()['risk']['correlations']
    assert not corr.get('pairs')
    assert corr.get('available') is False
    assert 'NON_IMPLÉMENTÉ' in corr['reason']
    assert '/api/portfolio/context' in corr['reason']
