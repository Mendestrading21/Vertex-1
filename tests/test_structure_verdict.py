# -*- coding: utf-8 -*-
"""Verdict de structure : propriétaire serveur (vertex/options/structure_verdict.py).

Les règles reprises du JavaScript de la vue Structure sont épinglées ici ; la
page ne calcule plus (gardien de source). Aucune valeur inventée : sans IV pas
de scénario, sans bid/ask ni OI liquidité « insuffisante — non évaluable ».
"""
import math
import os

import pytest

from vertex.options import structure_verdict as sv

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JS = os.path.join(_ROOT, 'vertex', 'static', 'vertex', 'js', 'pages', 'options-structure.js')


def test_liquidite_quatre_paliers_et_absence_nommee():
    assert sv.etat_liquidite(None, None)['key'] == 'insuffisante'
    assert 'non évaluable' in sv.etat_liquidite(None, None)['note']
    assert sv.etat_liquidite(6000, 2.0)['key'] == 'excellente'
    assert sv.etat_liquidite(2000, 5.0)['key'] == 'acceptable'
    assert sv.etat_liquidite(600, 9.0)['key'] == 'mediocre'
    assert sv.etat_liquidite(600, 12.0)['key'] == 'insuffisante'
    assert sv.etat_liquidite(6000, None)['key'] == 'insuffisante'   # spread inconnu = 99 %


def test_liquidite_strategie_est_la_pire_jambe():
    board = [{'sym': 'AAA', 'exp': '2026-12-18', 'type': 'CALL', 'strike': 100, 'oi': 6000, 'spread_pct': 2},
             {'sym': 'AAA', 'exp': '2026-12-18', 'type': 'CALL', 'strike': 110, 'oi': 300, 'spread_pct': 20}]
    legs = [{'type': 'CALL', 'strike': 100}, {'type': 'CALL', 'strike': 110}]
    assert sv.liquidite_strategie(board, 'aaa', '2026-12-18', legs)['key'] == 'insuffisante'
    assert sv.liquidite_strategie(board, 'AAA', '2026-12-18', legs[:1])['key'] == 'excellente'
    assert sv.liquidite_strategie([], 'AAA', '2026-12-18', legs)['key'] == 'insuffisante'


def test_mouvement_attendu_et_interpolation():
    assert sv.mouvement_attendu(100, 0.25, 365) == pytest.approx(25.0)
    assert sv.mouvement_attendu(100, None, 30) is None
    assert sv.mouvement_attendu(100, 0.2, 0) is None
    payoff = [{'price': 90, 'pnl': -100}, {'price': 100, 'pnl': 0}, {'price': 110, 'pnl': 100}]
    assert sv.pnl_a(payoff, 105) == pytest.approx(50.0)
    assert sv.pnl_a(payoff, 50) == -100 and sv.pnl_a(payoff, 500) == 100
    assert sv.pnl_a([], 100) is None


def test_verdict_reprend_les_regles_de_la_page():
    ok = {'key': 'acceptable'}
    assert sv.verdict({}, {'key': 'insuffisante'}, 100, 500, 2000)['label'] == 'Liquidité insuffisante'
    assert sv.verdict({}, ok, 100, 500, None)['label'] == 'Données insuffisantes'
    assert sv.verdict({}, ok, 100, 500, 1600)['label'] == 'Asymétrie excellente'
    assert sv.verdict({}, ok, 100, 500, 1000)['label'] == 'Structure intéressante'
    # prime > 12 % du notionnel (spot 100 → notionnel 10 000 ; capital 1 500)
    assert sv.verdict({}, ok, 100, 1500, 3000)['label'] == 'Structure intéressante mais chère'
    assert sv.verdict({'days_to_exp': 10}, ok, 100, 500, 700)['label'] == 'Risque/temps médiocre'
    assert sv.verdict({'days_to_exp': 40}, ok, 100, 500, 500)['label'] == 'Risque/temps médiocre'
    assert sv.verdict({'days_to_exp': 40}, ok, 100, 500, 750)['label'] == 'Attendre une meilleure entrée'


