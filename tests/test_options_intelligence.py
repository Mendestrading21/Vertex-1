"""tests/test_options_intelligence.py — SKYLER LOT 6 : Options Intelligence.

Scanners TACTICAL/SWING/LEAPS strictement séparés (jamais ~35 DTE pour une
requête LEAPS), probabilité de doublement avec modèle DOCUMENTÉ et étiqueté
ESTIMATED (≠ PoP), mandat LEAPS V2 appliqué (delta 0,70-0,90, OI, spread),
OptionsContext branché dans le score Skyler (bloc options_quality réel).
"""
import math

import pytest

from vertex.options import double_prob as DP
from vertex.options import horizon_scanners as HS
from vertex.strategy import constitution as C


def _board():
    def c(sym, typ, dte, strike, delta, oi=2000, spread=2.0, quality=70, cost=500,
          iv=40.0, spot=100.0):
        return {'sym': sym, 'type': typ, 'dte': dte, 'strike': strike, 'delta': delta,
                'oi': oi, 'spread_pct': spread, 'quality': quality, 'cost': cost,
                'iv': iv, 'spot': spot, 'exp': 'X'}
    return [
        c('TST', 'CALL', 45, 105, 0.35),                       # TACTICAL
        c('TST', 'CALL', 120, 105, 0.40),                      # SWING
        c('TST', 'CALL', 365, 80, 0.80),                       # LEAPS conforme
        c('TST', 'CALL', 365, 120, 0.30, oi=100, spread=9.0),  # LEAPS hors mandat
        c('TST', 'PUT', 365, 90, -0.75),                       # LEAPS put long
        c('OTH', 'CALL', 365, 50, 0.85),                       # autre titre
    ]


# ─── Séparation stricte des univers ─────────────────────────────────────────────

def test_leaps_scan_never_returns_short_dte():
    res = HS.scan(_board(), 'LEAPS', sym='TST')
    assert res['available'] is True
    assert res['candidates']
    assert all(180 <= c['dte'] <= 540 for c in res['candidates'])
    assert res['window'] == [180, 540]


def test_tactical_and_swing_windows():
    t = HS.scan(_board(), 'TACTICAL', sym='TST')
    assert [c['dte'] for c in t['candidates']] == [45]
    s = HS.scan(_board(), 'SWING', sym='TST')
    assert [c['dte'] for c in s['candidates']] == [120]


def test_unknown_universe_refused():
    res = HS.scan(_board(), 'YOLO', sym='TST')
    assert res['available'] is False and 'univers' in res['reason']


def test_symbol_filter_and_empty_honest():
    res = HS.scan(_board(), 'LEAPS', sym='ZZZ')
    assert res['available'] is False and res['candidates'] == []


def test_profile_load_failure_uses_labeled_fallback_without_stopping_scan(monkeypatch):
    def unavailable_profile():
        raise RuntimeError('profil inaccessible')

    monkeypatch.setattr(C, 'load_profile', unavailable_profile)
    res = HS.scan(_board(), 'SWING', sym='TST')
    assert res['available'] is True
    assert res['profile_coverage'] == {
        'available': False,
        'status': 'PROFILE_FALLBACK',
        'read_only': True,
    }


# ─── Mandat LEAPS V2 appliqué (jamais silencieux) ───────────────────────────────

def test_leaps_mandate_flags():
    res = HS.scan(_board(), 'LEAPS', sym='TST')
    by_strike = {c['strike']: c for c in res['candidates']}
    good = by_strike[80]
    assert good['mandate']['delta_ok'] is True
    assert good['mandate']['oi_ok'] is True and good['mandate']['spread_ok'] is True
    assert good['hors_mandat'] is False
    bad = by_strike[120]
    assert bad['mandate']['delta_ok'] is False       # 0.30 hors [0.70, 0.90]
    assert bad['mandate']['oi_ok'] is False          # 100 < oi_min 500
    assert bad['mandate']['spread_ok'] is False      # 9 % > 5 %
    assert bad['hors_mandat'] is True


