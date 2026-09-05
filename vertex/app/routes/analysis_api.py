"""
vertex/app/routes/analysis_api.py — ENDPOINTS D'ANALYSE (Blueprint, Ch. II).

Trois lectures analytiques du scan : le deep-dive VERTEX d'un titre, le
validateur hors-échantillon (walk-forward / DSR / PSR / PBO) et le Risk Manager
de portefeuille. Lisent l'état partagé (`vertex.app.state.scan_state`) — plus
d'injection : le Blueprint importe directement le même objet.

Analyse uniquement, indicatif. Ces routes lisent, ne commandent jamais.
"""


from flask import Blueprint, jsonify, request

from vertex.engines import quant_engine as vertex
from vertex.validation import out_of_sample as validator
from vertex.portfolio import legacy_basket_risk as portfolio_risk
from vertex.app import snapshot as _instantane
from vertex.app.state import scan_state
from vertex.app import input_validation as _input

bp = Blueprint('analysis_api', __name__)

_PUBLIC_SOURCE_STATES = {'AVAILABLE', 'DEGRADED', 'UNAVAILABLE', 'NOT_COLLECTED', 'UNKNOWN'}
_PUBLIC_SOURCE_KEYS = ('scan', 'market', 'options', 'fundamentals')


def _source_health_summary(raw):
    """Réduit l'état de sources à des statuts non sensibles et bornés."""
    raw = raw if isinstance(raw, dict) else {}
    sources = {}
    for key in _PUBLIC_SOURCE_KEYS:
        state = str(raw.get(key) or 'UNKNOWN').upper()
        sources[key] = state if state in _PUBLIC_SOURCE_STATES else 'UNKNOWN'
    counts = {state: sum(1 for value in sources.values() if value == state)
              for state in sorted(_PUBLIC_SOURCE_STATES)}
    return {'available': bool(raw), 'sources': sources, 'counts': counts,
            'read_only': True,
            'note': 'statuts agrégés non sensibles ; aucun détail de fournisseur ni de demandeur'}


@bp.route('/api/vertex/<sym>')
def api_vertex(sym):
    """Deep-dive VERTEX d'un titre : bloc quant complet + décomposition explicable."""
    sym = _input.symbol(sym)
    if not sym:
        return jsonify({'ok': False, 'error': 'symbole_invalide'}), 400
    d = (scan_state.get('detail') or {}).get(sym)
    if not d:
        return jsonify({'ok': False, 'note': 'titre non scanné'})
    v = d.get('vertex')
    if not v:
        return jsonify({'ok': False, 'note': 'vertex indisponible'})
    return jsonify({'ok': True, 'symbol': sym, 'price': d.get('price'),
                    'grade': d.get('grade'), 'score': d.get('score'),
                    'vertex': v, 'explain': vertex.explain(v, d)})


@bp.route('/api/validator')
def api_validator():
    """VERTEX — validateur hors échantillon (walk-forward, DSR, PSR, PBO). Indicatif."""
    pf = scan_state.get('portfolio') or {}
    eq = pf.get('equity')
    if not eq:
        return jsonify({'ok': False, 'note': 'backtest indisponible (univers/historique insuffisant)'})
    return jsonify(validator.build(eq))


@bp.route('/api/risk', methods=['GET', 'POST'])
def api_risk():
    """VERTEX v4 — Risk Manager (corrélation, concentration, secteurs).

    GET  : panier = top convictions du scan (le COMITÉ, pas le portefeuille).
    POST {symbols:[…]} : panier = positions DÉCLARÉES par l'utilisateur, envoyées
    explicitement par la page (jamais lues chez un courtier). La réponse dit
    quel panier elle mesure (`panier`), les titres non mesurables
    (`non_mesures` : hors scan ou historique trop court) et son époque.
    Lecture seule, indicatif, aucun ordre."""
    detail = scan_state.get('detail') or {}
    if request.method == 'POST':
        body = request.get_json(silent=True) or {}
        syms = []
        for s in (body.get('symbols') or [])[:60]:
            v = _input.symbol(s)
            if v and v not in syms:
                syms.append(v)
        if not syms:
            out = {'n': 0, 'symbols': [], 'flags': [], 'no_new_risk': False,
                   'note': 'aucune position déclarée — rien à mesurer'}
        else:
            out = portfolio_risk.build(syms, detail)
        out['panier'] = 'declare'
        out['demandes'] = syms
        out['non_mesures'] = [s for s in syms if s not in (out.get('symbols') or [])]
    else:
        rows = scan_state.get('rows') or []
        out = portfolio_risk.build([r['symbol'] for r in rows[:10]], detail)
        out['panier'] = 'comite'
    out['as_of'] = scan_state.get('scan_ts_h') or scan_state.get('updated')
    return jsonify(out)


__all__ = ['bp']


@bp.route('/api/anomalies/<sym>')
def api_anomalies(sym):
    """SCANNER D'ANOMALIES DE COURS : spikes |z|≥2, changement de régime de
    volatilité, séquences, extrêmes — sur la série de clôtures RÉELLE du scan.
    Constat statistique descriptif, jamais une prévision. Lecture seule."""
    from vertex.data import series as _series
    from vertex.engines import anomaly as _an
    sym = _input.symbol(sym)
    if not sym:
        return jsonify({'ok': False, 'error': 'symbole_invalide'}), 400
    detail = (scan_state.get('detail') or {}).get(sym) or {}
    closes, src = _series.closes(detail)   # série CANONIQUE uniquement (LOT 4)
    d = _an.scan(closes)
    d['symbol'] = sym
    d['series_source'] = src
    d['as_of'] = scan_state.get('scan_ts_h') or scan_state.get('updated')
    return jsonify(d)


@bp.route('/api/evidence/<sym>')
def api_evidence(sym):
    """LABORATOIRE D'ÉVIDENCE (X2) : que s'est-il RÉELLEMENT passé après les
    spikes passés — rendements forward et MFE/MAE exacts sur la série
    canonique. In-sample, descriptif, jamais un backtest. Lecture seule."""
    from vertex.data import series as _series
    from vertex.engines import evidence_lab as _ev
    sym = _input.symbol(sym)
    if not sym:
        return jsonify({'ok': False, 'error': 'symbole_invalide'}), 400
    detail = (scan_state.get('detail') or {}).get(sym) or {}
    closes, src = _series.closes(detail)
    d = _ev.study(closes)
    d['symbol'] = sym
    d['series_source'] = src
    d['as_of'] = scan_state.get('scan_ts_h') or scan_state.get('updated')
    return jsonify(d)


