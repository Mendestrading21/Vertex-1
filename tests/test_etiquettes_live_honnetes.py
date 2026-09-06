# -*- coding: utf-8 -*-
"""tests/test_etiquettes_live_honnetes.py — « live » n'est écrit que sur preuve.

Mesuré (inventaire 2026-09-06) : `/api/pos-quotes` répondait `live: true` dès
que IBKR était CONFIGURÉ (`bool(ibkr_enabled)`), même quand toutes les marques
venaient du repli « clôture du scan » ; `live_engine.mode()` disait « live »
sur le même drapeau ; le Simulateur envoyait `iv: 0.25` codé en dur pour une
position en actions et affichait une probabilité de gain et des sensibilités
fabriquées sur cette constante.

Ces gardiens sont nés ROUGES sur `main` (ed363d67).
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _lire(*parts):
    return (ROOT / Path(*parts)).read_text(encoding='utf-8')


def test_pos_quotes_ne_dit_live_que_sur_preuve_de_socket():
    src = _lire('vertex', 'app', 'routes', 'desk.py')
    assert "'live': bool(ibkr_enabled)," not in src, 'live = configuration : étiquette non fondée'
    assert "_etat_scan.get('ibkr_live')" in src, 'live doit lire la preuve ibkr_live posée par ibkr_state.sync'
    assert "'ibkr_configure': bool(ibkr_enabled)" in src, 'la configuration reste dite, séparément'


def test_le_simulateur_n_invente_plus_de_volatilite():
    src = _lire('vertex', 'static', 'vertex', 'js', 'pages', 'simulator.js')
    assert 'iv: 0.25' not in src, 'une IV constante fabriquait PoP et Greeks'
    assert 'iv: null' in src
    assert 'non calculable sans volatilité implicite cotée' in src


def test_le_moteur_multi_jambes_refuse_pop_et_greeks_sans_iv():
    from vertex.engines import multileg_lab
    res = multileg_lab.analyze_strategy(
        [{'type': 'stock', 'strike': 0, 'premium': 100.0, 'qty': 10}],
        100.0, None, 90, r=0.04, q=0.0, name='test')
    assert res.get('available'), res
    assert res.get('probability_of_profit') is None, 'PoP sans IV = absence, pas un chiffre'
    assert res.get('greeks') is None, 'Greeks sans IV = absence'
    assert res.get('payoff'), 'le payoff, lui, ne dépend pas de l’IV'


def test_le_mode_global_live_exige_la_preuve():
    src = _lire('vertex', 'services', 'live_engine.py')
    assert "return 'live' if _CFG['ibkr_enabled'] else 'delayed'" not in src
    assert "st.get('ibkr_live')" in src
