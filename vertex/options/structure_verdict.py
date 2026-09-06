"""vertex/options/structure_verdict.py — verdict analytique d'une STRUCTURE d'options.

Propriétaire unique de ce qui vivait dans le JavaScript de la vue Structure
(`options-structure.js` : `liqState`, `strategyLiquidity`, `expectedMove`,
`pnlAt`, `computeVerdict`, scénarios) — un calcul financier dans l'interface,
contraire au contrat (l'UI peint, le serveur calcule). Les règles sont reprises
À L'IDENTIQUE, seul le domicile change ; les gardiens de
tests/test_structure_verdict.py les épinglent.

Rien n'est inventé : sans IV, pas de mouvement attendu ni de scénarios ; sans
bid/ask ni OI, la liquidité est « insuffisante — non évaluable », jamais zéro.
Lecture seule : aucun ordre, aucune probabilité garantie.
"""
from __future__ import annotations

import math

from . import board_fields as _bf

RANG_LIQUIDITE = {'excellente': 3, 'acceptable': 2, 'mediocre': 1, 'insuffisante': 0}

#: Prime « chère » : capital à risque > 12 % du notionnel (spot × 100).
SEUIL_PRIME_CHERE = 0.12


def _num(x):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _fmt(v, d=1):
    return ('%.' + str(d) + 'f') % v


def etat_liquidite(oi, spread_pct) -> dict:
    """État de liquidité d'un contrat : quatre paliers explicites, jamais un zéro
    pour un bid/ask ou un OI absent (→ insuffisante, non évaluable).

    Le spread absent NE PRODUIT PLUS DE CHIFFRE. La sentinelle 99.0 servait ici
    de seuil interne ET était mise en forme dans la note, dans la même phrase et
    la même unité qu'un OI mesuré : « OI 4615 · spread 99.0 % » a été servi sur
    un contrat dont le spread réel valait 6,5 % (NVDA CALL 230, 2026-09-06).
    Le classement reste prudent — sans spread coté, aucun palier positif — mais
    l'absence se nomme au lieu de se chiffrer (invariants 5 et 7).
    """
    o = _num(oi)
    s = _num(spread_pct)
    if o is None and s is None:
        return {'key': 'insuffisante', 'label': 'Insuffisante', 'tone': 'neg',
                'note': 'bid/ask ou OI absent — non évaluable',
                'spread_pct': None, 'spread_mesure': False}
    if s is None:
        return {'key': 'insuffisante', 'label': 'Insuffisante', 'tone': 'neg',
                'note': 'OI %s · spread non coté — liquidité non évaluable'
                        % (int(o) if o is not None else '—'),
                'spread_pct': None, 'spread_mesure': False}
    o = o or 0.0
    note = 'OI %s · spread %s %%' % (int(o) if oi is not None else '—', _fmt(s, 1))
    mesure = {'spread_pct': round(s, 2), 'spread_mesure': True}
    if o >= 5000 and s <= 3:
        return {'key': 'excellente', 'label': 'Excellente', 'tone': 'pos', 'note': note, **mesure}
    if o >= 1500 and s <= 6:
        return {'key': 'acceptable', 'label': 'Acceptable', 'tone': 'pos', 'note': note, **mesure}
    if o >= 500 and s <= 10:
        return {'key': 'mediocre', 'label': 'Médiocre', 'tone': 'warn', 'note': note, **mesure}
    return {'key': 'insuffisante', 'label': 'Insuffisante', 'tone': 'neg', 'note': note, **mesure}


def contrats_pour(board, sym, exp=None):
    sym = str(sym or '').upper()
    return [c for c in (board or []) if isinstance(c, dict)
            and str(c.get('sym') or '').upper() == sym and (not exp or c.get('exp') == exp)]


