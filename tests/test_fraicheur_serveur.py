# -*- coding: utf-8 -*-
"""tests/test_fraicheur_serveur.py — le serveur date ses données, le client n'invente pas l'âge.

Mesuré (inventaire 2026-09-06) : `scan_ts_h` était lu par 23 consommateurs et
écrit par aucun (la fraîcheur se lisait « HH:MM:SS » sans date) ;
`/api/market/regime` ne portait aucun `as_of` ; `/cal-feed` réhydraté depuis
le cache gardait un `dte` figé au moment de la collecte et aucun `ts` ; et
vingt-cinq emplacements de sept pages posaient `Date.now()` comme âge de
donnée — la carte disait « À l'instant » sur un scan de 30 minutes.

Ces gardiens sont nés ROUGES sur `main` (ed363d67).
"""
from __future__ import annotations

import re
import time
from datetime import date, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope='module')
def client():
    import terminal
    return terminal.app.test_client()


def test_le_scan_publie_un_horodatage_iso_utc_parseable():
    src = (ROOT / 'terminal.py').read_text(encoding='utf-8')
    assert src.count("'scan_ts_h': _horodatage_iso_utc()") == 2, 'les deux publications (partielle, complète) datent le scan'
    import terminal
    h = terminal._horodatage_iso_utc()
    assert re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z', h), h


def test_le_regime_est_date_par_le_scan_qui_l_a_produit(client):
    from vertex.app.state import scan_state
    avant = (scan_state.get('scan_ts_h'), scan_state.get('scan_ts'))
    scan_state['scan_ts_h'] = '2026-09-06T00:00:00Z'
    scan_state['scan_ts'] = 1788998400.0
    try:
        d = client.get('/api/market/regime').get_json()
        assert d.get('as_of') == '2026-09-06T00:00:00Z'
        assert d.get('ts') == 1788998400.0
    finally:
        scan_state['scan_ts_h'], scan_state['scan_ts'] = avant


def test_le_calendrier_recalcule_dte_et_date_ses_items(client):
    from vertex.app.routes import content as _content
    cal_state = _content.cal_state
    sauvegarde = dict(cal_state)
    dans_7_jours = (date.today() + timedelta(days=7)).isoformat()
    try:
        cal_state.clear()
        cal_state.update({'items': [{'sym': 'TEST', 'date': dans_7_jours, 'dte': 42,
                                     'score': None, 'grade': None, 'verdict': None}],
                          'ts': None})
        d = client.get('/cal-feed').get_json()
        it = d['items'][0]
        assert it['dte'] == 7, 'le dte figé du cache (42) est recalculé à la lecture'
        assert it['source'] in ('yfinance', 'demo') and it['confirmation']
        assert 'source' in d and 'demo' in d
    finally:
        cal_state.clear()
        cal_state.update(sauvegarde)


_PAGES = list((ROOT / 'vertex' / 'ui' / 'pages').glob('*.py')) + \
    list((ROOT / 'vertex' / 'static' / 'vertex' / 'js' / 'pages').glob('*.js'))
#  Usages LÉGITIMES de l'horloge du navigateur : durée, DTE d'une échéance,
#  heure de réception d'un événement, horodatage d'export. Tout usage comme
#  `timestamp:` d'une carte ou repli `||Date.now()` d'un âge est interdit.
_MOTIFS_INTERDITS = (re.compile(r'timestamp\s*:\s*Date\.now\(\)'),
                     re.compile(r'\|\|\s*Date\.now\(\)'),
                     re.compile(r'ts\s*=\s*Date\.now\(\)\s*;'))


@pytest.mark.parametrize('page', _PAGES, ids=lambda p: p.name)
def test_aucune_page_ne_pose_l_horloge_du_navigateur_comme_age_de_donnee(page):
    src = page.read_text(encoding='utf-8', errors='ignore')
    fautes = []
    for i, line in enumerate(src.splitlines(), 1):
        if line.lstrip().startswith(('//', '*', '#', '/*')):
            continue
        if 'localStorage' in line or 'exported' in line or 'NAVIGATEUR' in line or '`' in line:
            continue        # horodatage d'un EXPORT du bureau : c'est l'heure de l'événement
        for m in _MOTIFS_INTERDITS:
            if m.search(line):
                fautes.append('%d: %s' % (i, line.strip()[:110]))
    assert not fautes, '%s pose l’heure du navigateur comme âge de donnée :\n%s' % (
        page.name, '\n'.join(fautes))
