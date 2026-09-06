"""vertex/app/routes/options_intel_api.py — API Options Intelligence (§18).

Expose la synthèse de l'espace /options : vue d'ensemble, volatilité par
sous-jacent, risque d'événement, et l'interprétation canonique des graphiques.
⛔ LECTURE SEULE : aucune route ne passe/modifie/clôture d'ordre. Les données
proviennent du scan (options_board) et des mesures pures — champ absent → None,
jamais de chiffre inventé.
"""
from __future__ import annotations

import datetime as _dt

from flask import Blueprint, jsonify, request

from vertex.app.config import DEMO_MODE, IBKR_ENABLED
from vertex.app.state import scan_state
from vertex.options import overview as _ov
from vertex.options import interpretation as _oi
#: Strikes dont l'IV n'a pas pu etre recalculee (bornee, lecture seule).
_IV_NON_RECALCULEE: list = []

from vertex.options import chaine_a_la_demande as _chaine
from vertex.options import entrees_mesurees as _entrees
from vertex.options import chaine_a_la_demande as _chaine

bp = Blueprint('options_intel_api', __name__)


def _board():
    return scan_state.get('options_board') or []


def _board_for(sym):
    """Board ∪ chaîne à la demande pour `sym` — un titre pas encore couvert par la
    rotation obtient quand même son dossier options (IBKR si TWS ouvert, sinon
    yfinance). NON BLOQUANT : `on_demand.board_with` tirait la chaîne dans la
    requête (plusieurs secondes sur un titre froid) ; la collecte part en fond
    et le premier passage rend « pas encore » (voir `_board_pour`)."""
    return _board_pour(sym)[0]
def _board_pour(sym):
    """Le board VU DEPUIS un titre : ses contrats, complétés si besoin.

    Le board couvre l'univers par rotation IBKR ; entre deux passages, un titre
    consulté peut n'y être pour rien, et toutes ses cartes options restent vides
    sans qu'on sache si le titre n'a pas d'options ou si le board ne l'a pas
    encore vu.

    `vertex-live` comblait ce trou en appelant `warm_chain` EN SYNCHRONE dans la
    route — c'est-à-dire en rétablissant le défaut P0.1, mesuré à 28-48 s. Ici la
    chaîne est chargée EN FOND : la page rend la main tout de suite, et l'état
    dit si un chargement est en cours.
    """
    return _chaine.board_avec(sym, _board())


def _as_of():
    return scan_state.get('scan_ts_h') or scan_state.get('updated')


def _ts_epoch():
    """Époque (s) des données options servies : board d'abord (options_as_of),
    repli scan. `_as_of()` rend un LIBELLÉ humain — illisible pour un âge
    vivant côté client ; celle-ci porte le nombre."""
    return scan_state.get('options_as_of') or scan_state.get('scan_ts')


def _detail_by_sym():
    return scan_state.get('detail') or {}


@bp.route('/api/options/overview')
def options_overview():
    """Vue d'ensemble : compteurs, radar, environnement, pulses, interprétation."""
    try:
        return jsonify(_ov.summarize(_board(), as_of=_as_of(),
                                     demo=bool(DEMO_MODE), source='SCAN',
                                     detail_by_sym=_detail_by_sym()))
    except Exception as e:
        return jsonify({'empty': True, 'error': 'options_overview_unavailable'}), 500


@bp.route('/api/options/environment')
def options_environment():
    """Score LONG OPTION ENVIRONMENT (§14) — dimensions + verdict canonique."""
    from vertex.options.environment import score_environment
    try:
        return jsonify(score_environment(_board(), detail_by_sym=_detail_by_sym(),
                                         as_of=_as_of(), source='SCAN'))
    except Exception as e:
        return jsonify({'score': None, 'label': 'INCONNU',
                        'error': 'options_environment_unavailable'}), 500


@bp.route('/api/options/chain/<sym>')
def options_chain(sym):
    """Chaîne d'un titre : contrats du board ∪ fetch à la demande si absent.
    Le dossier /options/<sym> (scorecard + chaîne) lit ICI plutôt que de filtrer
    /scan côté client — un titre pas encore couvert par la rotation obtient
    quand même sa chaîne (IBKR si TWS ouvert, repli yfinance)."""
    sym = (sym or '').upper()[:12]
    board, meta = _board_pour(sym)
    contracts = [c for c in board if str(c.get('sym', '')).upper() == sym]
    detail = (scan_state.get('detail') or {}).get(sym) or {}
    spot = detail.get('price')
    if spot is None:
        spot = next((c.get('spot') for c in contracts if c.get('spot') is not None), None)
    on_demand = bool(contracts) and not any(
        str(c.get('sym', '')).upper() == sym
        for c in (scan_state.get('options_board') or []))
    #  « aucun contrat » ≠ « ce titre n'a pas d'options » : la chaîne peut être
    #  en cours de chargement en fond — dit à la page, qui réessaie.
    charge = (not contracts) and _chaine.en_cours(meta)
    return jsonify({'symbol': sym, 'spot': spot, 'contracts': contracts,
                    'on_demand': on_demand, 'as_of': _as_of(),
                    'en_cours': charge, 'retry_s': 8 if charge else None,
                    'source': (scan_state.get('options_source') or 'SCAN')})


# ── Lot 5a : cache des vues re-dérivées (grille / surface / max-pain) ──────────
# Ces vues se recalculent à CHAQUE requête depuis la même chaîne large STATIQUE
# (scan_state['options_chain_full'][sym]), qui ne change qu'à chaque warm (~15 min,
# stamp `ts`). On mémoïse le résultat réussi par (vue, sym) tant que `ts` est inchangé
# → byte-identique (même entrée figée → même sortie). Le vide n'est pas caché (retry).
_VIEW_MISS = object()


