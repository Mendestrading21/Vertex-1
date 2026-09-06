"""tests/test_options_flow.py — flux d'options notable : classement + honnêteté."""
from vertex.options import flow


def _c(t, k, vol, cost, oi=None, exp='2026-08-21', dte=30):
    return {'type': t, 'strike': k, 'vol': vol, 'cost': cost, 'oi': oi, 'exp': exp, 'dte': dte}


def test_ranks_by_traded_premium():
    d = flow.analyze([
        _c('CALL', 450, vol=100, cost=200),      # premium = 100*200 = 20 000
        _c('CALL', 460, vol=50, cost=1000),       # premium = 50*1000 = 50 000 (plus gros)
        _c('PUT', 400, vol=10, cost=300),         # premium = 3 000
    ])
    assert d['empty'] is False
    assert d['contracts'][0]['strike'] == 460      # plus gros premium en tête
    assert d['contracts'][0]['premium'] == 50000


def test_vol_oi_fresh_flag():
    d = flow.analyze([_c('CALL', 450, vol=5000, cost=100, oi=1000)])   # vol/oi = 5 → frais
    row = d['contracts'][0]
    assert row['vol_oi'] == 5.0
    assert row['fresh'] is True


def test_call_put_skew():
    d = flow.analyze([
        _c('CALL', 450, vol=100, cost=1000),      # 100 000 calls
        _c('PUT', 400, vol=10, cost=1000),        # 10 000 puts
    ])
    assert d['skew'] == 'calls'
    assert d['call_pct'] >= 60


def test_missing_volume_or_premium_ignored():
    d = flow.analyze([
        _c('CALL', 450, vol=None, cost=200),      # pas de volume
        _c('CALL', 460, vol=100, cost=None),      # pas de prime
        _c('CALL', 470, vol=100, cost=200),       # exploitable
    ])
    assert d['notable_count'] == 1
    assert d['contracts'][0]['strike'] == 470


def test_empty_is_honest():
    d = flow.analyze([])
    assert d['empty'] is True
    assert d['call_premium'] is None
    assert 'tick' in d['basis']            # honnêteté : pas un flux tick-par-tick


def test_bool_rejected():
    d = flow.analyze([{'type': 'CALL', 'strike': 450, 'vol': True, 'cost': 200}])
    assert d['empty'] is True


def test_le_flux_ne_fabrique_aucune_activite_depuis_un_volume_non_observe():
    """L'ordre des alias de volume a changé quand `_vol` a délégué à
    `board_fields` (`vol` PUIS `volume` → `volume` PUIS `vol`). Aucun
    producteur n'émet les deux clés, donc rien ne bouge en production ; mais
    l'ordre décidait quand même dès qu'un contrat en portait deux, parce que
    le témoin d'imputation n'était consulté que sur la branche de repli.

    Mesure du 2026-09-06 sur un contrat déclaré SANS volume observé
    (`liquidity_coverage.volume_present: false`) mais portant `volume: 675` :
    le flux publiait une ligne « premium négocié 418 500 $ » calculée sur un
    volume qui n'a jamais été observé. Le module promet pourtant « contrat sans
    volume [...] → ignoré ». Il l'est désormais, quel que soit l'alias."""
    non_observe = {'type': 'CALL', 'strike': 450, 'volume': 675, 'vol': 0,
                   'cost': 620, 'exp': '2026-08-21', 'dte': 30, 'oi': 4615,
                   'liquidity_coverage': {'quoted_bid_ask': True,
                                          'volume_present': False}}
    d = flow.analyze([non_observe], symbol='NVDA')
    assert d['empty'] is True
    assert d['contracts'] == []
    assert 'volume' in d['reason']
    #  Le même contrat AVEC volume observé reste analysé : on ferme une
    #  fabrication, on ne rend pas le module aveugle.
    observe = dict(non_observe)
    observe['liquidity_coverage'] = {'quoted_bid_ask': True, 'volume_present': True}
    d2 = flow.analyze([observe], symbol='NVDA')
    assert d2['empty'] is False
    assert d2['contracts'][0]['vol'] == 675
    assert d2['contracts'][0]['premium'] == 418500      # 675 × 620
