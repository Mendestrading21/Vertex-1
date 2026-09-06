"""vertex.options.environment — score LONG OPTION ENVIRONMENT (§14).

« L'environnement est-il porteur pour un ACHETEUR d'options long ? » Le desk
Vertex n'achète que des calls/puts : la convexité se paie, le theta ronge. Ce
score agrège plusieurs dimensions RÉELLES (volatilité, IV rank, qualité du
tableau, liquidité, event risk, momentum) en une note 0..100 et un verdict
canonique. Chaque dimension absente est marquée INCONNUE et EXCLUE de la
moyenne — jamais remplacée par un zéro. Lecture seule.
"""
from __future__ import annotations

from vertex.visualization.schemas import (
    interpretation, unknown, ST_FAVORABLE, ST_NEUTRE, ST_DEFAVORABLE,
)

from . import board_fields as _bf


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _iv_sample(board):
    """IV positives réellement reportées et couverture de leurs exclusions."""
    values = []
    missing = invalid = 0
    for contract in board or []:
        value = contract.get('iv')
        if value is None:
            missing += 1
            continue
        if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
            invalid += 1
            continue
        values.append(float(value) / 100.0)
    return values, {
        'contracts_total': len(board or []),
        'iv_observed': len(values),
        'iv_missing': missing,
        'iv_invalid': invalid,
        'status': 'IV_SAMPLE_AVAILABLE' if values else 'IV_SAMPLE_UNAVAILABLE',
        'read_only': True,
    }


