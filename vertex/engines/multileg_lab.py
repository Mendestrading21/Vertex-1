"""multileg_lab — analyse de stratégies options MULTI-JAMBES (READONLY).

Payoff à l'échéance, breakevens, gain/perte max (avec détection d'illimité),
probabilité de profit (modèle lognormal risque-neutre) et greeks agrégés — pour
les combinaisons que le scenario_pricer mono-jambe ne couvre pas : verticaux,
straddle/strangle, butterfly, iron condor…

100 % calcul local, AUCUNE dépendance externe (réutilise le Black-Scholes maison de
`options_lab`), AUCUN ordre : Vertex reste en lecture seule. L'UI se contente de tracer
les points renvoyés ici ; ce module ne price que ce qu'on lui donne (primes déclarées).

Convention de jambe : {type:'call'|'put'|'stock', strike, premium, qty}. qty>0 = long
(on paie), qty<0 = short (on encaisse). Les options portent un multiplicateur 100
(1 contrat = 100 actions) ; les actions un multiplicateur 1. Les montants (gain/perte
max, débit net) sont en DOLLARS ; les breakevens sont des niveaux de prix.
"""
from __future__ import annotations

import math

from vertex.engines.options_lab import _ncdf, _npdf
from vertex.options import iv_units

R_DEFAULT = 0.045  # taux sans risque annuel par défaut (traçé dans le bloc `model`)
Q_DEFAULT = 0.0    # rendement de dividende annuel par défaut (traçé dans `model`)
IV_MAX_DECIMAL = 3.0  # au-delà de 300 % : quasi certainement un POURCENTAGE non converti


def _mult(leg):
    return 100.0 if leg.get('type') in ('call', 'put') else 1.0


def _fin(x):
    """float fini ou None — jamais NaN/inf dans un calcul financier."""
    if isinstance(x, bool):
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    if math.isnan(v) or math.isinf(v):
        return None
    return v


def _validate_inputs(legs, spot, iv, days_to_exp):
    """Refus STRUCTURÉS (contrat OPTIONS_CORRECTNESS) : chaque entrée inutilisable
    est nommée (field/value/why) — jamais un calcul sur du douteux."""
    refusals = []

    def bad(field, value, why):
        refusals.append({'field': field, 'value': None if value is None else str(value), 'why': why})

    s = _fin(spot)
    if s is None or s <= 0:
        bad('spot', spot, 'cours sous-jacent absent, non fini ou <= 0')
    if days_to_exp is not None:
        d = _fin(days_to_exp)
        if d is None or d < 0:
            bad('days_to_exp', days_to_exp, 'DTE non fini ou négatif')
    if iv is not None:
        v = _fin(iv)
        if v is None or v < 0:
            bad('iv', iv, 'IV non finie ou négative (décimale attendue)')
        elif v > IV_MAX_DECIMAL:
            bad('iv', iv, 'IV > 300 % — probablement un POURCENTAGE non converti ; '
                          'le cœur exige une IV DÉCIMALE (vertex.options.iv_units)')
    for i, leg in enumerate(legs):
        t = leg.get('type')
        if t in ('call', 'put'):
            k = _fin(leg.get('strike'))
            if k is None or k <= 0:
                bad('strike', leg.get('strike'),
                    'jambe %d (%s) : strike absent, non fini ou <= 0' % (i + 1, t))
        p = leg.get('premium')
        if p is not None:
            pv = _fin(p)
            if pv is None or pv < 0:
                bad('premium', p, 'jambe %d : prime non finie ou négative' % (i + 1))
        if _fin(leg.get('qty')) is None:
            bad('qty', leg.get('qty'), 'jambe %d : quantité non finie' % (i + 1))
    return refusals


def _intrinsic(price, leg):
    """Valeur intrinsèque d'une jambe à l'échéance, par action (avant qty)."""
    t = leg.get('type')
    k = leg.get('strike') or 0.0
    if t == 'call':
        return max(0.0, price - k)
    if t == 'put':
        return max(0.0, k - price)
    return price  # stock : « intrinsèque » = cours


