"""vertex/options/flow.py — FLUX D'OPTIONS NOTABLE (activité inhabituelle).

Repère, pour un sous-jacent, les contrats à activité NOTABLE depuis la chaîne
DÉJÀ chargée (options_board) : gros premium négocié, volume anormal vs open
interest (positionnement frais), déséquilibre call/put. C'est l'équivalent
« unusual flow » des desks — mais fondé sur le VOLUME et l'OI du cycle de scan,
PAS sur un flux tick-par-tick ni des « prints » identifiés. Étiqueté honnêtement.

Mesures (données réelles du board, jamais inventées) :
- premium négocié du cycle ≈ volume × prime × 100 (prime = cost/100).
- ratio volume / OI : > 1 ⇒ activité du jour supérieure au stock ouvert (frais).
- skew call/put en premium : d'où vient l'argent.

Invariants : lecture seule, aucun ordre ; fonction pure ; contrat sans volume ou
sans prime exploitable → ignoré ; jamais de « whale/sweep » affirmé sans preuve tick.
"""
from __future__ import annotations

from . import board_fields as _bf

CONTRACT_MULTIPLIER = 100


def _num(x):
    if isinstance(x, bool):
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    if v != v or v in (float('inf'), float('-inf')):
        return None
    return v


def _premium_per_contract(c):
    """Prime × 100 (coût d'UN contrat) depuis 'cost' (déjà ×100) ou 'mid'×100. None si absent."""
    cost = _num(c.get('cost'))
    if cost is not None and cost > 0:
        return cost
    mid = _num(c.get('mid'))
    if mid is not None and mid > 0:
        return mid * CONTRACT_MULTIPLIER
    return None


def _vol(c):
    #  Alias dupliqué ici auparavant : un seul propriétaire de la forme du board
    #  (board_fields), sinon les lecteurs redivergent du producteur.
    #  ORDRE DES ALIAS : ce module lisait `vol` PUIS `volume`, l'accesseur lit
    #  `volume` PUIS `vol`. Aucun producteur n'émet les deux (board réel `vol`
    #  96/96, démo `vol`, fixtures `volume`), donc aucun contrat servi ne change
    #  de valeur ; et l'accesseur refuse désormais un volume imputé AVANT de
    #  choisir un alias, si bien que l'ordre ne décide plus d'aucune mesure.
    return _bf.volume(c)


def analyze(contracts, *, symbol=None, top=8):
    """Flux notable d'un sous-jacent : contrats classés par premium négocié du cycle.

    Retourne un dict JSON-sérialisable ; vide honnête si aucune activité exploitable.
    """
    contracts = [c for c in (contracts or []) if isinstance(c, dict)]
    rows = []
    call_prem = put_prem = 0.0
    for c in contracts:
        vol = _vol(c)
        per = _premium_per_contract(c)
        strike = _num(c.get('strike'))
        if vol is None or vol <= 0 or per is None or strike is None:
            continue
        notional = vol * per                          # premium négocié du cycle (réel)
        #  Accesseur honnête plutôt que champ brut : `_i(None) -> 0`. Ici le
        #  zéro imputé était déjà écarté par la garde suivante, mais lire le
        #  champ brut laisse croire que la garde protège d'un zéro RÉEL —
        #  elle protégeait surtout d'une absence. Un seul accesseur pour tous
        #  les lecteurs du dépôt, sinon le prochain oubli est invisible.
        oi = _bf.open_interest(c)
        vol_oi = round(vol / oi, 2) if oi and oi > 0 else None
        is_call = str(c.get('type', '')).upper() != 'PUT'
        (call_prem, put_prem) = ((call_prem + notional, put_prem) if is_call
                                 else (call_prem, put_prem + notional))
        rows.append({
            'type': 'CALL' if is_call else 'PUT', 'strike': strike,
            'exp': c.get('exp'), 'dte': c.get('dte'),
            'vol': int(vol), 'oi': (int(oi) if oi is not None else None),
            'vol_oi': vol_oi, 'premium': round(notional),
            'fresh': (vol_oi is not None and vol_oi >= 1.0),   # volume > OI → positionnement frais
        })

    if not rows:
        return {'symbol': (symbol or None), 'empty': True, 'contracts': [],
                'call_premium': None, 'put_premium': None, 'skew': None,
                'generator': 'deterministic',
                'reason': 'aucun contrat avec volume + prime exploitables (données réelles absentes)',
                'basis': 'volume × prime du cycle de scan (pas un flux tick-par-tick)'}

    rows.sort(key=lambda r: r['premium'], reverse=True)
    total = call_prem + put_prem
    skew = None
    if total > 0:
        cp = round(100 * call_prem / total)
        skew = ('calls' if cp >= 60 else 'puts' if cp <= 40 else 'équilibré')
    return {
        'symbol': (symbol or None), 'empty': False,
        'contracts': rows[:max(1, int(top))],
        'call_premium': round(call_prem), 'put_premium': round(put_prem),
        'call_pct': (round(100 * call_prem / total) if total else None),
        'skew': skew, 'notable_count': len(rows),
        'generator': 'deterministic',
        'basis': 'volume × prime du cycle de scan (données réelles ; pas un flux tick-par-tick)',
    }


__all__ = ['analyze']
