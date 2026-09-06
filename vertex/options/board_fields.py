# -*- coding: utf-8 -*-
"""vertex.options.board_fields — lecture normalisée des champs de liquidité
d'une ligne de board d'options.

POURQUOI CE MODULE EXISTE (mesure du 2026-09-06, instance de contrôle, board
RÉEL yfinance, DEMO_MODE=false) : le producteur canonique
`legacy_engine.build_board` (l. 383) publie `spread` (déjà en %, calculé l. 338
`(ask - bid) / mid * 100`) et `vol`. Le board de DÉMONSTRATION
(`vertex/data/demo.py`:111) et les fixtures de tests publient `spread_pct` et
`volume`. Comptage sur le board servi : `spread` présent 96/96 contrats,
`spread_pct` 0/96 ; sur `options_cache.json` : 481 contrats, `spread_pct` 0/481,
`volume` 0/481.

Tous les consommateurs qui lisaient `spread_pct` voyaient donc une ABSENCE
PERMANENTE sur données réelles, et ne fonctionnaient qu'en démonstration :
  - `structure_verdict.etat_liquidite` imprimait la sentinelle « spread 99.0 % »
    comme une mesure, à côté d'un OI réel, et rendait « Liquidité insuffisante »
    sur NVDA (spread réel 6,5 %), MSFT (3,2 %) et AAPL (2,0 %) ;
  - `environment._score_liquidity` déclarait « liquidité (spread) indisponible »
    et sortait la PIRE dimension du score : 52,2 MITIGÉ au lieu de 34,8 HOSTILE,
    couverture 40 % au lieu de 60 % ;
  - `overview.summarize` servait `avg_spread_pct: null` et un radar muet ;
  - `horizon_scanners` motivait 33/33 lignes du Scanner LEAPS par « spread
    indisponible » et 74/74 SWING_3_6M par « volume indisponible ».

UN SEUL ACCESSEUR, ICI. Il lit les deux noms, n'en invente aucun, et refuse de
rendre une valeur IMPUTÉE pour une mesure : quand les deux clés manquent, ou
quand le board a substitué une pénalité au défaut de cotation, la réponse est
`None` — une ABSENCE, distincte d'un zéro et d'une mesure (invariant 5).

Lecture seule : aucune écriture, aucun ordre, aucune donnée de compte.
"""
from __future__ import annotations

import math


def _num(x):
    """Nombre fini, ou None. Un booléen n'est pas une mesure."""
    if isinstance(x, bool):
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _couverture(contract):
    c = contract.get('liquidity_coverage')
    return c if isinstance(c, dict) else {}


def _spread_impute(contract) -> bool:
    """Vrai quand le `spread` du board réel est une PÉNALITÉ, pas une mesure.

    `legacy_engine.py:338` pose 99.0 dès que le bid/ask n'est pas exploitable
    alors que le contrat n'est pas marqué `stale` (marché croisé ou verrouillé,
    `ask <= bid`). Ce 99.0 n'a jamais été observé sur un carnet : le servir
    comme un pourcentage mesuré est exactement le défaut qui faisait imprimer
    « OI 4615 · spread 99.0 % » sur un contrat dont le spread réel valait 6,5 %.
    """
    if _couverture(contract).get('quoted_bid_ask') is False:
        return True
    bid, ask = _num(contract.get('bid')), _num(contract.get('ask'))
    if bid is not None and ask is not None and bid > 0 and ask > 0 and ask <= bid:
        return True
    return False


def spread_pct(contract):
    """Spread bid/ask en POURCENTAGE d'une ligne de board — ou None (absence).

    Ordre de lecture : `spread_pct` (démo, fixtures, chemins cotation) puis
    `spread` (board réel, MÊME grandeur et MÊME unité, cf. legacy_engine.py:345
    qui réinjecte cette valeur exacte sous le nom `spread_pct` dans le scoring).
    Aucune conversion d'unité : les deux sont déjà des pourcentages.
    """
    if not isinstance(contract, dict):
        return None
    value = _num(contract.get('spread_pct'))
    if value is not None:
        return value
    if _spread_impute(contract):
        return None
    return _num(contract.get('spread'))


def volume(contract):
    """Volume du jour d'une ligne de board — ou None (absence).

    `volume` (fixtures) puis `vol` (board réel et démo). `legacy_engine._i`
    convertit un volume absent en 0 : `liquidity_coverage.volume_present`
    est le seul témoin de la différence, et un zéro imputé ne doit jamais
    passer pour un volume observé.
    """
    if not isinstance(contract, dict):
        return None
    value = _num(contract.get('volume'))
    if value is None:
        if _couverture(contract).get('volume_present') is False:
            return None
        value = _num(contract.get('vol'))
    #  Un volume est un COMPTE : le rendre entier quand il l'est, pour ne pas
    #  servir « 675.0 » là où le board publiait 675.
    return int(value) if (value is not None and value.is_integer()) else value


__all__ = ['spread_pct', 'volume']
