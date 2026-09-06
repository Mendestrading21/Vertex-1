"""
tests/test_feeds_routes.py — Flux de données en Blueprint (Ch. II).

Import direct de l'état partagé, réponses lecture seule, jamais d'erreur 500
sur état vide.
"""

from flask import Flask
from vertex.app.routes import feeds


def _app():
    app = Flask(__name__)
    app.register_blueprint(feeds.bp)
    return app


def test_all_feed_routes_registered():
    rules = {r.rule for r in _app().url_map.iter_rules()}
    for path in ('/api/market/summary', '/api/cockpit', '/api/watchlist', '/api/options',
                 '/api/search', '/api/weekly', '/api/strategie', '/api/comite'):
        assert path in rules


def test_feeds_are_read_only_and_safe_on_empty_state():
    c = _app().test_client()
    for path in ('/api/market/summary', '/api/cockpit', '/api/watchlist', '/api/options',
                 '/api/weekly', '/api/strategie', '/api/comite'):
        r = c.get(path)
        assert r.status_code == 200, path


def test_market_summary_verdict_tracks_score():
    from vertex.app import state
    state.scan_state['market_ctx'] = {'spy_regime': 'TREND', 'roro': 'RISK-ON',
                                      'vix_band': 'calme', 'breadth': {'above50': 75}}
    try:
        j = _app().test_client().get('/api/market/summary').get_json()
        assert j['verdict'] == 'FAVORABLE' and j['score'] >= 65
    finally:
        state.scan_state['market_ctx'] = None


def test_market_summary_sans_climat_ne_fabrique_pas_de_verdict():
    """CONSTAT 47 — l'absence de climat était convertie en « DANGEREUX ».

    MESURE d'origine : `market_lens.climate({})` rend None À DESSEIN, mais la
    route faisait `verdict = 'FAVORABLE' if (sc or 0) >= 65 else ... else
    'DANGEREUX'` — `(sc or 0)` transformait None en 0 et servait
    {"score": null, "verdict": "DANGEREUX", "regime": null, "roro": null,
    "vix": null, "vix_band": null, "breadth": null, "market_verdict": null},
    c'est-à-dire un jugement catégoriel de marché à côté de six dimensions
    nulles. Le cas apparaît au démarrage à froid ou sur scan échoué, ce qui le
    rendait d'autant plus discret. Invariant 5 : absence et valeur restent
    distinctes — score et verdict voyagent désormais ensemble.
    """
    from vertex.app import state
    prev = state.scan_state.get('market_ctx')
    try:
        for vide in ({}, None):
            state.scan_state['market_ctx'] = vide
            j = _app().test_client().get('/api/market/summary').get_json()
            assert j['score'] is None and j['verdict'] is None, vide
    finally:
        state.scan_state['market_ctx'] = prev


def test_market_summary_verdict_est_celui_du_moteur_sur_toute_la_plage():
    """CONSTAT 48 — la route re-dérivait un label que le moteur possède déjà.

    MESURE d'origine, mc={'spy_regime':'TREND','roro':'RISK-ON',
    'vix_band':'stress'} : above50 ∈ {0, 4, 8} → scores 62/63/64 étiquetés
    FAVORABLE par `market_lens.climate` et NEUTRE par cette route, au même
    instant sur la même donnée (bornes 62 vs 65 pour une seule métrique).
    Le moteur est désormais le propriétaire unique du couple score+label ; ce
    test balaie toute la plage 0-100 de participation pour qu'aucune borne ne
    puisse re-diverger en silence.
    """
    from vertex.app import state
    from vertex.engines import market_lens
    prev = state.scan_state.get('market_ctx')
    c = _app().test_client()
    try:
        for regime in ('TREND', 'NEUTRAL', 'CHOP'):
            for band in ('calme', 'stress', None):
                for a50 in range(0, 101, 4):
                    mc = {'spy_regime': regime, 'roro': 'RISK-ON',
                          'vix_band': band, 'breadth': {'above50': a50}}
                    state.scan_state['market_ctx'] = mc
                    j = c.get('/api/market/summary').get_json()
                    attendu = market_lens.climate(mc)
                    assert j['score'] == attendu['score'], mc
                    assert j['verdict'] == attendu['label'], mc
    finally:
        state.scan_state['market_ctx'] = prev


def test_market_summary_signale_un_score_partiel():
    """CONSTAT 30 — un score partiel était servi sans aucune marque de couverture.

    MESURE d'origine (instance de contrôle, scan fait) : /api/market/summary
    rendait score=70 / verdict=FAVORABLE avec « clés de couverture détectées :
    [] » sur 18 clés totales. Rien ne permettait au consommateur de distinguer
    un score à couverture complète d'un score amputé de sa composante
    participation (25 points sur 100). La marque n'a de valeur que si elle est
    servie : elle traverse maintenant la route.
    """
    from vertex.app import state
    prev = state.scan_state.get('market_ctx')
    c = _app().test_client()
    try:
        state.scan_state['market_ctx'] = {'spy_regime': 'NEUTRAL', 'roro': 'RISK-ON',
                                          'vix_band': 'calme', 'breadth': {}}
        partiel = c.get('/api/market/summary').get_json()
        state.scan_state['market_ctx'] = {'spy_regime': 'NEUTRAL', 'roro': 'RISK-ON',
                                          'vix_band': 'calme',
                                          'breadth': {'above50': 50}}
        complet = c.get('/api/market/summary').get_json()
    finally:
        state.scan_state['market_ctx'] = prev
    # Même score servi : seule la COUVERTURE les distingue.
    assert partiel['score'] == complet['score'] == 70
    assert partiel['score_partiel'] is True
    assert partiel['breadth_status'] == 'MISSING' and partiel['score_note']
    assert complet['score_partiel'] is False
    assert complet['breadth_status'] is None and complet['score_note'] is None


def test_search_filters_universe():
    j = _app().test_client().get('/api/search?q=AAP').get_json()
    assert isinstance(j, list) and all('AAP' in x['ticker'] for x in j)


def test_terminal_registered_feeds():
    import terminal
    rules = {r.rule for r in terminal.app.url_map.iter_rules()}
    assert '/api/cockpit' in rules and '/api/watchlist' in rules
