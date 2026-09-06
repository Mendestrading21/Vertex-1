"""
tests/test_command_routes.py — Command Center en Blueprint (Ch. II).

Le régime final, la décision du jour, les alertes et le portefeuille sur
capital, testés sur un état de scan contrôlé. Lecture seule — la réponse ne
contient jamais d'ordre, seulement une analyse.
"""

import copy

import pytest
from flask import Flask

from vertex.app.routes import command
from vertex.app.state import scan_state


@pytest.fixture()
def client():
    app = Flask(__name__)
    app.register_blueprint(command.bp)
    saved = copy.deepcopy(scan_state)
    yield app.test_client()
    scan_state.clear()
    scan_state.update(saved)


def _set_market(roro='RISK-ON', regime='UP', vix=15):
    scan_state['market_ctx'] = {'roro': roro, 'spy_regime': regime, 'vix': vix,
                                'vix_band': 'calme', 'breadth': {'above50': 60}}


# ─── /api/command ───

def test_command_risk_off_goes_defensive(client):
    _set_market(roro='RISK-OFF')
    j = client.get('/api/command').get_json()
    assert 'RISK-OFF' in j['regime']['label']
    assert j['decision']['action'] == 'RÉDUIRE / DÉFENSIF'
    assert any(a[1] == 'RISK-OFF' for a in j['alerts'])


def test_command_chop_means_patience(client):
    _set_market(roro='RISK-ON', regime='CHOP')
    j = client.get('/api/command').get_json()
    assert j['regime']['label'].endswith('NEUTRE')
    assert j['decision']['action'] == 'RÉDUIRE / DÉFENSIF'
    assert any(a[1] == 'RANGE' for a in j['alerts'])


def test_command_high_vix_raises_alert(client):
    _set_market(vix=28)
    j = client.get('/api/command').get_json()
    assert any(a[1] == 'VOLATILITÉ' for a in j['alerts'])


def test_command_top_stocks_only_actionable(client):
    _set_market()
    scan_state['committee'] = {'decisions': [
        {'symbol': 'AAA', 'verdict': 'ACHETER', 'color': '#0f0', 'conviction': 80,
         'price': 10, 'note': 'ok', 'plan': {'rr': 2.5}},
        {'symbol': 'BBB', 'verdict': 'ÉVITER', 'color': '#f00', 'conviction': 20,
         'price': 5, 'note': 'non'},
    ], 'counts': {'ACHETER': 1}}
    j = client.get('/api/command').get_json()
    syms = [s['symbol'] for s in j['top_stocks']]
    assert syms == ['AAA']
    assert j['counts'] == {'ACHETER': 1}


def test_command_never_contains_orders(client):
    _set_market()
    j = client.get('/api/command').get_json()
    flat = str(j).lower()
    for forbidden in ('placeorder', 'order_id', 'submit_order'):
        assert forbidden not in flat


def test_command_exposes_unavailable_portfolio_controls_without_changing_decision(client, monkeypatch):
    _set_market()
    baseline = client.get('/api/command').get_json()['decision']

    def _unavailable(*args, **kwargs):
        raise RuntimeError('interne')

    monkeypatch.setattr(command.portfolio_risk, 'build', _unavailable)
    monkeypatch.setattr(command.validator, 'build', _unavailable)
    j = client.get('/api/command').get_json()
    assert j['decision'] == baseline
    assert j['risk'] is None and j['validation'] is None
    assert j['controls_availability'] == {
        'risk': {'available': False, 'status': 'PORTFOLIO_RISK_UNAVAILABLE',
                 'read_only': True, 'reason': 'contrôle de risque portefeuille indisponible'},
        'validation': {'available': False, 'status': 'PORTFOLIO_VALIDATION_UNAVAILABLE',
                       'read_only': True, 'reason': 'validation portefeuille indisponible'},
        'does_not_change_decision': True,
        'read_only': True,
    }


# ─── /api/portefeuille ───

