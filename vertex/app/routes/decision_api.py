"""
vertex/app/routes/decision_api.py — API DÉCISION (Blueprint, Ch. II).

Expose la DecisionStack par HTTP : décision d'un titre, Morning Brief, et
Committee Review. Premier groupe de routes sorti du monolithe en Blueprint.

L'état partagé (`scan_state`, mode démo) est INJECTÉ à l'enregistrement —
`scan_state` est le même objet dict muté en place par la boucle de scan, donc
les routes voient toujours les données fraîches. Logique déplacée verbatim.

Analyse uniquement. Aucune exécution — ces routes lisent, ne commandent rien.
"""


from flask import Blueprint, jsonify, request

from vertex.engines import decision_stack as _decision
from vertex.engines import context as _context
from vertex.engines import market_lens as _market_lens
from vertex.engines import recommendation as _reco


def make_blueprint(*, scan_state, demo_mode):
    """Construit le Blueprint API-décision en fermant sur l'état partagé injecté."""
    bp = Blueprint('decision_api', __name__)

    #  #779/G1 — cette fermeture dupliquait `terminal.py::_scan_age` a
    #  l'identique. Deux copies d'un meme calcul derivent au premier ajustement,
    #  et l'ecran afficherait deux ages differents pour la meme donnee.
    from vertex.app.state import scan_age as _scan_age

    def _best_option_for(sym):
        """Meilleur CALL du board pour un titre (véhicule DecisionStack). None si absent."""
        calls = [c for c in (scan_state.get('options_board') or [])
                 if c.get('sym') == sym and c.get('type') == 'CALL' and c.get('quality') is not None]
        if not calls:
            return None
        return max(calls, key=lambda c: c.get('quality', 0))

    def _market_ctx():
        """Contexte marché normalisé pour la DecisionStack (source unique)."""
        mctx = scan_state.get('market_ctx') or {}
        return {'roro': mctx.get('roro'), 'spy_regime': mctx.get('spy_regime'),
                'vix_band': mctx.get('vix_band')}

    def _ctx_for(sym):
        return _context.context_for(sym, scan_state.get('detail') or {})

    def _brief_row(sym, market, scan_age):
        """Une ligne du brief : la décision du comité pour un titre, condensée."""
        detail = dict((scan_state.get('detail') or {}).get(sym) or {})
        detail.setdefault('symbol', sym)
        ctx = _ctx_for(sym)
        r = _decision.evaluate(detail, symbol=sym, market=market, option=_best_option_for(sym),
                               scan_age_s=scan_age, demo=demo_mode, context=ctx)
        com = r.get('committee') or {}
        return {
            'symbol': sym, 'decision': r['final_decision'], 'label': r['decision_label'],
            'tone': r['decision_tone'], 'confidence': r['confidence'], 'conviction': r['conviction'],
            'view': com.get('view'), 'agreement': com.get('agreement'),
            'has_contradiction': com.get('has_contradiction', False),
            'devils_advocate': com.get('devils_advocate'),
            'top_pro': (r.get('pros') or [None])[0], 'top_con': (r.get('cons') or [None])[0],
            'price': detail.get('price'), 'context_headline': (ctx or {}).get('headline'),
        }

    def _top_symbols(limit):
        rows = sorted((scan_state.get('rows') or []),
                      key=lambda x: (x.get('score') or 0), reverse=True)
        syms, seen = [], set()
        for x in rows:
            s = x.get('symbol')
            if s and s not in seen:
                seen.add(s)
                syms.append(s)
            if len(syms) >= limit:
                break
        return syms, seen

    @bp.route('/api/decision/<sym>')
    def decision_ep(sym):
        """LA DÉCISION STACK — vérité unique, explicable, par titre. Analyse uniquement."""
        sym = sym.upper()
        detail = dict((scan_state.get('detail') or {}).get(sym) or {})
        detail.setdefault('symbol', sym)
        ctx = _ctx_for(sym)
        res = _decision.evaluate(detail, symbol=sym, market=_market_ctx(),
                                 option=_best_option_for(sym), scan_age_s=_scan_age(),
                                 demo=demo_mode, context=ctx)
        # Prisme marché & secteur : le vent est-il dans le dos ou de face ?
        sc = next((dm.get('pct_universe') for dm in (ctx or {}).get('dimensions', [])
                   if dm.get('key') == 'score'), None) if ctx else None
        res['market_lens'] = _market_lens.build(
            market=scan_state.get('market_ctx') or {}, sectors=scan_state.get('sectors') or [],
            sector_name=detail.get('sector'), stock_pct=sc)
        return jsonify(res)

    @bp.route('/api/position-decision/<sym>')
    def position_decision_ep(sym):
        """Décision de GESTION d'une position détenue — source unique (remplace les
        conseillers JS divergents). Params : type,entry,stop,tp,current,pl_pct,dte.
        Analyse uniquement."""
        sym = sym.upper()
        detail = dict((scan_state.get('detail') or {}).get(sym) or {})
        detail.setdefault('symbol', sym)
        try:
            underlying = _decision.evaluate(detail, symbol=sym, market=_market_ctx(),
                                            option=_best_option_for(sym), scan_age_s=_scan_age(),
                                            demo=demo_mode, context=_ctx_for(sym))
        except Exception:
            underlying = None

        def _f(name):
            v = request.args.get(name)
            try:
                return float(v) if v not in (None, '') else None
            except ValueError:
                return None

        pos = {'type': (request.args.get('type') or 'STK').upper(),
               'entry': _f('entry'), 'stop': _f('stop'), 'tp': _f('tp'),
               'current': _f('current'), 'pl_pct': _f('pl_pct'), 'dte': _f('dte')}
        reco = _reco.position_decision(pos, underlying)
        reco['symbol'] = sym
        reco['underlying'] = {'decision': (underlying or {}).get('final_decision'),
                              'label': (underlying or {}).get('decision_label'),
                              'tone': (underlying or {}).get('decision_tone')} if underlying else None
        reco['underlying_availability'] = {
            'available': underlying is not None,
            'status': 'UNDERLYING_ANALYSIS_AVAILABLE' if underlying is not None
            else 'UNDERLYING_ANALYSIS_UNAVAILABLE',
            'reason': None if underlying is not None
            else 'analyse sous-jacente indisponible ; décision de position calculée sans ce contexte',
            'read_only': True,
            'does_not_change_recommendation': True,
        }
        return jsonify(reco)

    @bp.route('/api/options-for/<sym>')
    def options_for_ep(sym):
        """« Options disponibles sur cette position » — meilleurs CALL/PUT/LEAPS/
        covered call/protective put pour un sous-jacent. Analyse uniquement."""
        held = (request.args.get('type') or 'STK').upper()
        held = 'STK' if held == 'STK' else 'OPT'
        from vertex.options import chaine_a_la_demande as _chaine
        #  Chaîne chargée EN FOND si le titre manque au board (jamais dans la
        #  requête) ; l'état est joint pour que la page distingue « pas encore ».
        board, meta = _chaine.board_avec(sym.upper(), scan_state.get('options_board') or [])
        out = _reco.options_for_position(sym.upper(), board, held_type=held)
        if isinstance(out, dict):
            out['chaine_en_cours'] = bool(_chaine.en_cours(meta)) and not any(
                str((c or {}).get('sym', '')).upper() == sym.upper()
                for c in board if isinstance(c, dict))
        return jsonify(out)

    @bp.route('/api/brief')
    def brief_ep():
        """🌅 MORNING BRIEF — le comité passe en revue les meilleurs setups du jour (Ch. XIX)."""
        market, scan_age = _market_ctx(), _scan_age()
        syms, _ = _top_symbols(8)
        briefs = [_brief_row(s, market, scan_age) for s in syms]
        buyish = [b for b in briefs if b['decision'] in ('STRONG_BUY', 'BUY', 'BUY_PULLBACK')]
        watch = [b for b in briefs if b['decision'] in ('WATCH_BREAKOUT', 'WAIT', 'TOO_LATE')]
        avoid = [b for b in briefs if b['decision'] in ('AVOID', 'NO_NEW_RISK')]
        contradictions = [b for b in briefs if b['has_contradiction']]
        mctx = scan_state.get('market_ctx') or {}
        return jsonify({
            'as_of': scan_state.get('scan_ts_h') or scan_state.get('updated'),
            'scan_age': scan_age, 'data_source': 'demo' if demo_mode else 'scan',
            'market': {'roro': mctx.get('roro'), 'spy_regime': mctx.get('spy_regime'),
                       'vix_band': mctx.get('vix_band'), 'breadth': mctx.get('breadth')},
            'setups': briefs,
            'counts': {'buy': len(buyish), 'watch': len(watch), 'avoid': len(avoid),
                       'contradictions': len(contradictions)},
            'contradictions': contradictions,
        })

    @bp.route('/api/committee-review')
    def committee_review_ep():
        """🧠 COMMITTEE REVIEW — le comité passe TOUT l'univers scanné en revue (Ch. XIX)."""
        market, scan_age = _market_ctx(), _scan_age()
        syms, seen = _top_symbols(60)          # borne dure, journalisée côté UI
        reviews = [_brief_row(s, market, scan_age) for s in syms]
        tally = {}
        for b in reviews:
            tally[b['decision']] = tally.get(b['decision'], 0) + 1
        mctx = scan_state.get('market_ctx') or {}
        return jsonify({
            'as_of': scan_state.get('scan_ts_h') or scan_state.get('updated'),
            'scan_age': scan_age, 'data_source': 'demo' if demo_mode else 'scan',
            'market': {'roro': mctx.get('roro'), 'spy_regime': mctx.get('spy_regime'),
                       'vix_band': mctx.get('vix_band')},
            'count': len(reviews), 'capped_at': 60, 'universe_scanned': len(seen),
            'tally': tally, 'reviews': reviews,
        })

    return bp


__all__ = ['make_blueprint']
