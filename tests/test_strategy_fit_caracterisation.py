"""
LOT 147 — Caractérisation étendue de la couche stratégie
(`vertex/engines/strategy_fit.py`, source unique : terminal.py délègue
vehicle_of / attach_vehicle / strat_score / playbook_of / strat_tilt).

Le golden existant (`tests/test_strategy_fit.py`) fige les chemins
dorés ; il ne couvrait ni la branche AU CHOIX, ni l'ordre de priorité
des playbooks, ni le seuil exact rr_ok, ni la bande NEUTRE du tilt,
ni les défauts du score. Ces tests figent le comportement observé —
tout changement futur doit faire échouer cette suite et être assumé.

Dictionnaires synthétiques déterministes — formes de signaux, pas de
titres réels.
"""

from vertex.engines import strategy_fit as sf


# ── vehicle_of : les branches non couvertes par le golden ────────────────────

def test_vehicule_au_choix_zone_intermediaire():
    # o = 1 (qualité ≥70 seulement) : ni OPTION (≥3) ni ACTION (≤0)
    # → AU CHOIX, ton gold.
    v = sf.vehicle_of({'verdict': 'BUY', 'score': 65},
                      {'quality': 70, 'pop': 40, 'iv': 50, 'pot': 50})
    assert v['reco'] == 'AU CHOIX' and v['tone'] == 'gold'
    assert 'levier' in v['why']


def test_vehicule_iv_chere_message_dedie():
    # IV ≥ 62 : pénalité -2 fait tomber o ≤ 0 ET le message cite l'IV.
    v = sf.vehicle_of({'verdict': 'BUY', 'score': 65},
                      {'quality': 50, 'pop': 40, 'iv': 62, 'pot': 10})
    assert v['reco'] == 'ACTION'
    assert 'IV chère (62%)' in v['why']


def test_vehicule_option_expose_le_contrat():
    v = sf.vehicle_of({'verdict': 'BUY', 'score': 80},
                      {'quality': 75, 'pop': 55, 'iv': 40, 'pot': 120,
                       'strike': 110, 'exp': '2026-06'})
    assert v['reco'] == 'OPTION' and v['tone'] == 'orange'
    assert v['opt'] == {'strike': 110, 'exp': '2026-06', 'q': 75, 'pop': 55, 'pot': 120}


# ── strat_score : défauts et bornes ──────────────────────────────────────────

def test_strat_score_defauts_score_seul():
    # st_mom/st_tech retombent sur le score, fund/risk/rs sur 50, régime
    # inconnu pèse 12 % de 12 : 0.30*60+0.16*60+0.10*50+0.10*50+0.22*50
    # +0.12*12 = 50.04 → 50.
    assert sf.strat_score({'score': 60}) == 50


def test_strat_score_ligne_vide_plancher_connu():
    # Tout absent → base 22 (défauts neutres, régime inconnu) — jamais
    # d'exception sur une ligne dégradée.
    assert sf.strat_score({}) == 22


def test_strat_score_clamp_a_zero_sous_les_penalites():
    assert sf.strat_score({'score': 0, 'regime': 'CHOP', 'vx_notrade': True,
                           'ext_atr': 5, 'rsi': 90}) == 0


# ── playbook_of : priorité déclarée et chacun des 6 playbooks ────────────────

def test_playbook_priorite_momentum_avant_qualite():
    # Une ligne qui matche Momentum Breakout ET Qualité forte reçoit le
    # PREMIER de la liste (ordre offensif assumé).
    both = {'regime': 'TREND', 'rs': 75, 'pos52': 85, 'score': 80, 'verdict': 'BUY'}
    assert sf.playbook_of(both)['name'] == 'Momentum Breakout'


def test_playbook_les_six_atteignables():
    cases = [
        ({'regime': 'TREND', 'rs': 75, 'pos52': 85}, 'Momentum Breakout'),
        ({'vx_edge': 65, 'regime': 'TREND'}, 'Levier LEAPS'),
        ({'regime': 'TREND', 'rsi': 50, 'pos52': 60}, 'Repli sur tendance'),
        ({'score': 75, 'verdict': 'BUY'}, 'Qualité forte'),
        ({'pos52': 20, 'change': 1.5}, 'Retournement de bas'),
        ({'score': 60, 'ext_atr': 0.5}, 'Socle défensif'),
    ]
    for row, name in cases:
        pb = sf.playbook_of(row)
        assert pb is not None and pb['name'] == name, (row, pb)
        assert set(pb) == {'ic', 'name', 'col', 'desc'}


def test_playbook_socle_defensif_exige_ext_atr_explicite():
    # Comportement limite DOCUMENTÉ : ext_atr absent → défaut 2 dans le
    # filtre → jamais Socle défensif sans extension connue (prudence :
    # « calme » non prouvé n'est pas calme).
    assert sf.playbook_of({'score': 60}) is None


# ── attach_vehicle : le meilleur CALL du board, PUT ignoré ───────────────────

def test_attach_vehicle_choisit_le_meilleur_call_et_ignore_les_puts():
    rows = [{'symbol': 'X', 'verdict': 'BUY', 'score': 80}]
    board = [
        {'sym': 'X', 'type': 'PUT', 'quality': 99},   # ignoré malgré sa qualité
        {'sym': 'X', 'type': 'CALL', 'quality': 50, 'pop': 40, 'iv': 50, 'pot': 50},
        {'sym': 'X', 'type': 'CALL', 'quality': 75, 'pop': 55, 'iv': 40, 'pot': 120,
         'strike': 111, 'exp': 'e'},
    ]
    sf.attach_vehicle(rows, board)
    assert rows[0]['vehicle']['reco'] == 'OPTION'
    assert rows[0]['vehicle']['opt']['strike'] == 111  # le CALL qualité 75, pas 50