def test_portefeuille_empty_without_rows(client):
    """Sans ligne de scan, la route ne CONSTRUIT rien — et le dit.

    Ce banc épinglait `== {}`, c'est-à-dire exactement le défaut : une charge
    vide dont personne ne peut dire si le portefeuille est vide ou si le calcul
    n'a pas tourné. Mesuré le 2026-09-06 en exerçant les 184 règles du runtime.
    Ce qui doit rester vrai, c'est qu'AUCUNE ligne de portefeuille n'est
    fabriquée ; ce qui change, c'est que l'absence est nommée.
    """
    scan_state['rows'] = []
    charge = client.get('/api/portefeuille').get_json()
    assert charge.get('disponible') is False, charge
    assert 'motif' in charge and len(charge['motif']) > 30, charge
    assert charge.get('read_only') is True
    #  Le capital demandé revient : l'appelant sait que sa requête a été lue.
    assert isinstance(charge.get('capital'), int), charge
    #  Et surtout : rien n'est construit.
    for interdit in ('positions', 'lignes', 'allocation', 'total'):
        assert interdit not in charge, (interdit, charge)


def test_le_double_de_build_portfolio_SUIT_la_vraie_signature():
    """Un double qui ne suit plus la signature reelle transforme un changement
    d'API en reponse vide : la route attrape `Exception` et rend `{}`. Le banc
    d'a cote echouait alors sur un `KeyError`, sans dire pourquoi.

    Ce temoin fait echouer le double AVANT, et avec le bon message.
    """
    import inspect
    from vertex.strategy import legacy_adapter
    attendus = set(inspect.signature(legacy_adapter.build_portfolio).parameters)
    assert 'board' in attendus


def test_portefeuille_capital_is_clamped(client, monkeypatch):
    scan_state['rows'] = [{'symbol': 'AAA'}]
    seen = {}

    #  `**extra` : la route passe desormais `board=` (D-107). Sans lui, l'appel
    #  levait, et le `except Exception` de la route rendait `{}` — le banc
    #  echouait sur un KeyError au lieu de dire ce qui s'etait passe. Le double
    #  doit suivre la signature reelle, et le banc suivant l'y oblige.
    def fake_build(rows, detail, market=None, capital=None, **extra):
        seen['capital'] = capital
        seen['extra'] = extra
        return {'capital': capital}
    monkeypatch.setattr(command.strategy, 'build_portfolio', fake_build)
    client.get('/api/portefeuille?capital=999999999')
    assert seen['capital'] == command.CAPITAL_MAX
    assert 'board' in seen['extra'], 'la route doit passer le board (D-107)'
    client.get('/api/portefeuille?capital=12')
    assert seen['capital'] == command.CAPITAL_MIN
    client.get('/api/portefeuille?capital=pas-un-nombre')
    assert seen['capital'] == command.CAPITAL_DEFAULT


def test_portefeuille_engine_error_is_reported(client, monkeypatch):
    scan_state['rows'] = [{'symbol': 'AAA'}]

    def boom(*a, **k):
        raise ValueError('cassé')
    monkeypatch.setattr(command.strategy, 'build_portfolio', boom)
    j = client.get('/api/portefeuille').get_json()
    assert j['error'] == 'portfolio_analysis_unavailable'


# ─── Intégration monolithe ───

def test_terminal_registers_command_blueprint():
    import terminal
    rules = {r.rule for r in terminal.app.url_map.iter_rules()}
    assert '/api/command' in rules and '/api/portefeuille' in rules


# ─── Le drapeau STRUCTUREL du panier, et la couverture du score ───

def _detail_synthetique(symbols):
    """Séries synthétiques déterministes (aucun réseau) : même amplitude et
    même fréquence pour toutes les lignes — donc des poids inverse-vol égaux,
    donc un drapeau STRUCTUREL et rien d'autre. Seule la phase change (120°),
    ce qui écarte la corrélation du seuil."""
    import math
    return {s: {'series': {'close': [100 + 5 * math.sin(x / 4.0 + i * 2.09) + x * 0.1
                                     for x in range(60)]},
                'sector': ''}
            for i, s in enumerate(symbols)}


