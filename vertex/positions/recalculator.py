"""vertex.positions.recalculator — orchestrateur du cycle de vie (§3-§19).

Assemble, pour chaque position : enrichissement (calculs) → cycle de vie
(statut) → santé de thèse → priorité → action analytique → verdict moteur.
Le verdict FINAL canonique reste produit par l'ExecutiveEngine (moteur
unique) ; ce module ne fait qu'orchestrer et présenter. LECTURE SEULE.
"""
from __future__ import annotations

import time

from vertex.positions import calculator, lifecycle, thesis_health
from vertex.positions.repository import load_positions


def _detail_for(scan_state: dict, sym: str) -> dict:
    return ((scan_state or {}).get('detail') or {}).get((sym or '').upper()) or {}


def _quote_for_stock(scan_state, quotes, p):
    """Cote une action : pos-quotes composite d'abord, sinon detail scan."""
    key = '%s||%s|' % (p['symbol'], '')
    q = (quotes or {}).get(key) or (quotes or {}).get(p['symbol'])
    if q and (q.get('spot') is not None or q.get('mark') is not None):
        return {'price': q.get('spot') if q.get('spot') is not None else q.get('mark'),
                'source': 'IBKR/desk', 'stale': False}
    d = _detail_for(scan_state, p['symbol'])
    if d.get('price') is not None:
        return {'price': d['price'], 'source': scan_state.get('source') or 'scan',
                'stale': (scan_state.get('source') == 'demo')}
    return None


def _quote_for_option(quotes, p):
    exp = p.get('expiration') or ''
    strike = p.get('strike') if p.get('strike') is not None else ''
    right = 'P' if p.get('right') == 'PUT' else 'C'
    key = '%s|%s|%s|%s' % (p['symbol'], exp, strike, right)
    q = (quotes or {}).get(key)
    if not q:
        return None, None
    #  `last` et `close` TRANSMIS. Avant, ils étaient abandonnés ici : l'écran
    #  affichait `mark 3,70` avec `last: None` et `mid: None`, donc un chiffre
    #  dont l'origine était invisible. Or c'est précisément l'origine qui
    #  explique un écart de 272 USD avec le courtier sur une option peu liquide.
    opt_q = {'mark': q.get('mark') if q.get('mark') is not None else q.get('last'),
             'bid': q.get('bid'), 'ask': q.get('ask'), 'iv': q.get('iv'),
             'last': q.get('last'), 'close': q.get('close'),
             'volume': q.get('vol'), 'oi': q.get('oi'),
             'source': 'IBKR', 'stale': False}
    under = {'price': q.get('spot')} if q.get('spot') is not None else None
    return opt_q, under


