# -*- coding: utf-8 -*-
"""Le contrôle croisé broker/modèle DIT quand il n'a pas tourné.

Mesure du 2026-09-06, balayage des lectures et des écritures du dépôt :
`broker_delta` et `model_delta` ne sont écrits nulle part en production — seul
un banc les fabrique. Le producteur réel (`positions.recalculator`) construit
`{'source': 'BROKER_GREEKS', 'delta', 'gamma', 'theta', 'vega'}`, c'est-à-dire
UN seul jeu de Greeks. `BROKER_MODEL_GREEK_DIVERGENCE` n'a donc jamais pu
s'allumer.

Le défaut n'est pas un chiffre faux : c'est qu'une garde muette se lit comme
une garde satisfaite. Un desk qui n'affiche aucune divergence laisse croire que
courtier et modèle sont d'accord, alors que personne n'a comparé.

Aucun réseau : position et cotation synthétiques.
"""
from vertex.positions import calculator


def _position():
    return {'symbol': 'NVDA', 'asset_type': 'OPTION', 'right': 'CALL',
            'quantity': 2, 'multiplier': 100.0, 'strike': 200.0,
            'expiration': '2026-12-18', 'average_cost': 5.0,
            'cost_basis': 1000.0, 'data_quality': {}}


def _cote():
    return {'mark': 6.0, 'bid': 5.9, 'ask': 6.1, 'iv': 0.35, 'source': 'IBKR'}


def test_un_seul_jeu_de_greeks_declare_le_controle_NON_EXECUTE():
    p = _position()
    calculator.enrich_option(p, _cote(), None,
                             {'source': 'BROKER_GREEKS', 'delta': 0.55,
                              'gamma': 0.01, 'theta': -0.05, 'vega': 0.2}, None)
    d = p['data_quality']['divergence_greeks']
    assert d['evaluee'] is False
    assert set(d['manquants']) == {'broker_delta', 'model_delta'}
    assert 'BROKER_GREEKS' in d['motif']
    assert 'BROKER_MODEL_GREEK_DIVERGENCE' not in p['data_quality'].get('issues', [])


def test_deux_jeux_servis_font_reprendre_la_comparaison():
    """Contre-épreuve : la garde n'est pas désactivée, elle est en attente."""
    p = _position()
    calculator.enrich_option(p, _cote(), None,
                             {'source': 'BROKER_GREEKS', 'delta': 0.55,
                              'gamma': 0.01, 'theta': -0.05, 'vega': 0.2,
                              'broker_delta': 0.50, 'model_delta': 0.65}, None)
    d = p['data_quality']['divergence_greeks']
    assert d['evaluee'] is True
    assert d['ecart_delta'] == 0.15 and d['seuil'] == 0.12
    assert 'BROKER_MODEL_GREEK_DIVERGENCE' in p['data_quality']['issues']


def test_un_ecart_sous_le_seuil_est_evalue_sans_alerter():
    p = _position()
    calculator.enrich_option(p, _cote(), None,
                             {'source': 'BROKER_GREEKS', 'delta': 0.55,
                              'broker_delta': 0.50, 'model_delta': 0.55}, None)
    d = p['data_quality']['divergence_greeks']
    assert d['evaluee'] is True and d['ecart_delta'] == 0.05
    assert 'BROKER_MODEL_GREEK_DIVERGENCE' not in p['data_quality'].get('issues', [])


def test_l_absence_d_un_SEUL_des_deux_est_nommee():
    p = _position()
    calculator.enrich_option(p, _cote(), None,
                             {'source': 'BROKER_GREEKS', 'broker_delta': 0.50}, None)
    d = p['data_quality']['divergence_greeks']
    assert d['evaluee'] is False and d['manquants'] == ['model_delta']
