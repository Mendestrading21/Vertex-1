"""
vertex/app/routes/options_lab_api.py — API du centre de recherche options.

Une seule route : /api/options-lab — le payload complet des 12 chapitres,
consolidé côté serveur (le client ne télécharge plus le /scan géant).

Analyse uniquement, lecture seule. Aucun ordre.
"""

from flask import Blueprint, jsonify, request

from vertex.app.config import DEMO_MODE
from vertex.app.state import cal_state, scan_state
from vertex.engines import multileg_lab, options_lab
from vertex.options import entrees_mesurees as _entrees

bp = Blueprint('options_lab_api', __name__)


@bp.route('/api/options-lab')
def api_options_lab():
    """OPTIONS RESEARCH CENTER — cockpit, fiche, analyse, plan, viz, stratégies,
    tops, comparateur, comité, risques, timeline. Lecture seule."""
    try:
        return jsonify(options_lab.build(scan_state, demo=DEMO_MODE,
                                         cal_items=cal_state.get('items')))
    except Exception as e:
        return jsonify({'empty': True, 'error': 'options_lab_unavailable'}), 500


@bp.route('/api/options/strategies/<sym>')
def api_options_strategies(sym):
    """Stratégies options MULTI-JAMBES construites depuis le board RÉEL : payoff à
    l'échéance, breakevens, gain/perte max, probabilité de profit, greeks agrégés.
    Analyse pure, lecture seule — aucun ordre. Donnée absente => available:false honnête."""
    sym = sym.upper()
    try:
        from vertex.options import chaine_a_la_demande as _chaine
        #  board ∪ chaîne à la demande si titre absent — chargée EN FOND :
        #  `on_demand.board_with` la tirait dans la requête (secondes).
        board, meta = _chaine.board_avec(sym, scan_state.get('options_board') or [])
        if not any(str((c or {}).get('sym', '')).upper() == sym
                   for c in board if isinstance(c, dict)) and _chaine.en_cours(meta):
            return jsonify({'available': False, 'symbol': sym, 'en_cours': True, 'retry_s': 8,
                            'reason': 'chaîne d’options en cours de chargement — '
                                      'la page réessaie d’elle-même'}), 200
        detail = (scan_state.get('detail') or {}).get(sym) or {}
        spot = detail.get('price')
        if not spot:
            spot = next((c.get('spot') for c in board
                         if c.get('sym') == sym and c.get('spot')), None)
        # Biais directionnel RÉEL du titre (verdict/score du scan) → recommandation adaptée.
        verdict = (detail.get('verdict') or '').upper()
        score = detail.get('score')
        if verdict in ('ACHETER', 'RENFORCER', 'BUY') or (score is not None and score >= 60):
            bias = 'bullish'
        elif verdict in ('ÉVITER', 'EVITER', 'ALLÉGER', 'ALLEGER', 'AVOID') or (score is not None and score < 40):
            bias = 'bearish'
        else:
            bias = 'neutral'
        #  Entrees MESUREES : sans elles, ces stratégies etaient analysees a
        #  4,5 % et dividende nul, comme le simulateur avant D-099.
        res = multileg_lab.strategies_for_symbol(
            board, sym, spot, bias=bias,
            r=_entrees.taux(scan_state, 35),
            q=(_entrees.rendement_dividende(scan_state, sym) or 0.0))
        res['entrees'] = _entrees.provenance(scan_state, sym)
        res['as_of'] = scan_state.get('scan_ts_h') or scan_state.get('updated')
        res['demo'] = DEMO_MODE
        #  Verdict, liquidité, mouvement attendu, asymétrie et scénarios : calculés
        #  ICI (vertex/options/structure_verdict.py), plus dans la page.
        if res.get('available') and isinstance(res.get('strategies'), list):
            from vertex.options import structure_verdict as _sv
            res.setdefault('sym', sym)
            for s in res['strategies']:
                if isinstance(s, dict):
                    s['analyse'] = _sv.analyser(res, s, board)
            res['analyse_source'] = 'structure_verdict (serveur)'
        return jsonify(res)
    except Exception as e:
        return jsonify({'available': False, 'reason': 'options_lab_unavailable'}), 200


@bp.route('/api/options/analyze', methods=['POST'])
def api_options_analyze():
    """Analyse une stratégie multi-jambes ARBITRAIRE (jambes fournies par le client :
    p.ex. les positions options RÉELLES du desk regroupées par sous-jacent). Payoff,
    breakevens, gain/perte max, PoP (si IV), greeks. Lecture seule, aucun ordre."""
    try:
        from vertex.app import payload_validation as _payload
        b = _payload.object_body(request.get_json(force=True, silent=True), max_keys=9)
        if not b.get('legs'):
            return jsonify({'available': False, 'reason': 'legs manquant'}), 200
        legs = _payload.object_list(b, 'legs', maximum=16, minimum=1)
        spot = _payload.optional_number(b, 'spot')
        iv = _payload.optional_number(b, 'iv', maximum=10)
        days = _payload.optional_number(b, 'days', maximum=3650)
        if b.get('name') is not None and len(str(b.get('name'))) > 96:
            raise _payload.PayloadError('name_trop_long')
        #  Le taux ne depend pas du titre : il est toujours mesurable ici. Le
        #  dividende exige un symbole ; la charge peut le fournir, et sans lui
        #  `q` reste 0,0 — valeur que le bloc `model` TRACE deja, donc declaree.
        sym_q = str(b.get('sym') or '').upper()[:12]
        res = multileg_lab.analyze_strategy(
            legs, spot, iv, days,
            r=_entrees.taux(scan_state, days),
            q=(_entrees.rendement_dividende(scan_state, sym_q) or 0.0) if sym_q else 0.0,
            name=b.get('name'))
        if isinstance(res, dict) and res.get('available'):
            res['entrees'] = _entrees.provenance(scan_state, sym_q)
        return jsonify(res)
    except _payload.PayloadError as exc:
        return jsonify({'available': False, 'error': str(exc)}), 400
    except Exception as e:
        return jsonify({'available': False, 'reason': 'options_analysis_unavailable'}), 200


__all__ = ['bp']
