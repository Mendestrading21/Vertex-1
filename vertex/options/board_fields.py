# -*- coding: utf-8 -*-
"""vertex.options.board_fields — lecture normalisée des champs de liquidité
d'une ligne de board d'options.

POURQUOI CE MODULE EXISTE (mesure du 2026-09-06, instance de contrôle, board
RÉEL yfinance, DEMO_MODE=false) : le producteur canonique
`legacy_engine.build_board` (l. 383) publie `spread` (déjà en %, calculé l. 338
`(ask - bid) / mid * 100`) et `vol`. Le board de DÉMONSTRATION
(`vertex/data/demo.py`:111) publie `spread_pct` et `vol` ; seules les fixtures
de tests publient `volume`. Comptage sur le board servi : `spread` présent
96/96 contrats, `spread_pct` 0/96 ; sur `options_cache.json` : 481 contrats,
`spread_pct` 0/481, `volume` 0/481.

(Ce paragraphe affirmait que la démonstration publie `volume` — vérifié le
2026-09-06 : `demo.py:111` écrit `'oi': oi, 'vol': vol, 'spread_pct': …`. Le
fichier se contredisait, le commentaire interne de `spread_pct()` disant déjà
la bonne chose. Trois alias, trois producteurs distincts : le dire faux ici,
c'est la première marche vers un quatrième alias mort.)

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

    L'ORDRE DES ALIAS N'EST PAS UNE AUTORITÉ : le refus d'imputation passe
    AVANT lui. Mesure du 2026-09-06 sur un contrat portant `spread_pct: 99.0`
    et `quoted_bid_ask: false` — l'accesseur rendait 99.0, c'est-à-dire la
    pénalité servie comme une mesure, le défaut même que ce module existe pour
    fermer, simplement arrivé par l'autre nom. Aucun producteur n'émet
    aujourd'hui les deux clés (board réel `spread` 96/96, démo `spread_pct`,
    fixtures `spread_pct`), donc l'ordre est inobservable : raison de plus pour
    qu'il ne décide de rien.

    CONTREPARTIE ASSUMÉE du refus, pour qu'elle ne surprenne personne : le
    refus porte sur le CONTRAT, pas sur la valeur. Un producteur futur qui
    servirait un spread RÉELLEMENT mesuré à côté d'un `quoted_bid_ask: false`
    verrait sa mesure refusée elle aussi. C'est délibéré — aucun producteur
    n'émet cette combinaison aujourd'hui, et tant que le témoin dit « pas de
    carnet exploitable », un pourcentage de fourchette n'a pas de référent
    observable. Le jour où un tel producteur existe, c'est le TÉMOIN qu'il
    faut enrichir (dire d'où vient le spread), pas ce refus qu'il faut lever.
    """
    if not isinstance(contract, dict):
        return None
    if _spread_impute(contract):
        return None
    value = _num(contract.get('spread_pct'))
    if value is not None:
        return value
    return _num(contract.get('spread'))


def volume(contract):
    """Volume du jour d'une ligne de board — ou None (absence).

    `volume` (fixtures) puis `vol` (board réel et démo). `legacy_engine._i`
    convertit un volume absent en 0 : `liquidity_coverage.volume_present`
    est le seul témoin de la différence, et un zéro imputé ne doit jamais
    passer pour un volume observé — QUEL QUE SOIT l'alias qui le porte.
    Mesuré : un contrat `{'vol': 675, 'volume': 0, volume_present: false}`
    rendait 0 (le zéro imputé servi comme une observation) parce que le témoin
    n'était consulté que sur la branche de repli.
    """
    if not isinstance(contract, dict):
        return None
    if _couverture(contract).get('volume_present') is False:
        return None
    value = _num(contract.get('volume'))
    if value is None:
        value = _num(contract.get('vol'))
    #  Un volume est un COMPTE : le rendre entier quand il l'est, pour ne pas
    #  servir « 675.0 » là où le board publiait 675.
    return int(value) if (value is not None and value.is_integer()) else value


def open_interest(contract):
    """Intérêt ouvert d'une ligne de board — ou None (absence).

    MÊME défaut que le volume, MÊME témoin, jamais lu. Mesuré le 2026-09-06 :
    `legacy_engine.build_board` publie quatre drapeaux de présence dans
    `liquidity_coverage` — `bid_present`, `ask_present`, `volume_present`,
    `open_interest_present` — et un balayage du dépôt ne trouve un lecteur que
    pour le troisième. Or `_i(raw_oi)` convertit un intérêt ouvert ABSENT en
    `0` : à l'écran comme dans les moteurs, un contrat dont le courtier n'a rien
    reporté est indiscernable d'un contrat réellement sans position ouverte.

    Le paquet porte pourtant la phrase « champ absent ≠ zéro observé ; aucune
    liquidité n'est imputée » : elle était vraie du paquet, fausse du champ.
    """
    if not isinstance(contract, dict):
        return None
    if _couverture(contract).get('open_interest_present') is False:
        return None
    value = _num(contract.get('open_interest'))
    if value is None:
        value = _num(contract.get('oi'))
    return int(value) if (value is not None and value.is_integer()) else value


def bid(contract):
    """Meilleure offre d'achat — ou None (absence).

    `_f(raw_bid)` impute `0.0` quand le courtier ne cote pas. Un bid de zéro est
    une information forte (contrat sans acheteur) ; un bid ABSENT n'en est pas
    une, et les confondre fabrique un spread de 100 %.
    """
    return _cote(contract, 'bid_present', 'bid')


def ask(contract):
    """Meilleure demande de vente — ou None (absence). Voir `bid`."""
    return _cote(contract, 'ask_present', 'ask')


def _cote(contract, temoin, cle):
    if not isinstance(contract, dict):
        return None
    if _couverture(contract).get(temoin) is False:
        return None
    return _num(contract.get(cle))


def couverture_liquidite(contract):
    """Ce que la ligne a RÉELLEMENT reporté, pour l'afficher sans le déduire.

    Rend un dict `{champ: bool|None}` — `None` quand le board ne porte aucun
    témoin (fixtures anciennes, board de démonstration), ce qui est distinct de
    « le champ est absent ».
    """
    c = _couverture(contract)
    return {nom: c.get(nom) if nom in c else None
            for nom in ('bid_present', 'ask_present', 'volume_present',
                        'open_interest_present')}


__all__ = ['spread_pct', 'volume', 'open_interest', 'bid', 'ask',
           'couverture_liquidite']
