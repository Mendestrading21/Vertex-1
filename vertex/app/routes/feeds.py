"""
vertex/app/routes/feeds.py — FLUX DE DONNÉES (Blueprint, Ch. II).

Les routes de lecture pour les widgets : résumé marché, cockpit, watchlist,
board d'options, recherche, watchlist hebdo, stratégie, comité. Toutes lisent
l'état partagé (`vertex.app.state`) — aucune injection, import direct.

Lecture seule, analyse uniquement. Ces routes servent des données, jamais d'ordre.
"""

import time

from flask import Blueprint, jsonify, request

from vertex.app.config import IBKR_ENABLED
from vertex.app.state import scan_state, weekly_state
from vertex.data.universe import UNIVERSE
from vertex.engines import market_lens

bp = Blueprint('feeds', __name__)


def _scan_age():
    return round(time.time() - scan_state['scan_ts']) if scan_state.get('scan_ts') else None


@bp.route('/api/market/summary')
def api_market_summary():
    """Résumé marché pour widgets (lecture seule)."""
    mc = scan_state.get('market_ctx') or {}
    cl = market_lens.climate(mc)
    sc = cl['score'] if cl else None
    #  Le verdict est celui du MOTEUR, il n'est plus re-dérivé ici. Deux défauts
    #  mesurés dans l'ancienne ligne `(sc or 0) >= 65 ... else 'DANGEREUX'` :
    #  1) au démarrage à froid ou scan échoué, `market_ctx` vide → climate() rend
    #     None à dessein, mais `(sc or 0)` convertissait l'ABSENCE en branche
    #     basse : la route servait {"score": null, "verdict": "DANGEREUX"} avec
    #     ses six dimensions nulles — un jugement catégoriel sans donnée derrière
    #     (invariant 5 : absence et valeur restent distinctes).
    #  2) la borne 65 re-dérivait un label que le moteur possède déjà, avec une
    #     valeur différente de la sienne (62) : mesuré, un score de 62/63/64 était
    #     FAVORABLE pour le moteur et NEUTRE pour cette route, au même instant.
    #  `market_lens.CLIMAT_FAVORABLE_MIN` vaut désormais 65 : le verdict servi
    #  ici est identique à celui d'avant sur toute la plage, la divergence est
    #  supprimée et l'absence voyage avec le score.
    verdict = cl['label'] if cl else None
    return jsonify({
        'score': sc, 'verdict': verdict,
        # Couverture du score : `partiel`/`breadth_status` ne sont posés par le
        # moteur QUE lorsque la largeur de marché manque (25 pts non mesurés) —
        # sans eux, un score partiel était indiscernable d'un score complet.
        #  Second tour : `bool(cl and ...)` rendait `score_partiel: False` quand
        #  il n'y a AUCUN climat (mesuré : `market_ctx` vide → `climate()` rend
        #  None, donc score null ET « couverture complète »). Affirmer une
        #  couverture complète sur un score absent est la même faute que le
        #  score partiel non marqué qu'on venait de corriger : absence et
        #  couverture restent trois états distincts (None / True / False).
        'score_partiel': (bool(cl.get('partiel')) if cl else None),
        'score_note': (cl or {}).get('note'),
        'breadth_status': (cl or {}).get('breadth_status'),
        'regime': mc.get('spy_regime'), 'roro': mc.get('roro'), 'roro_gap': mc.get('roro_gap'),
        'vix': mc.get('vix'), 'vix_band': mc.get('vix_band'), 'vix_chg': mc.get('vix_chg'),
        'breadth': mc.get('breadth'), 'market_verdict': mc.get('verdict'),
        'indices': scan_state.get('indices'), 'spy': scan_state.get('spy'),
        'best_sector': (scan_state.get('sectors') or [None])[0],
        'scanned': scan_state.get('scanned_n'), 'universe': len(UNIVERSE),
        'scan_age': _scan_age(), 'market': scan_state.get('market'),
        'source': 'ibkr' if IBKR_ENABLED else 'cloud',
    })


@bp.route('/api/market/context')
def api_market_context():
    """MarketContext canonique (SKYLER LOT 3) : dimensions typées valeur/unité/
    source/fraîcheur/statut, régime + transition, diff depuis la dernière session.
    Lecture seule ; absent = MISSING, jamais estimé."""
    from vertex.app.config import DEMO_MODE as _demo
    from vertex.engines import market_context as _mcx
    from vertex.services import persist
    prev = persist.load_json('market_context_last.json', None)
    ctx = _mcx.build(scan_state, prev=prev, demo=_demo)
    # base du « depuis la dernière session » : on ne persiste qu'un contexte daté
    # et seulement quand le scan a republié (as_of différent).
    if ctx.get('as_of') and (not prev or prev.get('as_of') != ctx.get('as_of')):
        persist.save_json('market_context_last.json', ctx)
    return jsonify(ctx)