def _pnl(price, legs):
    """P&L de la stratégie à l'échéance, en DOLLARS, pour un cours sous-jacent donné."""
    total = 0.0
    for leg in legs:
        q = leg.get('qty') or 0.0
        m = _mult(leg)
        prem = leg.get('premium') or 0.0
        total += q * m * (_intrinsic(price, leg) - prem)
    return total


def _net_premium(legs):
    """Débit net (>0 = on paie) / crédit net (<0 = on encaisse), en dollars."""
    return sum((leg.get('qty') or 0.0) * _mult(leg) * (leg.get('premium') or 0.0)
               for leg in legs)


def _leg_greeks(spot, leg, T, iv, r=R_DEFAULT, q=Q_DEFAULT):
    """Greeks d'une jambe, déjà multipliés par qty et le multiplicateur (position).
    `q` = rendement de dividende annuel continu (0 par défaut → formules inchangées)."""
    qty = leg.get('qty') or 0.0
    m = _mult(leg)
    if leg.get('type') == 'stock':
        return {'delta': qty * m, 'gamma': 0.0, 'theta': 0.0, 'vega': 0.0, 'vanna': 0.0, 'vomma': 0.0}
    k = leg.get('strike') or 0.0
    right = 'CALL' if leg.get('type') == 'call' else 'PUT'
    if T <= 0 or iv <= 0 or spot <= 0 or k <= 0:
        return {'delta': 0.0, 'gamma': 0.0, 'theta': 0.0, 'vega': 0.0}
    sq = iv * math.sqrt(T)
    d1 = (math.log(spot / k) + (r - q + iv * iv / 2.0) * T) / sq
    d2 = d1 - sq
    nd1 = _npdf(d1)
    dq = math.exp(-q * T)                      # facteur dividende (1.0 si q=0)
    if right == 'CALL':
        delta = dq * _ncdf(d1)
        theta_yr = (-(spot * dq * nd1 * iv) / (2.0 * math.sqrt(T))
                    - r * k * math.exp(-r * T) * _ncdf(d2)
                    + q * spot * dq * _ncdf(d1))
    else:
        delta = dq * (_ncdf(d1) - 1.0)
        theta_yr = (-(spot * dq * nd1 * iv) / (2.0 * math.sqrt(T))
                    + r * k * math.exp(-r * T) * _ncdf(-d2)
                    - q * spot * dq * _ncdf(-d1))
    gamma = dq * nd1 / (spot * sq)
    vega = spot * dq * nd1 * math.sqrt(T)
    # Greeks d'ordre supérieur (identiques call/put par parité — dépendent de φ(d1)) :
    vanna = -dq * nd1 * d2 / iv                # ∂vega/∂spot = ∂delta/∂vol
    vomma = vega * d1 * d2 / iv                # ∂vega/∂vol (convexité de vol)
    scale = qty * m
    return {
        'delta': scale * delta,               # par $1 de sous-jacent
        'gamma': scale * gamma,
        'theta': scale * theta_yr / 365.0,    # par jour
        'vega': scale * vega / 100.0,         # par point d'IV (1 %)
        'vanna': scale * vanna / 100.0,       # par 1 % d'IV
        'vomma': scale * vomma / 100.0,       # par 1 % d'IV
    }


def _lognormal_pdf(price, spot, T, iv, r=R_DEFAULT, q=Q_DEFAULT):
    """Densité risque-neutre du cours à l'échéance (S_T lognormal, drift r−q)."""
    if price <= 0 or spot <= 0 or T <= 0 or iv <= 0:
        return 0.0
    sq = iv * math.sqrt(T)
    mu = math.log(spot) + (r - q - iv * iv / 2.0) * T
    z = (math.log(price) - mu) / sq
    return _npdf(z) / (price * sq)


def _breakevens(legs, grid, pnls):
    """Prix où le P&L croise zéro (interpolation linéaire entre points de grille)."""
    bes = []
    for i in range(1, len(grid)):
        a, b = pnls[i - 1], pnls[i]
        if a == 0.0:
            bes.append(round(grid[i - 1], 2))
        elif (a < 0.0) != (b < 0.0):  # changement de signe
            x0, x1 = grid[i - 1], grid[i]
            be = x0 + (x1 - x0) * (0.0 - a) / (b - a)
            bes.append(round(be, 2))
    # dédoublonnage (croisements ~ identiques)
    out = []
    for be in bes:
        if not out or abs(be - out[-1]) > 1e-6:
            out.append(be)
    return out


