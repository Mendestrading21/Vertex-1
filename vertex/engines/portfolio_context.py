"""vertex/engines/portfolio_context.py — PORTFOLIOCONTEXT CANONIQUE (SKYLER LOT 7).

Depuis les positions CANONIQUES (vertex.positions.repository — provenance
étiquetée MANUAL/IBKR, simulées exclues), construit le contexte portefeuille :
poids par titre, concentration (HHI, top), bornes 8-15 du profil V2, candidat
(gagnant/perdant, impact marginal), sizing S+/S/A/B.

Règles d'honnêteté :
  - les allocations par niveau sont des PLAFONDS ANALYTIQUES de la Constitution
    V2 — `never_triggers_orders: true`, jamais un ordre ;
  - JAMAIS renforcer un perdant ; un gagnant n'est renforçable qu'APRÈS
    confirmation (liste V2) ; P&L inconnu → renforcement inconnu, pas autorisé ;
  - sans cote : valorisation au COÛT, étiquetée ; une OPTION se valorise par la
    marque du contrat × multiplicateur × quantité, à défaut par le capital
    engagé — JAMAIS par la cote de son sous-jacent ; une ligne sans marque ni
    coût déclaré est EXCLUE et nommée dans `unvalued_positions`, jamais
    comptée 0 ; sans stops déclarés : budget de risque `available: false`
    (jamais estimé) ;
  - fonction PURE, déterministe. Lecture seule, aucun ordre.
"""
from __future__ import annotations

from vertex.portfolio.correlation import correlation_matrix


def _profile():
    from vertex.strategy.constitution import load_profile
    return load_profile()


def _num(x):
    """Nombre exploitable, ou None. `False`/`True` ne sont pas des montants, et
    une chaîne illisible ne devient jamais 0 — sinon l'absence redeviendrait un
    zéro chiffré, ce que l'invariant 5 interdit."""
    if isinstance(x, bool) or x is None:
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    if v != v or v in (float('inf'), float('-inf')):
        return None
    return v


def _aligned_returns(series_by_symbol, symbols):
    """Rendements quotidiens strictement alignés sur les dates communes.

    Une liste de clôtures sans dates, ou un recouvrement inférieur à 31 séances,
    ne suffit pas à déclarer une corrélation disponible.
    """
    points = {}
    for symbol in symbols:
        series = (series_by_symbol or {}).get(symbol) or {}
        dates, closes = series.get('dates'), series.get('close')
        if not isinstance(dates, list) or not isinstance(closes, list) or len(dates) != len(closes):
            continue
        values = {}
        for date, close in zip(dates, closes):
            try:
                value = float(close)
            except (TypeError, ValueError):
                continue
            if date and value > 0:
                values[str(date)] = value
        if len(values) >= 31:
            points[symbol] = values
    if len(points) < 2:
        return {}, 'séries datées insuffisantes pour au moins deux positions'
    common = set.intersection(*(set(values) for values in points.values()))
    if len(common) < 31:
        return {}, 'moins de 31 séances communes entre les positions'
    ordered = [date for date in next(iter(points.values())) if date in common]
    out = {}
    for symbol, values in points.items():
        closes = [values[date] for date in ordered]
        returns = [(current / previous - 1.0) for previous, current in zip(closes, closes[1:])
                   if previous > 0]
        if len(returns) >= 30:
            out[symbol] = returns
    return out, (None if len(out) >= 2 else 'rendements alignés insuffisants')


