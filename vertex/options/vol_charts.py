"""vertex.options.vol_charts — jeux de données pour graphiques options (§15).

Construit, à partir du tableau d'options réel (options_board), les séries
prêtes à tracer pour un sous-jacent : structure par terme de l'IV, cône de
mouvement attendu, open interest par strike, smile d'IV. Chaque graphique est
accompagné d'une interprétation canonique. Aucune donnée inventée : série vide
si la donnée manque. Lecture seule ; les calculs vivent ici (côté serveur).
"""
from __future__ import annotations

import math

from vertex.options import board_fields as _bf
from vertex.visualization.schemas import (
    interpretation, unknown, ST_FAVORABLE, ST_NEUTRE, ST_DEFAVORABLE,
)

DAYS_YEAR = 365.0


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _contracts(board, sym):
    sym = str(sym or '').upper()
    return [c for c in (board or []) if str(c.get('sym', '')).upper() == sym]


def _spot(contracts):
    for c in contracts:
        s = _num(c.get('spot'))
        if s and s > 0:
            return s
    return None


# ───────────────────────────────────────────── structure par terme (§15.2)
def term_structure(contracts, spot):
    """ATM IV par échéance : pour chaque DTE, l'IV du contrat le plus proche du spot.

    Rend {points:[{dte,iv,strike}], slope} — IV en fraction (0.32)."""
    by_dte = {}
    for c in contracts:
        dte = _num(c.get('dte'))
        iv = _num(c.get('iv'))
        strike = _num(c.get('strike'))
        if dte is None or iv is None or strike is None or spot is None:
            continue
        d = int(dte)
        dist = abs(strike - spot)
        cur = by_dte.get(d)
        if cur is None or dist < cur['dist']:
            by_dte[d] = {'dte': d, 'iv': round(iv / 100.0, 4), 'strike': strike, 'dist': dist}
    pts = sorted((({'dte': v['dte'], 'iv': v['iv'], 'strike': v['strike']})
                  for v in by_dte.values()), key=lambda p: p['dte'])
    slope = None
    if len(pts) >= 2:
        slope = round(pts[-1]['iv'] - pts[0]['iv'], 4)
    return {'points': pts, 'slope': slope}


# ───────────────────────────────────────────── cône de mouvement attendu (§15.6)
def expected_move_cone(contracts, spot):
    """Bandes spot ± 1σ/2σ par échéance. σ = spot·IV_atm·√(dte/365)."""
    ts = term_structure(contracts, spot)
    if spot is None:
        return {'points': []}
    pts = []
    for p in ts['points']:
        em = spot * p['iv'] * math.sqrt(max(0, p['dte']) / DAYS_YEAR)
        pts.append({'dte': p['dte'],
                    'lo2': round(spot - 2 * em, 2), 'lo1': round(spot - em, 2),
                    'mid': round(spot, 2),
                    'hi1': round(spot + em, 2), 'hi2': round(spot + 2 * em, 2),
                    'em_pct': round(p['iv'] * math.sqrt(max(0, p['dte']) / DAYS_YEAR) * 100, 2)})
    return {'points': pts, 'spot': round(spot, 2)}


# ───────────────────────────────────────────── open interest par strike (§15.7)
def oi_by_strike(contracts, spot):
    """OI CALL vs PUT agrégé par strike (bar divergente). PUT en négatif pour l'axe."""
    agg = {}
    for c in contracts:
        strike = _num(c.get('strike'))
        #  Accesseur honnête plutôt que champ brut : `_i(None) -> 0`. Ici le
        #  zéro imputé était déjà écarté par la garde suivante, mais lire le
        #  champ brut laisse croire que la garde protège d'un zéro RÉEL —
        #  elle protégeait surtout d'une absence. Un seul accesseur pour tous
        #  les lecteurs du dépôt, sinon le prochain oubli est invisible.
        oi = _bf.open_interest(c)
        if strike is None or oi is None:
            continue
        k = round(strike, 1)
        side = 'call' if str(c.get('type', '')).upper() == 'CALL' else 'put'
        agg.setdefault(k, {'strike': k, 'call': 0.0, 'put': 0.0})
        agg[k][side] += oi
    rows = sorted(agg.values(), key=lambda r: r['strike'])
    return {'rows': [{'strike': r['strike'], 'call': round(r['call']),
                      'put': round(r['put'])} for r in rows],
            'spot': round(spot, 2) if spot else None}