def test_le_drapeau_structurel_du_panier_est_DIT_sans_devenir_un_blocage(client):
    """MESURE DU 2026-09-06 — la route n'ouvrait les alertes de risque que
    derrière `risk['no_new_risk']`.

    Or le moteur a séparé deux familles : `no_new_risk` ne suit plus que les
    drapeaux BLOQUANTS (corrélation, concentration sectorielle), tandis que
    `ligne_trop_grosse` est ARITHMÉTIQUE — avec un plafond de 15 % par ligne,
    trois lignes valent 33,3 % chacune. Résultat servi avant correctif, mesuré
    sur ce même panier : `flags == ['ligne_trop_grosse']`, `max_weight == 33.3`,
    `limits.max_pos == 15`, et `alerts == []` — le seul drapeau armé du panier
    n'atteignait plus aucun écran.

    Il est DIT, pas transformé en blocage : pastille distincte de celles du
    risque, texte qui nomme l'arithmétique, et la décision du jour ne change
    pas (ajouter une ligne est le remède, pas la faute).
    """
    _set_market()
    syms = ['NVDA', 'JPM', 'XOM']
    scan_state['committee'] = {'decisions': [], 'counts': {}}
    scan_state['rows'] = [{'symbol': s} for s in syms]
    scan_state['detail'] = _detail_synthetique(syms)
    j = client.get('/api/command').get_json()
    assert j['risk']['flags_structurels'] == ['ligne_trop_grosse']
    assert j['risk']['flags_bloquants'] == [] and j['risk']['no_new_risk'] is False
    a = next((a for a in j['alerts'] if a[1] == 'RÉPARTITION'), None)
    assert a is not None, ('le seul drapeau armé du panier ne produit aucune '
                           'ligne à l’écran : %s' % j['alerts'])
    assert '33.3 %' in a[2] and '15 %' in a[2], a[2]
    assert "n'interdit pas d'ajouter" in a[2], a[2]
    assert a[0] != '🔴', 'un fait arithmétique n’est pas une alerte rouge'
    #  Pas de blocage : la décision du jour est celle du marché, pas du panier.
    assert j['decision']['action'] != 'RÉDUIRE / DÉFENSIF'


def test_une_concentration_subie_reste_bloquante_et_le_dit(client):
    """La garde réelle n'est pas desserrée par le correctif ci-dessus : deux
    titres sur trois dans le même secteur arment `no_new_risk` et gardent leur
    alerte, avec la pastille du risque."""
    _set_market()
    syms = ['NVDA', 'AMD', 'XOM']          # deux Semiconducteurs sur trois
    scan_state['committee'] = {'decisions': [], 'counts': {}}
    scan_state['rows'] = [{'symbol': s} for s in syms]
    scan_state['detail'] = _detail_synthetique(syms)
    j = client.get('/api/command').get_json()
    assert 'concentration_sectorielle' in j['risk']['flags_bloquants']
    assert j['risk']['no_new_risk'] is True
    assert any(a[1] == 'CONCENTRATION' and a[0] == '🟠' for a in j['alerts'])


def test_le_score_de_marche_declare_quand_sa_largeur_n_est_pas_mesuree(client):
    """MESURE DU 2026-09-06 — la route ne lisait que `climate()['score']`.

    `market_lens.climate` substitue 50 % à une largeur ABSENTE (la composante
    participation pèse 25 points sur 100) et pose alors `partiel`,
    `breadth_status` et `note` dans le MÊME dictionnaire. La route les jetait :
    une largeur mesurée à 50 % et une largeur absente servaient le même score,
    au bit près, sans qu'aucun champ ne distingue la mesure de la substitution.

    Ce banc mesure les deux états côte à côte : même nombre, déclaration
    différente. La forme nominale ne change pas — les marqueurs n'existent que
    dans le cas dégradé.
    """
    scan_state['market_ctx'] = {'roro': 'RISK-ON', 'spy_regime': 'TREND',
                                'vix': 15, 'vix_band': 'calme', 'breadth': {}}
    absente = client.get('/api/command').get_json()
    scan_state['market_ctx'] = {'roro': 'RISK-ON', 'spy_regime': 'TREND',
                                'vix': 15, 'vix_band': 'calme',
                                'breadth': {'above50': 50}}
    mesuree = client.get('/api/command').get_json()
    assert absente['regime']['score'] == mesuree['regime']['score'], (
        'la substitution rend bien le même nombre : c’est pourquoi elle doit '
        'être DÉCLARÉE')
    assert absente['regime']['score_partiel'] is True
    assert absente['regime']['breadth_status'] == 'MISSING'
    assert 'participation' in absente['regime']['score_note']
    assert absente['decision']['score_partiel'] is True
    assert 'PARTIEL' in absente['decision']['msg']
    assert 'score_partiel' not in mesuree['regime'], 'forme nominale inchangée'
    assert 'score_partiel' not in mesuree['decision']
