# -*- coding: utf-8 -*-
"""Aucun réseau lent dans une requête utilisateur (§13 #8, partie 1).

- `/api/analyst/<sym>` servait yfinance DANS la requête à chaque cache manquant
  ou périmé (12 h). Il sert désormais le cache tel quel (`etat` CACHE / PERIME
  + `stale`) et lance la collecte EN FOND (`etat` EN_COURS + `retry_s`), une
  seule collecte par symbole à la fois.
- `/api/pos-quotes` attendait jusqu'à 12 s la file IBKR pour une clé jamais
  cotée. La requête n'attend plus que `POSQ_ATTENTE_S` ; au-delà, le repli
  étiqueté est servi, `en_attente` nomme les clés en cours et le cache est
  rempli par le worker pour le passage suivant.

Tests sans réseau : sources simulées par monkeypatch, temps mesuré.
"""
import os
import threading
import time

import pytest
from flask import Flask

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _src(*parts):
    with open(os.path.join(_ROOT, *parts), encoding='utf-8') as f:
        return f.read()


# ── /api/analyst ───────────────────────────────────────────────────────────

@pytest.fixture
def analyste(monkeypatch):
    from vertex.app.routes import company_api
    from vertex.data_sources import analyst_deep
    monkeypatch.setattr(company_api, 'DEMO_MODE', False)
    monkeypatch.setattr(company_api, '_ANALYST_EN_COURS', {})
    appels = []
    fini = threading.Event()

    def faux_get(sym, ttl=None, force=False):
        appels.append(sym)
        fini.set()
        return {'_ts': time.time(), 'growth_fwd': 1.0}
    monkeypatch.setattr(analyst_deep, 'get', faux_get)
    app = Flask(__name__)
    app.register_blueprint(company_api.bp)
    return app.test_client(), appels, fini, analyst_deep


def test_cache_absent_repond_en_cours_et_collecte_en_fond(analyste, monkeypatch):
    c, appels, fini, ad = analyste
    monkeypatch.setattr(ad, 'depuis_cache', lambda sym, ttl=None: (None, False))
    t0 = time.time()
    j = c.get('/api/analyst/AAPL').get_json()
    assert time.time() - t0 < 1.0, 'la requête a attendu la collecte'
    assert j['available'] is False and j['etat'] == 'EN_COURS' and j['retry_s'] > 0
    assert fini.wait(3), 'la collecte de fond ne s’est pas lancée'
    assert appels == ['AAPL']


def test_une_seule_collecte_par_symbole_a_la_fois(analyste, monkeypatch):
    c, appels, fini, ad = analyste
    monkeypatch.setattr(ad, 'depuis_cache', lambda sym, ttl=None: (None, False))
    from vertex.app.routes import company_api
    # simule une collecte encore en cours
    company_api._ANALYST_EN_COURS['MSFT'] = time.time()
    c.get('/api/analyst/MSFT')
    c.get('/api/analyst/MSFT')
    time.sleep(0.2)
    assert appels == [], 'une deuxième collecte a été lancée pendant la première'


def test_cache_frais_servi_sans_collecte(analyste, monkeypatch):
    c, appels, fini, ad = analyste
    monkeypatch.setattr(ad, 'depuis_cache',
                        lambda sym, ttl=None: ({'_ts': time.time(), 'growth_fwd': 2.5}, True))
    j = c.get('/api/analyst/NVDA').get_json()
    assert j['etat'] == 'CACHE' and j['growth_fwd'] == 2.5 and 'stale' not in j
    time.sleep(0.2)
    assert appels == []


def test_cache_perime_servi_etiquete_et_rafraichi_en_fond(analyste, monkeypatch):
    c, appels, fini, ad = analyste
    monkeypatch.setattr(ad, 'depuis_cache',
                        lambda sym, ttl=None: ({'_ts': 1.0, 'growth_fwd': 3.0}, False))
    j = c.get('/api/analyst/AMD').get_json()
    assert j['etat'] == 'PERIME' and j['stale'] is True and j['growth_fwd'] == 3.0
    assert 'périmées' in j['note']
    assert fini.wait(3) and appels == ['AMD']