@bp.route('/api/skyler/<sym>')
def api_skyler(sym):
    """SKYLER CORE (LOT 5) : packet typé + décision canonique déterministe
    (score /40, hard gates, scénarios sans probabilité inventée, audit trail).
    Analyse READONLY — jamais un ordre."""
    from vertex.data import series as _series
    from vertex.engines import anomaly_context as _anctx, events as _events
    from vertex.engines import market_context as _mcx, skyler_core as _sk
    from vertex.services import news_plus as _np
    from vertex.app.config import DEMO_MODE as _demo
    sym = _input.symbol(sym)
    if not sym:
        return jsonify({'ok': False, 'error': 'symbole_invalide'}), 400
    detail = (scan_state.get('detail') or {}).get(sym) or {}
    closes, _src = _series.closes(detail)
    from vertex.engines import drawdown_context as _ddctx
    drawdown = _ddctx.build(closes)
    from vertex.engines import downside_volatility as _dvctx
    downside_volatility = _dvctx.build(closes)
    benchmark_detail = (scan_state.get('detail') or {}).get('SPY') or {}
    from vertex.engines import relative_strength_context as _rsctx
    relative_strength = _rsctx.build(detail.get('series') or {}, benchmark_detail.get('series') or {})
    from vertex.engines import gap_risk_context as _grctx
    gap_risk = _grctx.build(detail)
    ano = _anctx.build(sym, detail, benchmark_detail=benchmark_detail) if closes else None
    market = _mcx.build(scan_state, demo=_demo)
    earnings = []
    try:
        from vertex.app.state import cal_state
        earnings = [e for e in (cal_state.get('items') or [])
                    if str(e.get('sym', '')).upper() == sym]
    except Exception:
        pass
    try:
        from vertex.data import macro_calendar
        macro = macro_calendar.events(horizon_days=30)
    except Exception:
        macro = []
    news = _np.sanitize_news(detail.get('news') or [])
    ev = _events.build(sym, news=news, earnings=earnings, macro=macro, anomaly=ano,
                       as_of=scan_state.get('scan_ts_h') or scan_state.get('updated'))
    from vertex.engines import earnings_proximity as _epctx
    earnings_proximity = _epctx.build(ev)
    as_of = scan_state.get('scan_ts_h') or scan_state.get('updated')
    # OptionsContext : mandat opérationnel 3–6 mois pour une détention de 1–3 semaines.
    # Le scanner conserve les candidats partiels et hors mandat, mais le moteur reçoit
    # explicitement leur statut : aucune conformité n’est supposée par défaut.
    from vertex.options import horizon_scanners as _hs
    octx = _hs.swing_3_6m_context(scan_state.get('options_board') or [], sym=sym,
                                  historical_closes=closes)
    from vertex.engines import earnings_option_overlap as _eoctx
    earnings_option_overlap = _eoctx.build(octx, earnings_proximity)
    from vertex.engines import earnings_holding_overlap as _ehctx
    earnings_holding_overlap = _ehctx.build(octx, earnings_proximity)
    from vertex.engines import iv_skew_context as _ivskew
    iv_skew = _ivskew.build(scan_state.get('options_board') or [], sym=sym, spot=detail.get('price'))
    from vertex.engines import call_put_structure as _callput
    call_put_structure = _callput.build(scan_state.get('options_board') or [], sym=sym)
    from vertex.engines import iv_term_structure as _ivterm
    iv_term_structure = _ivterm.build(scan_state.get('options_board') or [], sym=sym)
    from vertex.engines import relative_volume_context as _rvctx
    relative_volume = _rvctx.build(detail)
    from vertex.engines import open_interest_concentration as _oictx
    open_interest_concentration = _oictx.build(scan_state.get('options_board') or [], sym=sym)
    from vertex.engines import fundamental_context as _fctx
    fundamentals_ctx = _fctx.build(sym, scan_state.get('fundamentals') or {})
    from vertex.engines import decision_evidence as _evidence
    dqctx, recctx = _evidence.for_symbol(scan_state, sym, detail)
    # PortfolioContext (LOT 7) : positions canoniques du desk + cotes du scan.
    pctx = None
    try:
        from vertex.engines import portfolio_context as _pc
        from vertex.positions.repository import load_positions
        from vertex.services import persist
        pos = load_positions(persist.load_json('desk_data.json', {}) or {})
        detail_map = scan_state.get('detail') or {}
        quotes = {s: (d or {}).get('price') for s, d in detail_map.items()
                  if isinstance(d, dict) and d.get('price') is not None}
        series_by_symbol = {s: (d or {}).get('series') or {} for s, d in detail_map.items()
                            if isinstance(d, dict)}
        pctx = _pc.build(pos, quotes=quotes, sym=sym, series_by_symbol=series_by_symbol)
    except Exception:
        pctx = None
    # Red-team PRODUITE (LOT 14) : les 10 questions du comité évaluées sur le
    # packet réel — complete=True seulement si les 10 sont fondées.
    from vertex.engines import red_team as _rt
    packet0 = _sk.build_packet(sym, detail, market=market, events=ev, anomaly=ano,
                               as_of=as_of, demo=_demo, options_ctx=octx, portfolio_ctx=pctx,
                               data_quality_ctx=dqctx, reconciliation_ctx=recctx,
                               fundamental_ctx=fundamentals_ctx, drawdown_ctx=drawdown,
                               downside_volatility_ctx=downside_volatility,
                               relative_strength_ctx=relative_strength, gap_risk_ctx=gap_risk,
                               earnings_proximity_ctx=earnings_proximity,
                               earnings_option_overlap_ctx=earnings_option_overlap,
                               earnings_holding_overlap_ctx=earnings_holding_overlap,
                               iv_skew_ctx=iv_skew, call_put_structure_ctx=call_put_structure,
                               iv_term_structure_ctx=iv_term_structure, relative_volume_ctx=relative_volume,
                               open_interest_concentration_ctx=open_interest_concentration)
    rt_review = _rt.review(packet0, _sk.score40(packet0))
    rt_input = {'complete': rt_review['complete'], 'basis': rt_review['basis']}
    # Calibration RÉELLE (LOT 19/22) : facteur depuis les résultats mesurés de
    # la mémoire pour CETTE version — cellule du NIVEAU courant si mesurée
    # (§13), agrégat global en secours. Fail-safe, jamais inventé.
    calib = None
    option_calibration = None
    try:
        from vertex.engines import decision_memory as _dmc
        from vertex.services import persist as _pc
        _memc = _pc.load_json(_dmc.MEMORY_FILE, None) or _dmc.empty_memory()
        _score0 = _sk.score40(packet0)
        _reg0 = ((market or {}).get('regime') or {}).get('label')
        calib = _dmc.calibration_factor_for(_memc, _sk.ENGINE_VERSION,
                                            level=_score0.get('level'),
                                            regime=_reg0)
        option_calibration = _dmc.option_calibration_summary(_memc, _sk.ENGINE_VERSION, octx)
    except Exception:
        calib = None
        option_calibration = None
    #  Lot 10 — la fiche passe par l'AUTORITE NOMMEE. Delegation stricte vers
    #  le decideur du packet : meme entree, meme sortie, plus la provenance
    #  (moteur + version) sans laquelle un conseil n'est pas auditable.
    from vertex.engines.advice import AdviceEngine as _advice
    decision = _advice.evaluate({'symbol': sym, 'detail': detail,
                                 'market': market, 'events': ev, 'anomaly': ano,
                                 'as_of': as_of, 'demo': _demo,
                                 'options_ctx': octx, 'portfolio_ctx': pctx,
                                 'red_team': rt_input, 'calibration': calib,
                                 'data_quality_ctx': dqctx,
                                 'reconciliation_ctx': recctx,
                                 'fundamental_ctx': fundamentals_ctx})
    decision['option_calibration'] = option_calibration or {
        'available': False,
        'reason': 'mémoire de calibration indisponible',
        'scope': 'DIRECTIONAL_PROXY_ONLY',
    }
    packet = _sk.build_packet(sym, detail, market=market, events=ev, anomaly=ano,
                              as_of=as_of, demo=_demo, options_ctx=octx, portfolio_ctx=pctx,
                              red_team=rt_input, data_quality_ctx=dqctx,
                              reconciliation_ctx=recctx, fundamental_ctx=fundamentals_ctx,
                              drawdown_ctx=drawdown, downside_volatility_ctx=downside_volatility,
                              relative_strength_ctx=relative_strength, gap_risk_ctx=gap_risk,
                              earnings_proximity_ctx=earnings_proximity,
                              earnings_option_overlap_ctx=earnings_option_overlap,
                              earnings_holding_overlap_ctx=earnings_holding_overlap,
                              iv_skew_ctx=iv_skew, call_put_structure_ctx=call_put_structure,
                              iv_term_structure_ctx=iv_term_structure, relative_volume_ctx=relative_volume,
                              open_interest_concentration_ctx=open_interest_concentration)
    # Contrat de présentation stable : une interface ou un agent de design peut
    # expliquer les preuves manquantes sans jamais toucher au verdict canonique.
    from vertex.engines import decision_readiness as _readiness
    decision['readiness'] = _readiness.build(packet, decision)
    from vertex.engines import opportunity_attribution as _attribution
    decision['opportunity_attribution'] = _attribution.build(packet, decision)
    try:
        from vertex.market import regime_break as _regime_break
        decision['regime_break'] = _regime_break.assess((detail or {}).get('series') or {})
    except Exception:
        decision['regime_break'] = {'available': False, 'status': 'UNAVAILABLE',
                                    'read_only': True, 'does_not_change_decision': True,
                                    'reason': 'diagnostic de rupture indisponible'}
    try:
        from vertex.market import instrument_profile as _instrument
        from vertex.market import sector_coherence as _sector_coherence
        instrument = _instrument.build(sym, detail)
        decision['instrument_profile'] = instrument
        decision['sector_coherence'] = _sector_coherence.build(
            instrument, detail, scan_state.get('sectors') or [])
        from vertex.engines import multi_asset_guard as _multi_asset_guard
        decision['multi_asset_guard'] = _multi_asset_guard.build(
            instrument, decision['sector_coherence'],
            packet.get('contexts', {}).get('options'),
            packet.get('contexts', {}).get('portfolio'))
    except Exception:
        decision['instrument_profile'] = {'asset_class': 'UNKNOWN', 'classification': 'UNAVAILABLE'}
        decision['sector_coherence'] = {'available': False, 'reason': 'diagnostic indisponible'}
        decision['multi_asset_guard'] = {'status': 'UNAVAILABLE', 'read_only': True,
                                         'does_not_change_verdict': True}
    try:
        from vertex.engines import opportunity_reliability as _reliability
        from vertex.tracking import option_cohort as _cohort
        from vertex.tracking import repository as _tracking
        decision['opportunity_reliability'] = _reliability.build(
            packet, decision, _cohort.build(_tracking.list_all()))
    except Exception:
        decision['opportunity_reliability'] = {
            'status': 'UNAVAILABLE', 'read_only': True,
            'note': 'diagnostic de fiabilité indisponible'}
    try:
        from vertex.engines import intelligence_monitor as _monitor
        from vertex.services import persist as _persist_monitor
        from vertex.engines import decision_memory as _memory_monitor
        _memory = (_persist_monitor.load_json(_memory_monitor.MEMORY_FILE, None)
                   or _memory_monitor.empty_memory())
        decision['performance_monitor'] = _monitor.assess(_memory, _sk.ENGINE_VERSION)
    except Exception:
        decision['performance_monitor'] = {'available': False, 'status': 'UNAVAILABLE',
                                           'read_only': True,
                                           'reason': 'mémoire de performance indisponible'}
    # Journal de calibration (LOT 9) : chaque décision servie est enregistrée
    # (dédupliquée par scan) avec le prix du moment — base des résultats ex post.
    try:
        import time as _time
        from vertex.engines import skyler_journal as _sj
        from vertex.services import persist as _persist
        j = _persist.load_json(_sj.JOURNAL_FILE, [])
        j2 = _sj.record(j, decision, price=detail.get('price'), now=round(_time.time()))
        if j2 != j:
            _persist.save_json(_sj.JOURNAL_FILE, j2)
    except Exception:
        pass                                   # le journal ne casse jamais la décision
    # Mémoire décisionnelle institutionnelle (LOT 10) : chaque décision servie
    # est FIGÉE avec sa version de moteur, ses données du moment et l'empreinte
    # de série anti-look-ahead — append-only, jamais réécrite.
    try:
        import time as _time
        from vertex.engines import decision_memory as _dm
        from vertex.services import persist as _persist
        today = _time.strftime('%Y-%m-%d', _time.gmtime())   # date d'observation réelle (UTC)
        mem = _persist.load_json(_dm.MEMORY_FILE, None) or _dm.empty_memory()
        rec = _dm.freeze(decision, packet=packet, price=detail.get('price'),
                         closes=closes, portfolio_ctx=pctx, now=round(_time.time()),
                         session_date=today)
        mem2 = _dm.append_decision(mem, rec)
        if mem2 != mem:
            _persist.save_json(_dm.MEMORY_FILE, mem2)
        # Log de séances (LOT 15) : une clôture observée par jour réel de scan.
        from vertex.engines import session_log as _slog
        if detail.get('price') is not None:
            slog = _persist.load_json(_slog.SESSIONS_FILE, None) or _slog.empty_log()
            slog2 = _slog.record_close(slog, sym, today, detail.get('price'))
            if slog2 != slog:
                _persist.save_json(_slog.SESSIONS_FILE, slog2)
    except Exception:
        pass                                   # la mémoire ne casse jamais la décision
    return jsonify({'symbol': sym, 'as_of': as_of, 'demo': _demo,
                    'packet': packet, 'decision': decision,
                    'red_team_review': rt_review})