def analyze_strategy(legs, spot, iv, days_to_exp, r=R_DEFAULT, name=None, q=Q_DEFAULT):
    """Analyse complète d'une stratégie multi-jambes.

    Contrat d'unités (OPTIONS_CORRECTNESS) : `iv` DÉCIMALE (0.404 = 40,4 % —
    normaliser en amont via vertex.options.iv_units), `premium` PAR ACTION,
    multiplicateur 100 appliqué ici, `r`/`q` annuels continus et TRAÇÉS dans le
    bloc `model` de la sortie. Retourne un dict JSON-sérialisable ; toute donnée
    manquante => None honnête (jamais un chiffre inventé). Entrée insuffisante ou
    invalide => {'available': False, 'reason', 'refusals': [{field,value,why}]}.
    """
    legs = [l for l in (legs or []) if l and l.get('type') in ('call', 'put', 'stock')
            and (l.get('qty') or 0.0) != 0.0]
    if not legs or spot is None or (_fin(spot) or 0) == 0:
        return {'available': False, 'reason': 'jambes ou cours sous-jacent manquants.',
                'refusals': [{'field': 'legs' if not legs else 'spot', 'value': None,
                              'why': 'jambes ou cours sous-jacent manquants'}]}
    refusals = _validate_inputs(legs, spot, iv, days_to_exp)
    if refusals:
        return {'available': False,
                'reason': 'entrée invalide — ' + ' ; '.join(x['why'] for x in refusals),
                'refusals': refusals}
    # primes requises pour un P&L honnête (sinon on ne devine pas la prime)
    missing = [l for l in legs if l.get('type') in ('call', 'put') and l.get('premium') is None]
    if missing:
        return {'available': False, 'reason': 'prime manquante sur une jambe — pas de P&L inventé.',
                'refusals': [{'field': 'premium', 'value': None,
                              'why': 'prime manquante sur une jambe option'}]}

    T = max(0.0, (days_to_exp or 0) / 365.0)
    strikes = [l['strike'] for l in legs if l.get('strike')]
    hi = max([spot] + strikes) * 3.0
    steps = 480
    grid = [hi * i / steps for i in range(steps + 1)]  # inclut 0
    pnls = [_pnl(p, legs) for p in grid]

    # Pente TERMINALE au-delà de tous les strikes = exposition nette calls + actions.
    right_slope = sum((l.get('qty') or 0.0) * _mult(l)
                      for l in legs if l.get('type') in ('call', 'stock'))
    profit_unbounded = right_slope > 1e-9    # pente > 0 : gain → ∞ quand le cours monte
    loss_unbounded = right_slope < -1e-9     # pente < 0 : PERTE → ∞ (net vendeur de calls)
    max_profit = max(pnls)
    # Vers le bas, le cours ne descend pas sous 0 (P&L(0) est dans la grille) ; vers le
    # haut, le flag illimité PRIME sur tout minimum issu de la grille finie.
    max_loss = None if loss_unbounded else min(pnls)
    breakevens = _breakevens(legs, grid, pnls)

    # Probabilité de profit : intègre la densité lognormale sur les zones P&L >= 0.
    pop = None
    if T > 0 and iv and iv > 0:
        pgrid_hi = spot * math.exp(5.0 * iv * math.sqrt(T))
        pn = 1200
        pg = [pgrid_hi * i / pn for i in range(1, pn + 1)]  # évite 0
        dens = [_lognormal_pdf(p, spot, T, iv, r, q) for p in pg]
        step = pgrid_hi / pn
        total = sum(dens) * step
        if total > 0:
            prof = sum(d for p, d in zip(pg, dens) if _pnl(p, legs) >= 0.0) * step
            pop = round(prof / total * 100.0, 1)

    # Greeks agrégés (position)
    g = {'delta': 0.0, 'gamma': 0.0, 'theta': 0.0, 'vega': 0.0, 'vanna': 0.0, 'vomma': 0.0}
    have_iv = bool(iv and iv > 0 and T > 0)
    if have_iv:
        for leg in legs:
            lg = _leg_greeks(spot, leg, T, iv, r, q)
            for k in g:
                g[k] += lg[k]
        g = {k: round(v, 4) for k, v in g.items()}
    else:
        g = None

    net = _net_premium(legs)

    # Honnêteté d'exécution : les primes sont DÉCLARÉES ; un rendement exécutable
    # dépend du spread. Si bid/ask sont fournis sur toutes les jambes option, on
    # chiffre le rempli défavorable (achat à l'ask, vente au bid) ; sinon on le dit.
    opt_legs = [l for l in legs if l.get('type') in ('call', 'put')]
    have_ba = bool(opt_legs) and all(
        _fin(l.get('bid')) is not None and _fin(l.get('ask')) is not None for l in opt_legs)
    bid_ask_covered = sum(1 for l in opt_legs
                           if _fin(l.get('bid')) is not None and _fin(l.get('ask')) is not None)
    if have_ba:
        adverse = 0.0
        for l in legs:
            lq = l.get('qty') or 0.0
            if l.get('type') in ('call', 'put'):
                px = float(l['ask']) if lq > 0 else float(l['bid'])
            else:
                px = l.get('premium') or 0.0
            adverse += lq * _mult(l) * px
        execution = {'spread_slippage_included': True,
                     'net_premium_declared': round(net, 2),
                     'net_premium_adverse': round(adverse, 2),
                     'note': 'Rempli défavorable chiffré : achats à l’ask, ventes au bid (spread intégré).'}
    else:
        execution = {'spread_slippage_included': False,
                     'net_premium_declared': round(net, 2),
                     'net_premium_adverse': None,
                     'note': 'Primes déclarées (mid/last) — le rendement exécutable dépend du '
                             'spread bid/ask, non fourni ici.'}
    # Courbe payoff pour le tracé : ~80 points autour de la zone utile (0.4x → 1.8x spot).
    lo_c, hi_c = spot * 0.4, min(hi, spot * 1.8)
    cn = 80
    payoff = [{'price': round(lo_c + (hi_c - lo_c) * i / cn, 2),
               'pnl': round(_pnl(lo_c + (hi_c - lo_c) * i / cn, legs), 2)}
              for i in range(cn + 1)]

    return {
        'available': True,
        'name': name,
        'spot': round(spot, 2),
        'iv': round(iv, 4) if iv else None,
        'days_to_exp': days_to_exp,
        #  bid/ask SERVIS : la projection les coupait, donc la page ne pouvait
        #  pas montrer d'où venait le rempli défavorable qu'elle affichait.
        #  Absents quand le contrat n'est pas coté — une absence, pas un zéro.
        'legs': [{'type': l['type'], 'strike': l.get('strike'),
                  'premium': l.get('premium'), 'qty': l.get('qty'),
                  'bid': l.get('bid'), 'ask': l.get('ask')} for l in legs],
        'net_premium': round(net, 2),          # >0 débit (on paie) · <0 crédit (on encaisse)
        'is_credit': net < 0,
        'max_profit': None if profit_unbounded else round(max_profit, 2),
        'max_profit_unbounded': profit_unbounded,
        'max_loss': None if loss_unbounded else round(max_loss, 2),
        'max_loss_unbounded': loss_unbounded,  # net vendeur de calls : perte → ∞ (flag prime)
        'breakevens': breakevens,
        'probability_of_profit': pop,          # % (modèle lognormal, estimation)
        'greeks': g,                           # position (delta $1, theta/jour, vega/1%IV)
        'payoff': payoff,
        'execution': execution,                # spread/slippage : inclus ou honnêtement absent
        'input_coverage': {
            'legs': len(legs), 'option_legs': len(opt_legs),
            'premium_covered_option_legs': len(opt_legs),
            'bid_ask_covered_option_legs': bid_ask_covered,
            'bid_ask_coverage_pct': round(100 * bid_ask_covered / len(opt_legs), 1) if opt_legs else 0.0,
            'spot_available': True, 'iv_available': bool(iv and iv > 0),
            'days_to_exp_available': bool(days_to_exp and days_to_exp > 0),
            'greeks_available': g is not None, 'probability_of_profit_available': pop is not None,
            'read_only': True,
            'note': 'données absentes restent visibles ; aucune prime ou sensibilité n’est imputée',
        },
        'model': {                             # provenance du modèle — traçable, datée par l'appelant
            'type': 'lognormal_risk_neutral', 'r': r, 'q': q,
            'iv_unit': 'DECIMAL', 'premium_basis': 'declared',
            #  Lot 13 : l'hypothèse de devise est DITE, plus implicite. Aucune
            #  conversion n'existe dans Vertex — options US uniquement.
            'currency': 'USD',
            'currency_note': 'montants en USD — aucune conversion de devise '
                             'n\'existe ni n\'est estimée',
            'note': 'PoP risque-neutre — estimation, pas une fréquence historique.',
        },
        'model_note': 'Payoff à l’échéance ; PoP = modèle lognormal risque-neutre — estimation, pas une promesse.',
    }


