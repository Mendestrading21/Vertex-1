# -*- coding: utf-8 -*-
"""P2 — actualités : horodatage source normalisé, heure de réception, époque du
fil, provenance et nombre de sources sur la carte. Rien d'inventé : une source
sans horodatage lisible rend `published_at: None`.
"""
import os

from vertex.services import news_plus as np_

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _src(*parts):
    with open(os.path.join(_ROOT, *parts), encoding='utf-8') as f:
        return f.read()


def test_horodatage_source_normalise_les_trois_formats_du_fil():
    assert np_.horodatage_source('2026-09-06 07:12') == '2026-09-06T07:12'        # IBKR
    assert np_.horodatage_source('2026-09-06T07:12:30') == '2026-09-06T07:12'     # yfinance ISO
    assert np_.horodatage_source('Sat, 06 Sep 2026 07:00:00 GMT') == '2026-09-06T07:00Z'   # RSS
    assert np_.horodatage_source('Sat, 06 Sep 2026 09:00:00 +0200') == '2026-09-06T07:00Z'
    assert np_.horodatage_source('') is None and np_.horodatage_source(None) is None
    assert np_.horodatage_source('hier') is None                                 # illisible : rien d'inventé


def test_la_boucle_horodate_reception_et_publication_et_date_le_fil():
    src = _src('terminal.py')
    assert "_it['received_at'] = _recu" in src
    assert "_it['published_at'] = _news_plus.horodatage_source(_it.get('time'))" in src
    assert "news_state['ts'] = time.time()" in src and "news_state['as_of'] = _recu" in src


def test_le_dedoublonnage_garde_toutes_les_sources():
    items = [{'title': 'Fed holds rates', 'link': 'https://a/1', 'pub': 'Reuters', 'time': '2026-09-06 07:00'},
             {'title': 'Fed Holds Rates!', 'link': 'https://b/2', 'pub': 'Bloomberg', 'time': '2026-09-06 07:05'},
             {'title': 'Autre sujet', 'link': 'https://c/3', 'pub': 'IBKR', 'time': ''}]
    out = np_.dedupe_news(items)
    assert len(out) == 2 and out[0]['n_sources'] == 2
    assert {s['pub'] for s in out[0]['sources']} == {'Reuters', 'Bloomberg'}


def test_la_carte_montre_publication_et_nombre_de_sources():
    src = _src('vertex', 'ui', 'pages', 'briefing.py')
    assert "(n.published_at||n.time)" in src
    assert "n.n_sources" in src and "sources`" in src
    assert "reçu '+esc(n.received_at)" in src