def _view_get(kind, sym, ts):
    hit = scan_state.setdefault('options_view_cache', {}).get((kind, str(sym).upper()))
    return hit[1] if (hit is not None and hit[0] == ts) else _VIEW_MISS


def _view_put(kind, sym, ts, val):
    scan_state.setdefault('options_view_cache', {})[(kind, str(sym).upper())] = (ts, val)
    return val


#: Ce qui remplit `scan_state['options_chain_full']`, mesuré et non supposé :
#: `terminal.py::_IbkrChainSide._df` (branche courtier) et `demo.demo_chain_full`
#: (mode démonstration). Aucun autre écrivain dans le dépôt — donc, source
#: coupée, la chaîne large n'arrivera JAMAIS, et le dire est une mesure.
_SOURCE_CHAINE_LARGE = 'IBKR (données de marché, lecture seule)'


def _absence_chaine_large(sym, quoi, etat):
    """Pourquoi la chaîne large manque — MESURÉ, jamais supposé.

    ## Le défaut, mesuré le 2026-09-06

    Trois routes — `/api/options/max-pain/<sym>`, `/api/options/chain-grid/<sym>`
    et `/api/options/surface/<sym>` — servaient une phrase FIXE :

    ```json
    {"available": false,
     "note": "Chaîne large indisponible (TWS fermé, hors séance, ou titre pas
              encore chargé)."}
    ```

    Aucune de ces trois causes n'était mesurée. Relevé sur l'instance de test
    (`NO_IBKR=1`, `DEMO=0`) : `IBKR_ENABLED` valait **False** — la source de la
    chaîne large était coupée par la configuration, TWS n'a jamais été
    contacté, et la séance n'a jamais été consultée. La réponse affirmait donc
    trois causes dont **aucune** n'était la bonne, et l'écran les répétait mot
    pour mot (`options-symbol.js` rend `d.note` tel quel).

    Pire : `_chaine.prechauffer(sym)` RENVOIE l'état de la collecte — sa
    docstring dit explicitement « rend l'état, pour que l'appelant puisse le
    joindre à sa réponse au lieu d'avaler l'échec » — et les trois routes
    jetaient cette valeur de retour. Mesuré, deux appels successifs sur AAPL :
    `{'etat': 'MISSING', 'chargement_en_cours': True}` puis
    `{'etat': 'LIVE', 'chargement_en_cours': False}`. Deux états distincts,
    tous deux racontés par la même phrase.

    ## Ce que cette fonction sert

    Cinq motifs EXCLUSIFS, chacun adossé à une mesure, du plus définitif au
    plus circonstanciel : une source désactivée (rien n'arrivera, et c'est la
    configuration du processus qui le dit), une collecte en cours (réessayer),
    une persistance qui a échoué (`scan_state['chaine_non_persistee']`, posé
    par le monolithe et lu par personne jusqu'ici), aucune chaîne large jamais
    enregistrée dans ce processus (l'absence n'est alors PAS une mesure sur ce
    titre), ou une collecte aboutie ailleurs mais sans contrat pour ce titre.

    `available` et `note` restent en place : `options-symbol.js` les lit, et un
    aveu plus honnête ne doit pas casser l'écran qu'il corrige.

    ⛔ Le texte d'exception ne traverse PAS la frontière HTTP : `Meta.erreur`
    (`snapshot.py`) et `chaine_non_persistee['erreur']` portent tous deux
    `'%s: %s' % (type(exc).__name__, exc)`. On sert le FAIT de l'échec, jamais
    sa formulation Python.
    """
    sym = str(sym or '').upper()
    etat = etat or {}
    en_cours = bool(etat.get('chargement_en_cours'))
    #  La SOURCE d'abord — `chargement_en_cours` ne mesure PAS la chaîne large.
    #
    #  `prechauffer` rend l'état du magasin d'instantanés du board ÉTROIT
    #  (`on_demand.fetch` → `legacy_engine.best_for_symbol`). Ce chargement-là
    #  ne remplit `options_chain_full` que par un seul chemin : `terminal.py`
    #  substitue `legacy_engine.yf` par la passerelle IBKR (`terminal.py:1571`),
    #  dont `option_chain` persiste la chaîne large. Source coupée, la collecte
    #  de fond passe par yfinance et n'écrira JAMAIS `options_chain_full`.
    #
    #  MESURE du 2026-09-06 sur l'instance de contrôle (5003, `NO_IBKR=1`),
    #  premier appel sur trois titres froids — ZTS, PAYX, CDW :
    #  `raison: CHARGEMENT_EN_COURS`, `retry_s: 8`, « rechargez dans quelques
    #  secondes », et dans LA MÊME charge `source_activee: false`. Une charge
    #  qui se contredit, et une invitation à réessayer que rien ne peut
    #  satisfaire — exactement la cause inventée que cette fonction remplace,
    #  revenue par l'ordre des branches. La configuration est mesurée et
    #  définitive : elle passe devant.
    source_coupee = not IBKR_ENABLED and not DEMO_MODE
    echec_persistance = (scan_state.get('chaine_non_persistee') or {}).get(sym)
    if source_coupee:
        raison = 'SOURCE_DESACTIVEE'
        note = ('%s : la chaîne large vient de %s, désactivée dans cette '
                'configuration — aucune collecte de chaîne large n’a été '
                'tentée, et aucune n’aboutira tant qu’elle le reste.'
                % (quoi, _SOURCE_CHAINE_LARGE))
    elif en_cours:
        raison = 'CHARGEMENT_EN_COURS'
        note = ('%s : la chaîne large de %s est en cours de collecte — '
                'rechargez dans quelques secondes.' % (quoi, sym))
    elif echec_persistance:
        raison = 'PERSISTANCE_ECHOUEE'
        note = ('%s : la chaîne large de %s a été reçue mais n’a pas pu être '
                'enregistrée (échéance %s, côté %s) — motif au journal serveur.'
                % (quoi, sym, echec_persistance.get('echeance') or '?',
                   echec_persistance.get('cote') or '?'))
    elif etat.get('erreur'):
        raison = 'COLLECTE_EN_ERREUR'
        note = ('%s : la dernière collecte de la chaîne de %s a échoué — '
                'motif au journal serveur, rien n’est estimé.' % (quoi, sym))
    elif not (scan_state.get('options_chain_full') or {}):
        #  Même discrimination que `entrees_statut` sur `/api/options/
        #  event-risk` — « personne ne l'a » et « les autres l'ont, pas
        #  celui-ci » sont deux états, et l'un des deux seulement autorise à
        #  conclure sur CE titre. MESURE : source active mais
        #  `options_chain_full` absent de `scan_state` (démarrage à froid,
        #  avant la première rotation), la branche suivante affirmait « la
        #  collecte de la chaîne large de AAPL A ABOUTI sans aucun contrat »
        #  alors qu'aucune collecte n'avait encore rien enregistré, pour aucun
        #  titre. Un chiffre absent était présenté comme un résultat.
        raison = 'AUCUNE_COLLECTE_ENREGISTREE'
        note = ('%s : aucune chaîne large n’a encore été enregistrée dans ce '
                'processus — ni pour %s ni pour un autre titre. L’absence '
                'n’est donc pas une mesure sur %s.' % (quoi, sym, sym))
    else:
        raison = 'AUCUN_CONTRAT_COLLECTE'
        note = ('%s : la collecte de la chaîne large a abouti pour d’autres '
                'titres mais n’a rendu aucun contrat pour %s. Ce titre n’est '
                'pas couvert par la rotation, ou n’a pas de chaîne '
                'exploitable.' % (quoi, sym))
    return jsonify({
        'symbol': sym, 'available': False,
        'raison': raison, 'note': note,
        'chargement_en_cours': en_cours,
        #  Réessayer n'a de sens que si quelque chose peut arriver : la source
        #  coupée, `retry_s` promettait 8 s pour une chaîne qui n'arrivera pas.
        'retry_s': 8 if (en_cours and not source_coupee) else None,
        'source_chaine_large': _SOURCE_CHAINE_LARGE,
        'source_activee': bool(IBKR_ENABLED or DEMO_MODE),
        'collecte_en_erreur': bool(etat.get('erreur') or echec_persistance),
        'as_of': _as_of(), 'ts': _ts_epoch(),
        'read_only': True,
    })