# ─── Presets de stratégies : construit des jambes depuis 1-2 strikes déclarés ───

def build_preset(kind, spot, ref, prem=None):
    """Construit les jambes d'une stratégie canonique autour de `ref` (map de contrats).

    `ref` : {'atm':{'strike','call','put'}, 'otm_call':{...}, 'otm_put':{...}} — primes par
    action déclarées (jamais inventées). Renvoie une liste de jambes ou None si données
    insuffisantes. Sert de commodité UI ; l'utilisateur peut aussi passer des jambes libres.
    """
    def leg(t, node, key, qty):
        if not node or node.get('strike') is None or node.get(key) is None:
            return None
        jambe = {'type': t, 'strike': node['strike'], 'premium': node[key], 'qty': qty}
        #  Le carnet du contrat, RECOPIÉ s'il existe — jamais fabriqué. Les clés
        #  sont préfixées par côté (`call_bid`/`put_bid`) parce que le nœud `atm`
        #  porte les DEUX jambes. Sans ce report, `analyze_strategy` ne voyait
        #  aucun bid/ask : `bid_ask_coverage_pct` valait 0,0 et
        #  `net_premium_adverse` null sur 100 % des stratégies servies, alors
        #  que le board portait bid et ask sur les mêmes contrats.
        #  UNITÉ : `premium` vient de `cost / 100` (le coût est PAR CONTRAT),
        #  tandis que `bid`/`ask` du board sont DÉJÀ par action — les diviser
        #  fabriquerait un rempli défavorable faux d'un facteur 100.
        bid, ask = node.get(key + '_bid'), node.get(key + '_ask')
        if bid is not None and ask is not None:
            jambe['bid'], jambe['ask'] = bid, ask
        return jambe

    atm = (ref or {}).get('atm'); oc = (ref or {}).get('otm_call'); op = (ref or {}).get('otm_put')
    legs = None
    if kind == 'long_call':
        legs = [leg('call', atm, 'call', 1)]
    elif kind == 'long_put':
        legs = [leg('put', atm, 'put', 1)]
    elif kind == 'straddle':
        legs = [leg('call', atm, 'call', 1), leg('put', atm, 'put', 1)]
    elif kind == 'strangle':
        legs = [leg('call', oc, 'call', 1), leg('put', op, 'put', 1)]
    elif kind == 'bull_call_spread':
        legs = [leg('call', atm, 'call', 1), leg('call', oc, 'call', -1)]
    elif kind == 'bear_put_spread':
        legs = [leg('put', atm, 'put', 1), leg('put', op, 'put', -1)]
    elif kind == 'iron_condor':
        legs = [leg('put', op, 'put', 1), leg('put', atm, 'put', -1),
                leg('call', atm, 'call', -1), leg('call', oc, 'call', 1)]
    if not legs or any(l is None for l in legs):
        return None
    return legs


