"""Tests — API du cerveau Claude+web & invariant lecture seule (§28)."""
import glob
import os
import re


def test_enrich_symbols_dedup_and_cap(monkeypatch):
    from vertex.app.routes import ai_api
    from vertex.app import state
    monkeypatch.setitem(state.scan_state, 'rows',
                        [{'symbol': 'ACN'}, {'symbol': 'ABT'}, {'symbol': 'ACN'},
                         {'symbol': 'SPY.X'}])
    syms = ai_api.enrich_symbols()
    assert syms.count('ACN') == 1          # dédupliqué
    assert 'SPY.X' not in syms             # les symboles à point exclus
    assert 'ABT' in syms


def test_ai_status_endpoint_is_honest_without_key():
    import terminal
    client = terminal.app.test_client()
    r = client.get('/api/ai/status')
    assert r.status_code == 200
    data = r.get_json()
    assert 'status' in data and 'health' in data
    # Sans clé configurée dans l'environnement de test : jamais « CONNECTED ».
    if not os.environ.get('ANTHROPIC_API_KEY'):
        assert data['health']['status'] == 'MISSING'


def test_ai_enrichment_endpoint_never_fabricates_without_key():
    import terminal
    client = terminal.app.test_client()
    data = client.get('/api/ai/enrichment').get_json()
    if not os.environ.get('ANTHROPIC_API_KEY'):
        # Aucune cotation estimée ne doit exister sans clé.
        assert data.get('surfaces', {}).get('quotes', {}) in ({}, None)


def test_ai_refresh_endpoint_returns_202():
    import terminal
    client = terminal.app.test_client()
    r = client.post('/api/ai/refresh')
    assert r.status_code == 202
    assert 'accepted' in r.get_json()


def test_no_order_execution_verb_in_ai_package():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    banned = re.compile(r'(?:\.|\bdef\s+)(place_order|placeOrder|submit_order|'
                        r'transmit_order|send_order|execute_trade|cancel_order|'
                        r'modify_order|exercise_option)\s*\(')
    for p in glob.glob(os.path.join(root, 'vertex/ai/*.py')):
        assert not banned.search(open(p, encoding='utf-8').read()), p


def test_web_tool_is_read_only_search():
    """Le seul outil externe du cerveau est la recherche web (lecture)."""
    from vertex.ai import web_provider
    assert web_provider.WEB_TOOL_TYPE.startswith('web_search')


# ─────────────────────────────── Analyste IA (§28) : dossier réel, jamais d'ordre
def test_ai_analyst_unknown_symbol_is_honest():
    import terminal
    client = terminal.app.test_client()
    d = client.get('/api/ai/analyst/ZZZZ').get_json()
    assert d['available'] is False           # 200 + état honnête, jamais un faux verdict
    assert 'content' not in d


def test_ai_analyst_fallback_is_deterministic_and_schema_valid(monkeypatch):
    from vertex.app import state
    from vertex.ai.response_validator import validate_analysis
    monkeypatch.setitem(state.scan_state, 'detail', {
        'ACN': {'score': 72, 'rr': 3.0, 'sector': 'Technology', 'price': 200.0,
                'vertex': {'rr': 3.0, 'mc': {}, 'bootstrap': {}, 'kelly': {'pct': 10},
                           'asymmetry': 60, 'ev': 1.2},
                'physics': {'hurst': 0.55}, 'mtf': {'state': 'ALIGNED'}, 'plan': {}}})
    import terminal
    d = terminal.app.test_client().get('/api/ai/analyst/ACN').get_json()
    assert d['available'] is True
    ok, errs = validate_analysis(d['content'])       # le fallback respecte le schéma strict
    assert ok, errs
    for k in ('order', 'orders', 'execute', 'trade_now', 'position_size_final'):
        assert k not in d['content']                 # aucune clé d'ordre, jamais
    if not os.environ.get('ANTHROPIC_API_KEY'):      # sans clé : honnêteté MISSING
        assert d['source'] == 'deterministic-fallback'
        assert d['health']['status'] == 'MISSING'
        assert d['model'] is None


