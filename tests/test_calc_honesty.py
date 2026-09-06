"""Tests — honnêteté des calculs Greeks (audit système, §21).

Vérifie qu'aucune valeur absente n'est transformée en 0 fabriqué et qu'aucun
label de provenance (BROKER_GREEKS) n'est apposé sans valeurs réelles.
"""
from vertex.positions import calculator
from vertex.portfolio import risk_engine


def _opt(qty=1):
    return {
        'asset_type': 'OPTION', 'symbol': 'AAPL', 'right': 'CALL',
        'strike': 200, 'expiration': '2026-09-18', 'quantity': qty,
        'multiplier': 100, 'cost_total': 500, 'capital_committed': 500,
        'avg_cost': 5.0, 'data_quality': {},
    }


def test_positional_greek_none_when_quantity_unknown():
    """qty=None → Greek positionnel None, jamais 0 fabriqué (mais valeur unitaire gardée)."""
    p = _opt(qty=None)
    calculator.enrich_option(p, {'mark': 6.0, 'iv': 0.3}, None,
                             {'source': 'BROKER_GREEKS', 'delta': 0.5}, {})
    assert p['delta'] is None
    assert p.get('delta_per_option') == 0.5


def test_positional_greek_computed_once_with_quantity():
    p = _opt(qty=2)
    calculator.enrich_option(p, {'mark': 6.0, 'iv': 0.3}, None,
                             {'source': 'BROKER_GREEKS', 'delta': 0.5}, {})
    # 0.5 × 100 × 2 = 100 (multiplicateur appliqué une seule fois)
    assert p['delta'] == 100.0
    assert p['greeks_source'] == 'BROKER_GREEKS'


def test_no_broker_greeks_label_without_values():
    """Sans valeurs de Greeks, la provenance ne doit pas être BROKER_GREEKS."""
    p = _opt(qty=1)
    calculator.enrich_option(p, {'mark': 6.0, 'iv': 0.3}, None, None, {})
    assert p['greeks_source'] == 'UNAVAILABLE'
    assert p['delta'] is None


def test_une_marque_sans_aucune_reference_ne_pretend_pas_venir_d_un_echange():
    """MESURE : `POST /api/pos-quotes` rendait
    `{"mark":6.2,"mark_source":"DERNIER_ECHANGE","spot":230.36,"spread_pct":null}`
    pour NVDA 2026-10-23 245 C, alors que 6,20 est le MILIEU du board
    ((6,00 + 6,40) / 2 ; idem GEN 1,18 et MPC 23,95). Le dict de repli ne porte
    ni bid, ni ask, ni mid, ni last : la branche finale de `source_de_marque`
    affirmait une convention qu'elle n'avait aucun moyen de connaître, et le
    tiroir « Provenance et qualité » imprimait « Source de la marque : dernier
    échange ». Sans référence, la convention est INDÉTERMINÉE — le client sait
    déjà rendre cela par « convention non renseignée »."""
    assert calculator.source_de_marque(6.2) == calculator.MARQUE_INDETERMINEE
    p = _opt(qty=1)
    calculator.enrich_option(p, {'mark': 6.2}, None, None, {})
    assert p['mark'] == 6.2                       # la marque reste servie
    assert p['mark_source'] == calculator.MARQUE_INDETERMINEE


def test_les_trois_conventions_connues_restent_nommees():
    """Non-régression : dès qu'une référence est fournie, la provenance est
    affirmée comme avant — c'est l'affirmation SANS preuve qui est retirée."""
    assert calculator.source_de_marque(6.2, last=6.2) == calculator.MARQUE_DERNIER_ECHANGE
    assert calculator.source_de_marque(6.2, close=6.2) == calculator.MARQUE_CLOTURE
    assert calculator.source_de_marque(6.2, mid=6.2) == calculator.MARQUE_MILIEU
    #  Une marque qui ne colle à aucune des références FOURNIES vient bien d'un
    #  prix échangé : ce cas-là garde son étiquette.
    assert calculator.source_de_marque(6.35, mid=6.2) == calculator.MARQUE_DERNIER_ECHANGE
    assert calculator.source_de_marque(None) == calculator.MARQUE_ABSENTE