def _max_pain(sym):
    """Max pain + murs d'OI + PCR RÉELS depuis la chaîne LARGE persistée
    (scan_state['options_chain_full'], remplie par le worker IBKR). None honnête sinon."""
    e = (scan_state.get('options_chain_full') or {}).get(str(sym).upper())
    if not e:
        return None
    _vts = e.get('ts')
    _vc = _view_get('maxpain', sym, _vts)
    if _vc is not _VIEW_MISS:
        return _vc
    exps = [k for k in e if k not in ('spot', 'ts')]
    spot = e.get('spot') or 0
    out = []
    for exp in sorted(exps):
        calls = (e[exp] or {}).get('C') or {}
        puts = (e[exp] or {}).get('P') or {}
        strikes = sorted(set(calls) | set(puts))
        if len(strikes) < 3:
            continue
        # DAT-01 : l'OI persisté peut être None (absent) ≠ 0 (vrai zéro). _oi conserve la
        # valeur honnête (affichage → « — » si None) ; _oin la coerce à 0 pour les CALCULS.
        def _oi(side, k):
            return (side.get(k) or {}).get('oi')

        def _oin(side, k):
            return _oi(side, k) or 0
        best_k, best_pay = None, None
        for K in strikes:                     # payoff total aux détenteurs si règlement = K
            pay = sum(_oin(calls, k) * max(0.0, K - k) for k in strikes) \
                + sum(_oin(puts, k) * max(0.0, k - K) for k in strikes)
            if best_pay is None or pay < best_pay:   # max pain = K qui MINIMISE le payoff
                best_pay, best_k = pay, K
        call_oi = sum((v.get('oi') or 0) for v in calls.values())
        put_oi = sum((v.get('oi') or 0) for v in puts.values())
        walls = sorted(({'strike': k, 'call_oi': _oi(calls, k), 'put_oi': _oi(puts, k),
                         'oi': _oin(calls, k) + _oin(puts, k)}
                        for k in strikes), key=lambda w: -w['oi'])[:5]
        out.append({'exp': exp, 'max_pain': best_k, 'call_oi': call_oi, 'put_oi': put_oi,
                    'pcr': round(put_oi / call_oi, 2) if call_oi else None, 'walls': walls,
                    'by_strike': [{'strike': k, 'call_oi': _oi(calls, k),
                                   'put_oi': _oi(puts, k)} for k in strikes]})
    if not out:
        return None
    tc = sum(x['call_oi'] for x in out)
    tp = sum(x['put_oi'] for x in out)
    return _view_put('maxpain', sym, _vts, {'symbol': str(sym).upper(), 'spot': spot, 'ts': e.get('ts'),
            'total_call_oi': tc, 'total_put_oi': tp,
            'pcr': round(tp / tc, 2) if tc else None, 'expiries': out})


@bp.route('/api/options/max-pain/<sym>')
def options_max_pain(sym):
    """Max pain / murs d'OI / PCR sur la chaîne LARGE réelle (IBKR). Déclenche un
    fetch on-demand (qui persiste la chaîne via le worker) puis calcule. L'absence
    est NOMMÉE par une mesure — voir `_absence_chaine_large` — jamais inventée."""
    sym = (sym or '').upper()[:12]
    #  NON bloquant : la collecte part en fond (defaut P0.1, 28-48 s). La valeur
    #  de retour est CONSERVEE : c'est la seule mesure de l'etat de collecte.
    etat = _chaine.prechauffer(sym)
    mp = _max_pain(sym)
    if mp is None:
        return _absence_chaine_large(sym, 'Open interest par strike', etat)
    mp['available'] = True
    return jsonify(mp)


