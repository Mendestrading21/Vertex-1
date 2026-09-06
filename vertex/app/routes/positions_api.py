"""vertex/app/routes/positions_api.py — API Position Intelligence.

Expose l'état analytique des positions (calculs, cycle de vie, thèse,
verdict, priorité), le rapport de démarrage, l'audit et les alertes.
⛔ LECTURE SEULE : aucune route ne peut passer, modifier ou clôturer un
ordre. Le desk (myTrades) reste la source déclarative ; ces routes le
LISENT et l'analysent.
"""
from __future__ import annotations

import threading
import time

from flask import Blueprint, jsonify, request

from vertex.services import persist

#: CE QUE VERTEX SAIT DE L'INVENTAIRE COURTIER : RIEN, ET PAR CONSTRUCTION.
#:
#: MESURE (6 sept. 2026, processus rejouant la configuration live : socket
#: connectée, ticks temps réel frais) :
#:
#: ```text
#: PREUVE LIVENESS  ibkr_connected=True  ibkr_live=True
#: REPORT ibkr_online = False
#: REPORT note        = IBKR hors ligne — positions locales conservées, …
#: ```
#:
#: Le même processus affirmait donc « session IBKR vivante » sur /healthz et
#: « IBKR hors ligne » ici. `ibkr_online=False` n'est pas un état de session
#: mesuré : c'est un CHOIX de produit (IBKR = données de marché uniquement).
#: Servir une absence volontaire sous la cause d'une panne réseau confond deux
#: choses que l'invariant 5 exige de distinguer, et « aucune clôture
#: automatique » laissait entendre qu'une reprise viendrait au retour d'IBKR —
#: l'invariant 3 l'interdit définitivement. La cause servie est donc nommée
#: pour ce qu'elle est ; aucune valeur ne change.
_FRONTIERE_COURTIER = {
    'broker_positions_read': False,
    'boundary': 'MARKET_DATA_ONLY',
    'note': ('Positions courtier jamais lues — frontière IBKR : données de '
             'marché uniquement. Positions déclarées conservées, aucune '
             'clôture automatique.'),
}