def test_iv_normalized_and_labeled():
    res = HS.scan(_board(), 'LEAPS', sym='TST')
    c = res['candidates'][0]
    assert c['iv'] is not None and c['iv'] < 1.5      # décimale
    assert c['iv_unit'] == 'DECIMAL'


def test_ranking_in_mandate_first():
    res = HS.scan(_board(), 'LEAPS', sym='TST')
    hm = [c['hors_mandat'] for c in res['candidates']]
    assert hm == sorted(hm)                           # conformes d'abord


# ─── Mandat opérationnel Swing 3–6 mois ─────────────────────────────────────────

def test_swing_3_6m_prefers_target_dte_and_emits_holding_plan():
    board = [
        {'sym': 'TST', 'type': 'CALL', 'dte': 90, 'strike': 100, 'delta': 0.45,
         'oi': 900, 'volume': 90, 'spread_pct': 3.0, 'quote_age_seconds': 60,
         'quality': 95, 'iv': 0.35, 'spot': 100, 'exp': 'A'},
        {'sym': 'TST', 'type': 'CALL', 'dte': 135, 'strike': 105, 'delta': 0.45,
         'oi': 900, 'volume': 90, 'spread_pct': 3.0, 'quote_age_seconds': 60,
         'quality': 75, 'iv': 0.35, 'spot': 100, 'exp': 'B'},
        {'sym': 'TST', 'type': 'CALL', 'dte': 180, 'strike': 110, 'delta': 0.45,
         'oi': 900, 'volume': 90, 'spread_pct': 3.0, 'quote_age_seconds': 60,
         'quality': 99, 'iv': 0.35, 'spot': 100, 'exp': 'C'},
    ]
    res = HS.scan(board, 'SWING_3_6M', sym='TST', profile=C.load_profile())
    assert res['window'] == [75, 210]
    assert res['preferred_window'] == [90, 180]
    assert res['candidates'][0]['dte'] == 135
    assert res['candidates'][0]['mandate_status'] == 'IN_MANDATE'
    ctx = HS.swing_3_6m_context(board, sym='TST', profile=C.load_profile())
    assert ctx['universe'] == 'SWING_3_6M'
    assert ctx['best']['mandate']['bounds']['holding_plan_sessions'] == [5, 10, 15]


def test_swing_3_6m_never_assumes_missing_liquidity_is_compliant():
    board = [{'sym': 'TST', 'type': 'CALL', 'dte': 135, 'strike': 105, 'delta': 0.45,
              'oi': 900, 'spread_pct': 3.0, 'quality': 75, 'iv': 0.35,
              'spot': 100, 'exp': 'B'}]
    res = HS.scan(board, 'SWING_3_6M', sym='TST', profile=C.load_profile())
    candidate = res['candidates'][0]
    assert candidate['mandate_status'] == 'PARTIAL_MANDATE'
    assert candidate['mandate']['volume_ok'] is None
    assert candidate['mandate']['quote_fresh_ok'] is None
    assert HS.options_context(res)['best_in_mandate'] is False


def test_swing_3_6m_exposes_quote_freshness_without_hiding_candidates():
    base = {'sym': 'TST', 'type': 'CALL', 'dte': 135, 'strike': 105, 'delta': 0.45,
            'oi': 900, 'volume': 90, 'spread_pct': 3.0, 'quality': 75, 'iv': 0.35,
            'spot': 100, 'exp': 'B'}
    board = [{**base, 'quote_age_seconds': 60}, {**base, 'strike': 110, 'quote_age_seconds': 901},
             {**base, 'strike': 115}]
    out = HS.scan(board, 'SWING_3_6M', sym='TST', profile=C.load_profile())
    by_strike = {c['strike']: c for c in out['candidates']}
    assert by_strike[105]['quote_freshness']['status'] == 'QUOTE_FRESH'
    assert by_strike[110]['quote_freshness']['status'] == 'QUOTE_STALE'
    assert by_strike[115]['quote_freshness']['status'] == 'QUOTE_FRESHNESS_UNAVAILABLE'
    assert len(out['candidates']) == 3


