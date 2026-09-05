# -*- coding: utf-8 -*-
"""Risque du panier = positions DÉCLARÉES (docs/VERTEX_DATA_COVERAGE.md §13 #7).

Avant : Portefeuille › Dépendances cachées lisait `GET /api/risk` et
Opportunités › Risque du panier lisait `/api/command.risk` — tous deux
mesuraient le panier du COMITÉ (top convictions du scan) et l'affichaient sous
« Mon portefeuille ».

Après : `POST /api/risk {symbols}` mesure les symboles envoyés explicitement
par la page (portefeuille déclaré, jamais lu chez un courtier), dit quel
panier il mesure, nomme les titres non mesurables et date sa réponse.

Tests sans réseau : le scan est simulé en mémoire (séries synthétiques).
"""
import math
import os

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _src(*parts):
    with open(os.path.join(_ROOT, *parts), encoding='utf-8') as f:
        return f.read()


@pytest.fixture
def client():
    from vertex.runtime import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


@pytest.fixture
def scan_synthetique():
    """Trois titres avec 60 clôtures synthétiques (deux corrélés, un hors scan)."""
    from vertex.app.state import scan_state
    sauv = {k: scan_state.get(k) for k in ('rows', 'detail', 'scan_ts_h', 'updated')}
    serie_a = [100 + 5 * math.sin(i / 4.0) + i * 0.1 for i in range(60)]
    serie_b = [50 + 2.5 * math.sin(i / 4.0) + i * 0.05 for i in range(60)]
    serie_c = [20 + 3 * math.cos(i / 7.0) for i in range(60)]
    scan_state['rows'] = [{'symbol': s} for s in ('AAA', 'BBB', 'CCC')]
    scan_state['detail'] = {
        'AAA': {'series': {'close': serie_a}, 'sector': 'Technology'},
        'BBB': {'series': {'close': serie_b}, 'sector': 'Technology'},
        'CCC': {'series': {'close': serie_c}, 'sector': 'Energy'},
    }
    scan_state['scan_ts_h'] = '2026-09-06T01:00:00Z'
    yield
    for k, v in sauv.items():
        scan_state[k] = v


def test_post_mesure_les_symboles_declares(client, scan_synthetique):
    j = client.post('/api/risk', json={'symbols': ['aaa', 'BBB', 'ZZZ', 'AAA']}).get_json()
    assert j['panier'] == 'declare'
    assert j['demandes'] == ['AAA', 'BBB', 'ZZZ']          # dédoublonné, canonique
    assert set(j['symbols']) == {'AAA', 'BBB'}
    assert j['non_mesures'] == ['ZZZ']                      # hors scan : dit, jamais compté
    assert j['as_of'] == '2026-09-06T01:00:00Z'
    assert j['n'] == 2


def test_post_sans_position_ne_mesure_rien(client, scan_synthetique):
    j = client.post('/api/risk', json={'symbols': []}).get_json()
    assert j['panier'] == 'declare' and j['n'] == 0
    assert 'aucune position' in j['note']
    assert j['flags'] == [] and j['no_new_risk'] is False


def test_post_un_seul_titre_mesurable_est_une_absence_de_mesure(client, scan_synthetique):
    j = client.post('/api/risk', json={'symbols': ['AAA', 'ZZZ']}).get_json()
    assert j['n'] == 1 and 'trop petit' in j['note']
    assert j['non_mesures'] == ['ZZZ']


def test_post_refuse_les_symboles_invalides(client, scan_synthetique):
    j = client.post('/api/risk', json={'symbols': ['<script>', 'AAA;DROP', 'BBB']}).get_json()
    assert j['demandes'] == ['BBB']


def test_get_reste_le_panier_du_comite(client, scan_synthetique):
    j = client.get('/api/risk').get_json()
    assert j['panier'] == 'comite'
    assert 'non_mesures' not in j


def test_portefeuille_envoie_ses_positions_declarees():
    src = _src('vertex', 'ui', 'pages', 'portfolio_page.py')
    assert "VX.fetch('/api/risk'" not in src, 'le GET (panier du comité) ne doit plus servir le portefeuille'
    assert "fetch('/api/risk',{method:'POST'" in src
    assert 'function pfSymbolesDeclares(' in src
    assert 'VXEntities.positions()' in src
    assert 'non_mesures' in src


def test_opportunites_n_affiche_plus_le_panier_du_comite_comme_portefeuille():
    src = _src('vertex', 'ui', 'pages', 'opportunities_page.py')
    assert "const rk=(cmd&&cmd.risk)||null;" not in src
    assert "fetch('/api/risk',{method:'POST'" in src
    assert 'positions déclarées' in src
    assert 'non_mesures' in src
