"""tests/test_options_correctness.py — SKYLER LOT 1 : correctness options.

Tests ROUGES d'abord (procédure OPTIONS_CORRECTNESS.md §Modification d'un calcul) :
1. perte théoriquement ILLIMITÉE des expositions nettes vendeuses de calls
   (max_loss_unbounded — le flag prime sur toute valeur issue d'une grille finie) ;
2. unité d'IV EXPLICITE (frontière de normalisation typée, plus d'heuristique
   silencieuse dans le cœur métier) ;
3. refus STRUCTURÉS des entrées invalides (spot, strike, prime, qty, DTE, IV) ;
4. taux/dividende configurables et TRAÇABLES (bloc model) ;
5. honnêteté d'exécution (spread/slippage déclaré, jamais implicite) ;
6. filtrage des stratégies selon le PROFIL ACTIF (V1 : short_options=false,
   credit_spreads=false — jamais « recommandée » si hors mandat).

Chaque valeur attendue est calculable à la main. Aucun ordre, lecture seule.
"""
import math

import pytest

from vertex.engines import multileg_lab as ml
from vertex.options import iv_units


# ─── 1. Pertes illimitées (expositions nettes vendeuses de calls) ───────────────

def test_naked_short_call_loss_unbounded():
    """Short call nu : gain = prime (borné), perte → ∞ quand le cours monte.
    À la main : crédit 5×100 = 500 $ = gain max ; perte non bornée vers le haut."""
    r = ml.analyze_strategy([{'type': 'call', 'strike': 100, 'premium': 5, 'qty': -1}],
                            spot=100, iv=0.30, days_to_exp=30)
    assert r['available'] is True
    assert r['max_loss_unbounded'] is True
    assert r['max_loss'] is None            # le flag illimité PRIME sur la grille finie
    assert r['max_profit_unbounded'] is False
    assert r['max_profit'] == pytest.approx(500.0, abs=1.0)
    assert r['breakevens'] == [pytest.approx(105.0, abs=0.5)]


def test_net_short_call_ratio_unbounded():
    """Ratio 1×2 (1 long, 2 shorts) : pente terminale = −1 call net → perte illimitée."""
    legs = [{'type': 'call', 'strike': 100, 'premium': 5, 'qty': 1},
            {'type': 'call', 'strike': 110, 'premium': 2, 'qty': -2}]
    r = ml.analyze_strategy(legs, spot=100, iv=0.30, days_to_exp=30)
    assert r['max_loss_unbounded'] is True
    assert r['max_loss'] is None


def test_covered_call_is_bounded():
    """100 actions + 1 call vendu : pente terminale nulle → perte bornée (à cours 0 :
    −100×100 + 1×100×3 = −9 700 $).

    La prime vaut 3 et non 2 : à 2, le résultat tombait exactement sur un
    montant du desk réel de la machine de développement, et le gardien
    `test_aucun_patrimoine_publie` ne peut pas distinguer une coïncidence
    arithmétique d'une fuite. Lever la coïncidence coûte un chiffre ; laisser
    une exemption dans le gardien coûterait sa fiabilité.
    """
    legs = [{'type': 'stock', 'premium': 100, 'qty': 100},
            {'type': 'call', 'strike': 110, 'premium': 3, 'qty': -1}]
    r = ml.analyze_strategy(legs, spot=100, iv=0.30, days_to_exp=30)
    assert r['max_loss_unbounded'] is False
    assert r['max_loss'] == pytest.approx(-9700.0, abs=50.0)


def test_bounded_strategies_keep_numeric_max_loss():
    """Non-régression : short put (borné, cours ≥ 0) garde sa perte max numérique."""
    r = ml.analyze_strategy([{'type': 'put', 'strike': 100, 'premium': 5, 'qty': -1}],
                            spot=105, iv=0.30, days_to_exp=30)
    assert r['max_loss_unbounded'] is False
    assert r['max_loss'] == pytest.approx(-9500.0, abs=50.0)


# ─── 2. Unité d'IV explicite ────────────────────────────────────────────────────

def test_normalize_iv_explicit_units():
    assert iv_units.normalize_iv(40.4, iv_units.PERCENT) == pytest.approx(0.404)
    assert iv_units.normalize_iv(0.404, iv_units.DECIMAL) == pytest.approx(0.404)


def test_normalize_iv_rejects_unknown_unit_and_bad_values():
    with pytest.raises(ValueError):
        iv_units.normalize_iv(0.4, 'BANANES')
    assert iv_units.normalize_iv(None, iv_units.PERCENT) is None
    assert iv_units.normalize_iv(float('nan'), iv_units.DECIMAL) is None
    assert iv_units.normalize_iv(float('inf'), iv_units.PERCENT) is None
    assert iv_units.normalize_iv(-3, iv_units.PERCENT) is None
    assert iv_units.normalize_iv(0, iv_units.DECIMAL) is None