@bp.route('/api/skyler/sweep')
def api_skyler_sweep():
    """BALAYAGE SKYLER (X1) : le moteur canonique appliqué à tous les titres
    scannés, classé par score /40 — gate plafonnante visible par ligne.
    Ne journalise jamais. Lecture seule."""
    from vertex.app.config import DEMO_MODE as _demo
    from vertex.engines import skyler_sweep as _sw
    earnings_by_sym = {}
    try:
        from vertex.app.state import cal_state
        for e in (cal_state.get('items') or []):
            s = str(e.get('sym', '')).upper()
            if s:
                earnings_by_sym.setdefault(s, []).append(e)
    except Exception:
        pass
    return jsonify(_sw.sweep(scan_state, demo=_demo, earnings_by_sym=earnings_by_sym))


@bp.route('/api/skyler/calibration')
def api_skyler_calibration():
    """CALIBRATION EX POST (LOT 9) : comptages exacts du journal des décisions +
    rendements réels depuis le prix enregistré. Brier honnêtement indisponible
    tant qu'aucune probabilité calibrée n'existe. Lecture seule."""
    from vertex.engines import skyler_journal as _sj
    from vertex.services import persist as _persist
    journal = _persist.load_json(_sj.JOURNAL_FILE, [])
    quotes = {s: (d or {}).get('price') for s, d in (scan_state.get('detail') or {}).items()
              if isinstance(d, dict) and d.get('price') is not None}
    out = _sj.calibration(journal, quotes=quotes)
    out['as_of'] = scan_state.get('scan_ts_h') or scan_state.get('updated')
    from vertex.app.config import DEMO_MODE as _demo
    out['demo'] = _demo
    return jsonify(out)