def test_attach_vehicle_board_vide_reco_action():
    rows = [{'symbol': 'X', 'verdict': 'BUY', 'score': 80}]
    sf.attach_vehicle(rows, [])
    assert rows[0]['vehicle']['reco'] == 'ACTION'
    assert 'aucune option' in rows[0]['vehicle']['why']


# ── attach_strategy : seuil R:R exact, et plus AUCUN repli d'une autre échelle ─

def test_le_seuil_rr_ok_est_2_strict_sur_le_ratio_mesure():
    """Le seuil reste ≥ 2 STRICT — seule la SOURCE du nombre a changé.

    Ce test figeait auparavant le repli sur `vx_rr` avec des valeurs 1.99/2.00,
    qui ressemblaient à des ratios. Elles n'en sont pas : `vx_rr` = `vertex['rr']`
    = `quant_engine.rr_score`, une NOTE /100 (`rr_real * 32` : « 2:1→64 »).
    Mesuré le 6 sept. 2026 sur /api/vertex/<sym> — NVDA 8, MSFT 22, AAPL 41,
    TSLA 44, AMD 55, META 44, GOOGL 64, AMZN 55 — le repli allumait donc
    `rr_ok` (note ≥ 2) sur 8/8 titres, note 8 comprise, qui encode le PIRE
    ratio réel (~0,25:1). Le seuil est désormais appliqué au ratio mesuré.
    """
    r199 = [{'symbol': 'Y', 'score': 50}]
    r200 = [{'symbol': 'Z', 'score': 50}]
    sf.attach_strategy(r199, {'Y': {'plan': {'rr_res': 1.99}}})
    sf.attach_strategy(r200, {'Z': {'plan': {'rr_res': 2.0}}})
    assert r199[0]['rr'] == 1.99 and r199[0]['rr_ok'] is False
    assert r200[0]['rr'] == 2.0 and r200[0]['rr_ok'] is True


def test_la_note_quant_sur_100_n_allume_plus_le_drapeau_de_ratio():
    """Une note /100 ne remplace jamais un ratio : ni valeur, ni feu vert."""
    notes_mesurees_le_6_septembre = [8, 22, 41, 44, 55, 64]
    for note in notes_mesurees_le_6_septembre:
        rows = [{'symbol': 'X', 'score': 50, 'vx_rr': note}]
        sf.attach_strategy(rows, {})
        assert rows[0]['rr'] is None, note
        assert rows[0]['rr_ok'] is False, note


def test_rr_plan_est_la_seule_source():
    rows = [{'symbol': 'X', 'score': 50, 'vx_rr': 100}]
    sf.attach_strategy(rows, {'X': {'plan': {'rr_res': 2.5}}})
    assert rows[0]['rr'] == 2.5 and rows[0]['rr_ok'] is True


def test_rr_inconnu_honnete_jamais_ok():
    rows = [{'symbol': 'X', 'score': 50}]
    sf.attach_strategy(rows, {})
    assert rows[0]['rr'] is None and rows[0]['rr_ok'] is False


# ── strat_tilt : les trois bandes et l'arithmétique exacte ───────────────────

def test_tilt_favorable_arithmetique_exacte():
    # TREND 35 + RISK-ON 25 + breadth 70 → round(17.5)=18 + calme 15 = 93.
    t = sf.strat_tilt({'spy_regime': 'TREND', 'roro': 'RISK-ON',
                       'vix_band': 'calme', 'breadth': {'above50': 70}})
    assert t['score'] == 93 and t['regime'] == 'FAVORABLE'
    assert t['emphasis'] == ['Momentum Breakout', 'Levier LEAPS', 'Repli sur tendance']
    assert 'agressive' in t['call_size']


def test_tilt_neutre_climat_inconnu_prudence_mediane():
    # Régime NEUTRAL, roro/vix inconnus, breadth vide : 18+12+12+8 = 50
    # (round(12.5) bancaire → 12) → bande NEUTRE, CALL en taille réduite.
    #  CONSTAT 30 (second tour) : ces 12 points de participation venaient d'un
    #  50 SUBSTITUÉ à une largeur jamais mesurée. Le score ne bouge pas — aucun
    #  seuil déplacé — mais la couverture est désormais MARQUÉE : sans cette
    #  marque, ce 50 était indiscernable d'une participation réellement mesurée
    #  à 50 % (mesuré : breadth {} et {'above50': 50} rendaient exactement le
    #  même dictionnaire). La caractérisation fige donc les deux : le chiffre
    #  ET son aveu de couverture.
    t = sf.strat_tilt({'spy_regime': 'NEUTRAL', 'roro': None,
                       'vix_band': None, 'breadth': {}})
    assert t['score'] == 50 and t['regime'] == 'NEUTRE'
    assert 'réduite' in t['call_size']
    assert t['emphasis'] == ['Repli sur tendance', 'Qualité forte']
    assert t['partiel'] is True and t['breadth_status'] == 'MISSING'
    #  Bande NEUTRE : la prescription est déjà prudente, rien à plafonner.
    assert 'call_size_plafonne' not in t


def test_tilt_dangereux_defense_et_bornes():
    t = sf.strat_tilt({'spy_regime': 'CHOP', 'roro': 'RISK-OFF',
                       'vix_band': 'stress', 'breadth': {'above50': 10}})
    assert t['regime'] == 'DANGEREUX'
    assert t['emphasis'] == ['Socle défensif', 'Qualité forte']
    assert 0 <= t['score'] < 40
    assert 'cash' in t['call_size']