def test_swing_context_exposes_iv_hv_without_affecting_mandate_status():
    board = [{'sym': 'TST', 'type': 'CALL', 'dte': 120, 'strike': 100, 'delta': 0.45,
              'oi': 600, 'volume': 80, 'spread_pct': 2.0, 'quote_age_seconds': 60,
              'quality': 75, 'iv': 30.0, 'spot': 100.0, 'exp': 'X'}]
    closes = [100.0 + index * 0.5 for index in range(25)]
    ctx = HS.swing_3_6m_context(board, sym='TST', profile=C.load_profile(), historical_closes=closes)
    assert ctx['mandate_status'] == 'IN_MANDATE'
    assert ctx['iv_hv_context']['available'] is True
    assert ctx['iv_hv_context']['read_only'] is True


# ─── Probabilité de doublement (≠ PoP, modèle documenté) ────────────────────────

def test_double_probability_hand_computed_call():
    """S=100, K=100, prime 5, 365 j, IV 30 %, r=4.5 %, q=0 : doubler ⇒ S_T ≥ 110.
    d = (ln(100/110) + (r − σ²/2)) / σ = (−0.09531 + 0) / 0.3 → P = N(−0.3177) ≈ 0.375."""
    d = DP.double_probability(spot=100, strike=100, premium=5, dte=365, iv=0.30,
                              right='CALL')
    assert d['available'] is True
    assert d['threshold_price'] == pytest.approx(110.0)
    assert d['probability'] == pytest.approx(0.375, abs=0.01)
    assert d['status'] == 'ESTIMATED'


def test_double_probability_put():
    d = DP.double_probability(spot=100, strike=100, premium=5, dte=365, iv=0.30,
                              right='PUT')
    assert d['threshold_price'] == pytest.approx(90.0)
    assert 0.30 < d['probability'] < 0.45


def test_double_probability_model_documented():
    d = DP.double_probability(spot=100, strike=100, premium=5, dte=365, iv=0.30)
    m = d['model']
    assert m['type'] == 'lognormal_terminal_intrinsic'
    assert m['calibrated'] is False
    assert any('échéance' in a or 'echeance' in a for a in m['assumptions'])
    assert 'spread' in ' '.join(m['assumptions']).lower()
    assert d['confidence'] == 'REDUITE'


def test_double_probability_is_not_pop():
    """Doubler est plus dur que finir en profit : P(double) < P(S_T > breakeven)."""
    d = DP.double_probability(spot=100, strike=100, premium=5, dte=365, iv=0.30)
    # PoP terminal (breakeven 105) avec le même modèle :
    pop_d = (math.log(100 / 105) + (0.045 - 0.045)) / 0.30
    pop = 0.5 * (1 + math.erf(pop_d / math.sqrt(2)))
    assert d['probability'] < pop


def test_double_probability_refuses_bad_inputs():
    assert DP.double_probability(spot=-1, strike=100, premium=5, dte=30, iv=0.3)['available'] is False
    assert DP.double_probability(spot=100, strike=100, premium=0, dte=30, iv=0.3)['available'] is False
    assert DP.double_probability(spot=100, strike=100, premium=5, dte=30, iv=31)['available'] is False  # % non converti
    r = DP.double_probability(spot=100, strike=100, premium=5, dte=-2, iv=0.3)
    assert r['available'] is False and r['refusals']


def test_put_threshold_below_zero_prob_zero():
    d = DP.double_probability(spot=100, strike=8, premium=5, dte=365, iv=0.30, right='PUT')
    assert d['probability'] == 0.0                    # seuil ≤ 0 : impossible, pas d'invention


# ─── OptionsContext branché dans Skyler ─────────────────────────────────────────