@bp.route('/api/skyler/monitor')
def api_skyler_monitor():
    """MONITEUR D'INTELLIGENCE : dérive descriptive de performance issue des
    résultats mémoire mesurés. Jamais de recalibration ou désactivation cachée."""
    from vertex.engines import intelligence_monitor as _monitor
    from vertex.engines import decision_memory as _memory
    from vertex.engines import skyler_core as _sk
    from vertex.services import persist as _persist
    horizon = str(request.args.get('horizon', 'H10')).upper()
    if horizon not in ('H5', 'H10', 'H15', 'H20', 'H60'):
        return jsonify({'ok': False, 'error': 'horizon_invalide',
                        'allowed': ['H5', 'H10', 'H15', 'H20', 'H60']}), 400
    memory = _persist.load_json(_memory.MEMORY_FILE, None) or _memory.empty_memory()
    out = _monitor.assess(memory, _sk.ENGINE_VERSION, horizon=horizon)
    out['as_of'] = scan_state.get('scan_ts_h') or scan_state.get('updated')
    return jsonify(out)


@bp.route('/api/skyler/validation')
def api_skyler_validation():
    """Validation walk-forward de la mémoire, descriptive et sans recalibration."""
    from vertex.engines import decision_memory as _memory
    from vertex.engines import walk_forward_validation as _walk_forward
    from vertex.engines import skyler_core as _sk
    from vertex.services import persist as _persist
    horizon = str(request.args.get('horizon', 'H10')).upper()
    if horizon not in _walk_forward.HORIZON_SESSIONS:
        return jsonify({'ok': False, 'error': 'horizon_invalide',
                        'allowed': list(_walk_forward.HORIZON_SESSIONS)}), 400
    memory = _persist.load_json(_memory.MEMORY_FILE, None) or _memory.empty_memory()
    out = _walk_forward.assess(memory, _sk.ENGINE_VERSION, horizon=horizon)
    out['as_of'] = scan_state.get('scan_ts_h') or scan_state.get('updated')
    return jsonify(out)


@bp.route('/api/skyler/health')
def api_skyler_health():
    """Santé technique non sensible : compteurs, jamais de cache ni de données."""
    from vertex.services import persist as _persist
    from vertex.services import request_metrics as _metrics
    return jsonify({'read_only': True, 'persistence': _persist.health(),
                    'request_metrics': _metrics.summary(),
                    'source_health': _source_health_summary(scan_state.get('source_health'))})


@bp.route('/api/skyler/memory')
def api_skyler_memory():
    """MÉMOIRE DÉCISIONNELLE INSTITUTIONNELLE (LOT 10) : décisions figées
    (immuables, séparées par version de moteur), résultats mesurés UNIQUEMENT
    aux horizons déclarés depuis les séances strictement postérieures (aucun
    look-ahead), classification déterministe des erreurs, biais récurrents et
    recommandations en attente de validation humaine. Lecture seule."""
    from vertex.data import series as _series
    from vertex.engines import decision_memory as _dm
    from vertex.services import persist as _persist
    from vertex.app.config import DEMO_MODE as _demo
    mem = _persist.load_json(_dm.MEMORY_FILE, None) or _dm.empty_memory()
    # Passe de mesure (LOT 15) : le log de séances DATÉES est autoritaire quand
    # il couvre le titre (comptage de séances réel) ; l'empreinte de fin de
    # série reste le secours pour les anciens records. Non mesurable = dit.
    from vertex.engines import session_log as _slog
    slog = _persist.load_json(_slog.SESSIONS_FILE, None)
    changed = False
    detail_all = scan_state.get('detail') or {}
    for r in mem['decisions']:
        if not isinstance(r, dict):            # magasin corrompu → entrée ignorée
            continue
        after = _slog.closes_after_date(slog, r.get('symbol'), r.get('session_date'))
        if after is None:                      # log muet sur ce titre → secours empreinte
            closes, _src = _series.closes(detail_all.get(r.get('symbol')) or {})
            after = _dm.sessions_after(closes, r.get('tail_at_decision'))
        if after:
            mem2 = _dm.append_outcome(mem, _dm.measure(r, after))
            if mem2 != mem:
                mem, changed = mem2, True
    if changed:
        try:
            _persist.save_json(_dm.MEMORY_FILE, mem)
        except Exception:
            pass
    patterns = _dm.detect_patterns(mem)
    aggs = _dm.aggregates(mem)
    from vertex.engines import skyler_core as _sk2
    return jsonify({
        'generator': 'deterministic',
        'as_of': scan_state.get('scan_ts_h') or scan_state.get('updated'),
        'demo': _demo,
        'calibration_by_context': _dm.calibration_by_context(mem, _sk2.ENGINE_VERSION),
        'ledger_health': _dm.ledger_health(mem),
        'n_decisions': len(mem['decisions']),
        'n_outcomes': len(mem['outcomes']),
        'decisions': mem['decisions'][-50:],
        'outcomes': mem['outcomes'][-50:],
        'aggregates': aggs,
        'patterns': patterns,
        'recommendations': _dm.recommendations(patterns, aggs),
        'note': 'Mémoire immuable — décisions historiques jamais réécrites, résultats '
                'séparés par version de moteur, aucune recalibration automatique.',
    })


def _canonical_bundle_json(payload):
    """Forme CANONIQUE du bundle d'export pour l'empreinte sha256 (lots 42/47) :
    clés triées, séparateurs compacts, et flottants ENTIERS normalisés en
    entiers (100.0 ≡ 100) — JSON.stringify côté navigateur replie x.0 en x,
    l'empreinte doit être STABLE au round-trip JS (défaut réel attrapé en
    preuve navigateur, lot 47)."""
    import json as _json

    def norm(o):
        if isinstance(o, float) and o.is_integer():
            return int(o)
        if isinstance(o, dict):
            return {k: norm(v) for k, v in o.items()}
        if isinstance(o, list):
            return [norm(v) for v in o]
        return o

    return _json.dumps(norm(payload), sort_keys=True, ensure_ascii=False,
                       separators=(',', ':'))