def liquidite_strategie(board, sym, exp, legs) -> dict:
    """Liquidité d'une stratégie = sa PIRE jambe (approchée depuis le board)."""
    cs = contrats_pour(board, sym, exp)
    if not cs:
        near = contrats_pour(board, sym, None)
        if not near:
            return etat_liquidite(None, None)
        oi0 = min((_num(c.get('oi')) or 0.0) for c in near)
        #  Repli sur les échéances voisines : on prend le PIRE spread RÉELLEMENT
        #  coté. L'ancien `max(..., 99.0)` transformait un contrat non coté en
        #  spread de 99 % — un chiffre que personne n'a mesuré, qui écrasait le
        #  verdict de toutes les autres jambes. Si aucun voisin n'est coté, le
        #  spread reste None : absence, pas pénalité.
        sp_cotes = [v for v in (_bf.spread_pct(c) for c in near) if v is not None]
        return etat_liquidite(oi0, max(sp_cotes) if sp_cotes else None)
    pire = None
    for leg in (legs or []):
        t = str(leg.get('type') or '').upper()
        k = _num(leg.get('strike')) or 0.0
        exact = [c for c in cs if str(c.get('type') or '').upper() == t
                 and abs((_num(c.get('strike')) or 0.0) - k) < 0.6]
        c = exact[0] if exact else None
        if c is None:
            memes = sorted([c2 for c2 in cs if str(c2.get('type') or '').upper() == t],
                           key=lambda c2: abs((_num(c2.get('strike')) or 0.0) - k))
            c = memes[0] if memes else None
        if c is None:
            continue
        #  `spread_pct` n'existe que sur le board de démonstration ; le board
        #  réel publie `spread`. L'accesseur lit les deux (cf. board_fields).
        st = etat_liquidite(c.get('oi'), _bf.spread_pct(c))
        if pire is None or RANG_LIQUIDITE[st['key']] < RANG_LIQUIDITE[pire['key']]:
            pire = st
    return pire or etat_liquidite(None, None)


def pnl_a(payoff, px):
    """P&L à l'échéance interpolé linéairement sur la courbe payoff servie."""
    if not payoff or px is None:
        return None
    pts = [(p.get('price'), p.get('pnl')) for p in payoff
           if isinstance(p, dict) and _num(p.get('price')) is not None and _num(p.get('pnl')) is not None]
    if not pts:
        return None
    if px <= pts[0][0]:
        return pts[0][1]
    if px >= pts[-1][0]:
        return pts[-1][1]
    for i in range(1, len(pts)):
        if px <= pts[i][0]:
            (pa, va), (pb, vb) = pts[i - 1], pts[i]
            t = (px - pa) / (pb - pa) if pb != pa else 0.0
            return va + t * (vb - va)
    return pts[-1][1]


def mouvement_attendu(spot, iv_dec, dte):
    """Mouvement attendu ~1σ à l'échéance : spot × IV × √(dte/365). None sans IV."""
    spot, iv_dec, dte = _num(spot), _num(iv_dec), _num(dte)
    if not spot or not iv_dec or not dte:
        return None
    return spot * iv_dec * math.sqrt(dte / 365.0)


def verdict(strategie, liq, spot, capital, gain_exc) -> dict:
    """Verdict analytique — jamais une probabilité inventée."""
    asym = (gain_exc / capital) if (capital and capital > 0 and gain_exc is not None) else None
    cher = bool(spot and capital and (capital / (spot * 100.0) > SEUIL_PRIME_CHERE))
    if liq.get('key') == 'insuffisante':
        #  Le motif doit rester distinguable : « spread non coté » (absence) et
        #  « spread mesuré hors seuil » (mesure) menaient au MÊME libellé, ce qui
        #  rendait indiscernable un contrat illiquide d'un contrat non coté.
        motif = ('liquidité mesurée insuffisante' if liq.get('spread_mesure')
                 else 'liquidité NON ÉVALUABLE (spread non coté)')
        return {'label': 'Liquidité insuffisante', 'tone': 'neg',
                'why': '%s — aucun verdict positif possible' % motif,
                'dominant': 'liquidite'}
    if asym is None:
        return {'label': 'Données insuffisantes', 'tone': 'muted', 'why': 'asymétrie non calculable'}
    if asym >= 3:
        return {'label': 'Asymétrie excellente', 'tone': 'pos',
                'why': 'gain exceptionnel ≈ %s× la perte max' % _fmt(asym, 1)}
    if asym >= 1.8:
        if cher:
            return {'label': 'Structure intéressante mais chère', 'tone': 'warn',
                    'why': 'asymétrie %s× mais prime élevée (>12 %% du notionnel)' % _fmt(asym, 1)}
        return {'label': 'Structure intéressante', 'tone': 'muted',
                'why': 'asymétrie %s× — correcte sans être exceptionnelle' % _fmt(asym, 1)}
    dte = strategie.get('days_to_exp')
    if dte is not None and dte < 20:
        return {'label': 'Risque/temps médiocre', 'tone': 'warn',
                'why': 'échéance courte (%s j) pour cette asymétrie' % dte}
    if asym < 1.2:
        return {'label': 'Risque/temps médiocre', 'tone': 'warn',
                'why': 'asymétrie faible (%s×)' % _fmt(asym, 1)}
    return {'label': 'Attendre une meilleure entrée', 'tone': 'muted',
            'why': 'asymétrie moyenne — patienter est une décision valide'}