def test_skyler_options_block_scored_when_context_wired():
    from vertex.engines import skyler_core as SK
    leaps = HS.scan(_board(), 'LEAPS', sym='TST')
    octx = HS.options_context(leaps)
    p = SK.build_packet('TST', {'score': 70, 'verdict': 'ACHETER',
                                'plan': {'entry': 100, 'stop': 94, 'tp1': 106,
                                         'tp2': 112, 'tp3': 118, 'rr_res': 3.0}},
                        options_ctx=octx, as_of='10:00')
    assert p['contexts']['options']['available'] is True
    sc = SK.score40(p)
    b = sc['blocks']['options_quality']
    assert b['points'] > 0 and b['status'] in ('AVAILABLE', 'PARTIAL')
    assert 'options_quality' not in sc['insufficient_blocks']


def test_skyler_options_block_insufficient_without_context():
    from vertex.engines import skyler_core as SK
    p = SK.build_packet('TST', {'score': 70}, as_of='10:00')
    sc = SK.score40(p)
    assert sc['blocks']['options_quality']['status'] == 'INSUFFICIENT'


# ─── Route ──────────────────────────────────────────────────────────────────────

def test_scanner_route():
    import terminal
    from vertex.app.state import scan_state
    saved = scan_state.get('options_board')
    scan_state['options_board'] = _board()
    try:
        c = terminal.app.test_client()
        d = c.get('/api/options/scanner/LEAPS?sym=TST').get_json()
        assert d['available'] is True
        assert all(180 <= x['dte'] <= 540 for x in d['candidates'])
        assert d['candidates'][0].get('double_prob') is not None
        bad = c.get('/api/options/scanner/NOPE?sym=TST').get_json()
        assert bad['available'] is False
    finally:
        if saved is None:
            scan_state.pop('options_board', None)
        else:
            scan_state['options_board'] = saved


def test_scanner_route_calcule_la_probabilite_sur_la_forme_reelle_du_board():
    """MESURE : `build_board` (legacy_engine.py:437) n'écrit AUCUNE clé 'spot'.
    La route appelait `double_probability(spot=c.get('spot'))` SANS repli — seul
    point d'appel du fichier dans ce cas — et 100 % des candidats des 4 univers
    (LEAPS, TACTICAL, SWING, SWING_3_6M) étaient refusés avec le motif « entrée
    invalide — cours absent », alors que le même processus servait 230,36 $ pour
    NVDA au même instant sur /scenarios, /gex-radar et /chain.

    L'ancienne assertion `double_prob is not None` était satisfaite par un DICT
    DE REFUS : elle ne distinguait pas « calculé » de « refusé ». Ce banc part de
    la forme RÉELLE du board (pas de 'spot', `spread`/`vol` au lieu de
    `spread_pct`/`volume`) et exige un calcul, plus le lignage du cours."""
    import terminal
    from vertex.app.state import scan_state
    reel = [{'sym': 'NVDA', 'type': 'CALL', 'bucket': 'long', 'exp': '2027-03-19',
             'dte': 193, 'strike': 230.0, 'delta': 0.75, 'iv': 42.7, 'cost': 2860,
             'oi': 4615, 'vol': 675, 'spread': 6.5, 'bid': 6.0, 'ask': 6.4,
             'quality': 61, 'stale': False,
             'liquidity_coverage': {'quoted_bid_ask': True, 'volume_present': True}}]
    assert 'spot' not in reel[0], 'la forme réelle du board ne porte pas de cours'
    saved_board = scan_state.get('options_board')
    saved_detail = scan_state.get('detail')
    scan_state['options_board'] = reel
    scan_state['detail'] = {'NVDA': {'price': 230.36}}
    try:
        d = terminal.app.test_client().get('/api/options/scanner/LEAPS?sym=NVDA').get_json()
        cand = d['candidates'][0]
        dp = cand['double_prob']
        assert dp['available'] is True, dp.get('reason')
        assert 0.0 <= dp['probability'] <= 1.0
        assert dp['status'] == 'ESTIMATED'
        #  Le repli est NOMMÉ : le cours vient du scan, pas de la cotation du
        #  contrat — sans ce lignage, le correctif recréerait une fausse précision.
        assert cand['spot'] == 230.36
        assert cand['spot_source'] == 'scan.detail.price'
        #  Le spread mesuré du board réel est lu et JUGÉ (plus « indisponible »).
        assert cand['spread_pct'] == 6.5 and cand['volume'] == 675
        assert 'spread indisponible' not in cand['mandate_reasons']
    finally:
        if saved_board is None:
            scan_state.pop('options_board', None)
        else:
            scan_state['options_board'] = saved_board
        if saved_detail is None:
            scan_state.pop('detail', None)
        else:
            scan_state['detail'] = saved_detail