@bp.route('/api/cockpit')
def api_cockpit():
    """Widgets du cockpit : action du jour + top opportunités."""
    recs = scan_state.get('recommendations') or []
    cand = sorted([r for r in recs if r.get('tone') in ('buy', 'pullback')],
                  key=lambda r: ((r.get('timing') == 'BUY_NOW'), r.get('score40', 0)), reverse=True)
    top = cand[0] if cand else (recs[0] if recs else None)
    # TOP VERTEX : les meilleurs setups du jour selon le noyau quant (edge décroissant, verdict BUY/S+)
    _rows = scan_state.get('rows') or []
    _vxb = [r for r in _rows if (r.get('vx_verdict') or '') in ('VERTEX BUY', 'VERTEX S+') and r.get('vx_edge') is not None]
    vertex_top = sorted(_vxb, key=lambda r: r.get('vx_edge') or 0, reverse=True)[:5]
    return jsonify({'action': top, 'opportunities': recs[:15], 'vertex_top': vertex_top,
                    'updated': scan_state.get('updated')})


@bp.route('/api/watchlist')
def api_watchlist():
    return jsonify({'rows': scan_state.get('rows') or [], 'sectors': scan_state.get('sectors') or [],
                    'scanned': scan_state.get('scanned_n'), 'universe': len(UNIVERSE),
                    'updated': scan_state.get('updated')})


@bp.route('/api/options')
def api_options():
    return jsonify({'board': scan_state.get('options_board') or [], 'updated': scan_state.get('updated')})


#  QUATRE CHARGES VIDES SANS MOTIF — mesuré le 2026-09-06 en exerçant les 184
#  règles du runtime : `/api/search`, `/api/weekly`, `/api/strategie` et
#  `/api/comite` rendaient `[]` ou `{}` sans une seule clé disant POURQUOI.
#  Un appelant ne pouvait donc pas distinguer « rien à signaler » de « le calcul
#  n'a pas tourné » — l'invariant 5 sépare précisément ces deux états.
#
#  Aucune de ces routes n'a de consommateur dans le dépôt (relevé .py/.js) :
#  elles servent un humain ou un script externe, c'est-à-dire exactement le
#  lecteur qui n'a aucun moyen de deviner. La forme non vide est INCHANGÉE ;
#  seul le cas vide gagne un motif.
def _vide(motif, **extra):
    charge = {'disponible': False, 'motif': motif, 'read_only': True}
    charge.update(extra)
    return jsonify(charge)


@bp.route('/api/search')
def api_search():
    q = (request.args.get('q') or '').upper().strip()
    if not q:
        return jsonify({'disponible': False, 'read_only': True,
                        'usage': 'GET /api/search?q=NVDA — recherche dans '
                                 'l’univers scanné, 20 résultats au plus',
                        'resultats': []})
    res = [{'ticker': s} for s in UNIVERSE if q in s][:20]
    #  La liste reste la forme historique quand il y a des résultats ; un
    #  ensemble VIDE dit qu'il l'est, et sur quel univers il a cherché.
    if not res:
        return jsonify({'disponible': True, 'read_only': True, 'resultats': [],
                        'motif': 'aucun titre de l’univers scanné ne contient « %s »' % q,
                        'univers': len(UNIVERSE)})
    return jsonify(res)


@bp.route('/api/weekly')
def api_weekly():
    d = weekly_state.get('data')
    if not d:
        return _vide('revue hebdomadaire pas encore produite sur cette '
                     'instance — elle est écrite par le job WEEKLY_REVIEW')
    return jsonify(d)


@bp.route('/api/strategie')
def api_strategie():
    """Stratégie options personnalisée (1/2/3/6/9/12 mois). Lecture seule, analyse only."""
    d = scan_state.get('strategy')
    if not d:
        return _vide('aucune stratégie dans le dernier scan — le scan n’a pas '
                     'encore tourné, ou il n’a produit aucune ligne',
                     scan=scan_state.get('scan_ts_h'))
    return jsonify(d)


@bp.route('/api/comite')
def api_comite():
    """Comité d'investissement : décisions documentées (4 portes). Analyse only."""
    d = scan_state.get('committee')
    if not d:
        return _vide('aucune délibération de comité dans le dernier scan — '
                     'le scan n’a pas encore tourné, ou aucune ligne n’a '
                     'franchi les portes', scan=scan_state.get('scan_ts_h'))
    return jsonify(d)


__all__ = ['bp']