@bp.route('/api/skyler/memory/export')
def api_skyler_memory_export():
    """EXPORT SOUVERAIN (LOT 29, intégrité LOT 42) : sauvegarde LECTURE SEULE
    de tout l'état runtime Skyler — mémoire décisionnelle, log de séances
    datées, journal de calibration — avec les versions, la santé du ledger
    AU MOMENT de l'export (l'archive se décrit elle-même) et une empreinte
    sha256 du contenu canonique, vérifiable HORS LIGNE sans le serveur.
    Aucun effet de bord, servi en téléchargement."""
    import hashlib as _hashlib
    import json as _json
    import time as _time
    from vertex.engines import decision_memory as _dm
    from vertex.engines import session_log as _slog
    from vertex.engines import skyler_journal as _sj
    from vertex.engines import skyler_core as _sk
    from vertex.services import persist as _persist
    mem = _persist.load_json(_dm.MEMORY_FILE, None) or _dm.empty_memory()
    payload = {
        'exported_at': _time.strftime('%Y-%m-%dT%H:%M:%SZ', _time.gmtime()),
        'versions': {'decision_engine': _sk.ENGINE_VERSION,
                     'memory_schema': _dm.MEMORY_SCHEMA_VERSION,
                     'packet_schema': _sk.SCHEMA_VERSION},
        'memory': mem,
        'sessions': _persist.load_json(_slog.SESSIONS_FILE, None) or _slog.empty_log(),
        'journal': _persist.load_json(_sj.JOURNAL_FILE, []) or [],
        # l'archive dit elle-même si le ledger était cohérent à l'export —
        # un magasin corrompu est fidèlement empreinté, jamais maquillé
        'ledger_health': _dm.ledger_health(mem),
        'note': 'Export lecture seule de l’état runtime Skyler — les décisions '
                'historiques ne sont jamais réécrites ; ce fichier est la '
                'sauvegarde souveraine de la mémoire du trader. Vérification '
                'hors ligne : content_sha256 = sha256 du JSON canonique '
                '(clés triées, séparateurs compacts, flottants entiers '
                'normalisés en entiers : 100.0 ≡ 100) du bundle SANS ce champ.',
    }
    canonical = _canonical_bundle_json(payload)
    payload['content_sha256'] = _hashlib.sha256(
        canonical.encode('utf-8')).hexdigest()
    resp = jsonify(payload)
    resp.headers['Content-Disposition'] = (
        'attachment; filename="skyler_export_%s.json"'
        % _time.strftime('%Y%m%d', _time.gmtime()))
    return resp


@bp.route('/api/skyler/memory/import', methods=['POST'])
def api_skyler_memory_import():
    """RESTAURATION SOUVERAINE (LOT 45) : ré-importe un bundle d'export
    (lots 29/42) par REJEU APPEND-ONLY — l'empreinte `content_sha256` est
    VÉRIFIÉE AVANT toute écriture (archive altérée → 400 dit, rien touché) ;
    un decision_id déjà présent n'est JAMAIS remplacé (l'historique local
    gagne) ; les outcomes restent monotones. Périmètre : ledger mémoire ;
    séances/journal restent au backlog (dit dans la note). Jamais 500."""
    import hashlib as _hashlib
    import json as _json
    from flask import request
    from vertex.engines import decision_memory as _dm
    from vertex.services import persist as _persist
    bundle = request.get_json(force=True, silent=True)
    if not isinstance(bundle, dict):
        return jsonify({'ok': False, 'error': 'bundle_invalide',
                        'note': 'corps JSON objet attendu (bundle d’export)'}), 400
    claimed = bundle.pop('content_sha256', None)
    if not isinstance(claimed, str) or not claimed:
        return jsonify({'ok': False, 'error': 'empreinte_absente',
                        'note': 'content_sha256 requis — un bundle sans '
                                'empreinte n’est pas restaurable'}), 400
    canonical = _canonical_bundle_json(bundle)
    actual = _hashlib.sha256(canonical.encode('utf-8')).hexdigest()
    if actual != claimed:
        return jsonify({'ok': False, 'error': 'empreinte_invalide',
                        'note': 'l’archive a été altérée depuis son export — '
                                'RIEN n’a été écrit'}), 400
    imported = bundle.get('memory')
    if not isinstance(imported, dict):
        return jsonify({'ok': False, 'error': 'memoire_absente',
                        'note': 'le bundle ne contient pas de magasin mémoire'}), 400
    from vertex.engines import session_log as _slog
    from vertex.engines import skyler_journal as _sj
    current = _persist.load_json(_dm.MEMORY_FILE, None) or _dm.empty_memory()
    merged, stats = _dm.merge_memory(current, imported)
    _persist.save_json(_dm.MEMORY_FILE, merged)
    # LOT 46 : le même bundle restaure aussi les séances datées et le journal
    # de calibration — la donnée LOCALE gagne toujours (rejeu honnête).
    cur_slog = _persist.load_json(_slog.SESSIONS_FILE, None) or _slog.empty_log()
    merged_slog, s_stats = _slog.merge_log(cur_slog, bundle.get('sessions'))
    _persist.save_json(_slog.SESSIONS_FILE, merged_slog)
    cur_j = _persist.load_json(_sj.JOURNAL_FILE, []) or []
    merged_j, j_stats = _sj.merge_journal(cur_j, bundle.get('journal'))
    _persist.save_json(_sj.JOURNAL_FILE, merged_j)
    stats['sessions'] = s_stats
    stats['journal'] = j_stats
    return jsonify({'ok': True, 'stats': stats,
                    'ledger_health': _dm.ledger_health(merged),
                    'versions_bundle': bundle.get('versions'),
                    'note': 'restauration par rejeu — l’historique local gagne '
                            'toujours (décisions append-only, séances et journal '
                            'jamais remplacés) ; périmètre complet : mémoire + '
                            'séances + journal'})


@bp.route('/api/skyler/memory/cell/<group>/<key>')
def api_skyler_memory_cell(group, key):
    """DRILL-DOWN CELLULE (LOT 39) : les décisions MESURÉES qui composent une
    cellule de calibration par contexte — même règle d'appartenance que le
    badge (source unique moteur). 404 structurés ; lecture seule."""
    from vertex.engines import decision_memory as _dm
    from vertex.engines import skyler_core as _sk
    from vertex.services import persist as _persist
    mem = _persist.load_json(_dm.MEMORY_FILE, None) or _dm.empty_memory()
    out = _dm.cell_decisions(mem, _sk.ENGINE_VERSION, group, key)
    if out is None:
        return jsonify({'ok': False, 'error': 'groupe_inconnu', 'group': group,
                        'groups': list(_dm.CONTEXT_GROUPS)}), 404
    ctx = _dm.calibration_by_context(mem, _sk.ENGINE_VERSION)
    cell = (ctx.get(group) or {}).get(key)
    if cell is None:
        return jsonify({'ok': False, 'error': 'cellule_inconnue',
                        'group': group, 'key': key,
                        'note': 'aucune décision mesurée ne forme cette cellule '
                                'pour le moteur courant'}), 404
    out['cell'] = cell
    return jsonify(out)


@bp.route('/api/skyler/memory/<decision_id>')
def api_skyler_memory_detail(decision_id):
    """DRILL-DOWN MÉMOIRE (LOT 20) : record figé complet + résultat mesuré +
    revue post-mortem déterministe (décision vs résultat, scénario contenant
    le résultat, classification par horizon). Id inconnu → 404 structuré.
    Lecture seule."""
    from vertex.engines import decision_memory as _dm
    from vertex.services import persist as _persist
    mem = _persist.load_json(_dm.MEMORY_FILE, None) or _dm.empty_memory()
    rec = _dm.find_decision(mem, decision_id)
    if rec is None:
        return jsonify({'ok': False, 'error': 'decision_inconnue',
                        'decision_id': decision_id,
                        'note': 'aucune décision figée sous cet identifiant'}), 404
    out = _dm.find_outcome(mem, decision_id)
    return jsonify({'generator': 'deterministic',
                    'record': rec, 'outcome': out,
                    'post_mortem': _dm.post_mortem(rec, out),
                    'note': 'record immuable — le post-mortem lit, ne réécrit jamais'})