STRATEGY_LABELS = {
    'long_call': 'Call long', 'long_put': 'Put long', 'straddle': 'Straddle (ATM)',
    'strangle': 'Strangle (OTM)', 'bull_call_spread': 'Spread haussier (call)',
    'bear_put_spread': 'Spread baissier (put)', 'iron_condor': 'Iron condor',
}
_STRATEGY_ORDER = ['bull_call_spread', 'bear_put_spread', 'iron_condor', 'straddle',
                   'strangle', 'long_call', 'long_put']


# Adéquation directionnelle de base par stratégie (0 = contre-indiqué, 1 = idéal).
_FIT = {
    'long_call':        {'bullish': 1.00, 'bearish': 0.00, 'neutral': 0.20},
    'bull_call_spread': {'bullish': 0.90, 'bearish': 0.00, 'neutral': 0.30},
    'long_put':         {'bullish': 0.00, 'bearish': 1.00, 'neutral': 0.20},
    'bear_put_spread':  {'bullish': 0.00, 'bearish': 0.90, 'neutral': 0.30},
    'iron_condor':      {'bullish': 0.25, 'bearish': 0.25, 'neutral': 1.00},
    'straddle':         {'bullish': 0.45, 'bearish': 0.45, 'neutral': 0.55},
    'strangle':         {'bullish': 0.45, 'bearish': 0.45, 'neutral': 0.55},
}
_BIAS_LABEL = {'bullish': 'haussier', 'bearish': 'baissier', 'neutral': 'neutre'}