def test_legacy_board_frontier_is_labeled():
    """La détection legacy (board mixte %/décimal) vit dans UNE frontière documentée
    qui étiquette ce qu'elle a détecté — plus d'heuristique muette dans le cœur."""
    v, unit, warn = iv_units.from_legacy_board(40.4)
    assert v == pytest.approx(0.404) and unit == iv_units.PERCENT and warn
    v2, unit2, _ = iv_units.from_legacy_board(0.30)
    assert v2 == pytest.approx(0.30) and unit2 == iv_units.DECIMAL
    v3, unit3, _ = iv_units.from_legacy_board(None)
    assert v3 is None and unit3 is None


def _board(iv=0.30):
    return [
        {'sym': 'TST', 'type': 'CALL', 'strike': 100, 'exp': '2026-09-18', 'dte': 45, 'iv': iv, 'cost': 500},
        {'sym': 'TST', 'type': 'PUT', 'strike': 100, 'exp': '2026-09-18', 'dte': 45, 'iv': iv, 'cost': 500},
        {'sym': 'TST', 'type': 'CALL', 'strike': 106, 'exp': '2026-09-18', 'dte': 45, 'iv': iv, 'cost': 200},
        {'sym': 'TST', 'type': 'PUT', 'strike': 94, 'exp': '2026-09-18', 'dte': 45, 'iv': iv, 'cost': 200},
    ]


def test_strategies_result_declares_iv_unit():
    res = ml.strategies_for_symbol(_board(), 'TST', 100.0, bias='bullish')
    assert res['available'] is True
    assert res['iv_unit'] == 'DECIMAL'
    assert res['iv'] == pytest.approx(0.30, abs=1e-6)


def test_core_refuses_percent_iv():
    """Une IV « 30 » (pourcentage) qui atteint le cœur = erreur d'unité certaine →
    refus structuré, jamais une PoP absurde à 100 %."""
    r = ml.analyze_strategy([{'type': 'call', 'strike': 100, 'premium': 5, 'qty': 1}],
                            spot=100, iv=30, days_to_exp=30)
    assert r['available'] is False
    assert any(x['field'] == 'iv' for x in r['refusals'])


# ─── 3. Refus structurés ────────────────────────────────────────────────────────

def test_refusal_negative_spot_structured():
    r = ml.analyze_strategy([{'type': 'call', 'strike': 100, 'premium': 5, 'qty': 1}],
                            spot=-5, iv=0.30, days_to_exp=30)
    assert r['available'] is False
    assert any(x['field'] == 'spot' for x in r['refusals'])


def test_refusal_bad_strike_and_premium_and_dte():
    r = ml.analyze_strategy([{'type': 'call', 'strike': -100, 'premium': 5, 'qty': 1}],
                            spot=100, iv=0.30, days_to_exp=30)
    assert r['available'] is False and any(x['field'] == 'strike' for x in r['refusals'])
    r2 = ml.analyze_strategy([{'type': 'call', 'strike': 100, 'premium': -5, 'qty': 1}],
                             spot=100, iv=0.30, days_to_exp=30)
    assert r2['available'] is False and any(x['field'] == 'premium' for x in r2['refusals'])
    r3 = ml.analyze_strategy([{'type': 'call', 'strike': 100, 'premium': 5, 'qty': 1}],
                             spot=100, iv=0.30, days_to_exp=-3)
    assert r3['available'] is False and any(x['field'] == 'days_to_exp' for x in r3['refusals'])


def test_refusal_nan_inputs():
    r = ml.analyze_strategy([{'type': 'call', 'strike': 100, 'premium': float('nan'), 'qty': 1}],
                            spot=100, iv=0.30, days_to_exp=30)
    assert r['available'] is False and any(x['field'] == 'premium' for x in r['refusals'])
    r2 = ml.analyze_strategy([{'type': 'call', 'strike': 100, 'premium': 5, 'qty': 1}],
                             spot=float('inf'), iv=0.30, days_to_exp=30)
    assert r2['available'] is False and any(x['field'] == 'spot' for x in r2['refusals'])


def test_missing_premium_still_refused_with_reason():
    """Comportement historique conservé : prime manquante → refus honnête."""
    r = ml.analyze_strategy([{'type': 'call', 'strike': 100, 'premium': None, 'qty': 1}],
                            spot=100, iv=0.30, days_to_exp=30)
    assert r['available'] is False
    assert 'prime manquante' in r['reason']


# ─── 4. Taux / dividende configurables et traçables ─────────────────────────────

def test_model_provenance_traced():
    r = ml.analyze_strategy([{'type': 'call', 'strike': 100, 'premium': 5, 'qty': 1}],
                            spot=100, iv=0.30, days_to_exp=30)
    m = r['model']
    assert m['type'] == 'lognormal_risk_neutral'
    assert m['r'] == pytest.approx(0.045)
    assert m['q'] == pytest.approx(0.0)
    assert m['iv_unit'] == 'DECIMAL'
    assert m['premium_basis'] == 'declared'