@bp.route('/memory/cell/<group>/<key>')
def memory_cell_view(group, key):
    """VUE LISIBLE D'UNE CELLULE DE CALIBRATION (LOT 40) : rendu HTML serveur
    du résumé de cellule + table des décisions MESURÉES qui la composent,
    chaque record lié à son post-mortem. TOUT contenu mémoire ÉCHAPPÉ
    (markupsafe, même exigence que la vue post-mortem). 404 lisibles.
    Lecture seule."""
    from markupsafe import escape as _e
    from vertex.engines import decision_memory as _dm
    from vertex.engines import skyler_core as _sk
    from vertex.services import persist as _persist
    from vertex.ui.shell import render_shell
    mem = _persist.load_json(_dm.MEMORY_FILE, None) or _dm.empty_memory()
    out = _dm.cell_decisions(mem, _sk.ENGINE_VERSION, group, key)
    if out is None:
        return render_shell(
            title='Groupe inconnu', active='journal', space_label='Journal',
            content='<section class="vx-card vx-mt3"><div class="vx-empty">'
                    'Groupe de contexte inconnu — groupes valides : %s.'
                    '</div></section>' % _e(', '.join(_dm.CONTEXT_GROUPS))), 404
    ctx = _dm.calibration_by_context(mem, _sk.ENGINE_VERSION)
    cell = (ctx.get(group) or {}).get(key)
    if cell is None:
        return render_shell(
            title='Cellule inconnue', active='journal', space_label='Journal',
            content='<section class="vx-card vx-mt3"><div class="vx-empty">'
                    'Cellule inconnue — aucune décision mesurée ne la forme '
                    'pour le moteur courant.</div></section>'), 404

    if cell['status'] == 'MESURE':
        summary = ('facteur %s · hit rate %s · %d mesure(s)'
                   % (cell['value'], cell['hit_rate'], cell['n_measured']))
    else:
        summary = 'INSUFFISANT — %d mesure(s), facteur non calculé' % cell['n_measured']

    dec_rows = ''.join(
        '<tr><td data-label="Titre"><b>%s</b></td>'
        '<td data-label="Séance">%s</td>'
        '<td data-label="Décision">%s</td>'
        '<td data-label="Niveau">%s</td>'
        '<td data-label="Régime">%s</td>'
        '<td data-label="Catalyseur">%s</td>'
        '<td data-label="Résultat"><span class="vx-badge" data-tone="%s">%s</span></td>'
        '<td data-label="Post-mortem"><a class="vx-btn vx-btn-sm vx-btn-ghost" '
        'href="/memory/%s">détail →</a></td></tr>'
        % (_e(x.get('symbol') or 'n/d'), _e(x.get('session_date') or 'n/d'),
           _e(x.get('decision') or 'n/d'), _e(x.get('level') or 'n/d'),
           _e(x.get('regime') or 'n/d'),
           _e('%s (%s)' % (x['catalyst'], x.get('catalyst_kind') or 'inconnu')
              if x.get('catalyst') else 'sans catalyseur'),
           'positive' if x['hit'] else 'negative',
           'contenu (hit)' if x['hit'] else 'hors scénarios (miss)',
           _e(x.get('decision_id') or ''))
        for x in out['decisions'])

    content = (
        '<section class="vx-card vx-mt3" aria-label="Cellule de calibration">'
        '<div class="vx-card-header"><span class="vx-card-title">Cellule — %s</span></div>'
        '<div class="vx-meta vx-mb1">%s</div>'
        '<div class="vx-meta vx-mb1">%s</div>'
        '<div class="vx-table-wrap"><table class="vx-table">'
        '<thead><tr><th>Titre</th><th>Séance</th><th>Décision</th><th>Niveau</th>'
        '<th>Régime</th><th>Catalyseur</th><th>Résultat</th><th>Post-mortem</th></tr></thead>'
        '<tbody>%s</tbody></table></div>'
        '<div class="vx-meta vx-mt1">%s</div>'
        '<div class="vx-mt2"><a class="vx-btn vx-btn-sm vx-btn-ghost" '
        'href="/journal">&larr; Retour Performance</a></div>'
        '</section>'
        % (_e(cell.get('basis', '').split(' : ')[0] or ('%s=%s' % (group, key))),
           _e(summary), _e(cell.get('basis') or ''), dec_rows,
           _e(out.get('note') or '')))
    return render_shell(title='Cellule de calibration', active='journal',
                        space_label='Journal', content=content)