_MANDATE_CACHE = {'loaded': False, 'value': None}


def _options_mandate():
    """Règles options du PROFIL ACTIF (constitution V1) — chargées une fois.
    None honnête si la constitution est indisponible (aucune règle inventée)."""
    if not _MANDATE_CACHE['loaded']:
        try:
            from vertex.strategy.constitution import load_profile
            p = load_profile()
            op = getattr(p, 'options_profile', {}) or {}
            dte = op.get('dte') or {}
            _MANDATE_CACHE['value'] = {
                'short_options': bool(op.get('short_options', False)),
                'credit_spreads': bool(op.get('credit_spreads', False)),
                'dte_min': dte.get('absolute_minimum'),
                'dte_max': dte.get('absolute_maximum'),
                'profile_version': getattr(p, 'version', None),
            }
        except Exception:
            _MANDATE_CACHE['value'] = None
        _MANDATE_CACHE['loaded'] = True
    return _MANDATE_CACHE['value']


def _mandate_reasons(s, mandate):
    """Pourquoi une stratégie est HORS MANDAT (jamais recommandable). Le risque
    illimité est bloquant même sans profil chargé (hard gate Skyler)."""
    reasons = []
    if s.get('max_loss_unbounded'):
        reasons.append('perte théoriquement illimitée — jamais recommandable')
    if mandate is not None:
        has_short = any((l.get('qty') or 0) < 0 for l in (s.get('legs') or []))
        if has_short and not mandate['short_options']:
            reasons.append('jambe vendue — interdite par le profil actif (short_options=false)')
        if s.get('is_credit') and not mandate['credit_spreads']:
            reasons.append('stratégie à crédit — interdite par le profil actif (credit_spreads=false)')
    return reasons