# ───────────────────────────────────────────── smile d'IV (§15.3)
def iv_smile(contracts, spot, expiry=None):
    """IV par strike pour une échéance (défaut : DTE médian). Rend calls/puts séparés."""
    dtes = sorted({int(_num(c.get('dte'))) for c in contracts if _num(c.get('dte')) is not None})
    if not dtes:
        return {'calls': [], 'puts': [], 'dte': None}
    target = expiry if expiry in dtes else dtes[len(dtes) // 2]
    calls, puts = [], []
    for c in contracts:
        if _num(c.get('dte')) is None or int(_num(c.get('dte'))) != target:
            continue
        strike, iv = _num(c.get('strike')), _num(c.get('iv'))
        if strike is None or iv is None:
            continue
        row = {'strike': round(strike, 1), 'iv': round(iv / 100.0, 4)}
        (calls if str(c.get('type', '')).upper() == 'CALL' else puts).append(row)
    calls.sort(key=lambda r: r['strike'])
    puts.sort(key=lambda r: r['strike'])
    return {'calls': calls, 'puts': puts, 'dte': target, 'spot': round(spot, 2) if spot else None}


# ───────────────────────────────────────────── interprétation de la structure
def _interpret_term(ts, *, sym, as_of, source):
    cid = 'options.iv_term'
    q = 'La structure par terme de l\'IV favorise-t-elle un achat, et sur quelle échéance ?'
    pts = ts['points']
    if len(pts) < 2:
        return unknown(cid, q, reason='pas assez d\'échéances cotées', source=source)
    slope = ts['slope']
    front = pts[0]['iv']
    pos, neg = [], []
    if slope is not None and slope > 0.02:
        status = ST_FAVORABLE
        reading = 'Structure ascendante (contango) : les échéances courtes sont relativement bon marché.'
        pos.append('Pente +%.1f pt entre %d j et %d j' % (slope * 100, pts[0]['dte'], pts[-1]['dte']))
        impact = 'Le court terme paie moins de vol — favorable à une entrée tactique courte.'
    elif slope is not None and slope < -0.02:
        status = ST_DEFAVORABLE
        reading = 'Structure inversée (backwardation) : stress/événement price sur le court terme.'
        neg.append('Pente %.1f pt : IV courte au-dessus de l\'IV longue' % (slope * 100))
        impact = 'IV courte gonflée — risque de crush ; préférer une échéance plus longue ou attendre.'
    else:
        status = ST_NEUTRE
        reading = 'Structure plate : pas d\'avantage d\'échéance marqué.'
        impact = 'Choisir l\'échéance sur la thèse, pas sur la structure de vol.'
    return interpretation(
        cid, q, reading, status, confidence=0.5,
        positive_evidence=pos, negative_evidence=neg,
        uncertainties=['IV ATM approximée par le contrat le plus proche du spot'],
        strategy_impact=impact, source=source, as_of=as_of,
        limitations=['Structure reconstruite depuis le tableau (pas une surface complète de vol)'])


def build(board, sym, *, as_of=None, source='SCAN', expiry=None):
    """Assemble tous les jeux de données de graphiques options pour un titre."""
    contracts = _contracts(board, sym)
    spot = _spot(contracts)
    if not contracts:
        return {'symbol': str(sym or '').upper(), 'empty': True, 'spot': None,
                'term_structure': {'points': []}, 'expected_move_cone': {'points': []},
                'oi_by_strike': {'rows': []}, 'iv_smile': {'calls': [], 'puts': []},
                'interpretation': unknown('options.iv_term',
                                          'Structure par terme de l\'IV',
                                          reason='aucun contrat pour ce titre',
                                          source=source)}
    ts = term_structure(contracts, spot)
    return {
        'symbol': str(sym or '').upper(),
        'empty': False,
        'spot': round(spot, 2) if spot else None,
        'contracts': len(contracts),
        'term_structure': ts,
        'expected_move_cone': expected_move_cone(contracts, spot),
        'oi_by_strike': oi_by_strike(contracts, spot),
        'iv_smile': iv_smile(contracts, spot, expiry=expiry),
        'interpretation': _interpret_term(ts, sym=sym, as_of=as_of, source=source),
    }


__all__ = ['build', 'term_structure', 'expected_move_cone', 'oi_by_strike', 'iv_smile']