def recalculate_all(scan_state: dict, desk_blob: dict | None = None,
                    quotes: dict | None = None) -> dict:
    """Recalcule TOUTES les positions ouvertes et le portefeuille agrégé."""
    positions = load_positions(desk_blob)
    positions = [p for p in positions if p.get('status') != 'CLOSED']

    for p in positions:
        d = _detail_for(scan_state, p.get('symbol') or p.get('underlying_symbol'))
        if p['asset_type'] == 'OPTION':
            oq, uq = _quote_for_option(quotes, p)
            greeks = None
            # Ne réclamer BROKER_GREEKS que si des valeurs de Greeks RÉELLES sont
            # présentes (§21). Une IV seule ne prouve pas des Greeks broker :
            # étiqueter BROKER_GREEKS sans delta/gamma/theta/vega serait un
            # label de provenance faux (règle de vérité).
            if oq and any(oq.get(k) is not None for k in ('delta', 'gamma', 'theta', 'vega')):
                greeks = {'source': 'BROKER_GREEKS',
                          'delta': oq.get('delta'), 'gamma': oq.get('gamma'),
                          'theta': oq.get('theta'), 'vega': oq.get('vega')}
            calculator.enrich_option(p, oq, uq, greeks, d)
            p['lifecycle_status'] = lifecycle.option_status(p)
        else:
            calculator.enrich_stock(p, _quote_for_stock(scan_state, quotes, p),
                                    detail=d)
            p['lifecycle_status'] = lifecycle.stock_status(p)
        th = thesis_health.assess(p, d, p.get('thesis_health')
                                  if isinstance(p.get('thesis_health'), str) else None)
        p['thesis_health'] = th['overall_status']
        p['thesis_detail'] = th
        p['priority'] = lifecycle.priority(p)
        p['analytic_action'] = lifecycle.action_for(p)

    calculator.portfolio_weights(positions)

    # Verdict moteur (ExecutiveEngine) pour les actions scannées
    #  Un verdict absent SANS cause nommée est une absence muette : mesuré en
    #  faisant lever le lecteur de catalyseurs, `recalculate_all` rendait
    #  `decision: None` sur TOUTES les positions sans qu'aucun champ ne dise
    #  pourquoi. La cause est désormais publiée avec le lot (`decision_engine`).
    moteur_indisponible = None
    try:
        from vertex.strategy import executive_engine as _ee
        from vertex.strategy import decision_packet as _dp
        #  DEUX AUTORITÉS DE DÉCISION, MESURÉ LE 2026-09-06 — et une garde
        #  dure franchie par une valeur SUPPOSÉE.
        #
        #  Ce bloc construisait son paquet à la main. Les corrections
        #  précédentes ont branché ses lecteurs un par un (fondamental,
        #  catalyseurs, régime), mais trois entrées restaient des LITTÉRAUX :
        #
        #      'data_quality': {'overall': 'RECENT' if source not in (…) …},
        #      'reconciliation': {'actionable_allowed': True},
        #      'guard': {'blocking_rules': [], 'mandatory_reviews': []},
        #
        #  `reconciliation.actionable_allowed: True` est une AFFIRMATION sans
        #  mesure. Or `scan_evidence.build_scan` pose sur CHAQUE titre le
        #  rapprochement réellement calculé. Mesure sur un detail à la forme
        #  d'un scan enrichi dont le rapprochement INTERDIT l'action
        #  (`{'available': True, 'actionable_allowed': False,
        #  'issues': ['SPOT_VS_CHAIN_MISMATCH']}`) : /api/positions/state
        #  rendait « RENFORCER » sans règle bloquante pendant que
        #  /api/strategy/decision rendait « ATTENDRE »
        #  ['SOURCE_DISAGREEMENT'] pour le MÊME titre et le MÊME scan_state.
        #  Le desk des positions détenues franchissait donc une garde dure —
        #  sur des positions déclarées par l'utilisateur — parce qu'il
        #  s'autorisait lui-même. Tant que le régime dégradait en UNKNOWN, un
        #  `REGIME_BLOCKS_NEW_RISK` fabriqué MASQUAIT le contournement ; en
        #  réparant le régime, la correction précédente l'a rendu atteignable.
        #
        #  Il n'y a donc plus de second constructeur : `decision_packet.build`
        #  est le propriétaire canonique du paquet, y compris du régime (son
        #  `_market_regime` appelle déjà `classify_regime(regime_inputs(…))`
        #  avec un repli non actionnable). Ce module n'ajoute que ce que la
        #  POSITION sait et que le scan ignore.
        #  LE GARDE PORTEFEUILLE EST MESURÉ, PAS SUPPOSÉ — ni omis.
        #
        #  `decision_packet` traite un garde ABSENT comme une preuve manquante
        #  et ajoute `DECISION_PACKET_INCOMPLETE`, ce qui plafonne le verdict à
        #  ATTENDRE. Mesuré : sans cette section, TOUTES les positions
        #  détenues rendent ATTENDRE en permanence — une garde toujours allumée
        #  ne distingue plus rien, exactement le défaut reproché au
        #  `REGIME_BLOCKS_NEW_RISK` fabriqué. L'ancien code résolvait ça par un
        #  littéral `{'blocking_rules': []}` : une autorisation affirmée.
        #
        #  Le garde est donc CALCULÉ par son propriétaire canonique
        #  (`portfolio_guard.guard_rules` sur `risk_engine.portfolio_risk`), à
        #  partir des seules positions DÉCLARÉES par l'utilisateur.
        #
        #  CE QUE CE PLAN DE TRAVAIL NE MESURE PAS, et qui est dit : la
        #  trésorerie et le pic d'équité ne sont pas déclarés sur cette
        #  surface. Vérifié chez le producteur : sans pic, `drawdown_pct` vaut
        #  None et `PORTFOLIO_DRAWDOWN_LIMIT` ne peut donc pas s'allumer à
        #  tort — mais il ne peut pas s'allumer du tout, et la couverture le
        #  nomme au lieu de laisser croire à un garde complet.
        garde = None
        try:
            from vertex.portfolio import models as _pm
            from vertex.portfolio import portfolio_guard as _pg
            from vertex.portfolio import risk_engine as _re
            from vertex.strategy import constitution as _const
            profil = _const.load_profile()
            lignes = [_pm.Position(symbol=p.get('symbol') or '',
                                   quantity=float(p.get('quantity') or 0),
                                   avg_cost=p.get('average_cost'),
                                   last_price=p.get('current_price'),
                                   sector=p.get('sector') or '',
                                   beta=p.get('beta'),
                                   sec_type=('OPT' if p.get('asset_type') == 'OPTION' else 'STK'))
                      for p in positions]
            instantane = _pm.PortfolioSnapshot(positions=lignes, cash=0.0,
                                               provenance='REAL', peak_equity=None)
            garde = _pg.guard_rules(_re.portfolio_risk(instantane, profil), profil)
            garde['coverage'] = {
                'cash_declared': False, 'peak_equity_declared': False,
                'note': 'trésorerie et pic d’équité non déclarés sur le plan de '
                        'travail : le plafond de drawdown portefeuille n’est pas '
                        'évalué ici (il l’est sur /api/portfolio/team)'}
        except Exception as exc:                          # noqa: BLE001
            #  Un garde non calculable reste ABSENT : le paquet sera déclaré
            #  incomplet et le verdict plafonné. Jamais un feu vert par défaut.
            garde = None
            moteur_indisponible = moteur_indisponible or type(exc).__name__
        etat = dict(scan_state)
        if garde is not None:
            etat['guard'] = garde

        for p in positions:
            d = _detail_for(scan_state, p.get('symbol') or p.get('underlying_symbol'))
            if not d:
                continue
            plan = d.get('plan') or {}
            packet = _dp.build(p['symbol'], d, etat)
            #  Le rapport gain/risque RESTANT est propre à la position tenue
            #  (le paquet du scan ne connaît que celui du plan d'entrée), et
            #  l'invalidation de thèse est suivie par le desk.
            tech = packet['technical']
            tech['reward_risk'] = (p.get('remaining_rr') or d.get('rr')
                                   or (plan.get('rr') if isinstance(plan, dict) else None))
            if p.get('thesis_health') == 'INVALIDATED':
                tech['thesis_invalidated'] = True
            packet['position_held'] = True
            packet['position_pl_pct'] = p.get('unrealized_pnl_pct')
            verdict = _ee.decide(packet)
            p['decision'] = verdict['final_decision']
            p['decision_blocking'] = verdict.get('blocking_rules', [])
    except Exception as exc:                              # noqa: BLE001
        moteur_indisponible = type(exc).__name__

    return {'positions': positions, 'portfolio': aggregate(positions),
            'decision_engine': {
                'available': moteur_indisponible is None,
                'reason': (None if moteur_indisponible is None else
                           'moteur de verdict indisponible (%s) — aucune décision '
                           'servie sur ce cycle' % moteur_indisponible)},
            'updated_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}


def aggregate(positions: list[dict]) -> dict:
    """Recalcul portefeuille (§23) — compteurs CALLS/PUTS séparés."""
    stocks = [p for p in positions if p['asset_type'] != 'OPTION']
    opts = [p for p in positions if p['asset_type'] == 'OPTION']
    calls = [p for p in opts if p.get('right') == 'CALL']
    puts = [p for p in opts if p.get('right') == 'PUT']

    def _sum(lst, field):
        vals = [p[field] for p in lst if p.get(field) is not None]
        return round(sum(vals), 2) if vals else None

    invested = _sum(positions, 'cost_basis') or 0
    invested += _sum(positions, 'capital_committed') or 0
    value = None
    marked = [p for p in positions if p.get('market_value') is not None]
    if marked and len(marked) == len(positions):
        value = round(sum(p['market_value'] for p in positions), 2)
    pl = round(value - invested, 2) if (value is not None and invested) else None

    # Greeks globaux — uniquement si TOUTES les options cotées avec Greeks broker
    delta = theta = None
    opt_greeks = [p for p in opts if p.get('delta') is not None]
    if opts and len(opt_greeks) == len(opts):
        delta = round(sum(p['delta'] for p in opts), 2)
        theta = round(sum(p['theta'] for p in opts if p.get('theta') is not None), 2)

    return {
        'value': value, 'value_at_cost': round(invested, 2) if invested else None,
        'unrealized_pnl': pl,
        'unrealized_pnl_pct': round(pl / invested * 100, 2) if (pl is not None and invested) else None,
        'stocks_count': len(stocks), 'stocks_max': 10,
        'calls_count': len(calls), 'puts_count': len(puts), 'puts_max': 1,
        'options_count': len(opts), 'options_max': 3,
        'delta_global': delta, 'theta_global': theta,
        'greeks_note': 'Greeks agrégés uniquement si toutes les options ont des Greeks broker (jamais estimés en agrégat).',
        'positions_needing_action': [
            {'position_id': p['position_id'], 'symbol': p['symbol'],
             'asset_type': p['asset_type'], 'priority': p.get('priority'),
             'status': p.get('lifecycle_status'), 'action': p.get('analytic_action'),
             'decision': p.get('decision'), 'pl_pct': p.get('unrealized_pnl_pct'),
             'updated_at': p.get('last_updated_at')}
            for p in sorted(positions, key=lambda x: {'P0_CRITICAL': 0, 'P1_HIGH': 1,
                                                      'P2_NORMAL': 2, 'P3_LOW': 3}.get(x.get('priority'), 4))
            if p.get('priority') in ('P0_CRITICAL', 'P1_HIGH')],
    }


__all__ = ['recalculate_all', 'aggregate']