def rank_strategies(strategies, bias='neutral', mandate=None):
    """Note et classe les stratégies par ADÉQUATION au contexte (heuristique TRANSPARENTE,
    aide à la décision — pas une promesse). Score = 45 % alignement directionnel +
    30 % probabilité de profit + 25 % reward/risk. Filtre ensuite par le PROFIL ACTIF :
    une stratégie hors mandat (jambe vendue, crédit, perte illimitée) reste analysable
    en laboratoire mais n'est JAMAIS marquée `recommended`. Modifie et renvoie la liste."""
    bias = bias if bias in ('bullish', 'bearish', 'neutral') else 'neutral'
    if mandate is None:
        mandate = _options_mandate()
    for s in strategies:
        fit = _FIT.get(s.get('kind'), {}).get(bias, 0.4)
        pop = (s.get('probability_of_profit') or 0.0) / 100.0
        # reward/risk normalisé (gain illimité → plafonné à 1 ; perte illimitée → 0)
        loss = abs(s.get('max_loss') or 0.0)
        if s.get('max_loss_unbounded'):
            rr = 0.0
        elif s.get('max_profit_unbounded'):
            rr = 1.0
        elif loss > 0 and s.get('max_profit') is not None:
            rr = min(1.0, (s['max_profit'] / loss) / 2.0)
        else:
            rr = 0.0
        score = 0.45 * fit + 0.30 * pop + 0.25 * rr
        s['fit_score'] = round(score * 100, 1)
        reasons = _mandate_reasons(s, mandate)
        s['hors_mandat'] = bool(reasons)
        s['mandate_reasons'] = reasons
        bits = ['aligné ' + _BIAS_LABEL[bias] if fit >= 0.7 else
                ('neutre au biais' if fit >= 0.4 else 'peu aligné au biais')]
        if s.get('probability_of_profit') is not None:
            bits.append('PoP %s%%' % s['probability_of_profit'])
        if rr >= 0.5:
            bits.append('R:R favorable')
        if reasons:
            bits.append('HORS MANDAT')
        s['fit_reason'] = ' · '.join(bits)
    strategies.sort(key=lambda s: s.get('fit_score', 0), reverse=True)
    reco_done = False
    for s in strategies:
        if not reco_done and not s['hors_mandat']:
            s['recommended'] = True
            reco_done = True
        else:
            s['recommended'] = False
    return strategies