def make_blueprint(scan_state: dict, *, opt_job=None, ibkr_enabled=False) -> Blueprint:
    bp = Blueprint('positions_api', __name__)

    def _desk_blob():
        return persist.load_json('desk_data.json', {}) or {}

    #  Lot 2 — frontiere IBKR market-data-only : les positions du COMPTE ne
    #  sont plus lues. Chaque route passe None a load_positions/recalculate_all
    #  et la seule source de portefeuille est le desk declare. Le verrou et le
    #  memo restent pour les COTATIONS (_quotes) : coter un symbole est du
    #  marche, lire un compte n'en est pas.
    _pos_verrou = threading.Lock()
    _q_memo = {'clef': None, 'ts': 0.0, 'valeur': None}

    def _quotes(positions):
        """Cote via le worker IBKR (posq) quand disponible — sinon None."""
        if not ibkr_enabled or opt_job is None:
            return {}
        todo = []
        for p in positions:
            if p['asset_type'] == 'OPTION':
                todo.append({'sym': p['symbol'], 'exp': p.get('expiration'),
                             'strike': p.get('strike'),
                             'right': 'P' if p.get('right') == 'PUT' else 'C',
                             'key': '%s|%s|%s|%s' % (p['symbol'], p.get('expiration') or '',
                                                     p.get('strike') if p.get('strike') is not None else '',
                                                     'P' if p.get('right') == 'PUT' else 'C')})
            else:
                todo.append({'sym': p['symbol'], 'exp': '', 'strike': '', 'right': '',
                             'key': '%s||%s|' % (p['symbol'], '')})
        #  MEME politique que les positions, et pour la meme raison mesuree :
        #  `/state` et `/alerts` demandaient CHACUNE la cotation du meme
        #  panier, chacune derriere un `timeout=45` — 27 s puis 19 s sur une
        #  seule page. La cle est le panier lui-meme : deux paniers differents
        #  ne partagent jamais une reponse.
        clef = tuple(sorted(x['key'] for x in todo))
        with _pos_verrou:
            if (_q_memo['clef'] == clef and _q_memo['valeur'] is not None
                    and (time.time() - _q_memo['ts']) < _POS_TTL_S):
                return _q_memo['valeur']
        try:
            valeur = opt_job('posq', (todo,), timeout=45) or {}
        except Exception:  # noqa: BLE001
            return {}
        if valeur:
            with _pos_verrou:
                _q_memo['clef'], _q_memo['ts'], _q_memo['valeur'] = clef, time.time(), valeur
        return valeur

    @bp.route('/api/positions/state')
    def positions_state():
        """État complet recalculé de toutes les positions ouvertes."""
        from vertex.positions.recalculator import recalculate_all
        from vertex.positions.repository import load_positions
        blob = _desk_blob()
        base = load_positions(blob)
        quotes = _quotes([p for p in base if p.get('status') != 'CLOSED'])
        state = recalculate_all(scan_state, blob, quotes)
        #  `live` dit desormais : « les COTATIONS viennent du marche en
        #  direct ». Il ne dit plus rien d'un compte : il n'y en a plus.
        state['live'] = bool(ibkr_enabled)
        return jsonify(state)

    #  Lot 2 — la route de rapprochement du P&L courtier est RETIRÉE.
    #  Elle lisait le resume de compte, le P&L temps reel et le portefeuille
    #  du compte — la frontiere market-data-only l'interdit, readonly ou pas.
    #  Son hote UI (`pf-pnl-recon`) n'existait d'ailleurs dans aucune vue : la
    #  carte ne se peignait jamais. Le P&L de Vertex reste calcule sur les
    #  positions declarees, cotees par symbole via `_quotes`.

    @bp.route('/api/positions/report')
    def positions_report():
        """Startup Position Report (§6) — détection/réconciliation."""
        from vertex.positions.detector import startup_position_report
        #  Plus de lecture de compte : le rapport ne detecte plus de cloture
        #  par disparition chez le courtier. La route est PROPRIETAIRE de ce
        #  choix, donc elle en nomme la cause (cf. `_FRONTIERE_COURTIER`) au
        #  lieu de laisser servir « IBKR hors ligne », mesure contredite par
        #  le meme processus.
        rapport = startup_position_report(_desk_blob(), ibkr_online=False)
        rapport.update(_FRONTIERE_COURTIER)
        return jsonify(rapport)

    @bp.route('/api/positions/audit')
    def positions_audit():
        """Audit d'intégrité (§41) — HEALTHY/DEGRADED/CRITICAL."""
        from vertex.positions.audit import audit_positions
        from vertex.positions.repository import load_positions
        return jsonify(audit_positions(load_positions(_desk_blob())))

    @bp.route('/api/positions/reconcile')
    def positions_reconcile():
        """Réconciliation locale ↔ IBKR (§7) — DATA_REPAIR_REQUIRED explicite."""
        from vertex.positions.repository import load_positions
        from vertex.positions.reconciler import reconcile
        #  Sans lecture de compte, plus de cote courtier : la reconciliation
        #  rend l'etat honnete « courtier non lu », jamais un faux accord.
        pos = load_positions(_desk_blob())
        local = [p for p in pos if p['source'] != 'IBKR']
        rapport = reconcile(local, [], ibkr_online=False)
        rapport.update(_FRONTIERE_COURTIER)
        return jsonify(rapport)

    @bp.route('/api/portfolio/stress')
    def portfolio_stress():
        """STRESS-SCÉNARIOS du book : ±X % appliqués aux positions actions déclarées,
        valorisées au prix RÉEL du scan. Options exclues honnêtement (IBKR requis).
        Descriptif — pas une prévision, aucun ordre."""
        import json as _json
        from vertex.engines import portfolio_stress as _stress
        blob = _desk_blob()
        data = (blob or {}).get('data') or {}
        raw = data.get('myTrades')
        try:
            positions = _json.loads(raw) if isinstance(raw, str) else (raw or [])
            if not isinstance(positions, list):
                positions = []
        except Exception:
            positions = []
        detail = scan_state.get('detail') or {}
        prices = {s: (d or {}).get('price') for s, d in detail.items()}
        return jsonify(_stress.build(positions, prices))

    @bp.route('/api/portfolio/context')
    def portfolio_context_ep():
        """PORTFOLIOCONTEXT canonique (SKYLER LOT 8d) : poids par titre, HHI,
        bornes 8-15 du profil V2, plafond par titre, provenance. Positions
        déclarées du desk + cotes réelles du scan. Lecture seule, aucun ordre."""
        from vertex.engines import portfolio_context as _pc
        from vertex.positions.repository import load_positions
        pos = load_positions(_desk_blob())
        detail = scan_state.get('detail') or {}
        quotes = {s: (d or {}).get('price') for s, d in detail.items()
                  if isinstance(d, dict) and d.get('price') is not None}
        out = _pc.build(pos, quotes=quotes)
        out['as_of'] = scan_state.get('scan_ts_h') or scan_state.get('updated')
        return jsonify(out)

    @bp.route('/api/pretrade/check', methods=['POST'])
    def pretrade_check():
        """TICKET PRÉ-TRADE (le « ticket d'ordre », version analyse) : titre + montant
        envisagé → 7 contrôles réels (comité, régime, GEX, résultats, concentration
        résultante, plan, garde-fou perdants §18) et verdict DESCRIPTIF. Ne passe
        JAMAIS d'ordre — Vertex analyse, la décision reste humaine."""
        import json as _json
        from vertex.engines import pretrade as _pt
        from vertex.options import gex as _gex
        from vertex.app import payload_validation as _payload
        try:
            b = _payload.object_body(request.get_json(force=True, silent=True), max_keys=12)
            sym = _payload.required_symbol(b)
            amount = _payload.optional_number(b, 'amount')
        except _payload.PayloadError as exc:
            return jsonify({'error': str(exc)}), 400
        # verdict comité (vérité des verdicts, jamais recalculé)
        verdict = None
        for dcn in ((scan_state.get('committee') or {}).get('decisions') or []):
            if isinstance(dcn, dict) and str(dcn.get('symbol') or '').upper() == sym:
                verdict = dcn.get('verdict')
                break
        mc = scan_state.get('market_ctx') or {}
        detail = (scan_state.get('detail') or {}).get(sym) or {}
        board = scan_state.get('options_board') or []
        contracts = [c for c in board if str(c.get('sym', '')).upper() == sym]
        prof = _gex.compute(contracts, spot=detail.get('price'), symbol=sym) if contracts else {}
        blob = _desk_blob()
        raw = ((blob or {}).get('data') or {}).get('myTrades')
        try:
            positions = _json.loads(raw) if isinstance(raw, str) else (raw or [])
            if not isinstance(positions, list):
                positions = []
        except Exception:
            positions = []
        prices = {s: (d or {}).get('price') for s, d in (scan_state.get('detail') or {}).items()}
        return jsonify(_pt.build(
            sym, amount, verdict=verdict, roro=mc.get('roro'),
            gex_bias=prof.get('bias'), gex_regime=prof.get('regime'),
            earnings_in_days=detail.get('earnings_in_days'),
            positions=positions, prices_by_sym=prices,
            plan=detail.get('plan') or {}))

    @bp.route('/api/positions/alerts')
    def positions_alerts():
        """Alertes consolidées de positions (§29) — lecture seule."""
        from vertex.positions.recalculator import recalculate_all
        from vertex.positions.alerts import ALERTS
        from vertex.positions.repository import load_positions
        blob = _desk_blob()
        base = [p for p in load_positions(blob) if p.get('status') != 'CLOSED']
        state = recalculate_all(scan_state, blob, _quotes(base))
        fresh = ALERTS.evaluate(state['positions'])
        return jsonify({'new': fresh, 'active': ALERTS.active(),
                        'gamma': _gamma_events(state['positions'])})

    def _gamma_events(positions):
        """SURVEILLANCE GAMMA (descriptive, lecture seule) : pour chaque titre en
        position, signale depuis le profil GEX réel du board (a) un support de
        positionnement cassé (spot < mur put) et (b) un régime accélérateur
        (spot sous la bascule zero-gamma). Aucun état, aucun ordre — la liste
        DÉCRIT le positionnement courant ; board vide → liste vide honnête."""
        from vertex.options import gex as _gex
        board = scan_state.get('options_board') or []
        out, seen = [], set()
        for p in positions or []:
            sym = str(p.get('symbol') or '').upper()
            if not sym or sym in seen:
                continue
            seen.add(sym)
            contracts = [c for c in board if str(c.get('sym', '')).upper() == sym]
            if not contracts:
                continue
            detail = (scan_state.get('detail') or {}).get(sym) or {}
            prof = _gex.compute(contracts, spot=detail.get('price'), symbol=sym)
            if prof.get('empty') or prof.get('spot') is None:
                continue
            spot = prof['spot']
            pw, zg = prof.get('put_wall'), prof.get('zero_gamma')
            if pw is not None and spot < pw:
                out.append({'type': 'GAMMA_SUPPORT_BREAK', 'symbol': sym,
                            'spot': spot, 'put_wall': pw,
                            'detail': 'Spot sous le mur put (%s < %s) — le support de '
                                      'positionnement a cédé.' % (spot, pw)})
            # PIN RISK : spot collé au max pain (<1,5 %) avec une échéance proche (≤7 j)
            # → l'OI tend à épingler le cours vers ce niveau à l'expiration.
            mp = prof.get('max_pain')
            dtes = [c.get('dte') for c in contracts
                    if isinstance(c.get('dte'), (int, float)) and not isinstance(c.get('dte'), bool)]
            if (mp is not None and spot and dtes and min(dtes) <= 7
                    and abs(spot - mp) / spot * 100 <= 1.5):
                out.append({'type': 'GAMMA_PIN_RISK', 'symbol': sym,
                            'spot': spot, 'max_pain': mp, 'min_dte': int(min(dtes)),
                            'detail': 'Spot collé au max pain (%s ~ %s) à J-%d de la plus '
                                      'proche échéance — risque d\'épinglage (pinning) vers '
                                      'ce niveau.' % (spot, mp, int(min(dtes)))})
            if zg is not None and spot < zg:
                out.append({'type': 'GAMMA_REGIME_ACCELERATING', 'symbol': sym,
                            'spot': spot, 'zero_gamma': zg,
                            'detail': 'Spot sous la bascule zero-gamma (%s < %s) — les '
                                      'dealers amplifient les mouvements.' % (spot, zg)})
        return out

    @bp.route('/api/positions/<position_id>/changes')
    def position_changes(position_id):
        """« Ce qui a changé » (§27) pour une position — depuis le dernier snapshot."""
        from vertex.positions.recalculator import recalculate_all
        from vertex.positions.change_detector import diff
        blob = _desk_blob()
        from vertex.positions.repository import load_positions
        base = [p for p in load_positions(blob) if p.get('status') != 'CLOSED']
        state = recalculate_all(scan_state, blob, _quotes(base))
        cur = next((p for p in state['positions'] if p['position_id'] == position_id), None)
        if not cur:
            return jsonify({'error': 'position introuvable', 'changed': False}), 200
        prev = persist.load_json('position_snap_%s.json' %
                                 position_id.replace('|', '_').replace(':', '_'), None)
        d = diff(prev, cur)
        try:
            persist.save_json('position_snap_%s.json' %
                              position_id.replace('|', '_').replace(':', '_'), cur)
        except Exception:
            pass
        return jsonify(d)

    return bp


__all__ = ['make_blueprint']
