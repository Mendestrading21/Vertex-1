"""vertex.positions.thesis_health — santé de la thèse (§16).

Dimensions RÉELLEMENT évaluées ici : FUNDAMENTAL, CATALYST, TECHNICAL,
SENTIMENT, RISK / DATA_QUALITY — depuis ce que les moteurs FOURNISSENT
(scan detail + plan + qualité). Sans thèse écrite : THESIS_REQUIRED.

⚠ PORTFOLIO_FIT n'est PAS évalué ici (constat du lot 365 : la docstring
l'annonçait, aucune ligne ne le calculait). L'adéquation au portefeuille est
produite ailleurs — `vertex/scanner/stages.py` et
`vertex/strategy/executive_engine.py` (champ `portfolio_fit` du packet). La
santé de thèse ne la prend donc pas en compte : ne pas le supposer.
Gardien : `tests/test_thesis_health_dimensions.py`.
Une microvariation intraday ne bascule jamais un statut (matérialité).
"""
from __future__ import annotations

import time

STATUSES = ('STRENGTHENING', 'INTACT', 'MIXED', 'WEAKENING', 'AT_RISK',
            'INVALIDATED', 'UNKNOWN')


def assess(p: dict, detail: dict | None = None,
           previous_status: str | None = None) -> dict:
    d = detail or {}
    pos_ev, neg_ev, unknowns, blocking = [], [], [], []

    if not p.get('thesis_text'):
        return {'overall_status': 'UNKNOWN', 'previous_status': previous_status,
                'changed': previous_status not in (None, 'UNKNOWN'),
                'positive_evidence': [], 'negative_evidence': [],
                'unknowns': ['thèse absente'], 'blocking_factors': ['THESIS_REQUIRED'],
                'confidence': 0.0,
                'updated_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}

    # FUNDAMENTAL
    #  CONSTAT 5, SITE JUMEAU. Ce module lisait `d.get('st_fund') or
    #  d.get('fund_score')`. Les deux clés sont MORTES sur le `detail` du scan
    #  que lui passe `recalculator.assess(p, d, …)` : `fund_score` n'a aucune
    #  assignation dans le dépôt, `st_fund` n'est posée que sur la LIGNE de
    #  tableau, jamais sur le `detail`. MESURE : avec
    #  `detail['sub']['fundamental'] = 72` réellement servi, `assess()` rendait
    #  unknowns ['fondamental'] et confidence 0.67 — une note MESURÉE déclarée
    #  inconnue, sur des positions DÉCLARÉES par l'utilisateur (invariant 5).
    #  Le lecteur canonique est celui de `decision_packet` : même producteur
    #  (`detail['sub']`), même sémantique du 0 (« fondamentaux non branchés »,
    #  donc absent, jamais « mauvais »), et le lignage `is_proxy` voyage avec
    #  la note au lieu d'être perdu (invariant 6).
    from vertex.strategy.decision_packet import read_fundamental
    _f = read_fundamental(d)
    fund, fund_proxy = _f['score'], _f['is_proxy']
    #  Un fondamental DÉRIVÉ d'un proxy technique ne se lit pas comme une
    #  mesure comptable : la preuve le dit au lieu de laisser croire l'inverse.
    _prov = ' (proxy technique)' if fund_proxy else ''
    if fund is None:
        unknowns.append('fondamental')
    elif fund >= 60:
        #  `:g` — le lecteur canonique rend un float ; « fondamental 72.0 »
        #  suggérerait une précision décimale que la note sur 100 n'a pas.
        pos_ev.append(f'fondamental {fund:g}{_prov}')
    elif fund < 45:
        neg_ev.append(f'fondamental faible {fund:g}{_prov}')
    # CATALYST
    edte = d.get('earnings_dte') if d.get('earnings_dte') is not None else p.get('days_to_earnings')
    if edte is None:
        unknowns.append('catalyseur')
    elif 0 <= edte <= 30:
        pos_ev.append(f'earnings dans {edte} j (catalyseur actif)')
    # TECHNICAL — invalidation = franchissement CONFIRMÉ du stop (pas intraday)
    price, stop = p.get('current_price') or p.get('underlying_price'), \
        p.get('stop') or p.get('underlying_stop')
    if price is None or stop is None:
        unknowns.append('technique (prix ou stop manquant)')
    else:
        breached = price <= stop if p.get('right') != 'PUT' else price >= stop
        if breached:
            blocking.append('INVALIDATION_LEVEL_BREACHED')
            neg_ev.append('niveau d’invalidation franchi')
        elif p.get('remaining_rr') is not None and p['remaining_rr'] >= 2:
            pos_ev.append(f"R:R restant {p['remaining_rr']}")
        elif p.get('remaining_rr') is not None and p['remaining_rr'] < 1:
            neg_ev.append(f"R:R restant dégradé {p['remaining_rr']}")
    # SENTIMENT
    rs = d.get('rs')
    if rs is None:
        unknowns.append('sentiment')
    elif rs >= 60:
        pos_ev.append(f'force relative {rs}')
    elif rs < 40:
        neg_ev.append(f'force relative faible {rs}')
    # RISK / DATA_QUALITY
    if (p.get('data_quality') or {}).get('overall') in ('STALE', 'MISSING_PRICE',
                                                        'MISSING_MARK'):
        unknowns.append('qualité de données dégradée')

    if blocking and 'INVALIDATION_LEVEL_BREACHED' in blocking:
        overall = 'INVALIDATED'
    elif len(neg_ev) >= 2 and not pos_ev:
        overall = 'AT_RISK'
    elif neg_ev and len(neg_ev) > len(pos_ev):
        overall = 'WEAKENING'
    elif pos_ev and neg_ev:
        overall = 'MIXED'
    elif len(pos_ev) >= 2:
        overall = 'STRENGTHENING'
    elif pos_ev:
        overall = 'INTACT'
    elif len(unknowns) >= 3:
        overall = 'UNKNOWN'
    else:
        overall = 'INTACT'

    known = len(pos_ev) + len(neg_ev)
    confidence = round(known / (known + len(unknowns)), 2) if (known + len(unknowns)) else 0.0
    return {'overall_status': overall, 'previous_status': previous_status,
            'changed': previous_status is not None and previous_status != overall,
            'positive_evidence': pos_ev, 'negative_evidence': neg_ev,
            'unknowns': unknowns, 'blocking_factors': blocking,
            'confidence': confidence,
            'updated_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}


__all__ = ['assess', 'STATUSES']
