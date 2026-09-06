"""vertex/app/routes/strategy_os_api.py — API du Vertex Strategy OS (Ch. §36-37).

Expose les nouveaux moteurs : constitution, décision exécutive unique, régime
de marché, anomalies, équipe, diagnostics, qualité de données, alertes.
Lecture seule — aucune route n'écrit ailleurs que dans la mémoire stratégique
(propositions) et rien ne peut toucher un ordre.
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from vertex.alerts.engine import AlertEngine
from vertex.ai.audit import AUDIT as _AI_AUDIT
from vertex.data_sources.tradingview_signal_store import SIGNAL_STORE
from vertex.engines.market_context import regime_inputs
from vertex.market.regime_engine import classify_regime
from vertex.observability.diagnostics import data_quality_report, system_diagnostics
from vertex.portfolio import models as _pmodels
from vertex.portfolio import portfolio_guard, risk_engine, stress_tests
from vertex.portfolio.team_engine import team_view
from vertex.strategy import constitution as _constitution
from vertex.strategy import decision_packet as _decision_packet
from vertex.strategy import executive_engine as _executive

ALERTS = AlertEngine()


def build_executive_decision(sym: str, scan_state: dict):
    """Construit le packet moteur + rend la décision exécutive pour <sym>.

    Source UNIQUE du verdict — réutilisée par l'API décision ET l'analyste IA,
    pour qu'aucun verdict ne diverge entre le dossier et l'interprétation Claude.
    Retourne (packet, resp) ou (None, None) si le titre est absent du scan.
    """
    sym = (sym or '').upper()
    detail = (scan_state.get('detail') or {}).get(sym) or {}
    if not detail:
        return None, None
    #  UN SEUL constructeur de packet. Le corps qui vivait ici en fabriquait
    #  un second, a la main, en posant `blocking_rules: []`,
    #  `mandatory_reviews: []` et `actionable_allowed: True` EN DUR : le packet
    #  se declarait donc complet par construction, sans que rien ne l'ait
    #  verifie. Consequence mesuree : un packet INCOMPLET rendait `ACHETER` la
    #  ou la doctrine impose `ATTENDRE` (invariant 6 — un score eleve ne
    #  contourne jamais une garde dure), et `decision_packet.complete`
    #  n'existait meme pas dans la reponse.
    #
    #  `decision_packet.build` est le proprietaire canonique : il derive la
    #  qualite, le rapprochement et les gardes des donnees REELLES, et pose
    #  `DECISION_PACKET_INCOMPLETE` quand une preuve manque.
    packet = _decision_packet.build(sym, detail, scan_state)
    #  Lot C — ce bloc ECRASAIT le regime du packet avec un mapping inline lisant
    #  `scan_state['market'].{regime,spy_trend,breadth,vix}`. Or cette cle est
    #  l'HORLOGE de seance (market_status) : clés réelles ['et','open','session'].
    #  Les trois entrees arrivaient donc None -> regime UNKNOWN, confidence 0.0,
    #  dimensions [] -> `REGIME_BLOCKS_NEW_RISK` allume sur 15/15 des titres du
    #  scan, avec l'audit « regime UNKNOWN — nouveau risque bloque ». Au meme
    #  instant, /api/market/regime — defini dans CE fichier, sur CE meme
    #  scan_state — rendait CHOP, confidence 0.6, 4 dimensions et
    #  new_risk_allowed True. Deux autorites contradictoires pour une capacite,
    #  et la garde dure la plus visible du produit neutralisee en se faisant
    #  passer pour active. Le proprietaire canonique du mapping scan -> moteur
    #  est `market_context.regime_inputs`, deja importe en tete de fichier et
    #  deja consomme par /api/market/regime : `decision_packet.build` l'appelle
    #  desormais, ce bloc n'a plus lieu d'etre. Un ecrasement en moins = un
    #  proprietaire unique du regime, comme l'exige CLAUDE.md.
    #
    #  L'ancien `except` posait `{}`, falsy : executive_engine.py:92 teste
    #  `if regime_ctx and ...`, donc un classifieur en PANNE ouvrait le risque
    #  neuf au lieu de le fermer. `decision_packet._market_regime` rend un
    #  UNKNOWN fail-closed a la place.
    resp = _executive.decide(packet, _constitution.load_profile())
    # Fraîcheur RÉELLE du scan (jamais l'heure du navigateur) — le verdict dérive de
    # scan_state['detail'], aussi vieux que le dernier scan.
    if isinstance(resp, dict):
        resp['as_of'] = scan_state.get('scan_ts_h') or scan_state.get('updated')
    return packet, resp


def make_blueprint(scan_state: dict) -> Blueprint:
    bp = Blueprint('strategy_os', __name__)

    def _profile():
        return _constitution.load_profile()

    @bp.route('/api/strategy/profile')
    def strategy_profile():
        p = _profile()
        return jsonify({'strategy_id': p.strategy_id, 'display_name': p.display_name,
                        'version': p.version, 'style': p.style,
                        'versions_available': _constitution.list_versions(),
                        'profile': p.raw})

    @bp.route('/api/strategy/decision/<sym>')
    def strategy_decision(sym):
        packet, resp = build_executive_decision(sym, scan_state)
        if packet is None:
            # 200 + available:false : état applicatif honnête (pas une erreur
            # transport) — un 404 pollue la console navigateur à chaque fiche.
            # Aucun verdict n'est FABRIQUÉ hors scan : `final_decision` est
            # null et l'état `NON_EVALUE` dit pourquoi. Un « ATTENDRE » ici
            # se lisait comme une conclusion du moteur alors qu'il n'avait
            # rien calculé.
            return jsonify({'available': False,
                            'etat': 'NON_EVALUE',
                            'error': f'{sym.upper()} absent du scan courant',
                            'final_decision': None,
                            'reason': 'titre hors scan courant — aucun verdict calculé'}), 200
        #  `build_executive_decision` ci-dessus construit DEJA le packet,
        #  appelle le moteur et pose `as_of`. Le corps qui suivait refaisait
        #  tout une seconde fois — et sur `detail`, un nom qui n'existe pas
        #  dans cette portee. La route de decision, coeur du produit, levait
        #  donc `NameError` a CHAQUE appel : le gestionnaire d'erreur de Flask
        #  rendait 500 et la fiche restait sans verdict.
        if isinstance(resp, dict):
            resp['decision_packet'] = packet.get('decision_packet') or {}
        return jsonify(resp)

    @bp.route('/api/market/regime')
    def market_regime():
        # La clé `market` du scan est l'horloge (market_status), pas les données —
        # le mapping canonique scan → moteur vit dans market_context.regime_inputs.
        resp = classify_regime(regime_inputs(scan_state))
        if isinstance(resp, dict):
            #  Le régime est daté par le SCAN qui l'a produit : sans `as_of`,
            #  trois pages affichaient l'heure du navigateur comme âge.
            resp['as_of'] = scan_state.get('scan_ts_h') or scan_state.get('updated')
            resp['ts'] = scan_state.get('scan_ts')
        return jsonify(resp)

    @bp.route('/api/company/twin/<sym>')
    def company_twin_ep(sym):
        """Jumeau analytique entreprise (§16) — champs absents = None, jamais 0."""
        from vertex.companies import company_twin
        return jsonify(company_twin(sym, scan_state))

    #  Lot 9 — la route /api/anomalies/<sym> qui vivait ici est RETIRÉE.
    #  Elle etait MASQUEE depuis toujours : analysis_api declare le meme
    #  chemin et gagne au dispatch. Les deux formes de reponse divergeaient
    #  (ici {anomalies:[...]}, la-bas le scan du moteur canonique), et le seul
    #  consommateur de CETTE forme — la page legacy /strategy-os — est une
    #  redirection 301 : du code mort des deux cotes. Le proprietaire unique
    #  est analysis_api.api_anomalies, sur la serie canonique. Un gardien
    #  generique (test_collisions_routes) interdit toute reapparition
    #  d'une route a deux proprietaires.

    @bp.route('/api/portfolio/team', methods=['GET', 'POST'])
    def portfolio_team():
        """GET : message d'usage. POST : positions EXPLICITES {positions:[...], cash}."""
        if request.method == 'GET':
            return jsonify({'usage': 'POST {positions: [{symbol, quantity, avg_cost, '
                                     'last_price, sector, beta}], cash, peak_equity, '
                                     'simulated: bool} — le risque ne se calcule que sur '
                                     'des positions réelles ou simulées explicites'})
        body = request.get_json(silent=True) or {}
        positions = [_pmodels.Position(
            symbol=str(p.get('symbol', '')).upper(), quantity=float(p.get('quantity') or 0),
            avg_cost=p.get('avg_cost'), last_price=p.get('last_price'),
            sector=p.get('sector', ''), beta=p.get('beta'),
            sec_type=p.get('sec_type', 'STK')) for p in body.get('positions') or []]
        cash = float(body.get('cash') or 0)
        peak = body.get('peak_equity')
        if body.get('simulated'):
            snap = _pmodels.simulated(positions, cash=cash, peak_equity=peak)
        else:
            snap = _pmodels.PortfolioSnapshot(positions=positions, cash=cash,
                                              provenance='REAL', peak_equity=peak)
        profile = _profile()
        # ── Greeks RÉELS du desk (modelGreeks IBKR persistés) — jamais estimés ──
        from vertex.options import on_demand as _od
        _greeks = _od.desk_greeks(body.get('option_positions') or [])
        _legs = _greeks.get('legs') or []
        #  Aucune série de rendements n'est alignée sur cette route. La variable
        #  le DIT au lieu de le sous-entendre : la cause servie plus bas est
        #  conditionnée à ce fait mesurable, et non plus à « la matrice est vide ».
        #  Sans cela, le jour où `returns_by_symbol` sera branché, une matrice
        #  légitimement vide (aucune paire à 30 rendements communs) recevrait
        #  encore le texte « cette route ne fournit aucune série de rendements »,
        #  qui serait alors FAUX — une cause inventée à la place d'une cause
        #  mesurée.
        _returns_by_symbol = None
        risk = risk_engine.portfolio_risk(snap, profile,
                                          returns_by_symbol=_returns_by_symbol,
                                          options_greeks=_legs if _legs else None)
        # ── Corrélations : capacité NON BRANCHÉE sur cette route, dite comme telle ──
        # Mesure : POST /api/portfolio/team avec 1 puis 3 positions rend le MÊME
        # {'average': None, 'pairs': {}, 'symbols_covered': []} — `symbols_covered`
        # reste vide même à 3 titres, donc ce n'est pas « moins de deux titres » :
        # `portfolio_risk` est appelé ici sans `returns_by_symbol` (seul appelant de
        # production), et risk_engine fait alors `correlation_matrix({})`. Le moteur
        # fonctionne quand on le nourrit (mesuré : average 0.946 sur AAPL/KO). Une
        # matrice vide SANS cause nommée se lisait comme « pas de corrélation » et
        # laissait l'interface promettre un flux live qui ne l'alimentera jamais
        # (invariant 8). Les corrélations MESURÉES sont servies par
        # /api/portfolio/context, qui aligne de vraies séries de rendements.
        if (_returns_by_symbol is None
                and isinstance(risk.get('correlations'), dict)
                and not risk['correlations'].get('pairs')):
            risk['correlations']['reason'] = (
                'NON_IMPLÉMENTÉ sur /api/portfolio/team — cette route ne fournit '
                'aucune série de rendements au moteur ; les corrélations mesurées '
                'sont servies par /api/portfolio/context (vue Allocation)')
            risk['correlations']['available'] = False
        # ── Enrichissement stress avec des données RÉELLES du scan (jamais inventées) ──
        # Secteur : réel (yfinance via le scan). Nasdaq : classification par secteur —
        # Technology + Communication Services = cœur tech/comm du NDX (hypothèse documentée,
        # pas un chiffre inventé). Taux / vega / résultats : laissés à None → le moteur les
        # marque « non estimé » plutôt que d'afficher un faux 0.
        _det = scan_state.get('detail') or {}
        _sector_of = {}
        for p in snap.positions:
            _sector_of[p.symbol] = (p.sector or (_det.get(p.symbol) or {}).get('sector') or 'Inconnu')
        _NDX_SECTORS = {'Technology', 'Communication Services'}
        _nasdaq_exposure = {p.symbol: (_sector_of.get(p.symbol) in _NDX_SECTORS)
                            for p in snap.positions}
        #  CONSTAT 26 — LE PÉRIMÈTRE OPTIONS N'ARRIVAIT PAS AU MOTEUR. Cette
        #  route ne transmettait que le vega ; `options_open` restait None, et
        #  le moteur ne pouvait donc pas distinguer « aucune option » (IV crush
        #  réellement nul) de « des options sans greeks broker » (impact
        #  inconnu). Conséquence mesurée sur un desk sans aucune option (KO
        #  88,07 $ + 25 000 $ de cash) : IV_CRUSH et VIX_PLUS_50 sortaient tous
        #  deux `impact_pct: null` alors que le premier vaut un 0,0 % VRAI et
        #  le second -0,01 %. Deux mesures justes perdues sur TOUTE route
        #  réelle — l'état `options_open == 0` était inatteignable en
        #  production. `desk_greeks` compte déjà les jambes déclarées
        #  (`open_options` = len(legs), 0 quand le corps n'en porte aucune) :
        #  c'est le périmètre DÉCLARÉ par l'utilisateur, jamais une déduction.
        stress = stress_tests.run_stress_tests(
            snap, profile, sector_of=_sector_of, nasdaq_exposure=_nasdaq_exposure,
            options_vega_value=_greeks.get('vega_usd'),
            options_open=_greeks.get('open_options'))
        # Le scan ne porte pas les dates de résultats → on n'affiche PAS un faux 0 :
        # le scénario « gap résultats » devient honnêtement « inconnu ».
        _has_earn = any(isinstance((_det.get(p.symbol) or {}).get('earnings_dte'), (int, float))
                        for p in snap.positions)
        if not _has_earn and 'EARNINGS_GAP_ADVERSE' in stress.get('scenarios', {}):
            stress['scenarios']['EARNINGS_GAP_ADVERSE'] = {
                'impact_pct': None,
                'note': 'dates de résultats non disponibles dans le scan — non estimé'}
            stress['worst_case_pct'] = min(
                (v['impact_pct'] for v in stress['scenarios'].values()
                 if v.get('impact_pct') is not None), default=None)
        return jsonify({'team': team_view(snap, profile), 'risk': risk,
                        'guard': portfolio_guard.guard_rules(risk, profile),
                        'stress': stress})

    @bp.route('/api/portfolio/greeks', methods=['POST'])
    def portfolio_greeks():
        """Greeks AGRÉGÉS du desk depuis les greeks BROKER (modelGreeks IBKR) persistés —
        jamais estimés. POST {option_positions:[{sym,exp,strike,right,qty}]}. Jambe non cotée
        (hors fenêtre tirée / chaîne pas chargée) → None honnête ; `priced`/`greeks_partial`
        signalent la couverture. Lecture seule, non bloquant."""
        from vertex.options import on_demand as _od
        body = request.get_json(silent=True) or {}
        g = _od.desk_greeks(body.get('option_positions') or [])
        g['note'] = ('greeks du broker (IBKR) sur les jambes dont la chaîne est chargée ; '
                     'ouvre la fiche options d’un titre pour charger sa chaîne')
        return jsonify(g)

    @bp.route('/api/alerts/active')
    def alerts_active():
        return jsonify({'active': ALERTS.active_alerts(), 'status': ALERTS.status()})

    @bp.route('/api/system/diagnostics')
    def diagnostics():
        from vertex.data_sources import ibkr_link as _lien
        from vertex.options import strike_memory as _strikes
        from vertex.app.caches import _TICKER_SNAPSHOTS
        from vertex.app.routes.analysis_api import _KG_MAGASIN
        return jsonify(system_diagnostics(scan_state=scan_state, ibkr_link=_lien,
                                          alert_engine=ALERTS, ai_audit=_AI_AUDIT,
                                          signal_store=SIGNAL_STORE,
                                          option_strikes=_strikes,
                                          magasins=(_TICKER_SNAPSHOTS,
                                                    _KG_MAGASIN)))

    @bp.route('/api/data-quality')
    def data_quality():
        detail = scan_state.get('detail') or {}
        source = scan_state.get('source') or ''
        is_demo = (source == 'demo')
        # Démo : données synthétiques PRÉSENTES → statut DEMO honnête (≠ MISSING,
        # qui signifie « absente »). Règle d'intégrité : la démo est étiquetée,
        # jamais masquée en donnée réelle ni en absence.
        overall = 'DEMO' if is_demo else ('RECENT' if source else 'MISSING')
        warnings = ['données de démonstration (synthétiques)'] if is_demo else []
        packets = [{'symbol': s,
                    'quality': {'overall': overall, 'warnings': warnings}}
                   for s in list(detail)[:200]]
        report = data_quality_report(packets)
        report['scan_source'] = source or 'aucune'
        report['note'] = ('qualité au niveau scan (source unique) — la provenance '
                          'valeur par valeur arrive avec le routage data_sources')
        return jsonify(report)

    return bp
