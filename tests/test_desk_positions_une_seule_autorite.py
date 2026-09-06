# -*- coding: utf-8 -*-
"""Le desk des positions et la route de décision rendent le MÊME verdict.

Mesure du 2026-09-06 (contrôle adverse du lot « positions/desk ») :
`recalculate_all` construisait son propre paquet de décision. Trois entrées
critiques y étaient des LITTÉRAUX — dont `reconciliation.actionable_allowed:
True`, une affirmation sans mesure. Or `scan_evidence.build_scan` pose sur
chaque titre le rapprochement réellement calculé.

Sur un `detail` dont le rapprochement INTERDIT d'agir, les deux surfaces se
contredisaient : le desk rendait « RENFORCER » sans règle bloquante, la route
canonique « ATTENDRE » avec `SOURCE_DISAGREEMENT`. Le desk franchissait donc
une garde dure sur des positions déclarées par l'utilisateur, en s'autorisant
lui-même. Tant que le régime dégradait en UNKNOWN, un `REGIME_BLOCKS_NEW_RISK`
fabriqué masquait le contournement ; en réparant le régime, la correction
précédente l'a rendu atteignable.

Aucun réseau, aucun compte, aucune donnée réelle : `scan_state` synthétique.
"""
import copy
import json

import pytest

from vertex.positions import recalculator
from vertex.strategy import decision_packet, executive_engine


def _scan_state(reconciliation: dict | None) -> dict:
    detail = {
        'score': 78, 'rs': 72, 'rr': 4.5, 'ext_atr': 1.1,
        'sub': {'fundamental': 72},
        'plan': {'rr': 4.5},
        'data_quality': {'overall': 'RECENT', 'actionable_allowed': True},
        'guard': {'blocking_rules': [], 'mandatory_reviews': []},
    }
    if reconciliation is not None:
        detail['reconciliation'] = reconciliation
    return {
        'source': 'ibkr',
        'market_ctx': {'spy_regime': 'TREND', 'vix': 15.0,
                       'breadth': {'above200': 68}, 'roro': 'RISK-ON'},
        'detail': {'AAPL': detail},
    }


def _desk(remaining_rr=None) -> dict:
    """Un desk DÉCLARÉ par l'utilisateur : une ligne AAPL, rien d'autre.

    Le portefeuille ne vient jamais d'une source externe (invariant 4) : ce
    banc passe donc par `desk_blob`, la seule entrée admise.
    """
    trade = {'sym': 'AAPL', 'type': 'STK', 'qty': 10, 'entry': 200.0,
             'date': '2026-08-01', 'status': 'OPEN'}
    if remaining_rr is not None:
        trade['remaining_rr'] = remaining_rr
    return {'data': {'myTrades': json.dumps([trade])}}


def _verdicts(reconciliation):
    """(verdict du desk, verdict de la route canonique) sur le MÊME état."""
    etat = _scan_state(reconciliation)
    sortie = recalculator.recalculate_all(copy.deepcopy(etat), _desk())
    assert sortie['decision_engine']['available'], sortie['decision_engine']['reason']
    desk = sortie['positions'][0]
    canonique = executive_engine.decide(
        decision_packet.build('AAPL', etat['detail']['AAPL'], etat))
    return desk, canonique


@pytest.mark.parametrize('reconciliation', [
    pytest.param({'available': True, 'actionable_allowed': True}, id='rapprochement-ok'),
    pytest.param({'available': True, 'actionable_allowed': False,
                  'issues': ['SPOT_VS_CHAIN_MISMATCH']}, id='rapprochement-en-desaccord'),
    pytest.param(None, id='rapprochement-absent'),
])
def test_les_deux_surfaces_portent_les_MEMES_regles_bloquantes(reconciliation):
    """Les gardes dures ne dépendent pas de la surface qui les interroge."""
    desk, canonique = _verdicts(reconciliation)
    assert sorted(desk['decision_blocking']) == sorted(canonique.get('blocking_rules') or []), (
        'le desk bloque sur %r et la route canonique sur %r pour le MÊME '
        'scan_state : deux autorités de décision, ce que la doctrine interdit'
        % (desk['decision_blocking'], canonique.get('blocking_rules')))


@pytest.mark.parametrize('reconciliation', [
    pytest.param({'available': True, 'actionable_allowed': True}, id='rapprochement-ok'),
    pytest.param({'available': True, 'actionable_allowed': False,
                  'issues': ['SPOT_VS_CHAIN_MISMATCH']}, id='rapprochement-en-desaccord'),
    pytest.param(None, id='rapprochement-absent'),
])
def test_les_deux_surfaces_attendent_ou_agissent_ENSEMBLE(reconciliation):
    """Le VERBE peut différer, la permission d'agir ne le peut pas.

    « RENFORCER » et « ACHETER » sont le même feu vert dit à deux publics :
    l'un tient déjà la ligne, l'autre non — c'est `position_held` qui les
    sépare, et c'est légitime. Ce qui ne l'est pas, c'est qu'une surface
    autorise pendant que l'autre fait attendre.
    """
    desk, canonique = _verdicts(reconciliation)
    attend_desk = desk['decision'] == 'ATTENDRE'
    attend_route = canonique['final_decision'] == 'ATTENDRE'
    assert attend_desk == attend_route, (
        'le desk rend %r et la route canonique %r : une surface autorise '
        'quand l’autre fait attendre'
        % (desk['decision'], canonique['final_decision']))


def test_un_rapprochement_en_desaccord_bloque_AUSSI_le_desk():
    """La garde dure ne doit pas s'ouvrir parce que la surface change."""
    desk, _ = _verdicts({'available': True, 'actionable_allowed': False,
                         'issues': ['SPOT_VS_CHAIN_MISMATCH']})
    assert 'SOURCE_DISAGREEMENT' in desk['decision_blocking'], desk['decision_blocking']
    assert desk['decision'] == 'ATTENDRE', desk['decision']


def test_un_rapprochement_absent_ne_vaut_pas_une_autorisation():
    """Une preuve manquante est une preuve manquante, jamais un feu vert."""
    desk, _ = _verdicts(None)
    assert decision_packet.INCOMPLETE_PACKET_RULE in desk['decision_blocking'], (
        'sans rapprochement mesuré, le paquet est INCOMPLET et doit le dire')


def test_le_desk_ne_reconstruit_plus_un_paquet_a_la_main():
    """Anti-régression de STRUCTURE : un seul constructeur de paquet."""
    import ast
    import inspect
    src = inspect.getsource(recalculator.recalculate_all)
    arbre = ast.parse(src.lstrip())
    litteraux = [n for n in ast.walk(arbre)
                 if isinstance(n, ast.Constant) and n.value in
                 ('reconciliation', 'data_quality')]
    assert not litteraux, (
        'recalculate_all nomme encore %r : les trois preuves critiques '
        'appartiennent à decision_packet.build, pas à ce module'
        % [n.value for n in litteraux])
    assert 'build(' in src, 'le desk doit appeler le constructeur canonique'


def test_la_position_apporte_ce_que_le_scan_ignore():
    """Le paquet canonique ne connaît pas le gain/risque RESTANT."""
    etat = _scan_state({'available': True, 'actionable_allowed': True})
    sortie = recalculator.recalculate_all(etat, _desk(remaining_rr=1.2))
    assert sortie['positions'], 'le desk déclaré n’a produit aucune position'
    assert sortie['positions'][0]['decision'] is not None