@bp.route('/memory/<decision_id>')
def memory_postmortem_view(decision_id):
    """VUE LISIBLE DU POST-MORTEM (LOT 23) : rendu HTML serveur du record figé,
    de son résultat mesuré et de la revue post-mortem — TOUT contenu de la
    mémoire est ÉCHAPPÉ (XSS). États honnêtes ; id inconnu → 404 lisible.
    Lecture seule."""
    from markupsafe import escape as _e
    from vertex.engines import decision_memory as _dm
    from vertex.services import persist as _persist
    from vertex.ui.shell import render_shell
    mem = _persist.load_json(_dm.MEMORY_FILE, None) or _dm.empty_memory()
    rec = _dm.find_decision(mem, decision_id)
    if rec is None:
        return render_shell(
            title='Décision inconnue', active='journal', space_label='Journal',
            content='<section class="vx-card vx-mt3"><div class="vx-empty">'
                    'Décision inconnue — aucun record figé sous cet identifiant.'
                    '</div></section>'), 404
    out = _dm.find_outcome(mem, decision_id)
    pm = _dm.post_mortem(rec, out)

    def _row(label, value):
        return ('<tr><th style="text-align:left;white-space:nowrap;padding-right:1rem">%s</th>'
                '<td>%s</td></tr>' % (_e(label), _e('n/d' if value is None else value)))

    rec_rows = ''.join(_row(lbl, rec.get(f)) for lbl, f in (
        ('Titre', 'symbol'), ('Décision', 'decision'), ('Niveau', 'level'),
        ('Score /40', 'score_total'), ('Moteur', 'engine_version'),
        ('Séance', 'session_date'), ('Mode démo', 'demo'),
        ('Thèse', 'thesis'), ('Catalyseur', 'catalyst'),
        ('Déclencheur', 'trigger'), ('Invalidation', 'invalidation'),
        ('État opérationnel', 'operational_state'), ('Confiance', 'confidence'),
        ('Objection adverse', 'strongest_objection'),
        ('Opinion minoritaire', 'minority_opinion')))

    if out:
        hz_rows = ''.join(
            '<tr><td>%s</td><td>%s</td><td class="vx-num">%s</td><td class="vx-meta">%s</td></tr>'
            % (_e(h), _e(hz.get('status')),
               _e('%+.1f %%' % hz['return_pct'] if hz.get('return_pct') is not None else 'n/d'),
               _e(hz.get('basis') or ''))
            for h, hz in sorted((out.get('horizons') or {}).items()))
        outcome_html = ('<div class="vx-table-wrap"><table class="vx-table">'
                        '<thead><tr><th>Horizon</th><th>Statut</th><th>Rendement</th><th>Base</th></tr></thead>'
                        '<tbody>%s</tbody></table></div>'
                        '<div class="vx-meta vx-mt1">%s séance(s) observée(s) · MFE %s · MAE %s</div>'
                        % (hz_rows, _e(out.get('sessions_observed')),
                           _e(out.get('mfe_pct')), _e(out.get('mae_pct'))))
    else:
        outcome_html = '<div class="vx-empty">Aucun résultat mesuré pour cette décision.</div>'

    if pm.get('available'):
        cls_rows = ''.join(
            '<tr><td>%s</td><td class="vx-num">%s</td><td>%s</td><td class="vx-meta">%s</td></tr>'
            % (_e(h['horizon']), _e('%+.1f %%' % h['return_pct']),
               _e(h['classification']['class']), _e(h['classification']['basis']))
            for h in pm['horizons'])
        pm_html = ('<div class="vx-mb1"><b>Scénario contenant le résultat :</b> %s</div>'
                   '<div class="vx-table-wrap"><table class="vx-table">'
                   '<thead><tr><th>Horizon</th><th>Rendement</th><th>Classe</th><th>Base</th></tr></thead>'
                   '<tbody>%s</tbody></table></div>'
                   '<div class="vx-meta vx-mt1">%s</div>'
                   '<div class="vx-meta">%s</div>'
                   % (_e(pm.get('scenario_containing') or pm.get('scenario_note') or 'n/d'),
                      cls_rows, _e(pm.get('summary') or ''), _e(pm.get('discipline_note') or '')))
    else:
        pm_html = '<div class="vx-empty">%s</div>' % _e(pm.get('reason') or 'aucun horizon mesuré')

    content = ('<section class="vx-card vx-mt3" aria-label="Record figé">'
               '<div class="vx-card-header"><span class="vx-card-title">Décision figée — %s</span>'
               '<span class="vx-chart-question">Ledger immuable — ce record ne sera jamais réécrit.</span></div>'
               '<div class="vx-table-wrap"><table class="vx-table"><tbody>%s</tbody></table></div>'
               '</section>'
               '<section class="vx-card vx-mt3" aria-label="Résultat mesuré">'
               '<div class="vx-card-header"><span class="vx-card-title">Résultat mesuré</span></div>%s</section>'
               '<section class="vx-card vx-mt3" aria-label="Post-mortem">'
               '<div class="vx-card-header"><span class="vx-card-title">Post-mortem</span>'
               '<span class="vx-chart-question">Que disent les scénarios figés face au résultat réel&nbsp;?</span></div>'
               '%s<div class="vx-card-footer"><a class="vx-btn vx-btn-sm vx-btn-ghost" href="/journal">← Retour Performance</a>'
               ' <a class="vx-btn vx-btn-sm vx-btn-ghost" href="/api/skyler/memory/%s" target="_blank" rel="noopener">JSON brut →</a></div>'
               '</section>'
               % (_e(rec.get('symbol')), rec_rows, outcome_html, pm_html,
                  _e(decision_id)))
    # `title` va dans <title> SANS échappement par le shell : un symbole
    # contenant `</title>` sortirait de la balise et injecterait du HTML actif
    # (constaté au lot 368 — le corps était échappé, pas le titre).
    return render_shell(title='Post-mortem %s' % _e(rec.get('symbol')), active='journal',
                        space_label='Journal', sub_label='Post-mortem',
                        content=content)


#: Le graphe mémoïsé, avec sa CLÉ DE FRAÎCHEUR — pas un cache sans propriétaire.
#:
#: Mesuré : 26 s par appel, et `/api/skyler/graph/<sym>` reconstruisait tout le
#: graphe avant de propager, donc 26 s de plus. Un widget qui met 26 s ne
#: s'affiche pas : il tourne, puis le navigateur abandonne. Le balayage des 92
#: surfaces les comptait « en erreur » alors que les deux routes rendaient 200 —
#: elles étaient seulement trop lentes pour être vues.
#:
#: Le résultat est DÉTERMINISTE pour un scan donné : mêmes séries, même
#: watchlist sectorielle, même calendrier, mêmes positions. La clé nomme donc
#: exactement ce dont il dépend, et rien de plus — un cache dont la clé oublie
#: une entrée sert une réponse périmée en la présentant comme fraîche.
#: Le graphe passe par le magasin d'instantanés PARTAGÉ. Il avait sa propre
#: implantation stale-while-revalidate — mémo, verrou de construction, fil de
#: fond, repos après échec — écrite pour lui seul. La fiche d'un titre en
#: réclamait une deuxième : deux implantations du même mécanisme divergent
#: toujours, et la doctrine interdit un propriétaire parallèle.
#:
#: Ce que le magasin conserve, à l'identique : une seule construction même à N
#: visiteurs, l'ancien graphe servi MARQUÉ pendant la reconstruction, un échec
#: qui n'efface jamais le dernier graphe connu, et un repos après échec.
_KG_MAGASIN = _instantane.Magasin('knowledge-graph')

#: Fenêtre de fraîcheur du graphe. Elle ne pilote PAS l'invalidation — c'est
#: `_kg_clef()` qui le fait, en nommant tout ce dont le graphe dépend. La
#: fenêtre est donc très large : changer de clé suffit à rendre l'entrée
#: obsolète, et un délai supplémentaire ne ferait que reconstruire un graphe
#: identique.
_KG_FRAICHEUR_S = 24 * 3600.0

FRAICHEUR_LIVE = _instantane.LIVE
FRAICHEUR_STALE = _instantane.STALE


def _kg_clef():
    """Ce dont le graphe dépend, mesuré SANS le construire.

    Les positions vivent dans `desk_data.json`, hors du scan : les oublier
    figerait le graphe sur un portefeuille périmé. On prend donc l'horodatage
    du fichier — lu, jamais deviné.
    """
    detail = scan_state.get('detail') or {}
    try:
        from vertex.app.state import cal_state
        n_cal = len(cal_state.get('items') or [])
    except Exception:  # noqa: BLE001
        n_cal = -1
    desk_ts = None
    try:
        import os
        from vertex.services import persist
        p = persist.cache_path('desk_data.json')
        desk_ts = os.path.getmtime(p) if os.path.exists(p) else None
    except Exception:  # noqa: BLE001
        desk_ts = None
    return (scan_state.get('scan_ts'), len(detail), n_cal, desk_ts)


def _kg_build():
    """Le graphe servi, TOUJOURS accompagné de ce qu'il vaut.

    Mesuré le 24 août 2026, produit live : après CHAQUE scan, le premier
    visiteur de la page Portefeuille attendait **15,1 s** (le suivant :
    0,007 s). Le graphe du scan PRÉCÉDENT est pourtant une réponse utilisable
    — à condition de dire qu'elle date.

    La fraîcheur est ajoutée sur une COPIE : la figer dans la valeur mémoïsée
    donnerait un âge qui ne bouge plus, c'est-à-dire un chiffre daté faux.
    """
    #  UNE seule clé, et un JETON qui porte la dépendance réelle : changer de
    #  clé à chaque scan aurait fait d'un graphe parfaitement utilisable une
    #  entrée « absente », donc une attente de 15 s. Le jeton le rend RASSIS.
    valeur, meta = _KG_MAGASIN.servir('graphe', _kg_construire,
                                      fraicheur_s=_KG_FRAICHEUR_S,
                                      attendre=True, jeton=str(_kg_clef()))
    if valeur is None:
        #  Aucun graphe n'a jamais pu être construit : on le DIT, on ne rend
        #  pas une coquille qui ressemblerait à « aucune dépendance cachée ».
        return {'as_of': None, 'demo': False, 'nodes': [], 'edges': [],
                'hidden_dependencies': [], 'hidden_groups': [],
                'research_questions': [], 'sector_exposure': {},
                'fraicheur': meta.etat, 'age_s': None,
                'reconstruction_en_cours': meta.rafraichissement_en_cours,
                'reconstruction_erreur': meta.erreur}
    sortie = dict(valeur)
    sortie['fraicheur'] = meta.etat
    sortie['age_s'] = meta.age_s
    sortie['reconstruction_en_cours'] = meta.rafraichissement_en_cours
    if meta.erreur:
        sortie['reconstruction_erreur'] = meta.erreur
    return sortie