def test_scanner_sans_cours_nulle_part_refuse_honnetement():
    """Contre-épreuve : quand NI le contrat NI le detail du scan ne portent de
    cours, le refus « cours absent » redevient vrai et doit rester servi."""
    import terminal
    from vertex.app.state import scan_state
    reel = [{'sym': 'ZZZ', 'type': 'CALL', 'exp': '2027-03-19', 'dte': 193,
             'strike': 230.0, 'delta': 0.75, 'iv': 42.7, 'cost': 2860,
             'oi': 4615, 'vol': 675, 'spread': 6.5, 'quality': 61}]
    saved_board = scan_state.get('options_board')
    saved_detail = scan_state.get('detail')
    scan_state['options_board'] = reel
    scan_state['detail'] = {}
    try:
        d = terminal.app.test_client().get('/api/options/scanner/LEAPS?sym=ZZZ').get_json()
        cand = d['candidates'][0]
        assert cand['spot'] is None and cand['spot_source'] is None
        assert cand['double_prob']['available'] is False
    finally:
        if saved_board is None:
            scan_state.pop('options_board', None)
        else:
            scan_state['options_board'] = saved_board
        if saved_detail is None:
            scan_state.pop('detail', None)
        else:
            scan_state['detail'] = saved_detail


def test_volatilite_ne_fabrique_pas_un_iv_rank_depuis_la_structure_par_terme():
    """MESURE : /api/options/volatility passait min/max des IV du board comme
    couloir [low, high] à `volatility.iv_rank`, qui le documente « SUR 52 SEM. ».
    Zéro historique n'entrait dans le calcul. NVDA, 3 contrats (36,0 / 41,5 /
    42,7 %) : (0,415-0,36)/(0,427-0,36) = « IV rank 82 », régime ELEVEE, verdict
    DEFAVORABLE. MSFT, 2 contrats d'IV quasi égales (33,0 et 32,7 %, écart
    0,3 pt) : « IV rank 100 » PAR CONSTRUCTION (avec n=2 la médiane est le max),
    avec `uncertainties` vide et confiance 0,6 — pendant que /api/options/
    environment déclarait au même as_of « IV rank indisponible ».

    Tant qu'aucune série d'IV historique n'est câblée, la carte doit dire
    INCONNU et ne publier aucun chiffre d'IV rank."""
    import json

    import terminal
    from vertex.app.state import scan_state

    def contrat(strike, iv, dte):
        return {'sym': 'NVDA', 'type': 'CALL', 'exp': '2027-03-19', 'dte': dte,
                'strike': strike, 'iv': iv, 'oi': 1000, 'spread': 2.0,
                'cost': 500, 'quality': 60}

    saved_board = scan_state.get('options_board')
    scan_state['options_board'] = [contrat(245, 36.0, 46), contrat(226, 41.5, 102),
                                   contrat(230, 42.7, 193)]
    try:
        d = terminal.app.test_client().get('/api/options/volatility/NVDA').get_json()
    finally:
        if saved_board is None:
            scan_state.pop('options_board', None)
        else:
            scan_state['options_board'] = saved_board
    assert d['iv_rank'] is None
    assert d['interpretation']['status'] == 'INCONNU'
    brut = json.dumps(d, ensure_ascii=False)
    assert 'IV rank 82' not in brut
    assert 'ELEVEE' not in brut
    #  La seule mention autorisée d'« IV rank » est la NOMINATION de son absence.
    for phrase in ('IV rank 100', 'IV rank 8', 'IV rank 6'):
        assert phrase not in brut, phrase