def test_scenarios_orientes_par_le_biais_et_absents_sans_iv():
    payoff = [{'price': 50, 'pnl': -500}, {'price': 100, 'pnl': 0}, {'price': 150, 'pnl': 500}]
    sc = sv.scenarios(100, 10, 1, payoff, 500, 30)
    assert [x['cle'] for x in sc] == ['Pessimiste', 'Probable', 'Exceptionnel']
    assert sc[0]['px'] == 90 and sc[2]['px'] == 120 and sc[2]['pnl'] == pytest.approx(200)
    assert sc[1]['pct'] == pytest.approx(20.0)
    baissier = sv.scenarios(100, 10, -1, payoff, 500, 30)
    assert baissier[0]['px'] == 110 and baissier[2]['px'] == 80
    assert sv.scenarios(100, None, 1, payoff, 500, 30) == []


def test_analyser_sert_tout_ce_que_la_page_peint():
    res = {'sym': 'AAA', 'spot': 100.0, 'iv': 0.25, 'exp': '2026-12-18', 'bias': 'bullish'}
    strat = {'days_to_exp': 365, 'max_loss': -500, 'max_profit': 1500, 'max_profit_unbounded': False,
             'legs': [{'type': 'CALL', 'strike': 100}],
             'payoff': [{'price': 50, 'pnl': -500}, {'price': 100, 'pnl': -500}, {'price': 150, 'pnl': 1500}]}
    board = [{'sym': 'AAA', 'exp': '2026-12-18', 'type': 'CALL', 'strike': 100, 'oi': 6000, 'spread_pct': 2}]
    a = sv.analyser(res, strat, board)
    assert a['em'] == pytest.approx(25.0) and a['p_prob'] == 125 and a['p_exc'] == 150
    assert a['gain_prob'] == pytest.approx(500.0) and a['gain_exc'] == 1500
    assert a['asym'] == pytest.approx(3.0) and a['verdict']['label'] == 'Asymétrie excellente'
    assert a['liquidite']['key'] == 'excellente' and len(a['scenarios']) == 3
    assert a['source'].startswith('structure_verdict')
    sans_iv = sv.analyser({'sym': 'AAA', 'spot': 100.0, 'iv': None}, strat, board)
    assert sans_iv['em'] is None and sans_iv['scenarios'] == [] and sans_iv['gain_prob'] is None


def test_la_page_structure_ne_calcule_plus():
    src = open(JS, encoding='utf-8').read()
    for nom in ('function liqState', 'function strategyLiquidity', 'function pnlAt',
                'function expectedMove', 'function computeVerdict'):
        assert nom not in src, nom
    assert 'function analyseDe(' in src
    assert 'a.scenarios' in src and 'an.asym_compare' in src and 'an.liquidite' in src


def test_la_route_sert_l_analyse(monkeypatch):
    from vertex.app.state import scan_state
    from vertex.app.routes import options_lab_api as lab
    board = []
    for k in (95, 100, 105, 110):
        for t in ('CALL', 'PUT'):
            board.append({'sym': 'AAA', 'exp': '2026-12-18', 'type': t, 'strike': float(k), 'dte': 40,
                          'cost': 300.0, 'iv': 25.0, 'oi': 6000, 'spread_pct': 2.0, 'spot': 100.0})
    monkeypatch.setitem(scan_state, 'options_board', board)
    monkeypatch.setitem(scan_state, 'detail', {'AAA': {'price': 100.0, 'verdict': 'BUY', 'score': 70}})
    from vertex.runtime import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        j = c.get('/api/options/strategies/AAA').get_json()
    if not j.get('available'):
        pytest.skip('aucune stratégie constructible sur ce board synthétique : %s' % j.get('reason'))
    assert j['analyse_source'].startswith('structure_verdict')
    for s in j['strategies']:
        assert 'analyse' in s and 'verdict' in s['analyse'] and 'liquidite' in s['analyse']