def _dte_from_exp(exp):
    """Jours jusqu'à échéance depuis une clé d'expiration (YYYYMMDD ou ISO). None honnête."""
    s = str(exp).replace('-', '').replace('T00:00:00', '')[:8]
    try:
        d = _dt.datetime.strptime(s, '%Y%m%d').date()
        return max(0, (d - _dt.date.today()).days)
    except (ValueError, TypeError):
        return None


def _chain_grid(sym):
    """Grille strikes × échéances (call/put par strike) depuis la chaîne LARGE
    persistée. Chaque cellule : iv (fraction), Δ/Γ/Θ/V, oi, vol, bid/ask. None honnête."""
    e = (scan_state.get('options_chain_full') or {}).get(str(sym).upper())
    if not e:
        return None
    _vts = e.get('ts')
    _vc = _view_get('grid', sym, _vts)
    if _vc is not _VIEW_MISS:
        return _vc
    spot = e.get('spot') or 0
    exps = sorted(k for k in e if k not in ('spot', 'ts'))
    greeks_src = 'none'
    out_exps = []
    for exp in exps:
        calls = (e[exp] or {}).get('C') or {}
        puts = (e[exp] or {}).get('P') or {}
        strikes = sorted(set(calls) | set(puts))
        if len(strikes) < 2:
            continue
        rows = []
        for K in strikes:
            c = calls.get(K)
            p = puts.get(K)
            if (c and c.get('delta') is not None) or (p and p.get('delta') is not None):
                greeks_src = 'broker'
            rows.append({'strike': K, 'call': c or None, 'put': p or None})
        out_exps.append({'exp': exp, 'dte': _dte_from_exp(exp), 'strikes': rows})
    if not out_exps:
        return None
    return _view_put('grid', sym, _vts, {'symbol': str(sym).upper(), 'spot': spot, 'ts': e.get('ts'),
            'source': ('DÉMO' if DEMO_MODE else 'courtier IBKR'),
            'greeks_source': ('demo' if DEMO_MODE else greeks_src),
            'expiries': out_exps})


@bp.route('/api/options/chain-grid/<sym>')
def options_chain_grid(sym):
    """Grille de chaîne (strikes × échéances) RÉELLE depuis la chaîne large IBKR
    (greeks courtier). Déclenche un fetch on-demand puis sérialise. L'absence est
    NOMMÉE par une mesure — voir `_absence_chaine_large`. En DÉMO : chaîne
    synthétique clairement étiquetée."""
    sym = (sym or '').upper()[:12]
    #  NON bloquant : la collecte part en fond (defaut P0.1, 28-48 s).
    etat = _chaine.prechauffer(sym)
    g = _chain_grid(sym)
    if g is None:
        return _absence_chaine_large(sym, 'Grille de chaîne', etat)
    g['available'] = True
    return jsonify(g)


def _surface(sym):
    """Surface d'IV (strike × échéance) + skew + term structure depuis la chaîne
    LARGE (iv en fraction, filtrée <=5 par build_surface). None honnête si vide."""
    from vertex.options.vol_surface import build_surface
    e = (scan_state.get('options_chain_full') or {}).get(str(sym).upper())
    if not e:
        return None
    _vts = e.get('ts')
    _vc = _view_get('surface', sym, _vts)
    if _vc is not _VIEW_MISS:
        return _vc
    spot = e.get('spot') or 0
    contracts = []
    for exp in e:
        if exp in ('spot', 'ts'):
            continue
        dte = _dte_from_exp(exp)
        for right in ('C', 'P'):
            for K, cell in (((e[exp] or {}).get(right)) or {}).items():
                iv = (cell or {}).get('iv')
                if iv is None:
                    continue
                contracts.append({'expiry': exp, 'dte': dte, 'strike': float(K),
                                  'right': right, 'iv': float(iv)})
    if not contracts or not spot:
        return None
    detail = (scan_state.get('detail') or {}).get(str(sym).upper()) or {}
    closes = detail.get('closes') or detail.get('history') or None
    surf = build_surface(str(sym).upper(), float(spot), contracts, closes=closes, as_of=_as_of())
    d = surf.to_dict()
    if not d.get('by_expiry'):
        return None
    d['available'] = True
    d['source'] = ('DÉMO' if DEMO_MODE else 'courtier IBKR')
    return _view_put('surface', sym, _vts, d)


@bp.route('/api/options/surface/<sym>')
def options_surface(sym):
    """Surface de volatilité (strike × échéance) + skew + structure par terme sur
    la chaîne large réelle. L'absence est NOMMÉE par une mesure — voir
    `_absence_chaine_large`."""
    sym = (sym or '').upper()[:12]
    #  NON bloquant : la collecte part en fond (defaut P0.1, 28-48 s).
    etat = _chaine.prechauffer(sym)
    s = _surface(sym)
    if s is None:
        return _absence_chaine_large(sym, 'Surface de volatilité', etat)
    return jsonify(s)