def test_options_leaps_view_has_universe_scanner():
    """Gardien LOT 8c : la vue LEAPS expose le scanner par univers."""
    import terminal
    body = terminal.app.test_client().get('/options?view=leaps').get_data(as_text=True)
    assert 'vx-sc-out' in body
    assert 'options-scanner.js' in body
    assert 'TACTICAL' in body and 'SWING' in body


def _closes_mesurees():
    """21 clôtures déterministes (marche aléatoire bornée) — assez pour que
    `volatility.realized_vol` (fenêtre 20) rende une mesure, jamais None."""
    closes, graine = [230.0], 7
    for _ in range(20):
        graine = (graine * 1103515245 + 12345) % 2147483648
        closes.append(round(closes[-1] * (1 + ((graine % 2001) - 1000) / 1000.0 * 0.03), 2))
    return closes


def test_la_prime_iv_rv_mesuree_survit_a_l_absence_d_iv_rank():
    """RÉGRESSION MESURÉE le 2026-09-06, puis corrigée ici.

    En fermant la fabrication d'IV rank, `interpret_volatility` a gagné une
    sortie anticipée `unknown()` dès que rank ET percentile manquent — AVANT
    d'avoir regardé la prime IV/RV. Mesure de l'appel avec 21 clôtures réelles
    et IV médiane 41,5 % : `positive_evidence []`, `negative_evidence []`.
    La prime IV/RV est pourtant la SEULE grandeur réellement mesurée de la
    carte Volatilité (vol réalisée close-to-close sur des clôtures servies) :
    une absence sur l'IV rank effaçait une mesure sur une AUTRE grandeur.

    Contrat rétabli : le verdict de cherté reste INCONNU (il se lit sur le
    rank), la prime mesurée est servie et l'absence d'IV rank est nommée."""
    from vertex.options import interpretation as oi
    from vertex.options import volatility as vol

    closes = _closes_mesurees()
    rv = vol.realized_vol(closes)
    assert rv is not None, 'la fixture doit produire une vol réalisée mesurable'
    prem = vol.iv_rv_premium(0.415, rv)

    d = oi.interpret_volatility('NVDA', current_iv=0.415, iv_low=None,
                                iv_high=None, closes=closes, source='SCAN')
    #  Aucun verdict fabriqué : sans rank, la cherté reste INCONNUE.
    assert d['status'] == 'INCONNU'
    assert d['confidence'] is None                 # non mesurable, jamais gonflée
    preuves = d['positive_evidence'] + d['negative_evidence']
    assert len(preuves) == 1, preuves
    assert 'vol réalisée' in preuves[0]
    assert ('%.2f' % prem) in preuves[0]           # la MESURE, pas une paraphrase
    assert any('IV rank' in u for u in d['uncertainties'])
    #  Et aucun chiffre d'IV rank ne réapparaît par la bande.
    import json
    brut = json.dumps(d, ensure_ascii=False)
    assert 'IV rank 8' not in brut and 'ELEVEE' not in brut


def test_sans_cloture_la_carte_volatilite_reste_un_inconnu_nu():
    """L'autre moitié du contrat : sans clôture, il n'y a AUCUNE mesure à
    servir — la carte doit rester un INCONNU nu, sans lecture dominante
    fabriquée. Mesure : positive_evidence [] et dominant_reading ''."""
    from vertex.options import interpretation as oi
    d = oi.interpret_volatility('NVDA', current_iv=0.415, iv_low=None,
                                iv_high=None, closes=None, source='SCAN')
    assert d['status'] == 'INCONNU'
    assert d['dominant_reading'] == ''
    assert d['positive_evidence'] == [] and d['negative_evidence'] == []