# ── Constat 29 : une échéance illisible n'est pas une échéance absente ──────

def test_lecheance_declaree_se_relit_quel_que_soit_le_separateur():
    """MESURE : le desk réel stocke `exp='2027.01.15'` (saisie libre) alors que
    le board d'options ne sert que du 'YYYY-MM-DD'. `_dte('2027.01.15')`
    rendait None là où `_dte('2027-01-15')` rend 131 jours — donc EXPIRED,
    DTE_WARNING et THETA_WARNING ne pouvaient jamais s'armer sur 2 des 3
    positions déclarées. La normalisation est une lecture, pas une réécriture :
    `desk_data.json` n'est pas touché."""
    from vertex.positions.models import _dte, echeance_normalisee
    for forme in ('2027-01-15', '2027.01.15', '2027/01/15', '20270115',
                  '2027-01-15T00:00:00'):
        assert echeance_normalisee(forme) == '2027-01-15', forme
        assert _dte(forme) == _dte('2027-01-15'), forme
    assert echeance_normalisee('2026.10') == '2026-10'        # mois seul reconnu
    assert _dte('2026-10') is None                            # jour inconnu, jamais deviné


def test_une_date_non_reconnue_ne_devient_jamais_une_date_plausible():
    """Rien n'est deviné : une date impossible ou incomplète rend None."""
    from vertex.positions.models import echeance_normalisee
    for forme in ('demain', '2027-1-5', '2027-02-31', '15/01/2027', '', None):
        assert echeance_normalisee(forme) is None, forme


def test_une_echeance_illisible_est_nommee_et_non_confondue_avec_une_absence():
    """MESURE : `/api/positions/state` rendait `expiration:'2027.01.15',
    dte:None, data_quality:{'overall':'MISSING_MARK','issues':[]}` — une date
    illisible strictement indistinguable d'une date absente, sans aucun
    `issue`. Le défaut est désormais NOMMÉ (et le reste après normalisation,
    pour une date réellement invalide)."""
    from vertex.positions import audit
    p = _opt(qty=1)
    p['expiration'] = 'demain'
    calculator.enrich_option(p, {'mark': 6.0}, None, None, {})
    assert 'EXPIRATION_ILLISIBLE' in p['data_quality']['issues']
    # L'audit d'intégrité le nomme aussi, à côté de EXPIRATION_MISSING.
    errs = audit._check({'symbol': 'AAPL', 'quantity': 1, 'capital_committed': 500,
                         'currency': 'USD', 'source': 'MANUAL', 'asset_type': 'OPTION',
                         'strike': 200, 'expiration': 'demain', 'thesis_text': 'x'})
    assert errs == ['EXPIRATION_ILLISIBLE']


def test_une_echeance_lisible_ne_leve_aucun_probleme():
    """Non-régression : les formes reconnues ne déclenchent rien."""
    from vertex.positions import audit
    p = _opt(qty=1)
    p['expiration'] = '2027.01.15'
    calculator.enrich_option(p, {'mark': 6.0}, None, None, {})
    assert 'EXPIRATION_ILLISIBLE' not in p['data_quality']['issues']
    assert audit._check({'symbol': 'AAPL', 'quantity': 1, 'capital_committed': 500,
                         'currency': 'USD', 'source': 'MANUAL', 'asset_type': 'OPTION',
                         'strike': 200, 'expiration': '2027.01.15', 'thesis_text': 'x'}) == []


def test_risk_engine_does_not_coerce_missing_greeks_to_zero():
    """Garde-fou source : l'agrégat Greeks du risk_engine ne doit plus utiliser
    `g.get('delta') or 0` (qui transformait un Greek absent en 0)."""
    import os
    src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            'vertex/portfolio/risk_engine.py'), encoding='utf-8').read()
    assert "g.get('delta') or 0" not in src
    assert 'greeks_partial' in src  # l'agrégat signale désormais l'incomplétude
