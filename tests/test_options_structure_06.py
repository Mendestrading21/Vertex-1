"""tests/test_options_structure_06.py — PR n°6 (gardiens Options).

Options répond « cette structure offre-t-elle une asymétrie suffisante ? » :
Carte-Verdict + Carte-Scénario + payoff canonique (multileg_lab) + Greeks
interprétés + liquidité + LEAPS explicable + comparaison. Positions options =
domicile canonique (réconcilié avec Portefeuille). Garde-fou perdants (option).
READONLY absolu. DATA_INSUFFICIENT honnête.
"""
import os

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(scope='module')
def client():
    import terminal
    terminal.app.config['TESTING'] = True
    return terminal.app.test_client()


def _read(rel):
    with open(os.path.join(ROOT, rel), encoding='utf-8') as fh:
        return fh.read()


JS = 'vertex/static/vertex/js/pages/options-structure.js'
PAGE = 'vertex/ui/pages/options_intel_page.py'
PF = 'vertex/ui/pages/portfolio_page.py'


# ── Vues & routes ────────────────────────────────────────────────────────
def test_options_new_views_registered():
    src = _read(PAGE)
    assert "('structure', 'Structure')" in src
    #  Lot 38 : la vue leaps EST le Scanner du contrat — libellé honnête,
    #  la clé d'URL ne change pas.
    assert "('leaps', 'Scanner LEAPS')" in src
    assert "('positions', 'Positions')" in src
    # défaut = structure (Carte-Verdict d'abord)
    assert "def render(view: str = 'structure')" in src


def test_options_legacy_views_still_served():
    """overview/radar/scenarios restent des routes valides (tests existants)."""
    src = _read(PAGE)
    assert '_ALL_VIEWS' in src
    for v in ('overview', 'radar', 'scenarios', 'volatility', 'events'):
        assert v in src


def test_options_pages_render_200(client):
    for v in ('structure', 'leaps', 'positions', 'volatility', 'events',
              'overview', 'radar', 'scenarios'):
        r = client.get('/options?view=' + v)
        assert r.status_code == 200, v
    # défaut sans view = 200 + h1 Options
    r = client.get('/options')
    assert (r.status_code == 200
            and '<h1 class="vx2-title">Options</h1>' in r.get_data(as_text=True))


# ── Carte-Verdict (LOT A) ────────────────────────────────────────────────
def test_verdict_card_present_and_honest():
    src = _read(JS)
    assert 'function verdictCard' in src and 'vx-verdict-card' in src
    for verdict in ('Asymétrie excellente', 'Structure intéressante mais chère',
                    'Risque/temps médiocre', 'Liquidité insuffisante',
                    'Données insuffisantes', 'Attendre une meilleure entrée'):
        assert verdict in src, f'verdict manquant : {verdict}'
    # ratio d'asymétrie = gain exceptionnel / perte max
    assert "d'asymétrie" in src or 'asymétrie' in src
    # aucune probabilité inventée : la PoP vient du moteur et reste estimation
    assert 'estimation' in src.lower()


# ── Carte-Scénario (LOT C) — payoff à l'échéance distinct d'avant échéance ──
def test_scenario_card_expiry_labeled():
    src = _read(JS)
    assert 'function renderScenarios' in src
    assert 'Pessimiste' in src and 'Probable' in src and 'Exceptionnel' in src
    assert "à l'échéance" in src
    # distinction explicite payoff échéance vs valeur avant échéance
    assert 'valeur-temps' in src or 'avant l' in src


# ── Payoff canonique (LOT D) — un seul moteur ────────────────────────────
def test_payoff_uses_canonical_engine():
    src = _read(JS)
    assert '/api/options/strategies/' in src
    assert 'multileg_lab' in src
    assert 'function renderPayoff' in src
    # aucun autre moteur de payoff local
    assert 'option-payoff.js' not in src


# ── Greeks interprétés (LOT E) ───────────────────────────────────────────
def test_greeks_always_interpreted_or_insufficient():
    src = _read(JS)
    assert 'function renderGreeks' in src
    assert 'Insuffisant' in src  # greeks non fiables => état honnête, écrit en français (refonte dashboards)
    assert 'par +1 $ du sous-jacent' in src  # interprétation delta en langage clair
    assert 'rosion' in src                   # interprétation theta (érosion de la valeur temps)


# ── Liquidité (LOT G) ────────────────────────────────────────────────────
def test_liquidity_states_explicit_no_zero_for_missing():
    src = _read(JS)
    assert 'function liqState' in src
    for s in ('Excellente', 'Acceptable', 'Médiocre', 'Insuffisante'):
        assert s in src
    # bid/ask ou OI absent => insuffisante (jamais remplacé par zéro)
    assert 'non évaluable' in src


# ── LEAPS explicable (LOT B) ─────────────────────────────────────────────
def test_leaps_score_is_explainable():
    src = _read(JS)
    assert 'function leapsScore' in src
    assert 'aucun score opaque' in src
    # le temps seul n'est pas une thèse
    assert "temps seul n'est pas une thèse" in src or 'durée ne remplace pas la thèse' in src


# ── Comparaison (LOT I) — matrice, pas radar ─────────────────────────────
def test_comparison_matrix_not_radar():
    src = _read(JS)
    assert 'function renderCompare' in src
    assert 'Comparer les structures' in src
    assert 'vx-table' in src  # matrice tabulaire


# ── Garde-fou perdants option (LOT K) — test gardien exigé ───────────────
def test_option_loser_reinforcement_forbidden():
    src = _read(JS)
    assert 'function optNextAction' in src
    assert 'Renforcement interdit : aucune confirmation positive détectée' in src
    # jamais renforcer parce que la prime a baissé
    assert 'prime a baissé' in src
    # règles gagnants indicatives
    assert 'sécuriser 25-50 %' in src and '+100' in src


# ── Réconciliation Portefeuille ↔ Options (LOT J) ────────────────────────
def test_portfolio_options_is_summary_with_link():
    src = _read(PF)
    # le Portefeuille renvoie vers le domicile canonique
    assert '/options?view=positions' in src
    assert "résumé d'exposition" in src.lower() or 'RÉSUMÉ' in src
    # le détail lourd (drawer/payoff combiné par position) a quitté le Portefeuille
    assert 'renderCombinedOptions' not in src
    assert 'openOptionDrawer' not in src


def test_options_positions_is_canonical_home():
    src = _read(JS)
    assert 'function loadPositions' in src
    assert 'domicile canonique' in src.lower()


# ── READONLY absolu (§21) ────────────────────────────────────────────────
def test_no_order_execution_in_options():
    src = _read(JS).lower()
    for bad in ('acheter maintenant', 'passer un ordre', 'envoyer un ordre',
                'place order', 'buy order', 'sell order', 'transmit'):
        assert bad not in src, f'chemin d’exécution interdit : {bad}'
