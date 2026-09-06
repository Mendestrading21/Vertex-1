"""Vertex Team Portfolio + moteur décisionnel unique (phases 12-13)."""
import pytest

from vertex.portfolio import models as PM
from vertex.portfolio import portfolio_guard, risk_engine, stress_tests
from vertex.portfolio.team_engine import candidate_fit, team_view
from vertex.strategy import constitution as C
from vertex.strategy import executive_engine as EE

PROFILE = C.load_profile()


def make_snapshot(n_stocks=9, peak=None, price=100.0, avg_cost=90.0, cash=8000.0):
    sectors = ['Technologie', 'Santé', 'Finance', 'Industrie', 'Énergie']
    positions = []
    for i in range(n_stocks):
        positions.append(PM.Position(
            symbol=f'POS{i}', quantity=10, avg_cost=avg_cost, last_price=price,
            sector=sectors[i % len(sectors)], beta=0.7 + 0.15 * (i % 5)))
    snap = PM.PortfolioSnapshot(positions=positions, cash=cash, provenance='REAL',
                                as_of='2026-07-11T15:00:00Z', peak_equity=peak)
    return snap


# ── Positions réelles obligatoires ────────────────────────────────────
def test_portfolio_uses_real_positions():
    snap = make_snapshot()
    report = risk_engine.portfolio_risk(snap, PROFILE)
    assert report['provenance'] == 'REAL'
    bad = PM.PortfolioSnapshot(positions=snap.positions, provenance='SCANNER_BASKET')
    with pytest.raises(ValueError):
        risk_engine.portfolio_risk(bad, PROFILE)


def test_simulated_positions_must_be_explicit():
    snap = PM.simulated([PM.Position('NVDA', 10, 400, 500, sector='Technologie')],
                        cash=1000)
    assert snap.provenance == 'SIMULATED'
    assert all(p.is_simulated for p in snap.positions)
    report = risk_engine.portfolio_risk(snap, PROFILE)
    assert report['provenance'] == 'SIMULATED'


def test_le_constructeur_depuis_le_compte_courtier_n_existe_plus():
    #  Lot 2 : `from_ibkr_positions` construisait un snapshot REAL depuis les
    #  positions du COMPTE. Capacite retiree — le snapshot REAL se construit
    #  depuis les positions declarees du desk.
    assert not hasattr(PM, 'from_ibkr_positions'), (
        'from_ibkr_positions est revenu : le portefeuille ne se lit pas chez '
        'le courtier.'
    )


# ── Équipe 8-10 et remplacements ─────────────────────────────────────
def test_team_view_roles_and_slots():
    snap = make_snapshot(9)
    view = team_view(snap, PROFILE)
    assert view['stock_count'] == 9
    # slots libres = max du profil actif − 9 (V1 : 10−9=1 ; V2 : 15−9=6 — LOT 2)
    assert view['free_slots'] == PROFILE.portfolio_max_positions - 9
    assert view['provenance'] == 'REAL'
    assert set(view['by_role']) == {'ATTACKER', 'MIDFIELDER', 'DEFENDER', 'GOALKEEPER'}
    assert view['by_role']['GOALKEEPER'], 'le cash doit apparaître comme gardien'


def test_eleventh_stock_requires_replacement():
    snap = make_snapshot(10)
    fit = candidate_fit(snap, PROFILE, {'symbol': 'NEW', 'role': 'MIDFIELDER'})
    assert fit['blocked'] is True
    assert any('remplacement' in r for r in fit['reasons'])
    fit2 = candidate_fit(snap, PROFILE, {'symbol': 'NEW', 'role': 'MIDFIELDER',
                                         'replaces': 'POS3'})
    assert fit2['blocked'] is False