def strategies_for_symbol(board, sym, spot, iv_hint=None, bias='neutral',
                          r=R_DEFAULT, q=Q_DEFAULT):
    """Construit + analyse les stratégies canoniques réalisables depuis le BOARD réel.

    Le board porte `cost` = prime PAR CONTRAT (×100) → convertie en prime/action.
    Choisit l'échéance la plus proche de ~35 DTE, un strike ATM et des strikes OTM,
    puis renvoie l'analyse de chaque preset constructible. Rien d'inventé : un preset
    dont un contrat manque est simplement omis.
    """
    contracts = [c for c in (board or []) if c.get('sym') == sym and c.get('strike') is not None]
    if not contracts or not spot or spot <= 0:
        return {'available': False, 'reason': 'aucun contrat pour ce titre dans le board.'}

    # échéance la plus proche de 35 DTE avec assez de strikes
    by_exp = {}
    for c in contracts:
        by_exp.setdefault(c.get('exp'), []).append(c)
    best = None
    for exp, cs in by_exp.items():
        dtes = [c.get('dte') for c in cs if c.get('dte') is not None]
        if not dtes:
            continue
        score = abs(dtes[0] - 35)
        if best is None or score < best[0]:
            best = (score, exp, cs, dtes[0])
    if best is None:
        return {'available': False, 'reason': 'échéance exploitable introuvable.'}
    _, exp, cs, dte = best

    strikes = sorted({c['strike'] for c in cs})
    atm_strike = min(strikes, key=lambda k: abs(k - spot))

    def at(typ, strike):
        if strike is None:
            return None
        return next((c for c in cs if c.get('type') == typ and c.get('strike') == strike
                     and c.get('cost') is not None), None)

    def prem(c):
        return (c.get('cost') or 0.0) / 100.0 if c else None

    def cotation(c):
        """(bid, ask) PAR ACTION du contrat, ou (None, None) — jamais imputés.

        `legacy_engine._f(None)` rend 0.0 : un contrat non coté porte donc
        `bid: 0.0, ask: 0.0` dans le board. Les recopier chiffrerait un rempli
        défavorable de 0 $ sur un carnet inexistant — exactement l'inverse de
        l'honnêteté d'exécution que ce bloc sert. Un carnet croisé (ask < bid)
        n'est pas un carnet non plus."""
        if not c:
            return (None, None)
        if (c.get('liquidity_coverage') or {}).get('quoted_bid_ask') is False:
            return (None, None)
        bid, ask = _fin(c.get('bid')), _fin(c.get('ask'))
        if bid is None or ask is None or bid <= 0 or ask <= 0 or ask < bid:
            return (None, None)
        return (bid, ask)

    def cote(c, cle):
        """Fragment `{'<cle>_bid':…, '<cle>_ask':…}` — vide si non coté."""
        bid, ask = cotation(c)
        return {} if bid is None else {cle + '_bid': bid, cle + '_ask': ask}

    otm_call_strike = min([k for k in strikes if k > atm_strike],
                          key=lambda k: abs(k - spot * 1.06), default=None)
    otm_put_strike = min([k for k in strikes if k < atm_strike],
                         key=lambda k: abs(k - spot * 0.94), default=None)
    atm_call, atm_put = at('CALL', atm_strike), at('PUT', atm_strike)
    otm_call, otm_put = at('CALL', otm_call_strike), at('PUT', otm_put_strike)

    #  Le carnet suit la prime : `ref` ne transportait QUE `strike` et la prime,
    #  donc bid/ask du board mouraient ici et toutes les stratégies servies
    #  déclaraient « spread bid/ask non fourni ».
    _atm = {'strike': atm_strike, 'call': prem(atm_call), 'put': prem(atm_put)}
    _atm.update(cote(atm_call, 'call'))
    _atm.update(cote(atm_put, 'put'))
    _oc = None
    if otm_call:
        _oc = {'strike': otm_call_strike, 'call': prem(otm_call)}
        _oc.update(cote(otm_call, 'call'))
    _op = None
    if otm_put:
        _op = {'strike': otm_put_strike, 'put': prem(otm_put)}
        _op.update(cote(otm_put, 'put'))
    ref = {'atm': _atm, 'otm_call': _oc, 'otm_put': _op}
    # IV : le contrat d'unité du board historique est mixte (%/décimal). La détection
    # vit dans l'UNIQUE frontière documentée iv_units.from_legacy_board — étiquetée
    # et propagée (iv_unit, avertissement), jamais silencieuse dans le cœur.
    raw_iv = iv_hint if (iv_hint and iv_hint > 0) else ((atm_call or atm_put or {}).get('iv'))
    iv, iv_detected_unit, iv_warning = iv_units.from_legacy_board(raw_iv)

    out = []
    for kind in _STRATEGY_ORDER:
        legs = build_preset(kind, spot, ref)
        if not legs:
            continue
        an = analyze_strategy(legs, spot, iv, dte, r=r, q=q,
                              name=STRATEGY_LABELS.get(kind, kind))
        if an.get('available'):
            an['kind'] = kind
            an['label'] = STRATEGY_LABELS.get(kind, kind)
            out.append(an)
    mandate = _options_mandate()
    rank_strategies(out, bias, mandate)  # classe + filtre par le profil actif
    # Mandat DTE du profil actif : signalé honnêtement (le labo analyse l'échéance
    # la plus liquide ~35 DTE ; la séparation TACTICAL/SWING/LEAPS arrive au lot 6).
    mandate_info = None
    if mandate is not None:
        dte_min, dte_max = mandate.get('dte_min'), mandate.get('dte_max')
        dte_ok = None
        if dte is not None and dte_min is not None and dte_max is not None:
            dte_ok = bool(dte_min <= dte <= dte_max)
        mandate_info = {
            'profile_version': mandate.get('profile_version'),
            'dte_ok': dte_ok, 'dte_bounds': [dte_min, dte_max],
            'note': None if dte_ok else (
                'Échéance analysée (%s DTE) hors du mandat DTE du profil actif (%s–%s) — '
                'analyse de laboratoire, pas une proposition de mandat.' % (dte, dte_min, dte_max)),
        }
    warnings = [w for w in [iv_warning] if w]
    return {'available': bool(out), 'sym': sym, 'spot': round(spot, 2),
            'exp': exp, 'dte': dte, 'iv': round(iv, 4) if iv else None,
            'iv_unit': ('DECIMAL' if iv else None),        # sortie toujours décimale
            'iv_detected_from': iv_detected_unit,          # unité détectée à la frontière
            'bias': bias, 'atm_strike': atm_strike, 'strategies': out,
            'mandate': mandate_info, 'warnings': warnings,
            'reason': None if out else 'primes insuffisantes dans le board pour construire une stratégie.'}
