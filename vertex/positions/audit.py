"""vertex.positions.audit — audit d'intégrité (§41).

Vérifie chaque position (quantité, coût, devise, multiplicateur, contrat,
plan, source, timestamps, doublons, expirations) et produit un statut
global HEALTHY / DEGRADED / CRITICAL. Lecture seule.
"""
from __future__ import annotations

import time

from vertex.positions.models import echeance_normalisee


def _check(p: dict) -> list[str]:
    errs = []
    if not p.get('symbol'):
        errs.append('SYMBOL_MISSING')
    if p.get('quantity') is None or (p.get('quantity') or 0) <= 0:
        errs.append('QUANTITY_INVALID')
    cb = p.get('cost_basis') if p.get('asset_type') != 'OPTION' else p.get('capital_committed')
    if cb is None or cb < 0:
        errs.append('COST_BASIS_INVALID')
    if not p.get('currency'):
        errs.append('CURRENCY_MISSING')
    if not p.get('source'):
        errs.append('SOURCE_MISSING')
    if p.get('asset_type') == 'OPTION':
        if p.get('strike') is None:
            errs.append('STRIKE_MISSING')
        if not p.get('expiration'):
            errs.append('EXPIRATION_MISSING')
        elif echeance_normalisee(p['expiration']) is None:
            #  Mesuré : '2027.01.15' (saisie libre du desk) ne se relit pas —
            #  `dte` tombe à None et les gates d'expiration ne s'arment jamais.
            #  L'audit d'intégrité doit NOMMER une échéance illisible plutôt que
            #  de la laisser passer pour une échéance valide.
            errs.append('EXPIRATION_ILLISIBLE')
        if (p.get('multiplier') or 100) <= 0:
            errs.append('MULTIPLIER_INVALID')
        if p.get('dte') is not None and p['dte'] < 0 \
                and p.get('lifecycle_status') not in ('EXPIRED', 'CLOSED'):
            errs.append('EXPIRED_STILL_OPEN')
    else:
        if p.get('stop') is None:
            errs.append('STOP_UNDEFINED')
    if not p.get('thesis_text'):
        errs.append('THESIS_REQUIRED')
    return errs


def _hachable(v):
    """La même valeur si elle peut servir de clé, sinon sa forme textuelle.

    MESURE : une échéance déclarée sous forme de liste ou d'objet JSON
    (`{'expiration': ['2027-01-15']}` — le desk accepte la saisie libre) faisait
    lever `TypeError: unhashable type: 'list'` à `key in seen`, et
    `/api/positions/audit` répondait 500 sur un desk réel. L'audit d'intégrité
    est précisément la route censée SURVIVRE à une donnée malformée pour la
    nommer : planter dessus la rend invisible.

    `repr` ne devine aucune identité — deux déclarations identiques restent
    identiques, deux différentes restent différentes — et `EXPIRATION_ILLISIBLE`
    nomme déjà le défaut par ailleurs (`echeance_normalisee` rend None sur ces
    formes, vérifié).
    """
    try:
        hash(v)
    except TypeError:
        return repr(v)
    return v


def _identite(p: dict) -> tuple:
    """Identité d'une ligne, pour la détection de doublons.

    Deux corrections MESURÉES, dans les deux sens de l'erreur :

    1. L'échéance entrait BRUTE. Le même contrat MSFT 2027-01-15 500 C déclaré
       une fois '2027-01-15' et une fois '2027.01.15' (le format réellement
       présent sur le desk) sortait `HEALTHY` / 0 critique, alors que les deux
       MÊMES formats sortent `CRITICAL` — la ligne était comptée deux fois
       (9 800 $ engagés × 2, poids doublé) sans que l'audit d'intégrité la
       voie. L'échéance est donc normalisée POUR LA COMPARAISON quand elle est
       lisible ; illisible, elle entre brute (aucune identité devinée) et
       `EXPIRATION_ILLISIBLE` la nomme déjà par ailleurs.

    2. Le sens de l'option (`right`) manquait. Mesuré : un straddle MSFT
       2027-01-15 500 (un CALL + un PUT) sortait `CRITICAL` avec
       `DUPLICATE_IDENTITY` — deux contrats DIFFÉRENTS déclarés comme une
       double saisie. Un défaut inventé est aussi faux qu'un défaut caché.
    """
    exp = p.get('expiration')
    return tuple(_hachable(v) for v in
                 (p.get('asset_type'), p.get('symbol'), p.get('strike'),
                  echeance_normalisee(exp) or exp, p.get('right'), p.get('source')))


def audit_positions(positions: list[dict]) -> dict:
    findings, seen = [], {}
    for p in positions:
        errs = _check(p)
        key = _identite(p)
        if key in seen:
            errs.append('DUPLICATE_IDENTITY')
        seen[key] = True
        if errs:
            findings.append({'position_id': p.get('position_id'),
                             'symbol': p.get('symbol'), 'errors': errs})
    critical = sum(1 for f in findings
                   if any(e in ('QUANTITY_INVALID', 'COST_BASIS_INVALID',
                                'EXPIRED_STILL_OPEN', 'DUPLICATE_IDENTITY')
                          for e in f['errors']))
    status = ('CRITICAL' if critical else
              'DEGRADED' if findings else 'HEALTHY')
    return {'status': status, 'positions_checked': len(positions),
            'findings': findings, 'critical': critical,
            'generated_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}


__all__ = ['audit_positions']
