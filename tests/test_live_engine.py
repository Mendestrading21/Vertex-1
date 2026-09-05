"""
tests/test_live_engine.py — Vertex Live Engine (moteur + API).

Le moteur central : statuts par domaine (source/ts/fraîcheur/état), mode
global honnête (live/delayed/demo/offline), refresh global et partiel qui
réveille la chaîne de recalcul, rapport de synchronisation, et l'injection
du Sync Center sur toutes les pages.
"""

import threading
import time

from vertex.services import live_engine


def _wire(scan=None, demo=True, ibkr=False, ev=None):
    live_engine.configure(scan_state=scan or {}, news_state={'items': []},
                          cal_state={'items': []}, weekly_state={'data': None},
                          rescan_event=ev, ibkr_enabled=ibkr, demo=demo)


def test_freshness_rule_single_source():
    assert live_engine.calculate_freshness(None)[0] == 'offline'
    assert live_engine.calculate_freshness(30, 'prices') == ('ok', 'il y a 30s')
    assert live_engine.calculate_freshness(900, 'prices')[0] == 'stale'
    assert live_engine.calculate_freshness(7200, 'prices')[0] == 'offline'
    assert live_engine.calculate_freshness(1800, 'options')[0] == 'ok'   # seuil par domaine


def test_mode_reflects_reality():
    _wire(scan={}, demo=True)
    assert live_engine.mode() == 'offline'                    # jamais scanné
    _wire(scan={'scan_ts': time.time()}, demo=True)
    assert live_engine.mode() == 'demo'
    _wire(scan={'scan_ts': time.time()}, demo=False, ibkr=False)
    assert live_engine.mode() == 'delayed'
    st = {'scan_ts': time.time()}
    _wire(scan=st, demo=False, ibkr=True)
    #  Mission alimentation (2026-09-06) : « live » exige la PREUVE de socket
    #  (`ibkr_live` posé par ibkr_state.sync), plus le seul drapeau de config.
    assert live_engine.mode() == 'delayed', 'IBKR configuré sans tick récent = différé'
    st['ibkr_live'] = True
    assert live_engine.mode() == 'live'


def test_status_has_all_domains_with_freshness():
    _wire(scan={'scan_ts': time.time(), 'rows': [{}] * 5,
                'options_board': [{}] * 3, 'committee': {'decisions': [{}] * 2}}, demo=True)
    st = live_engine.status()
    assert set(st['domains']) == {'prices', 'options', 'companies', 'news',
                                  'calendar', 'weekly', 'ai'}
    for d in st['domains'].values():
        assert d['state'] in ('ok', 'stale', 'offline')
        assert d['source'] and d['freshness'] and d['label']
    assert st['domains']['prices']['count'] == 5
    assert st['mode'] == 'demo'


def test_offline_prices_reported_as_error():
    _wire(scan={}, demo=True)
    st = live_engine.status()
    assert any(e['domain'] == 'prices' for e in st['errors'])


def test_refresh_kicks_rescan_and_builds_report():
    ev = threading.Event()
    _wire(scan={'scan_ts': time.time(), 'rows': [{}]}, demo=True, ev=ev)
    out = live_engine.refresh()
    assert out['ok'] and out['kicked'] and ev.is_set()
    labels = {l['domain'] for l in out['report']['lines']}
    assert 'prices' in labels and 'ai' in labels and 'options' in labels
    assert all(l['action'] for l in out['report']['lines'])
    assert live_engine.report()['ts'] is not None


def test_partial_refresh_only_touches_asked_domains():
    ev = threading.Event()
    _wire(scan={'scan_ts': time.time()}, demo=True, ev=ev)
    out = live_engine.refresh(['news'])
    assert {l['domain'] for l in out['report']['lines']} == {'news'}
    assert not ev.is_set()                                     # news ne réveille pas le scan
    assert 'démo' in out['report']['lines'][0]['action']       # honnête : pas de réseau en démo


