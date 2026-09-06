"""vertex/app/routes/ai_api.py — API du « cerveau Claude » (§28).

Expose l'enrichissement Claude+web : instantané daté, santé honnête, et un
rafraîchissement à la demande (« Mettre à jour avec Claude »). Lecture seule ;
aucun ordre. Sans clé ANTHROPIC_API_KEY → statut MISSING, aucune donnée estimée
(l'app le dit franchement plutôt que d'inventer).
"""
from __future__ import annotations

import threading

from flask import Blueprint, jsonify, request

from vertex.app.state import scan_state
from vertex.ai import enrichment as _enrich
from vertex.ai import health as _health

bp = Blueprint('ai_api', __name__)


@bp.route('/api/copilot/ask', methods=['POST'])
def copilot_ask():
    """COPILOTE d'analyse : répond à une question en s'ancrant dans les données
    réelles (digest, GEX/flux/thèse, positions du desk). Via Claude si la clé est
    configurée, sinon repli déterministe honnête. Lecture seule — aucun ordre."""
    from vertex.ai import copilot
    body = request.get_json(force=True, silent=True) or {}
    #  Lot 25 : les positions déclarées ne partent dans le prompt QUE sur
    #  action explicite du client (case cochée), jamais par défaut.
    return jsonify(copilot.answer(body.get('question'), scan_state,
                                  symbol=body.get('symbol'),
                                  avec_positions=bool(body.get('avec_positions'))))

_refresh_lock = threading.Lock()
_refreshing = {'on': False}

# Agent IA partagé : le RateLimiter persiste entre requêtes (anti-spam Claude).
_analyst_ref = {'agent': None}


def enrich_symbols(limit=None):
    """Titres à enrichir : scan (rows) + positions déclarées, dédupliqués."""
    syms: list[str] = []
    seen = set()

    def _add(s):
        s = str(s or '').upper().strip()
        if s and '.' not in s and s not in seen:
            seen.add(s)
            syms.append(s)

    for r in (scan_state.get('rows') or []):
        _add(r.get('symbol'))
    try:                                     # positions déclarées (localStorage synchronisé)
        import json
        from vertex.services import persist
        blob = persist.load_json('desk_data.json', {}) or {}
        raw = (blob.get('data') or {}).get('myTrades')
        for t in (json.loads(raw) if isinstance(raw, str) else (raw or [])):
            if isinstance(t, dict):
                _add(t.get('symbol') or t.get('ticker'))
    except Exception:
        pass
    return syms[:(limit or _enrich.MAX_SYMBOLS)]


def _run_refresh():
    try:
        _enrich.run(enrich_symbols())
    finally:
        with _refresh_lock:
            _refreshing['on'] = False


def start_background_enrichment():
    """Lance un enrichissement en tâche de fond (idempotent). Non bloquant."""
    with _refresh_lock:
        if _refreshing['on']:
            return False
        _refreshing['on'] = True
    try:
        threading.Thread(target=_run_refresh, daemon=True).start()
    except Exception:
        # Le thread n'a pas démarré : on relâche le verrou (sinon /refresh reste
        # bloqué à « déjà en cours » jusqu'au redémarrage).
        with _refresh_lock:
            _refreshing['on'] = False
        raise
    return True


def reconcilier_cotations(snap, detail):
    """Chaque cotation trouvée par recherche web reçoit le prix CANONIQUE du scan
    et l'écart en % — une cotation LLM n'est jamais un cours de marché ; le scan
    fait foi. Sans prix de scan : écart absent, dit tel quel. Ne mute pas
    l'instantané persisté."""
    import copy
    snap = copy.deepcopy(snap or {})
    quotes = (snap.get('surfaces') or {}).get('quotes') or {}
    detail = detail or {}
    for sym, q in quotes.items():
        if not isinstance(q, dict):
            continue
        prix = (detail.get(str(sym).upper()) or {}).get('price')
        q['canonique'] = 'scan'
        q['scan_price'] = prix if isinstance(prix, (int, float)) else None
        v = q.get('value')
        if isinstance(v, (int, float)) and isinstance(prix, (int, float)) and prix > 0:
            q['ecart_pct'] = round((v - prix) / prix * 100.0, 2)
        else:
            q['ecart_pct'] = None
    snap['note_quotes'] = ('cotations issues d’une recherche web par Claude — jamais le prix '
                           'canonique ; le prix du scan fait foi et l’écart est servi')
    return snap


@bp.route('/api/ai/enrichment')
def ai_enrichment():
    """Instantané complet Claude+web (cotations/actualités étiquetées provenance),
    cotations réconciliées avec le prix canonique du scan (`scan_price`, `ecart_pct`)."""
    return jsonify(reconcilier_cotations(_enrich.load_snapshot(),
                                         scan_state.get('detail') or {}))


@bp.route('/api/ai/status')
def ai_status():
    """Santé du cerveau Claude : configuration + dernier enrichissement observé."""
    st = _enrich.status()
    st['health'] = _health.health()
    st['refreshing'] = _refreshing['on']
    return jsonify(st)


