"""vertex.portfolio.risk_engine — risque du portefeuille RÉEL (§26, corrige §6.9).

Calcule sur les positions réelles (IBKR/desk) ou simulées explicitement
transmises — JAMAIS sur les candidats du scanner (ce vieux comportement vit
encore dans legacy_basket_risk.py pour les vues « panier », clairement nommé).
"""
from __future__ import annotations

from .correlation import correlation_matrix
from .models import PortfolioSnapshot

MAX_STOCK_WEIGHT_DEFAULT = 15.0


def portfolio_risk(snapshot: PortfolioSnapshot, profile,
                   returns_by_symbol: dict | None = None,
                   sector_of: dict | None = None,
                   options_greeks: list[dict] | None = None) -> dict:
    """Rapport de risque complet sur positions réelles/simulées explicites."""
    if snapshot.provenance not in ('REAL', 'SIMULATED'):
        raise ValueError('risque calculable uniquement sur positions réelles ou '
                         f'simulées explicites (reçu: {snapshot.provenance!r})')
    weights = snapshot.weights()
    sector_of = sector_of or {}
    warnings: list[str] = []

    # Poids & concentration
    stock_weights = {s: w for s, w in weights.items() if s != '_CASH'}
    overweight = {s: w for s, w in stock_weights.items()
                  if w > profile.max_stock_weight_pct}
    for s, w in overweight.items():
        warnings.append(f'{s}: poids {w}% > max {profile.max_stock_weight_pct}%')
    #  MESURE : 1 action KO (88,07 $) + 25 000 $ de cash sortait `hhi 0.0`,
    #  peint « bien dispersé » en vert, alors que la MÊME réponse levait
    #  `overweight ['KO']`. Cause : les poids étaient divisés par l'équité
    #  TOTALE (cash compris au dénominateur) mais le terme cash était retiré du
    #  numérateur — ni le Herfindahl du compartiment actions, ni celui du
    #  portefeuille complet, donc un indice qui ne mesure rien de nommable.
    #  Avec un titre unique, la jauge ne quittait le vert qu'au-delà de 57,4 %
    #  de l'équité : tout desk dont le cash dépasse ~0,75 × la valeur actions
    #  était peint en vert quelle que soit sa concentration réelle.
    #  `hhi` mesure désormais LE COMPARTIMENT ACTIONS, poids renormalisés à
    #  100 % — la seule base sur laquelle les seuils de lecture (3 lignes
    #  équipondérées ≈ 0,33) ont un sens. Sans action, il vaut None (inconnu),
    #  jamais 0 (« dispersé »).
    _invested_pct = round(sum(stock_weights.values()), 2)
    hhi = (round(sum((w / _invested_pct) ** 2 for w in stock_weights.values()), 4)
           if _invested_pct else None)

    # Secteurs
    sector_weights: dict[str, float] = {}
    for p in snapshot.positions:
        sec = p.sector or sector_of.get(p.symbol, 'Inconnu')
        w = weights.get(p.symbol, 0)
        sector_weights[sec] = round(sector_weights.get(sec, 0) + w, 2)
    top_sector = max(sector_weights.items(), key=lambda kv: kv[1]) if sector_weights else None
    if top_sector and top_sector[1] > 40:
        warnings.append(f'secteur {top_sector[0]} à {top_sector[1]}% (> 40%)')

    # Bêta pondéré
    betas = [(weights.get(p.symbol, 0) / 100, p.beta) for p in snapshot.positions
             if p.beta is not None]
    beta = round(sum(w * b for w, b in betas), 2) if betas else None
    beta_missing = [p.symbol for p in snapshot.positions if p.beta is None]
    beta_coverage = {
        'known_positions': len(betas),
        'total_positions': len(snapshot.positions),
        'coverage_pct': round(100 * len(betas) / len(snapshot.positions), 1) if snapshot.positions else 0.0,
        'missing_symbols': beta_missing,
        'partial': bool(beta_missing),
    }

    # Corrélations
    corr = correlation_matrix(returns_by_symbol or {})
    if corr.get('warning'):
        warnings.append(corr['warning'])

    # Drawdown & règle -25 %
    dd = snapshot.drawdown_pct
    no_new_risk = False
    if dd is not None and dd <= profile.portfolio_max_drawdown_pct:
        no_new_risk = True
        warnings.append(f'drawdown portefeuille {dd}% ≤ {profile.portfolio_max_drawdown_pct}% '
                        '— AUCUN nouveau risque, AUCUNE nouvelle option, revue obligatoire')

    # Drawdown par titre (-20 %)
    per_stock_dd = {}
    for p in snapshot.positions:
        if p.avg_cost and p.last_price:
            pl = round((p.last_price / p.avg_cost - 1) * 100, 1)
            per_stock_dd[p.symbol] = pl
            if pl <= profile.stock_max_drawdown_pct:
                warnings.append(f'{p.symbol}: {pl}% ≤ {profile.stock_max_drawdown_pct}% '
                                '— revue de position obligatoire')

    # Exposition options agrégée
    greeks = {'delta': None, 'gamma': None, 'theta': None, 'vega': None,
              'open_options': 0}
    if options_greeks:
        def _agg(name, dp):
            # Somme des seules valeurs connues ; None si aucune (jamais un 0
            # agrégé qui sous-estimerait l'exposition). `partial` signale un
            # agrégat incomplet.
            vals = [g.get(name) for g in options_greeks if g.get(name) is not None]
            return round(sum(vals), dp) if vals else None
        _known = sum(1 for g in options_greeks if g.get('delta') is not None)
        greeks = {'delta': _agg('delta', 3), 'gamma': _agg('gamma', 4),
                  'theta': _agg('theta', 3), 'vega': _agg('vega', 3),
                  'open_options': len(options_greeks),
                  'greeks_partial': _known < len(options_greeks),
                  'coverage': {
                      'delta_known': _known,
                      'total_options': len(options_greeks),
                      'delta_coverage_pct': round(100 * _known / len(options_greeks), 1) if options_greeks else 0.0,
                      'note': 'grecques absentes ne sont jamais interprétées comme nulles',
                  }}
        if greeks['open_options'] > profile.max_simultaneous_options:
            no_new_risk = True
            warnings.append(f"{greeks['open_options']} options ouvertes > maximum "
                            f'{profile.max_simultaneous_options}')

    return {'provenance': snapshot.provenance, 'as_of': snapshot.as_of,
            'equity': snapshot.equity, 'weights': weights,
            'sector_weights': sector_weights, 'hhi': hhi, 'beta': beta,
            #  Le périmètre voyage AVEC la mesure : un « HHI » sans base
            #  annoncée est illisible, et cette page en affiche déjà un second
            #  (portfolio_context, toutes lignes, cash exclu du dénominateur).
            'hhi_basis': ('compartiment actions, poids renormalisés à 100 % — '
                          'cash exclu du calcul'),
            'invested_pct': _invested_pct,
            #  Ancien indicateur CONSERVÉ sous son vrai nom : parts du capital
            #  total au carré, terme cash exclu du numérateur. Il répond à
            #  « quelle part du capital total un titre représente-t-il ? »,
            #  jamais à « le compartiment actions est-il concentré ? ».
            'hhi_total_equity': round(sum((w / 100) ** 2 for w in stock_weights.values()), 4),
            'beta_coverage': beta_coverage,
            'correlations': {'average': corr.get('average'),
                             'high_pairs': corr.get('high_pairs'),
                             'pairs': corr.get('pairs'),
                             'symbols_covered': corr.get('symbols_covered'),
                             'warning': corr.get('warning')},
            'drawdown_pct': dd, 'per_stock_pl_pct': per_stock_dd,
            'options_exposure': greeks, 'overweight': overweight,
            'no_new_risk': no_new_risk, 'warnings': warnings}