def test_api_routes_and_global_injection():
    import terminal
    from vertex.app.state import cal_state, news_state, scan_state, weekly_state
    # re-câble l'état RÉEL de l'app (les tests précédents ont posé des états factices)
    live_engine.configure(scan_state=scan_state, news_state=news_state,
                          cal_state=cal_state, weekly_state=weekly_state,
                          rescan_event=terminal._rescan_evt, ibkr_enabled=False, demo=True)
    c = terminal.app.test_client()
    st = c.get('/api/live/status').get_json()
    assert st['mode'] in ('live', 'delayed', 'demo', 'offline') and 'domains' in st
    r = c.post('/api/live/refresh?domains=prices').get_json()
    assert r['ok'] and r['report']['requested'] == ['prices']
    rp = c.get('/api/live/report').get_json()
    assert rp['lines']
    # La couche pages de terminal.py est retirée (lot 36) : le Sync Center
    # ne vit plus que dans son module (vérifié par test_sync_center_features).


#  (test_sync_center_features retiré au lot 37 avec le module
#  sync_center.py — la synchronisation servie est live-updates.js,
#  gardée par les tests d'API /api/live/* ci-dessous.)


# ─── Connexions données réelles : forçage de cycle, recherche news, chiffres ───

def test_force_event_wakes_loops():
    ev = live_engine.force_event('calendar')
    ev.clear()
    assert live_engine.wait_force('calendar', 0.01) is False   # timeout sans forçage
    live_engine.force_event('calendar').set()
    assert live_engine.wait_force('calendar', 5) is True       # réveil immédiat
    assert not live_engine.force_event('calendar').is_set()    # nettoyé après réveil


def test_partial_refresh_forces_real_cycles_outside_demo():
    _wire(scan={'scan_ts': time.time()}, demo=False, ibkr=False)
    live_engine.force_event('news').clear()
    live_engine.force_event('calendar').clear()
    out = live_engine.refresh(['news', 'calendar'])
    acts = {l['domain']: l['action'] for l in out['report']['lines']}
    assert 'forcé' in acts['news'] and 'forcé' in acts['calendar']
    assert live_engine.force_event('news').is_set()
    assert live_engine.force_event('calendar').is_set()


def test_news_feed_server_side_search():
    import terminal
    from vertex.app.state import news_state
    saved = dict(news_state)
    try:
        news_state['items'] = [
            {'sym': 'NVDA', 'title': 'Nvidia beats estimates', 'fr': 'Nvidia dépasse les attentes'},
            {'sym': 'AAPL', 'title': 'Apple event', 'fr': 'Conférence Apple'},
            {'sym': 'NVDA', 'title': 'Fed holds rates', 'fr': 'La Fed maintient ses taux'},
        ]
        c = terminal.app.test_client()
        j = c.get('/news-feed?sym=NVDA').get_json()
        assert len(j['items']) == 2 and j['filtered'] is True
        j = c.get('/news-feed?q=fed').get_json()
        assert len(j['items']) == 1 and 'Fed' in j['items'][0]['title']
        j = c.get('/news-feed?sym=NVDA&q=attentes').get_json()
        assert len(j['items']) == 1
        j = c.get('/news-feed').get_json()
        assert len(j['items']) == 3 and j['filtered'] is False
    finally:
        news_state.clear()
        news_state.update(saved)


def test_company_profile_enriched_fields():
    src = open('vertex/data/company.py', encoding='utf-8').read()
    for field in ('beta', 'ebitda', 'debt_to_ebitda', 'earnings_date'):
        assert "'" + field + "'" in src, field
    # exposés aussi dans la vue brève (fiche titre)
    assert "'beta', 'ebitda', 'debt_to_ebitda', 'earnings_date'" in src


def test_news_loop_follows_hot_scan_symbols():
    src = open('terminal.py', encoding='utf-8').read()
    assert 'NEWS_SYMS + hot' in src                      # socle + titres chauds du scan
    assert "_live.wait_force('news', 60)" in src         # cycle interruptible
    assert "_live.wait_force('calendar', 3 * 3600)" in src
