# -*- coding: utf-8 -*-
"""Cerveau Claude : une cotation trouvée par recherche web n'est jamais un cours.

`/api/ai/enrichment` réconcilie chaque cotation avec le prix CANONIQUE du scan
(`scan_price`, `ecart_pct`) et le dit (`note_quotes`) ; la page Système affiche
les deux prix et l'écart, sous un intitulé « non canoniques ». Aucun autre
consommateur ne lit ces cotations (`quote_for` n'a pas d'appelant).
"""
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _src(*parts):
    with open(os.path.join(_ROOT, *parts), encoding='utf-8') as f:
        return f.read()


def test_la_route_reconcilie_avec_le_prix_du_scan(monkeypatch):
    from vertex.app.routes import ai_api
    from vertex.app.state import scan_state
    snap = {'status': 'OK', 'as_of': '2026-09-06T02:00:00Z', 'symbols': ['AAA', 'BBB'],
            'surfaces': {'quotes': {'AAA': {'value': 101.0, 'currency': 'USD'},
                                    'BBB': {'value': 50.0, 'currency': 'USD'},
                                    'CCC': {'value': None}},
                         'news': {}}, 'errors': []}
    monkeypatch.setattr(ai_api._enrich, 'load_snapshot', lambda: snap)
    monkeypatch.setitem(scan_state, 'detail', {'AAA': {'price': 100.0}})
    from vertex.runtime import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        j = c.get('/api/ai/enrichment').get_json()
    q = j['surfaces']['quotes']
    assert q['AAA']['scan_price'] == 100.0 and q['AAA']['ecart_pct'] == 1.0
    assert q['AAA']['canonique'] == 'scan'
    assert q['BBB']['scan_price'] is None and q['BBB']['ecart_pct'] is None   # hors scan : dit
    assert q['CCC']['ecart_pct'] is None
    assert 'jamais le prix canonique' in j['note_quotes']
    # l'instantané persisté n'est pas muté
    assert 'scan_price' not in snap['surfaces']['quotes']['AAA']


def test_la_page_systeme_montre_les_deux_prix_et_l_ecart():
    src = _src('vertex', 'ui', 'pages', 'system_page.py')
    assert 'Prix du scan (canonique)' in src and 'q.ecart_pct' in src and 'q.scan_price' in src
    assert 'non canoniques' in src
    assert '<th class="vx-num">Cours (diff&eacute;r&eacute;)</th>' not in src


def test_aucun_autre_consommateur_des_cotations_llm():
    import glob
    for chemin in glob.glob(os.path.join(_ROOT, 'vertex', '**', '*.py'), recursive=True):
        if chemin.endswith(os.path.join('ai', 'enrichment.py')):
            continue
        src = open(chemin, encoding='utf-8').read()
        assert 'quote_for(' not in src or '_quote_for' in src, chemin