def scenarios(spot, em, direction, payoff, capital, dte):
    """Trois scénarios À L'ÉCHÉANCE (pessimiste ~−1σ, probable ~+1σ, exceptionnel
    ~+2σ, orientés par le biais). Liste vide sans mouvement attendu."""
    if not em or not spot:
        return []
    defs = [('Pessimiste', spot - direction * em, 'mouvement contraire ~1σ', 'neg', 'down'),
            ('Probable', spot + direction * em, 'mouvement attendu ~1σ (IV·√t)', 'muted', 'base'),
            ('Exceptionnel', spot + direction * 2 * em, 'mouvement favorable ~2σ', 'pos', 'up')]
    out = []
    for cle, px, cond, tone, kind in defs:
        pnl = pnl_a(payoff, px)
        pct = (pnl / capital * 100.0) if (pnl is not None and capital and capital > 0) else None
        out.append({'cle': cle, 'px': round(px, 4), 'cond': cond, 'tone': tone, 'kind': kind,
                    'pnl': None if pnl is None else round(pnl, 2),
                    'pct': None if pct is None else round(pct, 2),
                    'horizon_j': dte})
    return out


def analyser(resultat: dict, strategie: dict, board) -> dict:
    """Analyse servie avec chaque stratégie de `/api/options/strategies/<sym>`."""
    sym = str(resultat.get('sym') or resultat.get('symbol') or '').upper()
    spot = _num(resultat.get('spot'))
    iv_dec = _num(resultat.get('iv'))
    dte = strategie.get('days_to_exp')
    capital = abs(_num(strategie.get('max_loss')) or 0.0)
    em = mouvement_attendu(spot, iv_dec, dte)
    direction = -1 if str(resultat.get('bias') or '') == 'bearish' else 1
    p_prob = (spot + direction * em) if (em and spot) else None
    p_exc = (spot + direction * 2 * em) if (em and spot) else None
    payoff = strategie.get('payoff') or []
    gain_prob = pnl_a(payoff, p_prob) if p_prob is not None else None
    if strategie.get('max_profit_unbounded'):
        gain_exc = pnl_a(payoff, p_exc) if p_exc is not None else None
    else:
        gain_exc = _num(strategie.get('max_profit'))
    liq = liquidite_strategie(board, sym, resultat.get('exp'), strategie.get('legs'))
    verd = verdict(strategie, liq, spot, capital, gain_exc)
    asym = (gain_exc / capital) if (capital > 0 and gain_exc is not None) else None
    mp = _num(strategie.get('max_profit'))
    asym_compare = (mp / capital) if (capital > 0 and mp is not None
                                     and not strategie.get('max_profit_unbounded')) else None
    return {
        'spot': spot, 'dte': dte, 'capital': round(capital, 2), 'iv_dec': iv_dec,
        'em': None if em is None else round(em, 4),
        'p_prob': None if p_prob is None else round(p_prob, 4),
        'p_exc': None if p_exc is None else round(p_exc, 4),
        'gain_prob': None if gain_prob is None else round(gain_prob, 2),
        'gain_exc': None if gain_exc is None else round(gain_exc, 2),
        'asym': None if asym is None else round(asym, 4),
        'asym_compare': None if asym_compare is None else round(asym_compare, 4),
        'liquidite': liq, 'verdict': verd,
        'scenarios': scenarios(spot, em, direction, payoff, capital, dte),
        'source': 'structure_verdict (serveur)',
        'note': ('valeurs à l’échéance (payoff) ; sans IV, aucun mouvement attendu ni scénario ; '
                 'liquidité = pire jambe ; lecture seule'),
    }


__all__ = ['etat_liquidite', 'liquidite_strategie', 'pnl_a', 'mouvement_attendu',
           'verdict', 'scenarios', 'analyser', 'RANG_LIQUIDITE', 'SEUIL_PRIME_CHERE']
