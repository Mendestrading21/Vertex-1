"""vertex.portfolio.stress_tests — chocs standardisés sur le portefeuille réel (§26)."""
from __future__ import annotations

from .models import PortfolioSnapshot

SCENARIOS = ('SPY_MINUS_5', 'SPY_MINUS_10', 'NASDAQ_MINUS_10', 'VIX_PLUS_50',
             'RATES_PLUS_50BP', 'RATES_MINUS_50BP', 'TOP_SECTOR_MINUS_15',
             'IV_CRUSH', 'EARNINGS_GAP_ADVERSE', 'CORRELATIONS_TO_ONE')


def run_stress_tests(snapshot: PortfolioSnapshot, profile,
                     sector_of: dict | None = None,
                     nasdaq_exposure: dict | None = None,
                     rate_sensitivity_bp: float | None = None,
                     options_vega_value: float | None = None,
                     earnings_positions: list[str] | None = None,
                     options_open: int | None = None) -> dict:
    """Impacts estimés en % de l'équité. Hypothèses documentées, pas de fausse précision.

    `options_open` : nombre d'options ouvertes DÉCLARÉES, quand l'appelant le
    connaît. Il sépare deux situations que `options_vega_value=None` confondait :
    « aucune option » (impact d'un IV crush réellement nul) et « des options
    sans greeks broker » (impact INCONNU). Non transmis → inconnu, jamais 0.
    """
    eq = snapshot.equity
    out = {'equity': eq, 'scenarios': {}, 'assumptions': [
        'impact via bêta par position (bêta 1.0 si inconnu — documenté)',
        'chocs instantanés sans rebalancement',
    ], 'warnings': []}
    if not eq:
        out['warnings'].append('équité incalculable (prix manquants) — stress tests refusés')
        return out
    sector_of = sector_of or {}
    weights = snapshot.weights()
    beta_declared = [p.symbol for p in snapshot.positions if p.beta is not None]
    beta_defaulted = [p.symbol for p in snapshot.positions if p.beta is None]
    beta_coverage = round(sum(weights.get(symbol, 0) for symbol in beta_declared), 1)
    out['beta_assumptions'] = {
        'declared_symbols': beta_declared,
        'defaulted_symbols': beta_defaulted,
        'declared_weight_pct': beta_coverage,
        'default_beta': 1.0,
        'read_only': True,
        'note': 'bêta de repli explicitement identifié ; aucune sensibilité n’est inventée',
    }

    def beta_of(p):
        return p.beta if p.beta is not None else 1.0

    def market_shock(pct, only=None):
        impact = 0.0
        for p in snapshot.positions:
            if only is not None and not only(p):
                continue
            impact += (weights.get(p.symbol, 0) / 100) * beta_of(p) * pct
        return round(impact, 2)

    out['scenarios']['SPY_MINUS_5'] = {'impact_pct': market_shock(-5)}
    out['scenarios']['SPY_MINUS_10'] = {'impact_pct': market_shock(-10)}
    ndx = nasdaq_exposure or {}
    out['scenarios']['NASDAQ_MINUS_10'] = {
        'impact_pct': market_shock(-10, only=lambda p: ndx.get(p.symbol, True))}
    #  MESURE : avec 2 options déclarées et aucun greek broker, IV_CRUSH sortait
    #  « 0,0 % » et VIX_PLUS_50 « −0,0 % · choc actions modéré + gain/perte vega
    #  des options ». Preuve décisive : la même requête SANS `option_positions`
    #  rendait des scénarios BIT POUR BIT identiques — le vega ne changeait rien,
    #  pendant que la note affirmait le contraire. `options_vega_value or 0.0`
    #  écrasait l'INCONNU en un zéro CONNU : invariant 5 (« zéro, absent,
    #  estimation restent distincts »). Un 0 % n'est vrai que sans aucune option.
    vega_val = options_vega_value
    vega_inconnu = vega_val is None
    if vega_inconnu and options_open == 0:
        vega_val, vega_inconnu = 0.0, False       # aucune option : le zéro est un fait
    if vega_inconnu:
        _manque = ('%d option(s) ouverte(s) sans vega broker (greeks IBKR requis)'
                   % options_open if options_open else
                   'vega des options non transmis')
        out['scenarios']['VIX_PLUS_50'] = {
            'impact_pct': None,
            'note': '%s — non estimé (le volet actions seul ne serait pas ce scénario)' % _manque}
    else:
        out['scenarios']['VIX_PLUS_50'] = {
            'impact_pct': round(market_shock(-4) + (vega_val / eq * 100 if eq else 0), 2),
            'note': 'choc actions modéré + gain/perte vega des options'}
    if rate_sensitivity_bp is not None:
        out['scenarios']['RATES_PLUS_50BP'] = {'impact_pct': round(rate_sensitivity_bp * 50, 2)}
        out['scenarios']['RATES_MINUS_50BP'] = {'impact_pct': round(-rate_sensitivity_bp * 50, 2)}
    else:
        out['scenarios']['RATES_PLUS_50BP'] = {'impact_pct': None,
                                               'note': 'sensibilité taux inconnue — non estimé'}
        out['scenarios']['RATES_MINUS_50BP'] = {'impact_pct': None,
                                                'note': 'sensibilité taux inconnue — non estimé'}
    sector_weights: dict[str, float] = {}
    for p in snapshot.positions:
        sec = p.sector or sector_of.get(p.symbol, 'Inconnu')
        sector_weights[sec] = sector_weights.get(sec, 0) + weights.get(p.symbol, 0)
    if sector_weights:
        top_sec, top_w = max(sector_weights.items(), key=lambda kv: kv[1])
        out['scenarios']['TOP_SECTOR_MINUS_15'] = {
            'impact_pct': round(-15 * top_w / 100, 2), 'sector': top_sec}
    if vega_inconnu:
        out['scenarios']['IV_CRUSH'] = {
            'impact_pct': None,
            'note': 'greeks broker requis pour chiffrer un IV crush — non estimé'}
    else:
        out['scenarios']['IV_CRUSH'] = {
            'impact_pct': round(-abs(vega_val) * 0.3 / eq * 100, 2) if vega_val else 0.0,
            'note': ('contraction d’IV de 30 % sur les options longues détenues'
                     if vega_val else
                     'aucune option ouverte déclarée — un IV crush est sans effet')}
    earnings_positions = earnings_positions or []
    gap_w = sum(weights.get(s, 0) for s in earnings_positions)
    out['scenarios']['EARNINGS_GAP_ADVERSE'] = {
        'impact_pct': round(-12 * gap_w / 100, 2),
        'positions': earnings_positions,
        'note': 'gap défavorable de -12 % sur les positions avec résultats imminents'}
    stock_w = sum(w for s, w in weights.items() if s != '_CASH')
    out['scenarios']['CORRELATIONS_TO_ONE'] = {
        'impact_pct': round(-10 * stock_w / 100, 2),
        'note': 'toutes corrélations → 1 : la diversification disparaît, '
                'seul le cash protège (choc -10 % uniforme)'}
    #  PÉRIMÈTRE de la base de stress, publié avec les chiffres. `equity` vient
    #  de PortfolioSnapshot (positions valorisées + cash) : les options déclarées
    #  n'y entrent pas. Mesuré : 14 100 $ engagés sur 39 188 $ de capital déclaré
    #  (36 %) restaient hors base ET hors impact, sous une tuile « pire scénario
    #  −0,1 % » sans périmètre. La carte voisine (engines/portfolio_stress) le
    #  disait déjà ; ce bloc-ci ne le disait nulle part.
    out['coverage'] = {
        'equity_basis': 'positions valorisées du snapshot + cash',
        'options_open': options_open,
        'options_in_equity': False,
        'options_vega_known': not vega_inconnu,
        'read_only': True,
        'note': ('base de stress = positions valorisées + cash ; les options déclarées '
                 'exigent marque et greeks IBKR et restent hors base'),
    }
    if options_open:
        #  Avertissement réservé au cas où des options SONT déclarées : quand le
        #  périmètre n'est pas transmis, `coverage.options_open: null` et les
        #  notes « non estimé » des scénarios disent déjà ce qui manque, sans
        #  noyer un desk sans option sous un avertissement permanent.
        out['warnings'].append(
            '%d option(s) hors base de stress — les %% sont rapportés aux positions '
            'valorisées + cash, pas au capital total déclaré' % options_open)
    worst = min((v['impact_pct'] for v in out['scenarios'].values()
                 if v.get('impact_pct') is not None), default=None)
    out['worst_case_pct'] = worst
    if worst is not None and worst <= profile.portfolio_max_drawdown_pct:
        out['warnings'].append(f'pire scénario {worst}% dépasse le drawdown max '
                               f'{profile.portfolio_max_drawdown_pct}% — réduire le risque')
    return out
