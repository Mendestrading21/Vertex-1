"""vertex.research.institutional.factor_model — exposition aux facteurs (§23).

Facteurs : MARCHÉ, BÊTA, TAILLE, VALUE, QUALITY, GROWTH, MOMENTUM, LOW_VOL,
PROFITABILITY, INVESTMENT. Couche d'ENRICHISSEMENT : aucune décision, aucun ordre.
"""
from __future__ import annotations

import math

FACTORS = ('MARKET', 'BETA', 'SIZE', 'VALUE', 'QUALITY', 'GROWTH', 'MOMENTUM',
           'LOW_VOL', 'PROFITABILITY', 'INVESTMENT')


def _mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


def _std(xs):
    if len(xs) < 2:
        return 0.0
    m = _mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def beta_vs_benchmark(returns: list[float], bench_returns: list[float]) -> float | None:
    n = min(len(returns), len(bench_returns))
    if n < 30:
        return None
    r, b = returns[-n:], bench_returns[-n:]
    mb, mr = _mean(b), _mean(r)
    var_b = _mean([(x - mb) ** 2 for x in b])
    if not var_b:
        return None
    cov = _mean([(x - mb) * (y - mr) for x, y in zip(b, r)])
    return round(cov / var_b, 3)


def factor_exposures(stock: dict, bench_returns: list[float] | None = None) -> dict:
    """stock : {'returns': [...], 'market_cap', 'pe', 'pb', 'margin', 'roe',
    'revenue_growth', 'capex_to_revenue', 'debt_to_equity'}.
    Rend {facteur: {'value': float|None, 'note': str}} — None si donnée absente."""
    out: dict[str, dict] = {}
    rets = stock.get('returns') or []

    beta = beta_vs_benchmark(rets, bench_returns or []) if bench_returns else None
    out['MARKET'] = {'value': 1.0 if rets else None, 'note': 'exposé au marché actions US'}
    out['BETA'] = {'value': beta, 'note': 'bêta 60-252 séances vs benchmark' if beta is not None
                   else 'benchmark absent — bêta non calculé'}
    mc = stock.get('market_cap')
    out['SIZE'] = {'value': round(math.log10(mc), 2) if mc else None,
                   'note': 'log10 de la capitalisation'}
    pe, pb = stock.get('pe'), stock.get('pb')
    val = None
    if pe and pe > 0:
        val = round(min(2.0, 15.0 / pe), 2)
    elif pb and pb > 0:
        val = round(min(2.0, 2.0 / pb), 2)
    out['VALUE'] = {'value': val, 'note': 'proxy inverse de valorisation (>1 = value)'}
    roe, margin = stock.get('roe'), stock.get('margin')
    q = None
    if roe is not None or margin is not None:
        q = round(_mean([x for x in (roe, margin) if x is not None]), 3)
    out['QUALITY'] = {'value': q, 'note': 'moyenne ROE/marge'}
    out['GROWTH'] = {'value': stock.get('revenue_growth'), 'note': 'croissance CA'}
    if len(rets) >= 252:
        mom = 1.0
        for r in rets[-252:-21]:
            mom *= (1 + r)
        out['MOMENTUM'] = {'value': round(mom - 1, 3), 'note': '12-1 mois'}
    elif len(rets) >= 63:
        mom = 1.0
        for r in rets[-63:]:
            mom *= (1 + r)
        out['MOMENTUM'] = {'value': round(mom - 1, 3), 'note': '3 mois (historique court)'}
    else:
        out['MOMENTUM'] = {'value': None, 'note': 'historique insuffisant'}
    vol = _std(rets[-63:]) * math.sqrt(252) if len(rets) >= 63 else None
    out['LOW_VOL'] = {'value': round(-vol, 3) if vol is not None else None,
                      'note': 'négatif de la vol annualisée (haut = défensif)'}
    out['PROFITABILITY'] = {'value': margin, 'note': 'marge nette/opérationnelle'}
    capex = stock.get('capex_to_revenue')
    out['INVESTMENT'] = {'value': round(-capex, 3) if capex is not None else None,
                         'note': 'négatif du capex/CA (conservatisme d’investissement)'}

    #  CHAQUE FACTEUR DIT CE QUI LUI MANQUE — mesuré le 2026-09-06.
    #
    #  L'unique appelant de production (`engines/portfolio_context`) construit
    #  `factor_input = {symbole: {'returns': [...]}}` : il ne transmet AUCUNE
    #  donnée fondamentale. Sur les dix facteurs, seuls MARKET, BETA, MOMENTUM
    #  et LOW_VOL peuvent donc porter une valeur ; les six autres sont None en
    #  permanence, et l'appelant traduisait cela par une raison unique et vague,
    #  « preuve facteur indisponible pour les positions couvertes ».
    #
    #  Ce n'est pas faux, c'est INEXPLOITABLE : le lecteur ne peut pas savoir si
    #  la donnée manque à la source, si elle n'a pas été demandée, ou si le
    #  calcul a échoué. Le modèle est le seul à savoir ce que chaque facteur
    #  exige ; il le publie donc, et l'absence cesse d'être une seule couleur.
    for facteur, entrees in REQUIS.items():
        item = out.get(facteur)
        if item is None:
            continue
        item['requiert'] = list(entrees)
        if item['value'] is None and entrees:
            manquantes = [c for c in entrees if stock.get(c) in (None, '', [])]
            if manquantes:
                item['manquant'] = manquantes
                item['note'] = '%s — entrée(s) absente(s) : %s' % (
                    item['note'], ', '.join(manquantes))
    return out


#: Ce que chaque facteur EXIGE du dictionnaire `stock`. Un facteur sans exigence
#: (BETA) dépend d'un autre paramètre, nommé dans sa propre note.
REQUIS = {
    'MARKET': ('returns',),
    'BETA': (),
    'SIZE': ('market_cap',),
    'VALUE': ('pe', 'pb'),
    'QUALITY': ('roe', 'margin'),
    'GROWTH': ('revenue_growth',),
    'MOMENTUM': ('returns',),
    'LOW_VOL': ('returns',),
    'PROFITABILITY': ('margin',),
    'INVESTMENT': ('capex_to_revenue',),
}


def couverture_entrees(stock: dict) -> dict:
    """Quelles entrées le dictionnaire `stock` porte-t-il réellement ?

    Rend {entrée: bool} pour toutes les entrées citées par `REQUIS`, plus le
    compte des facteurs calculables. Sert à un appelant qui veut DIRE, sans
    deviner, pourquoi une exposition est incomplète.
    """
    entrees = sorted({c for cs in REQUIS.values() for c in cs})
    presentes = {c: stock.get(c) not in (None, '', []) for c in entrees}
    calculables = [f for f, cs in REQUIS.items()
                   if not cs or any(presentes.get(c) for c in cs)]
    return {'entrees': presentes, 'facteurs_calculables': sorted(calculables),
            'facteurs_totaux': len(REQUIS)}