def test_depuis_cache_ne_touche_pas_le_reseau(tmp_path, monkeypatch):
    from vertex.data_sources import analyst_deep as ad
    monkeypatch.setattr(ad, 'CACHE_PATH', str(tmp_path / 'analyst_cache.json'))
    import sys
    monkeypatch.setitem(sys.modules, 'yfinance', None)   # tout import lèverait
    ent, frais = ad.depuis_cache('AAPL')
    assert ent is None and frais is False


def test_la_fiche_reessaie_quand_la_collecte_est_en_cours():
    src = _src('vertex', 'ui', 'pages', 'analysis_page.py')
    assert "a.etat==='EN_COURS'" in src
    assert 'loadAnalyst(essai+1)' in src
    assert 'if(essai<3)' in src, 'le réessai doit être borné'
    assert "ttl:essai?0:600000" in src, 'le réessai doit contourner le cache client'
    assert 'a.stale' in src


# ── /api/pos-quotes ────────────────────────────────────────────────────────

def _client_desk(opt_job, ibkr=True):
    from vertex.app.routes import desk
    app = Flask(__name__)
    app.register_blueprint(desk.make_blueprint(opt_job=opt_job, ibkr_enabled=ibkr))
    return app.test_client()


def test_pos_quotes_n_attend_plus_la_file_ibkr(monkeypatch):
    from vertex.app.state import scan_state
    from vertex.app.routes import desk
    monkeypatch.setitem(scan_state, 'detail', {})
    monkeypatch.setitem(scan_state, 'options_board', [])
    monkeypatch.setattr(desk, 'POSQ_ATTENTE_S', 0.2)
    rendu = threading.Event()

    def job_lent(kind, args, timeout):
        if kind != 'posq':                   # résolution d'échéance : immédiate
            return {}
        time.sleep(0.8)                      # file IBKR chargée
        rendu.set()
        return {p['key']: {'px': 9.9} for p in args[0]}
    c = _client_desk(job_lent)
    body = {'positions': [{'sym': 'AAPL', 'exp': '2026-12', 'strike': 200, 'right': 'C'}]}
    t0 = time.time()
    j = c.post('/api/pos-quotes', json=body).get_json()
    assert time.time() - t0 < 0.7, 'la requête a attendu le worker'
    key = 'AAPL|2026-12|200|C'
    assert j['results'] == {} and j['en_attente'] == [key]
    assert rendu.wait(3), 'le worker de fond n’a pas terminé'
    time.sleep(0.05)
    j2 = c.post('/api/pos-quotes', json=body).get_json()
    assert j2['results'][key] == {'px': 9.9} and j2['en_attente'] == []


def test_pos_quotes_rapide_reste_synchrone():
    #  `timeout` est passé par MOT-CLÉ par la route : la doublure le nomme.
    c = _client_desk(lambda kind, args, timeout: {p['key']: {'px': 1.0} for p in args[0]})
    j = c.post('/api/pos-quotes', json={'positions': [{'sym': 'MSFT'}]}).get_json()
    assert j['results']['MSFT|||'] == {'px': 1.0} and j['en_attente'] == []


def test_la_marque_de_contrat_ne_tire_pas_la_chaine_dans_la_requete(monkeypatch):
    """`contract_mark(..., reseau=False)` sert le cache (même périmé) et lance la
    lecture en fond ; le repli de /api/pos-quotes l'appelle ainsi."""
    from vertex.options import on_demand as od
    from vertex.app.state import scan_state
    monkeypatch.setitem(scan_state, 'options_mark_cache', {})
    monkeypatch.setattr(od, '_MARQUES_EN_COURS', {})
    lus = []
    fini = threading.Event()

    class _Tk:
        def __init__(self, sym):
            lus.append(sym)
            fini.set()
        options = ()
    monkeypatch.setattr(od.legacy_engine, 'yf', type('Y', (), {'Ticker': _Tk}))
    t0 = time.time()
    assert od.contract_mark('AAPL', '2026-12', 200, 'C', reseau=False) is None
    assert time.time() - t0 < 0.3
    assert fini.wait(3) and lus == ['AAPL'], 'la lecture de fond ne s’est pas lancée'
    # cache périmé → servi tel quel, relecture en fond dédoublonnée
    scan_state['options_mark_cache']['AAPL|2026-12|200.0|C'] = {'ts': 1.0, 'mark': 4.2}
    od._MARQUES_EN_COURS['AAPL|2026-12|200.0|C'] = time.time()
    assert od.contract_mark('AAPL', '2026-12', 200, 'C', reseau=False) == 4.2
    time.sleep(0.1)
    assert lus == ['AAPL']
    src = _src('vertex', 'app', 'routes', 'desk.py')
    assert 'reseau=False' in src