def _score_volatility(board):
    """IV basse = favorable pour un acheteur. Rend (0..100, note) ou (None, note)."""
    ivs, coverage = _iv_sample(board)
    if not ivs:
        return None, 'IV du tableau indisponible (%d absente(s), %d invalide(s))' % (
            coverage['iv_missing'], coverage['iv_invalid'])
    ivs.sort()
    med = ivs[len(ivs) // 2]
    # IV médiane 20 % → 100 pts ; 60 %+ → 0 pt (acheter cher = défavorable).
    pts = max(0.0, min(100.0, (0.60 - med) / (0.60 - 0.20) * 100.0))
    return round(pts, 1), 'IV médiane %.0f %%' % (med * 100)


def _score_ivrank(iv_rank):
    if iv_rank is None:
        return None, 'IV rank indisponible'
    # rank bas = primes abordables = favorable → score = 100 - rank
    return round(max(0.0, min(100.0, 100.0 - iv_rank)), 1), 'IV rank %.0f' % iv_rank


def _score_quality(board):
    qs = [_num(c.get('quality')) for c in board if c.get('quality') is not None]
    qs = [q for q in qs if q is not None]
    if not qs:
        return None, 'qualité des contrats indisponible'
    avg = sum(qs) / len(qs)
    return round(max(0.0, min(100.0, avg)), 1), 'qualité moyenne %.0f/100' % avg


def _score_liquidity(board):
    #  Le board RÉEL publie `spread`, pas `spread_pct` (mesuré 96/96 contre
    #  0/96 le 2026-09-06) : cette dimension déclarait « indisponible » une
    #  mesure détenue, sortait du score la PIRE dimension du jour (spread moyen
    #  22,9 % = 0/100) et faisait passer le verdict de HOSTILE (34,8) à MITIGÉ
    #  (52,2), couverture 40 % au lieu de 60 %. L'exclusion flattait le verdict,
    #  ce que `data_coverage.note` promet explicitement de ne jamais faire.
    sp = [_bf.spread_pct(c) for c in board or []]
    sp = [s for s in sp if s is not None]
    if not sp:
        return None, 'liquidité (spread) indisponible'
    avg = sum(sp) / len(sp)
    # spread 1 % → ~90 pts ; 8 %+ → 0 pt.
    pts = max(0.0, min(100.0, (8.0 - avg) / (8.0 - 1.0) * 100.0))
    return round(pts, 1), 'spread moyen %.1f %%' % avg


def _score_event(board, detail_by_sym):
    """Pénalise un tableau saturé d'événements imminents. detail_by_sym: {sym:{earnings_in_days}}."""
    syms = {c.get('sym') for c in board if c.get('sym')}
    if not syms or not detail_by_sym:
        return None, 'calendrier d\'événements indisponible'
    near = 0
    known = 0
    for s in syms:
        e = (detail_by_sym.get(s) or {}).get('earnings_in_days')
        if e is None:
            continue
        known += 1
        try:
            if 0 <= int(e) <= 7:
                near += 1
        except (TypeError, ValueError):
            pass
    if not known:
        return None, 'aucune date d\'earnings connue'
    frac = near / known
    return round(max(0.0, 100.0 - frac * 100.0), 1), '%d/%d titres en earnings ≤7 j' % (near, known)


def _label(score):
    if score is None:
        return 'INCONNU'
    if score >= 66:
        return 'PORTEUR'
    if score >= 45:
        return 'MITIGE'
    return 'HOSTILE'


def score_environment(board, *, iv_rank=None, detail_by_sym=None,
                      as_of=None, source=''):
    """Agrège les dimensions en un score global + interprétation canonique.

    board : options_board (réel/démo). iv_rank : IV rank agrégé si connu.
    detail_by_sym : {sym: {earnings_in_days,...}} pour l'event risk."""
    board = board or []
    iv_coverage = _iv_sample(board)[1]
    dims = []
    for key, label, (pts, note) in (
        ('volatility', 'Volatilité', _score_volatility(board)),
        ('iv_rank', 'IV rank', _score_ivrank(iv_rank)),
        ('quality', 'Qualité contrats', _score_quality(board)),
        ('liquidity', 'Liquidité', _score_liquidity(board)),
        ('event_risk', 'Risque d\'événement', _score_event(board, detail_by_sym or {})),
    ):
        dimension = {'key': key, 'label': label, 'score': pts, 'note': note,
                     'known': pts is not None}
        if key == 'volatility':
            dimension['coverage'] = iv_coverage
        dims.append(dimension)
    known = [d for d in dims if d['known']]
    overall = round(sum(d['score'] for d in known) / len(known), 1) if known else None
    label = _label(overall)
    interp = _interpret(overall, label, dims, known, as_of=as_of, source=source)
    unknown_dimensions = [d['key'] for d in dims if not d['known']]
    return {
        'score': overall,
        'label': label,
        'dimensions': dims,
        'dimensions_known': len(known),
        'dimensions_total': len(dims),
        'data_coverage': {'known_dimensions': len(known), 'total_dimensions': len(dims),
                          'coverage_pct': round(100 * len(known) / len(dims), 1) if dims else 0.0,
                          'unknown_dimensions': unknown_dimensions, 'read_only': True,
                          'note': 'dimensions inconnues exclues du score et jamais traitées comme favorables'},
        'regime': label,
        'interpretation': interp,
    }


def _interpret(overall, label, dims, known, *, as_of, source):
    cid = 'options.environment'
    q = 'L\'environnement est-il porteur pour un achat d\'options long ?'
    if overall is None:
        return unknown(cid, q, reason='aucune dimension mesurable (tableau/scan vide)',
                       source=source)
    pos = [d['label'] + ' : ' + d['note'] for d in dims if d['known'] and d['score'] >= 60]
    neg = [d['label'] + ' : ' + d['note'] for d in dims if d['known'] and d['score'] < 45]
    unc = [d['label'] + ' : ' + d['note'] for d in dims if not d['known']]
    if label == 'PORTEUR':
        status = ST_FAVORABLE
        reading = 'Environnement porteur (%.0f/100) : convexité abordable et exploitable.' % overall
        impact = 'Fenêtre favorable à l\'achat de convexité — rester sélectif sur les contrats.'
    elif label == 'HOSTILE':
        status = ST_DEFAVORABLE
        reading = 'Environnement hostile (%.0f/100) : primes chères et/ou risques élevés.' % overall
        impact = 'Réduire l\'exposition vega, préférer attendre une détente de l\'IV.'
    else:
        status = ST_NEUTRE
        reading = 'Environnement mitigé (%.0f/100) : ni aubaine ni piège évident.' % overall
        impact = 'Sélection au cas par cas ; exiger un R:R et une liquidité stricts.'
    conf = round(len(known) / len(dims), 2) if dims else None
    return interpretation(
        cid, q, reading, status, confidence=conf,
        positive_evidence=pos, negative_evidence=neg, uncertainties=unc,
        strategy_impact=impact, source=source, as_of=as_of,
        limitations=['Score heuristique agrégeant des dimensions hétérogènes — '
                     'indicateur de contexte, pas une prédiction de rendement',
                     'Dimensions manquantes exclues de la moyenne (jamais comptées zéro)'])


__all__ = ['score_environment']