def test_la_carte_volatilite_inconnue_ne_rend_pas_le_verdict_qu_elle_declare_impossible():
    """RÉGRESSION INTRODUITE PAR LE CORRECTIF PRÉCÉDENT, mesurée et fermée ici.

    En donnant un propriétaire UNIQUE à la phrase de prime IV/RV pour les deux
    chemins, sa queue NORMATIVE a été transportée sur le chemin INCONNU. La
    carte se contredisait alors dans la même réponse — mesure du 2026-09-06
    (IV 0,415, 21 clôtures déterministes, vol réalisée 0,2237, prime +0,1913) :

      dominant_reading  « Cherté non classable : ni IV rank ni IV percentile
                          ne sont mesurés ici… »
      strategy_impact   « Aucun verdict de cherté… »
      negative_evidence ['IV au-dessus de la vol réalisée (prime +0.19) :
                          premium payé cher']   ← un verdict de cherté

    « premium payé cher » EST le verdict que les deux autres champs déclarent
    impossible : « cher » se lit sur le rank, la grandeur justement absente.
    La prime, elle, est bien MESURÉE — c'est la QUALIFICATION qui était de
    trop, pas le chiffre.

    Contrat : sur le chemin INCONNU, la mesure NUE ; sur le chemin classable,
    où le rank porte le verdict, la formulation complète."""
    from vertex.options import interpretation as oi

    closes = _closes_mesurees()
    inconnu = oi.interpret_volatility('NVDA', current_iv=0.415, iv_low=None,
                                      iv_high=None, closes=closes, source='SCAN')
    assert inconnu['status'] == 'INCONNU'
    preuves = inconnu['positive_evidence'] + inconnu['negative_evidence']
    assert len(preuves) == 1, preuves
    #  La MESURE est servie…
    assert 'vol réalisée' in preuves[0] and 'prime +' in preuves[0]
    #  …et AUCUN mot de cherté ne l'accompagne, sur une carte qui déclare
    #  qu'aucun verdict de cherté n'est possible.
    for mot in ('cher', 'bon marché'):
        assert mot not in preuves[0], (mot, preuves[0])

    #  Le chemin CLASSABLE garde la qualification : c'est là que le rank la porte.
    classable = oi.interpret_volatility('NVDA', current_iv=0.415, iv_low=0.20,
                                        iv_high=0.65, closes=closes, source='SCAN')
    assert classable['status'] != 'INCONNU'
    preuves_c = classable['positive_evidence'] + classable['negative_evidence']
    prime_c = [p for p in preuves_c if 'vol réalisée' in p]
    assert len(prime_c) == 1, preuves_c
    assert 'premium payé cher' in prime_c[0]
    #  Et la MÊME mesure y figure : la queue s'ajoute, elle ne remplace rien.
    assert 'prime +' in prime_c[0]


def test_les_deux_cartes_volatilite_peignent_la_mesure_et_nomment_l_absence():
    """Le champ `iv_rank_note` était servi par /api/options/volatility et lu par
    ZÉRO page (grep sur vertex/static : 0 occurrence) : l'explication de
    l'absence restait dans le JSON, l'humain ne lisait que « Statut inconnu ».
    Et `/options/dossier/<sym>` ne peignait QUE les incertitudes : la prime
    IV/RV, servie dans les preuves, y était invisible alors que
    `/options?view=volatility` l'imprimait. Les DEUX surfaces, ici."""
    import io
    import os
    js = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      'vertex', 'static', 'vertex', 'js', 'pages')

    def lire(nom):
        return io.open(os.path.join(js, nom), encoding='utf-8').read()

    dossier = lire('options-symbol.js')
    assert 'it.positive_evidence' in dossier and 'it.negative_evidence' in dossier
    assert 'v.iv_rank_note' in dossier
    intel = lire('options-intel.js')
    assert 'd.iv_rank_note' in intel