# ── Drawdown -25 % → aucun nouveau risque ─────────────────────────────
def test_portfolio_drawdown_blocks_new_risk():
    snap = make_snapshot(9, price=70.0, avg_cost=100.0)   # -30 % vs coût
    snap.peak_equity = (snap.equity or 0) / 0.70          # drawdown ≈ -30 %
    report = risk_engine.portfolio_risk(snap, PROFILE)
    assert report['drawdown_pct'] <= -25
    assert report['no_new_risk'] is True
    guard = portfolio_guard.guard_rules(report, PROFILE)
    assert guard['new_stock_allowed'] is False
    assert guard['new_option_allowed'] is False
    assert 'PORTFOLIO_DRAWDOWN_LIMIT' in guard['blocking_rules']
    assert guard['mandatory_reviews']


def test_stock_drawdown_triggers_review():
    snap = make_snapshot(9, price=75.0, avg_cost=100.0)   # -25 % par titre
    report = risk_engine.portfolio_risk(snap, PROFILE)
    assert any('-25.0%' in w or 'revue' in w for w in report['warnings'])


def test_max_options_blocks_new_option():
    snap = make_snapshot(9)
    report = risk_engine.portfolio_risk(
        snap, PROFILE, options_greeks=[{'delta': 0.4}, {'delta': 0.3}, {'delta': 0.2}])
    guard = portfolio_guard.guard_rules(report, PROFILE)
    assert 'MAX_OPTIONS_REACHED' in guard['blocking_rules']


# ── Stress tests ──────────────────────────────────────────────────────
def test_stress_tests_cover_required_scenarios():
    snap = make_snapshot(9)
    res = stress_tests.run_stress_tests(snap, PROFILE, options_vega_value=500.0,
                                        earnings_positions=['POS1'])
    assert set(stress_tests.SCENARIOS) <= set(res['scenarios'])
    assert res['scenarios']['SPY_MINUS_10']['impact_pct'] < \
        res['scenarios']['SPY_MINUS_5']['impact_pct'] < 0
    assert res['scenarios']['RATES_PLUS_50BP']['impact_pct'] is None, \
        'sensibilité taux inconnue → non estimé (honnête)'
    assert res['worst_case_pct'] is not None


# ── Moteur décisionnel unique ─────────────────────────────────────────
def full_packet(**kw):
    p = {'symbol': 'NVDA', 'asset_type': 'STOCK',
         'fundamental': {'score': 78},
         'catalysts': {'score': 70},
         'technical': {'score': 80, 'reward_risk': 2.4, 'timing_score': 70},
         'sentiment': {'score': 60},
         'anomalies': [],
         'portfolio_fit': {'blocked': False},
         'data_quality': {'overall': 'FRESH', 'actionable_allowed': True},
         'reconciliation': {'actionable_allowed': True},
         'guard': {'blocking_rules': [], 'mandatory_reviews': []}}
    p.update(kw)
    return p


def test_only_allowed_final_decisions():
    for pkt in (full_packet(), full_packet(fundamental={}, technical={}),
                full_packet(guard={'blocking_rules': ['NO_NEW_RISK'],
                                   'mandatory_reviews': []})):
        out = EE.decide(pkt, PROFILE)
        assert out['final_decision'] in ('ACHETER', 'RENFORCER', 'ATTENDRE',
                                         'REDUIRE', 'REFUSER')


def test_same_inputs_same_decision():
    a = EE.decide(full_packet(), PROFILE)
    b = EE.decide(full_packet(), PROFILE)
    assert a == b, 'le moteur exécutif doit être parfaitement déterministe'


def test_strong_packet_buys_weak_waits():
    assert EE.decide(full_packet(), PROFILE)['final_decision'] == 'ACHETER'
    weak = full_packet(fundamental={'score': 40}, technical={'score': 45,
                                                             'reward_risk': 1.2,
                                                             'timing_score': 40},
                       catalysts={'score': 40}, sentiment={'score': 40})
    assert EE.decide(weak, PROFILE)['final_decision'] == 'REFUSER'


def test_data_quality_caps_decision():
    pkt = full_packet(data_quality={'overall': 'STALE', 'actionable_allowed': False})
    out = EE.decide(pkt, PROFILE)
    assert out['final_decision'] == 'ATTENDRE'
    assert 'DATA_QUALITY' in out['blocking_rules']


def test_reconciliation_caps_decision():
    pkt = full_packet(reconciliation={'actionable_allowed': False})
    out = EE.decide(pkt, PROFILE)
    assert out['final_decision'] == 'ATTENDRE'