# ── Chaîne d'options : magasin non bloquant, jamais dans la requête ─────────

def test_aucune_route_ne_tire_la_chaine_dans_la_requete():
    """`on_demand.board_with`/`fetch` chargent la chaîne EN LIGNE ; les routes
    passent par `chaine_a_la_demande.board_avec` (collecte en fond)."""
    import glob
    for chemin in glob.glob(os.path.join(_ROOT, 'vertex', 'app', 'routes', '*.py')):
        src = open(chemin, encoding='utf-8').read()
        assert '_od.board_with(' not in src, chemin
        assert '_od.fetch(' not in src, chemin


def test_board_avec_complete_sans_bloquer(monkeypatch):
    from vertex.options import chaine_a_la_demande as ch
    from vertex.app import snapshot as sn
    # titre déjà couvert : rien n'est déclenché, le board est rendu tel quel
    board = [{'sym': 'AAPL', 'strike': 200}]
    b, meta = ch.board_avec('aapl', board)
    assert b == board and meta.etat == sn.LIVE
    # titre absent : le magasin répond MISSING + chargement en fond, sans attendre
    monkeypatch.setattr(ch, 'contrats', lambda sym, board=None, attendre=False:
                        ([], sn.Meta(etat=sn.MISSING, rafraichissement_en_cours=True)))
    t0 = time.time()
    b2, meta2 = ch.board_avec('ZZZZ', board)
    assert time.time() - t0 < 0.2 and b2 == board and ch.en_cours(meta2)
    # contrats arrivés : ajoutés au board, jamais substitués
    monkeypatch.setattr(ch, 'contrats', lambda sym, board=None, attendre=False:
                        ([{'sym': 'ZZZZ', 'strike': 10}], sn.Meta(etat=sn.LIVE)))
    b3, meta3 = ch.board_avec('ZZZZ', board)
    assert len(b3) == 2 and not ch.en_cours(meta3)


def test_strategies_disent_pas_encore_quand_la_chaine_charge(monkeypatch):
    from vertex.options import chaine_a_la_demande as ch
    from vertex.app import snapshot as sn
    from vertex.app.state import scan_state
    monkeypatch.setitem(scan_state, 'options_board', [])
    monkeypatch.setattr(ch, 'contrats', lambda sym, board=None, attendre=False:
                        ([], sn.Meta(etat=sn.MISSING, rafraichissement_en_cours=True)))
    from vertex.runtime import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        j = c.get('/api/options/strategies/ZZZZ').get_json()
        assert j['available'] is False and j['en_cours'] is True and j['retry_s'] > 0
        j2 = c.get('/api/options/chain/ZZZZ').get_json()
        assert j2['contracts'] == [] and j2['en_cours'] is True


def test_les_pages_options_reessaient_quand_la_chaine_charge():
    for nom in ('options-symbol.js', 'options-structure.js', 'options-intel.js'):
        src = _src('vertex', 'static', 'vertex', 'js', 'pages', nom)
        assert 'en_cours' in src and 'retry_s' in src, nom
        assert '< 2' in src, '%s : le réessai doit être borné' % nom


def test_la_route_ne_porte_plus_l_attente_de_12_s():
    src = _src('vertex', 'app', 'routes', 'desk.py')
    assert 'timeout=12' not in src
    assert 'POSQ_ATTENTE_S' in src and "'en_attente'" in src