def test_resolve_model_prefers_vertex_then_anthropic(monkeypatch):
    """Une seule source de vérité modèle : VERTEX_AI_MODEL > ANTHROPIC_MODEL > défaut."""
    from vertex.ai import health
    monkeypatch.setenv('VERTEX_AI_MODEL', 'claude-opus-4-8')
    monkeypatch.setenv('ANTHROPIC_MODEL', 'autre')
    assert health.resolve_model() == 'claude-opus-4-8'
    monkeypatch.delenv('VERTEX_AI_MODEL', raising=False)
    assert health.resolve_model() == 'autre'
    monkeypatch.delenv('ANTHROPIC_MODEL', raising=False)
    assert health.resolve_model() == health.DEFAULT_MODEL


def test_paquet_analyste_lit_le_fondamental_chez_son_producteur():
    """CONSTAT 5, site jumeau — le dossier envoyé à Claude lisait deux clés mortes.

    MESURE (detail portant `sub.fundamental = 100.0`) :
      - moteur   → fundamental {'score': 100.0, 'is_proxy': False}
      - paquet IA→ fundamental {'score': None, 'quality': None}
    Le paquet lisait `detail['st_fund'] or detail['fund_score']` : `fund_score`
    n'a AUCUNE assignation dans le dépôt et `st_fund` n'est posée que sur la
    LIGNE de tableau (terminal.py:643), jamais sur le `detail`. Le dossier
    servait donc une valeur MESURÉE comme une absence, sous un docstring
    promettant « aucune valeur inventée ».
    """
    from vertex.app.routes import ai_api
    detail = {'score': 78, 'sub': {'fundamental': 100.0, 'fundamental_is_proxy': False},
              'vertex': {'fund_quality': 'A'}}
    pk = ai_api._analyst_packet('NVDA', detail, {})
    assert pk['fundamental']['score'] == 100.0
    assert pk['fundamental']['is_proxy'] is False        # lignage transporté
    assert pk['fundamental']['quality'] == 'A'           # champ historique conservé
    # Le `or` écrasait en plus un 0 légitime : 0 = « fondamentaux non branchés »,
    # donc ABSENT (sémantique figée par tests/test_evidence_edges.py), jamais 0.
    zero = ai_api._analyst_packet('NVDA', {'sub': {'fundamental': 0}}, {})
    assert zero['fundamental']['score'] is None


def test_paquet_analyste_ne_se_contredit_pas_sur_les_inconnues():
    """RÉGRESSION du premier tour — fondamental « absent » ET non déclaré inconnu.

    MESURE après le correctif partiel du lot précédent : `unknowns`, repris du
    moteur exécutif corrigé, ne listait plus 'fundamental' pendant que le paquet
    IA servait toujours `fundamental {'score': None}`. Claude recevait donc un
    fondamental présenté comme ABSENT et simultanément PAS déclaré inconnu —
    état pire qu'avant le lot, où les deux disaient « inconnu ». L'invariant
    testé ici est la cohérence du dossier avec lui-même, dans les deux sens.
    """
    from vertex.app.routes import ai_api
    from vertex.strategy import decision_packet as dp
    from vertex.strategy import executive_engine as ex
    scan = {'source': 'stooq', 'market': {'et': '08:54 ET', 'open': False}}

    def _coherent(detail):
        resp = ex.decide(dp.build('NVDA', detail, scan))
        pk = ai_api._analyst_packet('NVDA', detail, resp)
        absent = pk['fundamental']['score'] is None
        declare = 'fundamental' in (pk['unknowns'] or [])
        return absent == declare, pk

    ok, pk = _coherent({'score': 78, 'rr': 2.3,
                        'sub': {'fundamental': 100.0, 'fundamental_is_proxy': False}})
    assert ok and pk['fundamental']['score'] == 100.0
    assert 'fundamental' not in pk['unknowns']
    ok, pk = _coherent({'score': 78, 'rr': 2.3})          # vraiment absent
    assert ok and pk['fundamental']['score'] is None
    assert 'fundamental' in pk['unknowns']