@bp.route('/api/ai/refresh', methods=['POST'])
def ai_refresh():
    """Déclenche « Mettre à jour avec Claude » (tâche de fond). 202 = accepté."""
    started = start_background_enrichment()
    return jsonify({'accepted': started, 'refreshing': True,
                    'note': ('Enrichissement Claude+web lancé.' if started
                             else 'Un enrichissement est déjà en cours.')}), 202


def _analyst_agent():
    """Agent IA partagé (construction paresseuse) — l'app démarre sans clé ni
    dépendance anthropic ; le RateLimiter vit ici pour brider les appels Claude."""
    if _analyst_ref['agent'] is None:
        from vertex.ai.investment_agent import InvestmentAgent
        from vertex.ai.anthropic_provider import AnthropicProvider
        _analyst_ref['agent'] = InvestmentAgent(provider=AnthropicProvider())
    return _analyst_ref['agent']


def _analyst_packet(sym, detail, resp):
    """Dossier RÉEL et complet passé à l'analyste : verdict déterministe + physique,
    Monte-Carlo, bootstrap, Kelly, MTF, anomalies — tout ce que l'app calcule déjà.
    Aucune valeur inventée : les champs absents restent None."""
    vx = detail.get('vertex') or {}
    plan = detail.get('plan') if isinstance(detail.get('plan'), dict) else {}
    resp = resp or {}
    return {
        'symbol': sym,
        'final_decision': resp.get('final_decision'),
        'decision_label': resp.get('decision_label') or resp.get('headline'),
        'blocking_rules': resp.get('blocking_rules') or [],
        'unknowns': resp.get('unknowns') or [],
        'scores': resp.get('scores') or {},
        'technical': {'score': detail.get('score'),
                      'reward_risk': vx.get('rr') or detail.get('rr'),
                      'trend': detail.get('trend'), 'structure': detail.get('structure'),
                      'setup_quality': detail.get('setup_quality'),
                      'overextended': (detail.get('ext_atr') or 0) >= 2.5,
                      'rsi': detail.get('rsi')},
        'fundamental': {'score': detail.get('st_fund') or detail.get('fund_score'),
                        'quality': vx.get('fund_quality')},
        'sector': detail.get('sector'), 'thesis': detail.get('thesis'),
        'chart_read': detail.get('chart_read'),
        'anomalies': detail.get('anomalies') or [],
        'physics': detail.get('physics') or {},
        'monte_carlo': vx.get('mc') or {}, 'bootstrap': vx.get('bootstrap') or {},
        'kelly': vx.get('kelly') or {}, 'expected_value': vx.get('ev'),
        'asymmetry': vx.get('asymmetry'), 'p_win': vx.get('p_win'),
        'risk_flags': vx.get('risk_flags') or [], 'mtf': detail.get('mtf') or {},
        'plan': {'entry': plan.get('entry'), 'stop': plan.get('stop'),
                 'target': plan.get('t1') or plan.get('target'), 'rr': plan.get('rr')},
        'price': detail.get('price'),
    }


@bp.route('/api/ai/analyst/<sym>')
def ai_analyst(sym):
    """Analyste IA : Claude INTERPRÈTE le dossier réel des moteurs déterministes
    (physique, Monte-Carlo, Kelly, MTF, anomalies) et répond à la question posée.
    Claude ne DÉCIDE jamais — le verdict reste au moteur exécutif. Sans clé →
    synthèse déterministe des moteurs, jamais de texte inventé. Lecture seule."""
    sym = (sym or '').upper().strip()
    question = (request.args.get('q') or '').strip()[:1000]
    detail = (scan_state.get('detail') or {}).get(sym) or {}
    if not detail:
        return jsonify({'available': False, 'symbol': sym,
                        'error': f'{sym} absent du scan courant — lancez un scan.'}), 200
    # Verdict déterministe (source unique du verdict) puis dossier enrichi.
    try:
        from vertex.app.routes.strategy_os_api import build_executive_decision
        _, resp = build_executive_decision(sym, scan_state)
    except Exception:
        resp = {}
    resp = resp or {}
    from vertex.ai.models import AnalysisRequest
    result = _analyst_agent().analyze(
        AnalysisRequest(symbol=sym, packet=_analyst_packet(sym, detail, resp),
                        question=question))
    # Santé honnête : n'affirme un appel réussi qu'après une vraie réponse Claude ;
    # une clé présente mais un échec est enregistré comme dégradation.
    if result.source == 'claude':
        _health.record_success()
    elif result.errors and _health.configured():
        _health.record_failure(' · '.join(str(e) for e in result.errors)[:200])
    return jsonify({
        'available': True, 'symbol': sym, 'question': question,
        'source': result.source, 'model': result.model or None,
        'content': result.content, 'errors': result.errors,
        'as_of': resp.get('as_of'),
        'decision': {'final_decision': resp.get('final_decision'),
                     'blocking_rules': resp.get('blocking_rules') or []},
        'health': _health.health(),
    })


__all__ = ['bp', 'enrich_symbols', 'start_background_enrichment']
