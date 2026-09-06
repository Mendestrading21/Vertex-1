"""vertex.options.overview — synthèse de l'espace Options Intelligence (§18).

Consolide l'`options_board` (réel ou démo) en une vue d'ensemble lisible :
compteurs CALL/PUT, qualité, liquidité, régime de volatilité agrégé, radar
des meilleurs contrats, et une interprétation canonique du graphique de
répartition. Lecture seule, aucune donnée inventée — champs absents → None.
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


def _avg(xs):
    xs = [v for v in xs if v is not None]
    return round(sum(xs) / len(xs), 2) if xs else None


def _quality_band(q):
    if q is None:
        return None
    if q >= 75:
        return 'EXCELLENT'
    if q >= 55:
        return 'CORRECT'
    if q >= 40:
        return 'MOYEN'
    return 'FAIBLE'


def summarize(board, *, as_of=None, demo=False, source='', detail_by_sym=None):
    """Vue d'ensemble consolidée du board options. board : liste d'items §18."""
    board = board or []
    calls = [c for c in board if str(c.get('type', '')).upper() == 'CALL']
    puts = [c for c in board if str(c.get('type', '')).upper() == 'PUT']
    ivs = [_num(c.get('iv')) for c in board]
    quals = [_num(c.get('quality')) for c in board]
    #  `spread_pct` est la clé du board de DÉMO ; le board réel publie `spread`
    #  (96/96 contre 0/96). D'où un `avg_spread_pct: null` et une carte
    #  « SPREAD MOY. — non disponible sur ce scan » alors que la page
    #  Opportunités imprimait « 6,5 % » pour le même contrat.
    spreads = [_bf.spread_pct(c) for c in board]
    ois = [_num(c.get('oi')) for c in board]
    avg_iv = _avg(ivs)
    avg_qual = _avg(quals)
    avg_spread = _avg(spreads)
    top = sorted([c for c in board if c.get('quality') is not None],
                 key=lambda c: c.get('quality', 0), reverse=True)[:6]
    counters = {
        'total': len(board),
        'calls': len(calls),
        'puts': len(puts),
        'symbols': len({c.get('sym') for c in board if c.get('sym')}),
        'avg_iv': avg_iv,
        'avg_quality': avg_qual,
        'quality_band': _quality_band(avg_qual),
        'avg_spread_pct': avg_spread,
        'avg_oi': _avg(ois),
    }
    radar = [{
        'sym': c.get('sym'), 'type': c.get('type'), 'bucket': c.get('bucket'),
        'strike': c.get('strike'), 'dte': c.get('dte'), 'iv': _num(c.get('iv')),
        'quality': _num(c.get('quality')), 'pop': _num(c.get('pop')),
        'spread_pct': _bf.spread_pct(c), 'why': c.get('why'),
        # pour « Suivre ce contrat » : coût (prime × 100) et échéance exacte.
        'cost': _num(c.get('cost')), 'exp': c.get('exp'),
    } for c in top]
    from .pulse import option_pulse, volatility_pulse
    from .environment import score_environment
    env = score_environment(board, detail_by_sym=detail_by_sym or {},
                            as_of=as_of, source=source)
    return {
        'as_of': as_of,
        'demo': bool(demo),
        'empty': not board,
        'counters': counters,
        'radar': radar,
        'environment': env,
        'option_pulse': option_pulse(board),
        'volatility_pulse': volatility_pulse(board),
        'interpretation': _interpret_mix(board, calls, puts, avg_qual,
                                         as_of=as_of, source=source),
    }


def _interpret_mix(board, calls, puts, avg_qual, *, as_of, source):
    """« Le tableau d'options penche-t-il haussier ou baissier, et est-il exploitable ? »"""
    cid = 'options.overview_mix'
    q = 'Le tableau d\'options est-il exploitable, et vers quel biais ?'
    if not board:
        return unknown(cid, q, reason='Aucun contrat dans le tableau (scan vide ou hors séance)',
                       source=source)
    nc, npu = len(calls), len(puts)
    pos, neg, unc = [], [], []
    if nc or npu:
        pos.append('%d CALLS / %d PUTS analysés' % (nc, npu))
    bias = 'haussier' if nc > npu * 1.3 else 'baissier' if npu > nc * 1.3 else 'équilibré'
    if avg_qual is not None:
        if avg_qual >= 55:
            pos.append('Qualité moyenne des contrats correcte (%.0f/100)' % avg_qual)
        else:
            neg.append('Qualité moyenne des contrats faible (%.0f/100)' % avg_qual)
    else:
        unc.append('Qualité moyenne non calculable')
    if avg_qual is None:
        status = ST_NEUTRE
    elif avg_qual >= 60:
        status = ST_FAVORABLE
    elif avg_qual < 40:
        status = ST_DEFAVORABLE
    else:
        status = ST_NEUTRE
    lean = ('penche %s' % bias) if bias != 'équilibré' else 'reste équilibré'
    reading = 'Le tableau d\'options %s ; exploitabilité %s.' % (
        lean, 'bonne' if status == ST_FAVORABLE else
        'limitée' if status == ST_DEFAVORABLE else 'moyenne')
    return interpretation(
        cid, q, reading, status,
        confidence=0.5 if avg_qual is not None else None,
        positive_evidence=pos, negative_evidence=neg, uncertainties=unc,
        strategy_impact=('Cibler les meilleurs contrats du radar.' if status == ST_FAVORABLE
                         else 'Rester sélectif : peu de contrats de qualité.'),
        source=source, as_of=as_of,
        limitations=['La qualité agrège plusieurs critères (liquidité, R:R, theta) '
                     '— pondération heuristique, pas un prix de marché'])


__all__ = ['summarize']