def build(positions, quotes=None, sym=None, capital=None, profile=None, series_by_symbol=None):
    """positions : liste canonique (repository.load_positions). quotes : {SYM: px}.
    capital : base de sizing (sinon valeur investie totale). sym : candidat étudié."""
    prof = profile or _profile()
    quotes = quotes or {}
    open_real = [p for p in (positions or [])
                 if isinstance(p, dict) and p.get('is_real') is not False
                 and str(p.get('status') or 'OPEN').upper() != 'CLOSED']
    if not open_real:
        return {'available': False,
                'reason': 'aucune position réelle déclarée (desk/IBKR) — contexte portefeuille indisponible'}

    valued_at_market = 0        # cote réelle du titre, ou marque du contrat
    valued_at_cost = 0          # action/ETF sans cote : repli sur le coût déclaré
    valued_at_committed = 0     # option sans marque : repli sur le capital engagé
    unvalued = []               # ni marque ni coût : EXCLUE et NOMMÉE, jamais 0
    by_sym = {}
    asset_values = {}
    asset_counts = {}
    unclassified_assets = 0
    for p in open_real:
        s = str(p.get('symbol') or p.get('sym') or '').upper()
        if not s:
            continue
        qty = _num(p.get('quantity')) or 0.0
        asset_type = str(p.get('asset_type') or '').upper()
        if not asset_type:
            asset_type = 'UNCLASSIFIED'
            unclassified_assets += 1
        px = _num(quotes.get(s))
        #  Clé propriétaire du coût DÉCLARÉ, alignée sur vertex/positions/audit.py:18 :
        #  le modèle canonique n'écrit jamais `cost_basis` sur une option, il écrit
        #  `capital_committed` (vertex/positions/models.py:151). Lire la mauvaise clé
        #  faisait tomber toute option à 0.
        cost = _num(p.get('capital_committed') if asset_type == 'OPTION' else p.get('cost_basis'))
        if cost is None:
            cost = _num(p.get('cost_basis') if asset_type == 'OPTION' else p.get('capital_committed'))
        if asset_type == 'OPTION':
            #  MESURE (2026-09) : 7 contrats MSFT étaient valorisés 7 × 499,70 $ =
            #  3 497,90 $ parce que `quotes` porte le SPOT DU SOUS-JACENT. Ce chiffre
            #  n'est ni la prime (marque absente), ni le capital engagé (9 800 $), ni
            #  le notionnel (349 800 $) : une cote d'action ne valorise pas un contrat.
            #  Marque du contrat → mark × multiplicateur × quantité (même formule que
            #  vertex/positions/calculator.py) ; sinon repli DIT sur le capital engagé.
            #  Le spot du sous-jacent n'entre jamais dans cette branche.
            mark = _num(p.get('mark'))
            mult = _num(p.get('multiplier')) or 100.0
            if mark is not None and qty:
                val = mark * mult * qty
                valued_at_market += 1
            elif cost is not None:
                val = cost
                valued_at_committed += 1
            else:
                val = None
        elif px is not None and qty:
            val = qty * px
            valued_at_market += 1
        elif cost is not None:
            val = cost
            valued_at_cost += 1
        else:
            val = None
        if val is None:
            #  Ni cote/marque, ni coût déclaré : la position est EXCLUE du total, des
            #  poids et du mix, et NOMMÉE. Mesure : une option à 50 000 $ engagés était
            #  comptée 0 $ / 0 % pendant que la note affirmait « valorisée au coût ».
            #  Absence et zéro doivent rester distincts (invariant 5).
            unvalued.append({
                'symbol': s, 'asset_type': asset_type,
                'reason': ('option sans marque ni capital engagé déclaré — jamais '
                           'valorisée par la cote du sous-jacent'
                           if asset_type == 'OPTION'
                           else 'ni cote réelle ni coût déclaré — jamais valorisée à zéro'),
            })
            continue
        asset_values[asset_type] = asset_values.get(asset_type, 0.0) + val
        asset_counts[asset_type] = asset_counts.get(asset_type, 0) + 1
        #  `cost` et `qty` TOUS LIGNES CONFONDUES sont retirés : depuis la
        #  séparation `quotable_*`, ils étaient écrits et plus jamais lus
        #  (vérifié : `by_sym` ne sort pas de cette fonction, et les seules
        #  lectures sont value / quotable_cost / quotable_qty / option_lines).
        #  Les garder côte à côte, c'est laisser à portée de main exactement la
        #  paire qui fabriquait le −64 % : un coût par contrat divisé par un
        #  nombre de contrats, confronté à un spot par titre.
        e = by_sym.setdefault(s, {'value': 0.0, 'quotable_cost': 0.0,
                                  'quotable_qty': 0.0, 'option_lines': 0})
        e['value'] += val
        if asset_type == 'OPTION':
            e['option_lines'] += 1
        else:
            #  Seules ces lignes sont comparables à `quotes[symbole]` (prix par titre) :
            #  le P&L du candidat ne doit jamais confronter un spot à un coût par contrat
            #  (9 800 $ / 7 contrats = 1 400 $ contre un spot de 499,70 $ → −64 % inventé).
            e['quotable_cost'] += cost or 0.0
            e['quotable_qty'] += qty

    total = sum(e['value'] for e in by_sym.values())
    if total <= 0:
        return {'available': False,
                'reason': ('aucune position valorisable : %d position(s) sans marque ni coût '
                           'déclaré — exclue(s) plutôt que comptée(s) 0' % len(unvalued)
                           if unvalued else 'valeur totale nulle — poids incalculables'),
                'unvalued_positions': unvalued}
    weights = {s: round(e['value'] / total * 100, 2) for s, e in by_sym.items()}
    asset_mix = {
        asset: {'value': round(value, 2), 'weight_pct': round(value / total * 100, 2),
                'positions': asset_counts.get(asset, 0)}
        for asset, value in sorted(asset_values.items())
    }
    from vertex.market import sectors
    sector_values, unclassified_sectors = {}, []
    for symbol, position in by_sym.items():
        sector = sectors.SECTOR_MAP.get(symbol)
        if not sector:
            unclassified_sectors.append(symbol)
            continue
        sector_values[sector] = sector_values.get(sector, 0.0) + position['value']
    classified_sector_value = sum(sector_values.values())
    sector_mix = {
        sector: {'value': round(value, 2), 'weight_pct': round(value / total * 100, 2)}
        for sector, value in sorted(sector_values.items())
    }
    sector_coverage = {
        'available': bool(sector_values), 'classified_symbols': sorted(
            symbol for symbol in by_sym if symbol not in unclassified_sectors),
        'unclassified_symbols': sorted(unclassified_sectors),
        'classified_value_pct': round(100 * classified_sector_value / total, 1),
        'unclassified_value_pct': round(100 * (total - classified_sector_value) / total, 1),
        'read_only': True,
        'note': 'seul le référentiel sectoriel existant est utilisé ; aucun secteur par défaut',
    }
    hhi = round(sum((e['value'] / total) ** 2 for e in by_sym.values()), 4)
    top_sym = max(by_sym, key=lambda s: by_sym[s]['value'])

    n = len(by_sym)
    pmin, pmax = prof.portfolio_min_positions, prof.portfolio_max_positions
    max_w = prof.max_stock_weight_pct
    rules = (prof.raw.get('position_rules') or {})
    confirmations = rules.get('add_only_after_confirmation') or []

    # ── Candidat ────────────────────────────────────────────────────────────────
    candidate = None
    if sym:
        s = str(sym).upper()
        held = s in by_sym
        weight = weights.get(s, 0.0)
        pnl_pct, pnl_note = None, None
        if held:
            e = by_sym[s]
            px = _num(quotes.get(s))
            #  `quotes[symbole]` est un prix PAR TITRE : il ne se compare qu'au coût
            #  des lignes linéaires. Confronter un spot de 499,70 $ au coût par contrat
            #  (9 800 $ / 7 = 1 400 $) rendrait un P&L de −64 % purement fabriqué : sur
            #  un symbole porté par des options, le P&L reste INCONNU (None), et
            #  `reinforcement_allowed` reste None — inconnu n'est pas autorisé.
            if px is not None and e['quotable_qty'] and e['quotable_cost']:
                avg = e['quotable_cost'] / e['quotable_qty']
                pnl_pct = round((px / avg - 1) * 100, 2) if avg > 0 else None
            if pnl_pct is None and e['option_lines']:
                pnl_note = ('%d ligne(s) option sur ce symbole : le P&L exige la marque du '
                            'contrat, la cote du sous-jacent ne le donne pas'
                            % e['option_lines'])
        is_loser = (None if pnl_pct is None else bool(pnl_pct < 0)) if held else False
        if not held:
            reinforcement = 'NOT_HELD'
        elif is_loser is True:
            reinforcement = False           # JAMAIS renforcer un perdant (V2)
        elif is_loser is False:
            reinforcement = 'AFTER_CONFIRMATION'   # gagnant : preuve exigée, pas un oui aveugle
        else:
            reinforcement = None            # P&L inconnu → inconnu, pas autorisé
        candidate = {'symbol': s, 'held': held, 'weight_pct': weight,
                     'pnl_pct': pnl_pct, 'pnl_note': pnl_note, 'is_loser': is_loser,
                     'reinforcement_allowed': reinforcement,
                     'reinforcement_conditions': list(confirmations),
                     'note': 'Jamais renforcer un perdant ; gagnant renforçable seulement après confirmation (Constitution V2).'}

    # ── Sizing par niveau (plafonds analytiques V2) ─────────────────────────────
    sizing = None
    lv = prof.raw.get('conviction_levels') or {}
    base = capital if capital is not None else total
    levels = {}
    cand_w = (candidate or {}).get('weight_pct', 0.0) if candidate else 0.0
    for name in ('S_PLUS', 'S', 'A', 'B'):
        cfg = lv.get(name) or {}
        alloc = cfg.get('allocation_pct')
        if not alloc:
            continue
        amounts = [round(base * alloc[0] / 100.0, 2), round(base * alloc[1] / 100.0, 2)]
        resulting = round(cand_w + alloc[1], 2)
        levels[name] = {'allocation_pct': list(alloc), 'amount_range': amounts,
                        'resulting_weight_pct': resulting,
                        'concentration_breach': bool(resulting > max_w)}
    if levels:
        sizing = {'base': base,
                  'base_note': ('capital fourni' if capital is not None
                                else 'valeur investie totale (capital non fourni)'),
                  'levels': levels, 'max_stock_weight_pct': max_w,
                  'never_triggers_orders': True,
                  'note': 'Plafonds ANALYTIQUES de la Constitution V2 — jamais un ordre.'}

    returns, correlation_reason = _aligned_returns(series_by_symbol, list(by_sym))
    correlations = correlation_matrix(returns) if returns else {}
    if returns:
        correlation_context = {
            'available': bool(correlations.get('pairs')),
            'average': correlations.get('average'),
            'high_pairs': correlations.get('high_pairs') or {},
            'pairs': correlations.get('pairs') or {},
            'symbols_covered': correlations.get('symbols_covered') or [],
            'warning': correlations.get('warning'),
            'method': 'rendements journaliers alignés sur dates communes ; minimum 30 rendements',
        }
        if not correlation_context['available']:
            correlation_context['reason'] = 'aucune paire corrélable malgré les séries disponibles'
    else:
        correlation_context = {'available': False,
                               'reason': correlation_reason or 'données de corrélation non branchées'}

    #  Périmètre de la valorisation, DIT plutôt que supposé. Chaque repli porte sa
    #  raison : le lecteur doit pouvoir distinguer « valorisé au marché », « valorisé
    #  au coût », « valorisé au capital engagé » et « non valorisable, exclu ».
    #  Mesure d'origine : `valuation_note` valait null sur un total de 4 256,59 $ dont
    #  4 168,52 $ venaient de contrats valorisés à la cote de leur sous-jacent.
    valuation = {
        'at_market': valued_at_market, 'at_cost': valued_at_cost,
        'at_committed': valued_at_committed, 'unvalued': len(unvalued),
        'total_positions': len(open_real), 'read_only': True,
        'method': ('cote réelle du titre ; marque du contrat × multiplicateur × quantité '
                   'pour une option ; à défaut coût déclaré (capital engagé pour une '
                   'option) ; jamais la cote du sous-jacent pour un contrat'),
    }
    _notes = []
    if valued_at_cost:
        _notes.append('%d position(s) valorisée(s) au coût (cote absente) — jamais un prix inventé'
                      % valued_at_cost)
    if valued_at_committed:
        _notes.append('%d option(s) valorisée(s) au capital engagé (marque du contrat absente ; '
                      'la cote du sous-jacent ne valorise pas un contrat)' % valued_at_committed)
    if unvalued:
        _notes.append('%d position(s) exclue(s) du total et des poids (ni marque, ni coût '
                      'déclaré) — jamais comptée(s) 0' % len(unvalued))
    valuation_note = ' · '.join(_notes) or None

    from vertex.portfolio import historical_stress
    stress_test = historical_stress.assess(weights, series_by_symbol)
    measured_risk, unmeasured_risk = [], []
    for position in open_real:
        symbol = str(position.get('symbol') or position.get('sym') or '').upper()
        quantity = position.get('quantity') or 0
        price, stop = quotes.get(symbol), position.get('stop')
        asset_type = str(position.get('asset_type') or '').upper()
        if asset_type == 'OPTION':
            unmeasured_risk.append({'symbol': symbol, 'reason': 'option : perte au stop sous-jacent non valorisable sans grecques de position'})
            continue
        if price is None or stop is None or not quantity:
            unmeasured_risk.append({'symbol': symbol, 'reason': 'cote, stop ou quantité manquant'})
            continue
        try:
            risk_value = (float(price) - float(stop)) * float(quantity)
        except (TypeError, ValueError):
            unmeasured_risk.append({'symbol': symbol, 'reason': 'cote, stop ou quantité non numérique'})
            continue
        if risk_value < 0:
            unmeasured_risk.append({'symbol': symbol, 'reason': 'stop au-dessus de la cote : risque long non interprétable'})
            continue
        measured_risk.append({'symbol': symbol, 'risk_to_stop': round(risk_value, 2)})
    risk_coverage = round(100 * len(measured_risk) / len(open_real), 1) if open_real else 0.0
    risk_budget = {'available': bool(measured_risk), 'read_only': True,
                   'covered_positions': len(measured_risk), 'total_positions': len(open_real),
                   'coverage_pct': risk_coverage,
                   'known_risk_to_stop': round(sum(item['risk_to_stop'] for item in measured_risk), 2) if measured_risk else None,
                   'by_position': measured_risk, 'unmeasured': unmeasured_risk,
                   'note': 'perte jusqu’au stop déclarée ; positions sans preuve de stop ne sont pas estimées'}
    if not measured_risk:
        risk_budget['reason'] = 'aucun stop mesurable — budget de risque non estimé'
    from vertex.portfolio.factor_exposure import portfolio_factor_exposure
    factor_input = {symbol: {'returns': returns.get(symbol) or []} for symbol in by_sym}
    factor_exposure = portfolio_factor_exposure(
        type('Snapshot', (), {'positions': [type('Position', (), {'symbol': symbol})() for symbol in by_sym],
                              'weights': lambda _self: weights})(),
        factor_input,
        returns.get('SPY') if returns else None,
    )
    factor_availability = {
        factor: {'available': (item.get('value') is not None),
                 'coverage_pct': item.get('coverage_pct', 0.0),
                 'reason': (None if item.get('value') is not None else
                            'preuve facteur indisponible pour les positions couvertes')}
        for factor, item in factor_exposure.items()
    }
    factor_coverage = max((item.get('coverage_pct') or 0 for item in factor_exposure.values()), default=0)
    factor_context = {
        'available': bool(returns), 'coverage_pct_max': factor_coverage,
        'factors': factor_exposure,
        'availability': factor_availability,
        'method': 'rendements canoniques alignés ; facteurs fondamentaux absents restent non disponibles',
        'read_only': True, 'never_triggers_orders': True,
    }
    if not returns:
        factor_context['reason'] = correlation_reason or 'rendements canoniques insuffisants'

    return {
        'available': True, 'generator': 'deterministic',
        'n_positions': n, 'bounds': {'min': pmin, 'max': pmax},
        'in_bounds': bool(pmin <= n <= pmax), 'free_slots': max(0, pmax - n),
        'total_value': round(total, 2), 'weights': weights, 'hhi': hhi,
        #  Le périmètre voyage AVEC la mesure. DEUX « HHI » cohabitent dans le
        #  produit et ne répondent pas à la même question : celui-ci porte sur
        #  TOUTES les lignes valorisées (options au capital engagé comprises),
        #  celui de portfolio/risk_engine sur le seul compartiment actions
        #  renormalisé. Sur la même page, sous le même nom et avec des seuils
        #  différents, ils rendaient deux verdicts opposés sans que rien ne dise
        #  lequel mesurait quoi. Nommer la base est la moitié serveur du
        #  correctif ; l'étiquetage à l'écran appartient à la page.
        'hhi_basis': ('toutes les lignes valorisées (actions, ETF et options au capital '
                      'engagé) ; le cash n’est pas une ligne et n’entre pas au dénominateur'),
        'asset_mix': asset_mix,
        'sector_mix': sector_mix,
        'sector_coverage': sector_coverage,
        'asset_mix_note': ('%d position(s) sans type d’actif canonique — jamais classée(s) par défaut'
                           % unclassified_assets if unclassified_assets else None),
        'top_symbol': top_sym, 'top_weight_pct': weights[top_sym],
        'valuation': valuation,
        'valuation_note': valuation_note,
        'unvalued_positions': unvalued,
        'candidate': candidate, 'sizing': sizing,
        'risk_budget': risk_budget,
        'correlations': correlation_context,
        'stress_test': stress_test,
        'factor_exposure': factor_context,
        'provenance': sorted({p.get('source') or 'MANUAL' for p in open_real}),
    }


__all__ = ['build']