def test_le_scanner_cable_le_cours_sur_TOUS_les_candidats_pas_seulement_les_cinq_premiers():
    """RÉGRESSION MESURÉE : la boucle de câblage s'arrêtait à `[:5]`.

    Mesure du 2026-09-06 sur /api/options/scanner/LEAPS : les 5 premiers
    candidats portaient `spot: 230.36` (replié sur `scan_state.detail.price`)
    et TOUS les suivants gardaient `spot: null` — alors que la même valeur
    était disponible dans la même requête. Dans UNE seule charge, la clé
    `spot` changeait donc de sens selon le rang : un lecteur de la queue
    concluait à une absence de cours de marché là où il n'y avait qu'une
    boucle trop courte.

    Contrat : le cours est câblé sur 100 % des candidats, chaque ligne porte
    son `spot_source`, et l'absence de modèle de doublement sur la queue est
    NOMMÉE au lieu d'être un trou."""
    import terminal
    from vertex.app.state import scan_state

    def leaps(strike):
        #  Pas de clé `spot` : c'est la forme du board RÉEL (build_board n'en
        #  écrit aucune) — le repli sur le cours du scan est le seul chemin.
        return {'sym': 'TST', 'type': 'CALL', 'dte': 365, 'strike': strike,
                'delta': 0.80, 'oi': 2000, 'spread_pct': 2.0, 'quality': 70,
                'cost': 500, 'iv': 40.0, 'exp': '2027-03-19'}

    board = [leaps(80 + i) for i in range(9)]          # 9 candidats > les 5 câblés
    sauve_board = scan_state.get('options_board')
    sauve_detail = scan_state.get('detail')
    scan_state['options_board'] = board
    scan_state['detail'] = dict(sauve_detail or {})
    scan_state['detail']['TST'] = {'price': 230.36}
    try:
        d = terminal.app.test_client().get('/api/options/scanner/LEAPS?sym=TST').get_json()
    finally:
        if sauve_board is None:
            scan_state.pop('options_board', None)
        else:
            scan_state['options_board'] = sauve_board
        if sauve_detail is None:
            scan_state.pop('detail', None)
        else:
            scan_state['detail'] = sauve_detail

    cands = d['candidates']
    assert len(cands) == 9, len(cands)
    #  Le défaut : 5 lignes servies, 4 muettes dans la même charge.
    assert [c['spot'] for c in cands] == [230.36] * 9
    assert {c['spot_source'] for c in cands} == {'scan.detail.price'}
    #  Le modèle reste borné aux 5 meilleurs, mais son absence est motivée.
    assert all(c['double_prob']['available'] is True for c in cands[:5])
    for c in cands[5:]:
        assert c['double_prob']['available'] is False
        assert '5 meilleurs' in c['double_prob']['reason']


def test_la_barre_de_contexte_des_vues_options_a_ses_deux_emplacements_et_leur_peintre():
    """Constat 45 — VÉRIFIÉ, pas re-corrigé. Les emplacements « Sous-jacent »
    et « Fraîcheur » de la barre de contexte étaient déclarés et remplis par
    personne (« Aucun sous-jacent choisi » / « Lecture… » indéfiniment).

    Mesure du 2026-09-06 sur les 6 vues (structure, positioning, leaps,
    volatility, events, scenarios) : `vx-options-symbol` 6/6,
    `vx-opt-ctx-sym` 6/6, `vx-opt-ctx-fresh` 6/6, `options-context.js` 6/6,
    `options-intel.js` 6/6 — le peintre est chargé partout où les
    emplacements existent, et l'émetteur d'horodatage (`vx:options-fresh`,
    options-intel.js) aussi. Ce banc empêche la moitié serveur de repartir
    sans la moitié cliente : `options-context.js` sort tôt s'il ne trouve pas
    le champ de symbole, et les deux emplacements resteraient figés."""
    import terminal
    c = terminal.app.test_client()
    for vue in ('structure', 'positioning', 'leaps', 'volatility', 'events', 'scenarios'):
        b = c.get('/options?view=' + vue).get_data(as_text=True)
        for jeton in ('vx-options-symbol', 'vx-options-apply', 'vx-opt-ctx-sym',
                      'vx-opt-ctx-fresh', 'options-context.js'):
            assert jeton in b, '%s manque sur la vue %s' % (jeton, vue)