def _kg_construire():
    """Assemble le Knowledge Graph depuis les sources réelles de l'état partagé :
    univers scanné, watchlist sectorielle statique, séries canoniques, calendrier
    earnings/macro, positions desk. Aucune relation inventée."""
    from vertex.data import series as _series
    from vertex.engines import knowledge_graph as _kg
    from vertex.market.sectors import SECTOR_MAP
    from vertex.app.config import DEMO_MODE as _demo
    detail_all = scan_state.get('detail') or {}
    symbols = sorted(detail_all.keys())
    closes_by_sym = {}
    for s in symbols:
        closes, _src = _series.closes(detail_all.get(s) or {})
        if closes:
            closes_by_sym[s] = closes
    events_by_sym = {}
    try:
        from vertex.app.state import cal_state
        for e in (cal_state.get('items') or []):
            s = str(e.get('sym', '')).upper()
            if s and e.get('dte') is not None:
                events_by_sym.setdefault(s, []).append(
                    {'kind': 'earnings', 'label': 'Résultats %s' % s,
                     'dte': e.get('dte'), 'source': 'calendar.earnings'})
    except Exception:
        pass
    positions = None
    try:
        from vertex.positions.repository import load_positions
        from vertex.services import persist
        positions = load_positions(persist.load_json('desk_data.json', {}) or {})
    except Exception:
        positions = None
    quotes = {s: (detail_all.get(s) or {}).get('price') for s in detail_all
              if isinstance(detail_all.get(s), dict)
              and (detail_all.get(s) or {}).get('price') is not None}
    return _kg.build(symbols, sector_map=SECTOR_MAP, closes_by_sym=closes_by_sym,
                     events_by_sym=events_by_sym, positions=positions, quotes=quotes,
                     as_of=scan_state.get('scan_ts_h') or scan_state.get('updated'),
                     demo=_demo)


@bp.route('/api/skyler/graph')
def api_skyler_graph():
    """KNOWLEDGE GRAPH INSTITUTIONNEL (LOT 11) : sociétés, secteurs, catalyseurs
    et portefeuille reliés uniquement par des sources réelles tracées — chaque
    arête porte provenance et niveau de preuve ; dépendances cachées (≥ 2 liens
    indépendants) et questions de recherche (relations non documentées, jamais
    inventées). Lecture seule."""
    return jsonify(_kg_build())


@bp.route('/api/skyler/graph/<sym>')
def api_skyler_graph_sym(sym):
    """PROPAGATION D'IMPACT EXPLICABLE (LOT 11/28) : chemins depuis un titre,
    chaque saut justifié. `?hops=1..3` optionnel (défaut 2, clampé) ; garde de
    volume MAX_PATHS — troncature TOUJOURS DITE (`truncated`). Lecture seule."""
    from flask import request
    from vertex.engines import knowledge_graph as _kg
    sym = (sym or '').upper()[:12]
    try:
        hops = max(1, min(3, int(request.args.get('hops', 2))))
    except (TypeError, ValueError):
        hops = 2
    g = _kg_build()
    paths = _kg.propagate(g, 'company:%s' % sym, max_hops=hops)
    truncated = len(paths) >= _kg.MAX_PATHS
    out = {'symbol': sym, 'generator': 'deterministic',
           'as_of': g['as_of'], 'demo': g['demo'],
           'engine_version': g['engine_version'],
           #  Cette route RECOPIE les champs a la main : sans ces trois-la,
           #  elle servirait un graphe date en le presentant comme courant,
           #  ce qui est pire que la lenteur qu'on vient de retirer.
           'fraicheur': g.get('fraicheur'),
           'age_s': g.get('age_s'),
           'reconstruction_en_cours': g.get('reconstruction_en_cours'),
           'hops': hops, 'truncated': truncated,
           'paths': paths,
           'hidden_dependencies': [d for d in g['hidden_dependencies']
                                   if sym in d['symbols']],
           'research_questions': [q for q in g['research_questions']
                                  if q['symbol'] == sym]}
    if truncated:
        out['note'] = ('propagation tronquée à %d chemin(s) (garde de volume) — '
                       'liste partielle DITE, jamais silencieuse' % _kg.MAX_PATHS)
    return jsonify(out)


@bp.route('/api/events/<sym>')
def api_events(sym):
    """TIMELINE D'ÉVÉNEMENTS NORMALISÉE (SKYLER LOT 4) : news assainies et
    dédupliquées, earnings/macro du calendrier réel, anomalies statistiques —
    faits distingués des interprétations, impact suggéré par mots-clés
    transparents seulement. Lecture seule."""
    from vertex.data import series as _series
    from vertex.engines import anomaly as _an, events as _events
    from vertex.services import news_plus as _np
    sym = (sym or '').upper()[:12]
    detail = (scan_state.get('detail') or {}).get(sym) or {}
    closes, _src = _series.closes(detail)
    ano = _an.scan(closes) if closes else None
    earnings = []
    try:
        from vertex.app.state import cal_state
        earnings = [e for e in (cal_state.get('items') or [])
                    if str(e.get('sym', '')).upper() == sym]
    except Exception:
        earnings = []
    macro = None
    macro_calendar_status = {
        'available': False,
        'status': 'MACRO_CALENDAR_UNAVAILABLE',
        'events_loaded': 0,
        'read_only': True,
        'reason': 'calendrier macro indisponible ; aucune absence d’événement n’est inférée',
    }
    try:
        from vertex.data import macro_calendar
        macro = macro_calendar.events(horizon_days=30)
        #  « Disponible » ne veut pas dire « complet » : la liste FOMC publiee
        #  a une fin, et au-dela le calendrier rendait MOINS d'evenements sans
        #  rien dire — indiscernable d'une periode calme.
        _cov = macro_calendar.couverture(horizon_days=30)
        macro_calendar_status = {
            'available': True,
            'status': ('MACRO_CALENDAR_PARTIAL' if _cov['fomc_horizon_depasse']
                       else 'MACRO_CALENDAR_AVAILABLE'),
            'events_loaded': len(macro) if isinstance(macro, list) else 0,
            'couverture': _cov,
            'read_only': True,
        }
    except Exception:
        macro = None
    # XSS : titres externes assainis AU POINT DE SORTIE (rendus innerHTML client).
    news = _np.sanitize_news(detail.get('news') or [])
    d = _events.build(sym, news=news, earnings=earnings, macro=macro, anomaly=ano,
                      as_of=scan_state.get('scan_ts_h') or scan_state.get('updated'))
    d['coverage']['macro_calendar'] = macro_calendar_status
    d['demo'] = bool(scan_state.get('source') == 'demo')
    return jsonify(d)