def test_dividend_yield_lowers_call_delta():
    """q > 0 abaisse le delta du call (e^{-qT}·N(d1), d1 décroît en q) — vérifiable à la main."""
    base = ml.analyze_strategy([{'type': 'call', 'strike': 100, 'premium': 5, 'qty': 1}],
                               spot=100, iv=0.30, days_to_exp=180)
    withq = ml.analyze_strategy([{'type': 'call', 'strike': 100, 'premium': 5, 'qty': 1}],
                                spot=100, iv=0.30, days_to_exp=180, q=0.05)
    assert withq['greeks']['delta'] < base['greeks']['delta']
    assert withq['model']['q'] == pytest.approx(0.05)


def test_default_q_zero_keeps_exact_bs_delta():
    """Non-régression : q par défaut = 0 → delta = N(d1) exact (calcul indépendant)."""
    S, K, iv, T, rr = 100.0, 100.0, 0.30, 30 / 365.0, 0.045
    d1 = (math.log(S / K) + (rr + iv * iv / 2) * T) / (iv * math.sqrt(T))
    expected = 100 * 0.5 * (1.0 + math.erf(d1 / math.sqrt(2)))   # qty 1 × mult 100 × N(d1)
    r = ml.analyze_strategy([{'type': 'call', 'strike': K, 'premium': 5, 'qty': 1}],
                            spot=S, iv=iv, days_to_exp=30)
    assert r['greeks']['delta'] == pytest.approx(expected, abs=0.05)


# ─── 5. Honnêteté d'exécution (spread/slippage) ─────────────────────────────────

def test_execution_declares_no_slippage_by_default():
    r = ml.analyze_strategy([{'type': 'call', 'strike': 100, 'premium': 5, 'qty': 1}],
                            spot=100, iv=0.30, days_to_exp=30)
    ex = r['execution']
    assert ex['spread_slippage_included'] is False
    assert 'déclarée' in ex['note'] or 'declared' in ex['note']


def test_execution_adverse_fill_with_bid_ask():
    """Avec bid/ask déclarés : rempli défavorable = achat à l'ask, vente au bid.
    À la main : long call ask 5.5 → 550 $ ; short call bid 1.8 → −180 $ ; net 370 $."""
    legs = [{'type': 'call', 'strike': 100, 'premium': 5, 'qty': 1, 'bid': 4.5, 'ask': 5.5},
            {'type': 'call', 'strike': 110, 'premium': 2, 'qty': -1, 'bid': 1.8, 'ask': 2.2}]
    r = ml.analyze_strategy(legs, spot=100, iv=0.30, days_to_exp=30)
    ex = r['execution']
    assert ex['spread_slippage_included'] is True
    assert ex['net_premium_adverse'] == pytest.approx(370.0, abs=0.5)
    assert ex['net_premium_declared'] == pytest.approx(300.0, abs=0.5)


# ─── 6. Filtrage par le profil actif (V1 : jamais de vendeuse recommandée) ──────

def test_short_leg_strategies_hors_mandat_never_recommended():
    res = ml.strategies_for_symbol(_board(), 'TST', 100.0, bias='neutral')
    assert res['available'] is True
    by_kind = {s['kind']: s for s in res['strategies']}
    # l'iron condor (jambes vendues + crédit) est hors mandat V1 et jamais recommandé
    if 'iron_condor' in by_kind:
        ic = by_kind['iron_condor']
        assert ic['hors_mandat'] is True
        assert ic['recommended'] is False
        assert ic['mandate_reasons']
    # la recommandée, si elle existe, n'a AUCUNE jambe vendue
    reco = [s for s in res['strategies'] if s.get('recommended')]
    for s in reco:
        assert all((l.get('qty') or 0) > 0 for l in s['legs'])
        assert s['hors_mandat'] is False


def test_unbounded_loss_never_recommended():
    naked = ml.analyze_strategy([{'type': 'call', 'strike': 100, 'premium': 5, 'qty': -1}],
                                spot=100, iv=0.30, days_to_exp=30)
    naked['kind'] = 'naked_call'
    lc = ml.analyze_strategy([{'type': 'call', 'strike': 100, 'premium': 5, 'qty': 1}],
                             spot=100, iv=0.30, days_to_exp=30)
    lc['kind'] = 'long_call'
    ranked = ml.rank_strategies([naked, lc], bias='bullish')
    nk = next(s for s in ranked if s['kind'] == 'naked_call')
    assert nk['recommended'] is False
    assert nk['hors_mandat'] is True
    assert any('illimit' in r for r in nk['mandate_reasons'])


def test_dte_mandate_flag_present():
    """DTE 45 < minimum absolu 60 du profil V1 → signalé honnêtement (labo, pas mandat)."""
    res = ml.strategies_for_symbol(_board(), 'TST', 100.0, bias='bullish')
    md = res.get('mandate')
    assert md is not None
    assert md['dte_ok'] is False
    assert md['profile_version'] is not None
