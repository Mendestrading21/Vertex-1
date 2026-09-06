"""
tests/test_reasoning.py — Le moteur de raisonnement (Ch. XVIII).

Trois scénarios conditionnels, invalidations explicites, conviction ≠ prédiction.
"""

from vertex.engines import reasoning


_D = {
    'symbol': 'TEST', 'price': 100,
    'plan': {'entry': 100, 'stop': 92, 'tp1': 108, 'tp2': 116, 'tp3': 130,
             'resistance': 104, 'rr_res': 2.5},
    'signals': {'above200': True},
}


def test_three_scenarios_present():
    sc = reasoning.scenarios(_D, {'lean': 60}, 'BUY')
    names = [s['name'] for s in sc]
    assert names == ['Haussier', 'Central', 'Baissier']
    for s in sc:
        assert s['trigger'] and s['invalidation']


def test_aucune_probabilite_n_est_emise_sans_calibration():
    """CONSTAT 39 — ces trois assertions REMPLACENT le gel du vocabulaire probabiliste.

    Les tests précédents épinglaient le défaut : `likelihood ∈ {plausible,
    possible, peu probable}` et des `weight` sommant à 100, dérivés du seul
    `committee.lean`. MESURE de l'anti-calibration, par appel direct :
    lean=10 → 15/25/60, lean=50 → 45/**9**/45, lean=90 → 60/25/15. Au comité
    parfaitement partagé — incertitude MAXIMALE — le scénario « Central »
    recevait le poids le plus faible possible, les deux extrêmes 45 chacun :
    le résidu `base = max(0.1, 1 - bull - bear)` inversait le sens du mot.
    Aucune source, aucune calibration, aucun marqueur ; l'invariant 7 interdit
    d'inventer une probabilité, pas seulement de l'afficher. Le dépôt possédait
    déjà la version honnête (skyler_core.scenarios : `probability: None` +
    note + `model.calibrated False`) : ce module s'y aligne.
    """
    for lean in (10, 50, 80, 90):
        for s in reasoning.scenarios(_D, {'lean': lean}, 'BUY'):
            assert s['probability'] is None
            assert 'non calibré' in s['probability_note']
            assert 'weight' not in s and 'likelihood' not in s
    assert not hasattr(reasoning, '_weights')
    assert reasoning.build(_D, {'lean': 55}, 'BUY')['model'] == {
        'type': 'plan_levels_deterministic', 'calibrated': False}


def test_scenario_central_atteignable_sous_son_propre_declencheur():
    """CONSTAT 39 — la cible du Central dépassait le plafond de sa propre zone.

    MESURE 5/5 sur /api/decision : NVDA « Maintien de la zone $211.91–$234.76 »
    → cible 267.26 ; AAPL 300.89–344.27 → 358.14 ; MSFT 473.3–517.78 → 552.51 ;
    TSLA 315.91–406.59 → 430.42 ; AMD 421.3–574.2 → 590.12. La résistance est
    le plus-haut 40 séances (analysis.py:267), la cible vaut `entry + 2×risque`
    (analysis.py:264) : deux grandeurs indépendantes. Le scénario ne pouvait pas
    atteindre sa cible SOUS sa propre condition. Les niveaux servis n'ont pas
    changé — c'est la condition qui est désormais énoncée en deux temps.
    """
    central = reasoning.scenarios(_D, {'lean': 50}, 'BUY')[1]
    assert central['target'] == 116                     # tp2, inchangé
    assert 'Maintien de la zone' not in central['trigger']
    assert '104' in central['trigger'] and '92' in central['trigger']
    # la cible (116) est au-dessus de la résistance (104) : la condition le dit.
    assert 'dépassement' in central['trigger']


def test_scenario_baissier_n_a_pas_sa_cible_pour_declencheur():
    """CONSTAT 39 — atteindre la cible ÉTAIT le déclencheur (100 % par construction).

    MESURE 5/5 en réel : trigger « Clôture sous $stop » avec `target = stop`
    (NVDA 211.91/211.91, AAPL 300.89/300.89, MSFT 473.3/473.3, TSLA
    315.91/315.91, AMD 421.3/421.3), et 3/3 en appel direct du moteur. Le plan
    moteur ne contient AUCUN objectif sous le stop : l'absence est déclarée au
    lieu d'être comblée par le niveau d'invalidation déguisé en cible.
    """
    bear = reasoning.scenarios(_D, {'lean': 50}, 'BUY')[2]
    assert bear['trigger'] == 'Clôture sous $92'
    assert bear['target'] is None and bear['move_pct'] is None
    assert 'invalidation' in bear['target_note'] and '92' in bear['target_note']


def test_invalidations_include_stop():
    inv = reasoning.invalidations(_D)
    assert any('92' in x for x in inv)
    assert 1 <= len(inv) <= 4


def test_below_ma200_adds_invalidation():
    inv = reasoning.invalidations({**_D, 'signals': {'above200': False}})
    assert any('MM200' in x for x in inv)


def test_build_carries_conviction_note():
    b = reasoning.build(_D, {'lean': 55}, 'BUY')
    assert 'scenarios' in b and 'invalidations' in b
    assert 'prédiction' in b['conviction_note'].lower()


def test_missing_plan_degrades_gracefully():
    # aucun plan → pas de crash, scénarios présents avec cibles None
    sc = reasoning.scenarios({'symbol': 'X'}, {'lean': 50}, 'WAIT')
    assert len(sc) == 3
