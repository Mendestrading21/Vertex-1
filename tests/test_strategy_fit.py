"""
tests/test_strategy_fit.py — Couche stratégie (véhicule / score / playbook / tilt).

Non-régression golden : re-pondération offensive de champs déjà calculés, sans
jamais toucher les moteurs quant, sans passer d'ordre.
"""

from vertex.engines import strategy_fit as sf


def test_vehicle_selection_golden():
    assert sf.vehicle_of({'verdict': 'AVOID', 'score': 30}, None)['reco'] == '—'
    assert sf.vehicle_of({'verdict': 'BUY', 'score': 80}, None)['reco'] == 'ACTION'      # pas d'option
    assert sf.vehicle_of({'verdict': 'BUY', 'score': 80}, {'quality': 30, 'pop': 20})['reco'] == 'ACTION'
    opt = sf.vehicle_of({'verdict': 'BUY', 'score': 80},
                        {'quality': 75, 'pop': 55, 'iv': 40, 'pot': 120, 'strike': 110, 'exp': '2025'})
    assert opt['reco'] == 'OPTION' and opt['opt']['strike'] == 110
    # IV chère → action (évite de surpayer la prime)
    assert sf.vehicle_of({'verdict': 'BUY', 'score': 60}, {'quality': 50, 'pop': 40, 'iv': 70, 'pot': 50})['reco'] == 'ACTION'


def test_strat_score_golden():
    assert sf.strat_score({'score': 80, 'st_mom': 85, 'rs': 75, 'regime': 'TREND', 'pos52': 82}) == 82
    assert sf.strat_score({'score': 40, 'regime': 'CHOP', 'rsi': 80, 'ext_atr': 4, 'vx_notrade': True}) == 6
    assert 0 <= sf.strat_score({'score': 60, 'regime': 'NEUTRAL'}) <= 100


def test_playbook_matching():
    assert sf.playbook_of({'regime': 'TREND', 'rs': 75, 'pos52': 85})['name'] == 'Momentum Breakout'
    assert sf.playbook_of({'score': 75, 'verdict': 'BUY'})['name'] == 'Qualité forte'
    assert sf.playbook_of({'regime': 'CHOP', 'score': 30}) is None


def test_strat_tilt_climate():
    fav = sf.strat_tilt({'spy_regime': 'TREND', 'roro': 'RISK-ON', 'vix_band': 'calme', 'breadth': {'above50': 70}})
    dang = sf.strat_tilt({'spy_regime': 'CHOP', 'roro': 'RISK-OFF', 'vix_band': 'stress', 'breadth': {'above50': 30}})
    assert fav['regime'] == 'FAVORABLE' and dang['regime'] == 'DANGEREUX'
    assert sf.strat_tilt(None) is None


def test_attach_mutates_rows():
    rows = [{'symbol': 'X', 'verdict': 'BUY', 'score': 80, 'st_mom': 85, 'rs': 75, 'regime': 'TREND'}]
    sf.attach_vehicle(rows, [{'sym': 'X', 'type': 'CALL', 'quality': 75, 'pop': 55, 'iv': 40, 'pot': 120,
                              'strike': 110, 'exp': '2025'}])
    sf.attach_strategy(rows, {'X': {'plan': {'rr_res': 2.5}}})
    r = rows[0]
    assert r['vehicle']['reco'] == 'OPTION'
    assert r['rr'] == 2.5 and r['rr_ok'] is True
    # pos52 absent → Momentum Breakout ne matche pas ; score 80 + BUY → « Qualité forte »
    assert r['playbook']['name'] == 'Qualité forte'


def test_terminal_bindings_are_the_module():
    import terminal
    assert terminal._strat_tilt is sf.strat_tilt


def test_tilt_largeur_absente_ne_pousse_jamais_le_ton_offensif():
    """CONSTAT 30, second moteur — un neutre 50 non marqué pilotait la prescription.

    MESURE avant correctif, mctx = {'spy_regime':'TREND','roro':'RISK-ON',
    'vix_band':'stress'} : breadth {'above50': 50}, {} et {'above50': None}
    rendaient TOUS `score 74 / FAVORABLE / call_size « normale → agressive »`,
    identiques au bit près. `_strat_tilt` substituait 50 à une participation
    JAMAIS mesurée (``(a50 if a50 is not None else 50)``) et cette invention
    poussait le ton le plus offensif du produit — taille de CALL « agressive »
    contre « réduite (½ taille) » au palier voisin — sans aucune marque.
    Ce tilt n'est pas mort : terminal.py:845 l'appelle et le publie dans
    `scan_state['strat_tilt']` (terminal.py:901).
    """
    mesure = sf.strat_tilt({'spy_regime': 'TREND', 'roro': 'RISK-ON',
                            'vix_band': 'stress', 'breadth': {'above50': 50}})
    absente = sf.strat_tilt({'spy_regime': 'TREND', 'roro': 'RISK-ON',
                             'vix_band': 'stress', 'breadth': {}})
    # Le score reste celui du moteur (aucun seuil déplacé) …
    assert mesure['score'] == absente['score'] == 74
    # … mais la couverture est dite, et la prescription plafonnée au palier NEUTRE.
    assert mesure.get('partiel') is None and 'agressive' in mesure['call_size']
    assert absente['partiel'] is True and absente['breadth_status'] == 'MISSING'
    assert absente['call_size_plafonne'] is True
    assert 'agressive' not in absente['call_size'] and 'réduite' in absente['call_size']
    assert 'Levier LEAPS' not in absente['emphasis']
    assert absente['couverture_note'] and 'Largeur' in absente['note']


def test_tilt_delegue_sa_borne_au_moteur_de_climat(monkeypatch):
    """CONSTAT 48, troisième propriétaire — la borne FAVORABLE était recopiée.

    `_strat_tilt` répliquait la formule entière de `market_lens.climate`
    (35/18/6/14, 25/2/12, /100*25, 15/2/8) et étiquetait FAVORABLE sur un `65`
    LITTÉRAL. La divergence numérique disparaissait par coïncidence — les deux
    valaient 65 — mais la duplication qui l'avait produite restait : une
    prochaine modification de CLAUDE_FAVORABLE_MIN l'aurait rouverte en
    silence. Ce test déplace la borne du moteur : si la formule est de nouveau
    recopiée ici, le tilt ignore le déplacement et le test échoue.
    """
    from vertex.engines import market_lens
    mc = {'spy_regime': 'TREND', 'roro': 'RISK-ON', 'vix_band': 'calme',
          'breadth': {'above50': 70}}
    assert sf.strat_tilt(mc)['regime'] == 'FAVORABLE'      # score 93, borne 65
    monkeypatch.setattr(market_lens, 'CLIMAT_FAVORABLE_MIN', 95)
    deplace = sf.strat_tilt(mc)
    assert deplace['score'] == 93, 'la formule ne bouge pas, seule la borne bouge'
    assert deplace['regime'] == 'NEUTRE', 'le tilt suit la borne du moteur canonique'
    assert market_lens.climate(mc)['label'] == deplace['regime']