@bp.route('/api/options/volatility/<sym>')
def options_volatility(sym):
    """Interprétation de la volatilité d'un sous-jacent (depuis le board/detail)."""
    sym = (sym or '').upper()[:12]
    board = _board_for(sym)
    contracts = [c for c in board if str(c.get('sym', '')).upper() == sym]
    detail = (scan_state.get('detail') or {}).get(sym) or {}
    # IV courante = médiane des IV du board pour ce titre (en fraction)
    ivs = sorted(c.get('iv') / 100.0 for c in contracts
                 if isinstance(c.get('iv'), (int, float)))
    cur_iv = ivs[len(ivs) // 2] if ivs else None
    #  AUCUN COULOIR : `volatility.iv_rank` définit son couloir [low, high] SUR
    #  52 SEMAINES. Passer min/max des IV du board revenait à lui donner
    #  l'étendue TRANSVERSALE de quelques strikes au même instant — un artefact
    #  de structure par terme / skew servi comme un IV rank historique. Mesuré
    #  le 2026-09-06 : NVDA 3 contrats (36,0 / 41,5 / 42,7 %) →
    #  (0,415-0,36)/(0,427-0,36) = « IV rank 82 » et verdict DEFAVORABLE ;
    #  MSFT 2 contrats (33,0 et 32,7 %, écart 0,3 pt) → « IV rank 100 » par
    #  construction (avec n=2 la médiane EST le max : 0 exception sur 1000
    #  tirages), régime « ELEVEE », confiance 0,6, incertitudes vides. La carte
    #  Environnement déclarait au même as_of « IV rank — non mesuré ».
    #  Sans source d'historique d'IV câblée, l'absence se nomme :
    #  `interpretation.interpret_volatility` rend déjà unknown('IV
    #  rank/percentile indisponibles') quand rank et pctl manquent.
    iv_low = iv_high = None
    # Série CANONIQUE du scan (LOT 4) — les formes legacy 'closes'/'history'
    # n'avaient aucun producteur et ne sont plus admises.
    from vertex.data import series as _series
    closes, _closes_src = _series.closes(detail)
    closes = closes or None
    d = _oi.interpret_volatility(sym, current_iv=cur_iv, iv_low=iv_low,
                                 iv_high=iv_high, closes=closes,
                                 source='SCAN', as_of=_as_of())
    return jsonify({'symbol': sym, 'contracts': len(contracts),
                    'current_iv': cur_iv,
                    'iv_rank': None,
                    'iv_rank_note': ('IV rank NON MESURÉ : aucune série d’IV historique n’est '
                                     'câblée ici. L’étendue des IV du tableau décrit la structure '
                                     'par terme et le skew du jour, pas un couloir 52 semaines.'),
                    'interpretation': d})


@bp.route('/api/options/scenarios/<sym>')
def options_scenarios(sym):
    """Scénarios multi-facteurs (§19) du meilleur contrat d'un titre : spot ×
    temps × IV via scenario_pricer. ESTIMATION Black-Scholes clairement étiquetée."""
    from vertex.options import scenario_pricer
    from vertex.options.models import UnderlyingSetup
    sym = (sym or '').upper()[:12]
    contracts = sorted([c for c in _board_for(sym)
                        if str(c.get('sym', '')).upper() == sym and c.get('quality') is not None],
                       key=lambda c: c.get('quality', 0), reverse=True)
    if not contracts:
        return jsonify({'symbol': sym, 'empty': True,
                        'reason': 'aucun contrat pour ce titre dans le tableau'}), 200
    c = contracts[0]
    detail = (scan_state.get('detail') or {}).get(sym) or {}
    plan = detail.get('plan') or {}
    spot = _num(c.get('spot')) or _num(detail.get('price'))
    if not spot or spot <= 0:
        return jsonify({'symbol': sym, 'empty': True,
                        'reason': 'spot indisponible — simulation refusée (aucune donnée inventée)'}), 200
    try:
        dte_raw = float(c.get('dte'))
        dte = int(dte_raw) if dte_raw >= 0 and dte_raw.is_integer() else None
    except (TypeError, ValueError):
        dte = None
    if dte is None:
        return jsonify({'symbol': sym, 'empty': True,
                        'reason': 'dte indisponible ou invalide — simulation refusée (aucune échéance inventée)',
                        'input_coverage': {'dte_available': False,
                                           'status': 'DTE_UNAVAILABLE',
                                           'read_only': True}}), 200
    iv = c.get('iv')
    contract = {'symbol': sym, 'right': 'P' if c.get('type') == 'PUT' else 'C',
                'strike': _num(c.get('strike')), 'dte': dte,
                'mid': ((_num(c.get('cost')) or 0) / 100.0 if _num(c.get('cost')) else None),
                'iv': (iv / 100.0 if isinstance(iv, (int, float)) and iv > 3 else iv),
                'expiry': c.get('exp') or ''}
    #  Entrees MESUREES, pas des constantes : la courbe et le rendement sont
    #  deja collectes et en memoire. Voir `options/entrees_mesurees`.
    setup = UnderlyingSetup(symbol=sym, spot=spot, invalidation=plan.get('stop'),
                            tp1=plan.get('tp1'), tp2=plan.get('tp2'), tp3=plan.get('tp3'),
                            dividend_yield=(_entrees.rendement_dividende(scan_state, sym) or 0.0))
    try:
        sim = scenario_pricer.simulate(contract, setup,
                                       rate_curve=_entrees.courbe(scan_state))
        sim['entrees'] = _entrees.provenance(scan_state, sym)
    except Exception as e:
        return jsonify({'symbol': sym, 'empty': True,
                        'reason': 'simulation_indisponible'}), 200
    return jsonify({'symbol': sym, 'empty': False, 'contract': {
        'type': c.get('type'), 'strike': c.get('strike'), 'dte': c.get('dte'),
        'exp': c.get('exp'), 'iv': iv, 'cost': c.get('cost'), 'spot': spot,
    }, 'sim': sim, 'as_of': _as_of(), 'ts': _ts_epoch()})


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


@bp.route('/api/options/gex-radar')
def options_gex_radar():
    """RADAR de positionnement : GEX de tous les sous-jacents du board, classés
    par |net GEX|. « Où les dealers poussent-ils le plus fort ? » Lecture seule."""
    from vertex.options import gex_scan as _gs
    try:
        d = _gs.scan(_board(), _detail_by_sym(), top=30)
        d['as_of'] = _as_of()
        d['demo'] = bool(DEMO_MODE)
        return jsonify(d)
    except Exception as e:
        return jsonify({'empty': True, 'rows': [],
                        'error': 'options_gex_radar_unavailable'}), 500


@bp.route('/api/options/gex/<sym>')
def options_gex(sym):
    """Positionnement dealer d'un sous-jacent : profil GEX + flux notable + thèse.
    Données réelles du board (OI/gamma/volume) — jamais inventées. Vue FENÊTRÉE :
    le board ne retient que les strikes du scan (±35 % du spot), pas la chaîne
    entière — signalé honnêtement au client. Lecture seule, aucun ordre."""
    from vertex.options import gex as _gex, flow as _flow, dealer_synthesis as _ds
    sym = (sym or '').upper()[:12]
    board = _board()
    contracts = [c for c in board if str(c.get('sym', '')).upper() == sym]
    detail = (scan_state.get('detail') or {}).get(sym) or {}
    spot = None
    for c in contracts:
        spot = _num(c.get('spot'))
        if spot:
            break
    if not spot:
        spot = _num(detail.get('price'))
    # Move attendu du cycle : médiane des em_pct RÉELS des contrats (jamais inventé).
    ems = sorted(_num(c.get('em_pct')) for c in contracts
                 if _num(c.get('em_pct')) is not None)
    em_pct = ems[len(ems) // 2] if ems else None
    try:
        profile = _gex.compute(contracts, spot=spot, symbol=sym)
        flow = _flow.analyze(contracts, symbol=sym)
        synth = _ds.build(profile, flow,
                          earnings_in_days=detail.get('earnings_in_days'),
                          symbol=sym, em_pct=em_pct)
    except Exception as e:
        return jsonify({'symbol': sym, 'empty': True,
                        'error': 'options_gex_unavailable'}), 500
    # Journal quotidien du GEX (best-effort, réel seulement) → série « Daily GEX ».
    history = []
    history_availability = {
        'available': False,
        'status': 'GEX_HISTORY_UNAVAILABLE',
        'points_loaded': 0,
        'read_only': True,
        'reason': 'historique GEX indisponible ; une série vide ne signifie pas absence d’observation historique',
    }
    try:
        from vertex.options import gex_history as _gh
        _gh.record(profile)
        history = _gh.series(sym)
        history_availability = {
            'available': True,
            'status': 'GEX_HISTORY_AVAILABLE',
            'points_loaded': len(history) if isinstance(history, list) else 0,
            'read_only': True,
        }
    except Exception:
        pass
    return jsonify({
        'symbol': sym, 'as_of': _as_of(), 'demo': bool(DEMO_MODE),
        'contracts_available': len(contracts),
        'coverage': 'fenêtre du scan (strikes ±35 % du spot) — pas la chaîne complète',
        'gex': profile, 'flow': flow, 'synthesis': synth, 'history': history,
        'history_availability': history_availability,
    })
def _wide_contracts(sym):
    """Chaîne LARGE persistée (options_chain_full) → contrats au format board
    (sym/strike/type/dte/iv/oi/spot). Alimente les graphes de volatilité (OI par
    strike, smile, structure par terme, cône) avec les VRAIES données — OI réel,
    PUTS, 15 strikes/côté, 3 échéances — au lieu du board « finalistes » (souvent
    calls-only, OI=0, spot absent). [] si la chaîne large n'est pas chargée."""
    e = (scan_state.get('options_chain_full') or {}).get(str(sym).upper())
    if not e:
        return []
    from vertex.options import legacy_engine as _le
    spot = e.get('spot')
    out = []
    for exp in e:
        if exp in ('spot', 'ts'):
            continue
        dte = _dte_from_exp(exp)
        T = (dte / 365.0) if dte else None
        for right, side in (e.get(exp) or {}).items():
            typ = 'CALL' if right == 'C' else 'PUT'
            for k, row in (side or {}).items():
                iv = row.get('iv')
                # IBKR sans greeks OU IV aberrante (stale de clôture : <1 % ou >300 %) →
                # IV RECALCULÉE en Black-Scholes depuis le mid RÉEL (bid/ask persistés)
                # → smile / surface / verdict corrects. None honnête si non calculable.
                if not (iv and 0.01 <= iv <= 3.0):
                    iv = None
                    if T and spot:
                        bid, ask, last = row.get('bid'), row.get('ask'), row.get('last')
                        mid = (round((bid + ask) / 2.0, 2) if (bid and ask) else last)
                        if mid:
                            try:
                                _civ = _le._iv_from_price(spot, k, T, mid, right == 'C')
                                if _civ and 0.01 <= _civ <= 3.0:
                                    iv = _civ
                            except Exception as _e:
                                #  D-100 : l'IV est une ENTREE de prix. Un echec
                                #  qui laisse l'ancienne valeur melange deux
                                #  origines dans la meme surface — on le compte.
                                _IV_NON_RECALCULEE.append(
                                    {'strike': k, 'cote': right, 'erreur': str(_e)[:120]})
                                del _IV_NON_RECALCULEE[:-50]
                out.append({'sym': str(sym).upper(), 'strike': k, 'type': typ,
                            'dte': dte, 'iv': iv, 'oi': row.get('oi'),
                            'delta': row.get('delta'), 'spot': spot})
    return out


@bp.route('/api/options/vol-charts/<sym>')
def options_vol_charts(sym):
    """Jeux de données pour les graphiques de volatilité d'un titre (§15).
    Priorité à la chaîne LARGE réelle (OI/puts/strikes) ; repli sur le board."""
    from vertex.options import vol_charts
    sym = (sym or '').upper()[:12]
    expiry_raw = request.args.get('dte')
    expiry = None
    if expiry_raw is not None:
        try:
            expiry_number = float(expiry_raw)
            expiry = int(expiry_number) if expiry_number >= 0 and expiry_number.is_integer() else None
        except (TypeError, ValueError):
            expiry = None
        if expiry is None:
            return jsonify({'symbol': sym, 'empty': True,
                            'error': 'options_vol_charts_invalid_dte',
                            'input_coverage': {'dte_parameter_available': False,
                                               'status': 'DTE_PARAMETER_INVALID',
                                               'read_only': True}}), 400
    #  NON bloquant : la collecte part en fond (defaut P0.1, 28-48 s).
    _chaine.prechauffer(sym)
    try:
        wide = _wide_contracts(sym)
        board = wide if wide else _board_for(sym)
        src = 'chaîne large IBKR' if wide else 'SCAN'
        payload = vol_charts.build(board, sym, as_of=_as_of(),
                                   source=src, expiry=expiry)
        payload['ts'] = _ts_epoch()   # époque serveur pour l'âge des 4 cartes
        return jsonify(payload)
    except Exception as e:
        return jsonify({'symbol': sym, 'empty': True,
                        'error': 'options_vol_charts_unavailable'}), 500


@bp.route('/api/options/event-risk/<sym>')
def options_event_risk(sym):
    """Risque d'événement pour le meilleur contrat d'un titre.

    ## Deux des quatre entrées n'ont AUCUN producteur — mesuré, pas supposé

    La route lit `detail['earnings_in_days']` et `detail['ex_dividend_days']`.
    Relevé le 2026-09-06 sur une charge `/scan` RÉELLE (513 titres, capturée
    sur l'instance de contrôle) : une entrée de `detail` porte 66 clés, et
    **aucune** des 513 ne porte l'une de ces deux-là — la seule clé contenant
    « div » est `rsi_div`. Balayage du dépôt : aucun écrivain non plus, ni dans
    `terminal.py`, ni dans `vertex/`.

    Conséquence : `interpret_event_risk` recevait `None` sur les deux dates à
    **chaque** appel, rendait `status: 'INCONNU'` et l'incertitude « Dates
    d'événement inconnues » — une phrase qui se lit comme « on a regardé le
    calendrier et il est vide », alors que le calendrier n'a jamais été lu. Une
    entrée non câblée et une absence mesurée sont deux états distincts
    (invariants 4 et 6) ; seul le second autorise « inconnu ».

    Ce qui change ici : la route DIT lesquelles de ses entrées existent, sans
    toucher au moteur d'interprétation ni inventer de date. Elle ne branche
    volontairement pas `cal_state` : la seule source d'échéances disponible
    (`cal_cache.json`) donne la MÊME date à AAPL, NVDA, MSFT, META, GOOGL et
    AMZN — s'en servir remplacerait une absence honnête par une date fausse.
    """
    sym = (sym or '').upper()[:12]
    board = _board_for(sym)
    contracts = sorted([c for c in board if str(c.get('sym', '')).upper() == sym
                        and c.get('quality') is not None],
                       key=lambda c: c.get('quality', 0), reverse=True)
    detail = (scan_state.get('detail') or {}).get(sym) or {}
    top = contracts[0] if contracts else {}
    entrees = {
        'earnings_in_days': detail.get('earnings_in_days'),
        'ex_dividend_days': detail.get('ex_dividend_days'),
        'right': top.get('type'),
        'dte': top.get('dte'),
    }
    d = dict(_oi.interpret_event_risk(
        sym, earnings_in_days=entrees['earnings_in_days'],
        ex_dividend_days=entrees['ex_dividend_days'],
        right=entrees['right'], dte=entrees['dte'],
        source='SCAN', as_of=_as_of()))
    #  Les quatre entrées n'ont pas la même origine, donc pas les mêmes états
    #  possibles — les confondre produirait justement le genre de verdict
    #  uniforme que ce bloc existe pour défaire.
    #
    #  · `earnings_in_days` / `ex_dividend_days` viennent de `scan_state
    #    ['detail']`. NON_CABLEE = aucune entrée de `detail`, sur tout
    #    l'univers, ne porte cette clé : elle n'a pas d'écrivain, l'attendre
    #    pour ce titre-ci n'a aucun sens. ABSENTE = d'autres titres l'ont, pas
    #    celui-ci : là, c'est bien une absence mesurée.
    #  · `right` / `dte` viennent du meilleur contrat du board options.
    #    Absents, ils disent « aucun contrat noté pour ce titre », ce qui est
    #    une mesure — pas un câblage manquant.
    detail_toutes = scan_state.get('detail') or {}

    def _statut_detail(cle):
        if entrees[cle] is not None:
            return 'MESUREE'
        produite = any(isinstance(v, dict) and v.get(cle) is not None
                       for v in detail_toutes.values())
        return 'ABSENTE' if produite else 'NON_CABLEE'

    statuts = {c: _statut_detail(c)
               for c in ('earnings_in_days', 'ex_dividend_days')}
    statuts.update({c: ('MESUREE' if entrees[c] is not None else 'AUCUN_CONTRAT')
                    for c in ('right', 'dte')})
    non_cablees = sorted(c for c, s in statuts.items() if s == 'NON_CABLEE')
    if non_cablees:
        d['limitations'] = list(d.get('limitations') or []) + [
            'Entrées non câblées dans le scan : %s — le verdict ne peut pas '
            'être autre chose qu’INCONNU, et ce n’est pas une mesure de '
            'l’absence d’événement.' % ', '.join(non_cablees)]
    return jsonify({
        'symbol': sym,
        'interpretation': d,
        'entrees': entrees,
        'entrees_statut': statuts,
        'entrees_non_cablees': non_cablees,
        'source': 'SCAN', 'as_of': _as_of(), 'ts': _ts_epoch(),
        'read_only': True,
    })


@bp.route('/api/charts/<path:chart_id>/interpretation')
def chart_interpretation(chart_id):
    """Interprétation canonique d'un graphique identifié. Route de contrat :
    délègue aux moteurs selon chart_id (options.overview_mix, options.volatility…)."""
    sym = (request.args.get('sym') or '').upper()[:12]
    cid = str(chart_id)
    if cid in ('options.overview_mix', 'options.overview'):
        s = _ov.summarize(_board(), as_of=_as_of(), demo=bool(DEMO_MODE), source='SCAN')
        return jsonify(s['interpretation'])
    if cid == 'options.volatility' and sym:
        return jsonify(options_volatility(sym).get_json()['interpretation'])
    if cid == 'options.event_risk' and sym:
        return jsonify(options_event_risk(sym).get_json()['interpretation'])
    from vertex.visualization.schemas import unknown
    return jsonify(unknown(cid, 'Graphique non reconnu',
                           reason='chart_id inconnu ou paramètre sym manquant',
                           source='SCAN'))


#  Borne du MODÈLE de doublement (coût de calcul), pas du câblage des données.
_DOUBLE_PROB_TOP = 5


@bp.route('/api/options/scanner/<universe>')
def api_options_scanner(universe):
    """SCANNERS PAR UNIVERS (SKYLER LOT 6) : TACTICAL / SWING / LEAPS strictement
    séparés, mandat LEAPS V2 étiqueté par candidat, probabilité de doublement
    (modèle documenté, ESTIMATED) sur les 5 meilleurs — le cours, lui, est
    câblé et tracé sur TOUS les candidats. Lecture seule."""
    from flask import request
    from vertex.options import double_prob as _dp, horizon_scanners as _hs
    sym = (request.args.get('sym') or '').upper().strip() or None
    res = _hs.scan(scan_state.get('options_board') or [], universe, sym=sym)
    if res.get('available'):
        _detail_all = scan_state.get('detail') or {}
        #  Le CÂBLAGE DU COURS vaut pour TOUS les candidats, pas seulement pour
        #  ceux qui reçoivent le modèle de doublement. Mesure du 2026-09-06 :
        #  la boucle s'arrêtait à `[:5]`, donc sur LEAPS (33 candidats) 5 lignes
        #  portaient `spot: 230.36` et 28 gardaient `spot: null` dans LA MÊME
        #  charge — la clé `spot` changeait de sens selon le rang, et un lecteur
        #  de la queue aurait conclu à une absence de cours de marché.
        #  Le repli reste NOMMÉ ligne par ligne (`spot_source`).
        for c in res['candidates']:
            _sym_line = str(c.get('sym') or '').upper()
            _spot_line = c.get('spot')
            _src_line = 'contrat' if _spot_line is not None else None
            if _spot_line is None:
                _spot_line = (_detail_all.get(_sym_line) or {}).get('price')
                _src_line = 'scan.detail.price' if _spot_line is not None else None
            c['spot'] = _spot_line
            c['spot_source'] = _src_line
        #  Le MODÈLE de doublement, lui, reste borné aux 5 meilleurs (coût de
        #  calcul) — mais son absence se NOMME sur les suivants au lieu de
        #  laisser un trou que la page rendait « non disponible » sans motif.
        for c in res['candidates'][_DOUBLE_PROB_TOP:]:
            c['double_prob'] = {
                'available': False,
                'reason': 'probabilité de doublement calculée sur les %d meilleurs '
                          'candidats seulement — non calculée pour cette ligne'
                          % _DOUBLE_PROB_TOP}
        for c in res['candidates'][:_DOUBLE_PROB_TOP]:
            prem = (c.get('cost') / 100.0) if isinstance(c.get('cost'), (int, float)) else None
            #  Entrees MESUREES par candidat : le taux a SON echeance, et le
            #  dividende de SON sous-jacent. Avec les constantes (4,5 % / 0),
            #  la probabilite de doublement etait surevaluee jusqu'a 20,9 %
            #  sur un titre distributeur — dans le sens optimiste.
            _sym_c = str(c.get('sym') or '').upper()
            #  `build_board` (legacy_engine.py:437) n'ecrit AUCUNE cle 'spot' :
            #  ce point d'appel etait le seul du fichier sans repli, et 100 %
            #  des candidats des 4 univers (LEAPS, TACTICAL, SWING, SWING_3_6M)
            #  etaient refuses pour « cours absent » alors que le meme processus
            #  servait 230,36 $ pour NVDA au meme instant sur /scenarios (l.358),
            #  /gex-radar (l.430) et /chain (l.104). Un defaut de cablage etait
            #  presente a l'humain comme une absence de donnee de marche.
            #  Le repli est NOMME dans la charge (`spot_source`) : le cours du
            #  scan n'est pas horodate sur la cotation du contrat.
            #  Le cours est desormais pose par la boucle CI-DESSUS pour TOUS les
            #  candidats ; le relire ici le re-etiquetterait « contrat » alors
            #  qu'il vient du scan — le lignage serait faux.
            _spot = c.get('spot')
            c['double_prob'] = _dp.double_probability(
                spot=_spot, strike=c.get('strike'), premium=prem,
                dte=c.get('dte'), iv=c.get('iv'), right=c.get('type') or 'CALL',
                r=_entrees.taux(scan_state, c.get('dte')),
                q=(_entrees.rendement_dividende(scan_state, _sym_c) or 0.0))
            c['entrees'] = _entrees.provenance(scan_state, _sym_c)
    res['as_of'] = _as_of()
    from vertex.app.config import DEMO_MODE as _demo
    res['demo'] = _demo
    return jsonify(res)


__all__ = ['bp']