def test_guard_blocks_new_risk():
    pkt = full_packet(guard={'blocking_rules': ['PORTFOLIO_DRAWDOWN_LIMIT'],
                             'mandatory_reviews': ['revue']})
    out = EE.decide(pkt, PROFILE)
    assert out['final_decision'] == 'ATTENDRE'


def test_invalidated_held_position_reduces():
    pkt = full_packet(technical={'score': 60, 'reward_risk': 1.8, 'timing_score': 50,
                                 'thesis_invalidated': True},
                      position_held=True)
    out = EE.decide(pkt, PROFILE)
    assert out['final_decision'] == 'REDUIRE'


def test_held_strong_packet_reinforces():
    out = EE.decide(full_packet(position_held=True), PROFILE)
    assert out['final_decision'] == 'RENFORCER'


def test_output_structure_matches_spec():
    out = EE.decide(full_packet(), PROFILE)
    for key in ('symbol', 'asset_type', 'analysis_order', 'fundamental', 'catalysts',
                'technical', 'sentiment', 'anomalies', 'institutional_context',
                'portfolio_fit', 'option_selection', 'scenarios', 'execution_plan',
                'scores', 'blocking_rules', 'unknowns', 'audit_trail', 'final_decision'):
        assert key in out
    assert set(out['scores']) == {'conviction', 'risk', 'timing', 'asymmetry',
                                  'data_quality'}
    assert out['analysis_order'][0] == 'FUNDAMENTAL'


def test_single_decision_source():
    """Le vocabulaire final de la constitution n'est produit QUE par executive_engine.

    Les anciens moteurs (comité, scorecard, decide) existent encore comme
    ENTRÉES mais aucun module en dehors de vertex/strategy/ ne doit définir
    la liste des 5 décisions constitutionnelles complète.
    """
    import pathlib
    root = pathlib.Path(EE.__file__).resolve().parents[2]
    offenders = []
    for path in (root / 'vertex').rglob('*.py'):
        rel = path.relative_to(root)
        if 'strategy' in rel.parts:
            continue
        if 'ui' in rel.parts:
            continue  # la couche d'affichage RENDS le vocabulaire, elle ne décide pas
        text = path.read_text(encoding='utf-8', errors='ignore')
        if all(d in text for d in ('ACHETER', 'RENFORCER', 'REDUIRE', 'REFUSER')):
            offenders.append(str(rel))
    assert not offenders, ('modules hors constitution définissant le vocabulaire '
                           f'décisionnel complet: {offenders}')


def test_audit_du_timing_nomme_la_valeur_reellement_substituee():
    """CONSTAT 5 (nuance) — l'audit annonçait 50.0 pendant qu'il substituait 0.0.

    MESURE : `decide({'technical': None})` rendait `scores.timing = 0.0` sous la
    ligne d'audit « timing non mesuré — neutre 50.0 substitué ». La branche
    `timing = 50.0 if tech else 0.0` a DEUX issues, le message n'en nommait
    qu'une. L'audit est le canal qui explique le chiffre servi : s'il en nomme
    un autre, il ment sur la substitution qu'il est censé avouer. Aucune route
    du scan n'atteint cette branche (le paquet porte toujours un bloc
    technique), mais `decide()` est publique et appelée avec des paquets
    construits à la main.
    """
    sans_tech = EE.decide({'symbol': 'X', 'technical': None})
    ligne = [l for l in sans_tech['audit_trail'] if 'timing non mesuré' in l]
    assert len(ligne) == 1
    assert sans_tech['scores']['timing'] == 0.0
    assert '0.0 substitué' in ligne[0] and '50.0' not in ligne[0]
    assert 'sans bloc technique' in ligne[0]
    # L'autre issue reste dite avec SA valeur.
    avec_tech = EE.decide({'symbol': 'X', 'technical': {'score': 70}})
    ligne = [l for l in avec_tech['audit_trail'] if 'timing non mesuré' in l]
    assert avec_tech['scores']['timing'] == 50.0
    assert '50.0 substitué' in ligne[0]
