"""vertex/options/on_demand.py — chaîne d'options À LA DEMANDE.

Le board (rotation IBKR + focus) couvre l'univers en quelques heures ; entre-temps,
un titre consulté (/options/<sym>, carte options de la fiche) peut ne pas y être →
toutes ses cartes restaient « Aucune donnée ». Ce module comble le trou : si le
board n'a AUCUN contrat pour le symbole demandé, on va chercher sa chaîne tout de
suite via le même moteur (legacy_engine.best_for_symbol — IBKR si TWS est ouvert,
repli yfinance sinon), avec un cache TTL pour ne pas marteler la source.

Honnêteté des données (règle produit) : si le fetch échoue ou si le titre n'a pas
de spot dans le scan, on renvoie [] — l'UI garde son état vide honnête, jamais un
chiffre inventé. ⛔ LECTURE SEULE.
"""
from __future__ import annotations

import threading
import time

from vertex.app.state import scan_state
from vertex.options import legacy_engine

# Lot 5b : un verrou PAR SYMBOLE pour casser le « thundering herd » — la fiche tire
# grille + surface + max-pain en même temps, chacun appelant warm_chain : sans verrou,
# les 3 passent le check TTL avant que le 1er écrive le cache → 3 pulls réseau identiques.
_WARM_GUARD = threading.Lock()
_WARM_LOCKS = {}

#: POURQUOI une chaine n'a pas pu etre chargee, par symbole. Trois `except:
#: pass` vivaient ici : les puts perdus, la sonde des deux cotes, et l'echec
#: complet du prechauffage. Chacun jetait une information sans le dire — et le
#: gardien `test_pass_et_contexte` a refuse de voir sa borne relevee
#: sans examen. Il avait raison : une chaine qui ne se charge pas doit pouvoir
#: le DIRE, sinon « aucun contrat » et « la source a refuse » se confondent —
#: et seul le second se corrige.
_ECHECS: dict = {}


def _noter(sym, quoi, exc):
    #  Enregistre un echec au lieu de l'avaler.
    _ECHECS[str(sym).upper()] = '%s: %s: %s' % (quoi, type(exc).__name__, exc)


def dernier_echec(sym):
    #  La raison du dernier echec pour ce titre, ou None. Sert aux surfaces.
    return _ECHECS.get(str(sym or '').upper())


def _warm_lock(sym):
    with _WARM_GUARD:
        return _WARM_LOCKS.setdefault(sym, threading.Lock())

# TTL du cache à la demande : 15 min — assez frais pour l'analyse, assez long pour
# ne pas refaire 3 appels de chaîne à chaque rafraîchissement de page.
TTL_S = 900
# Résultat VIDE (scan pas prêt, chaîne injoignable) : réessai rapide — sinon un
# fetch raté au démarrage laisserait le dossier vide 15 minutes.
EMPTY_TTL_S = 120


def _has_sym(board, sym):
    return any(str(c.get('sym', '')).upper() == sym for c in board)


def fetch(sym):
    """Contrats à la demande pour `sym` (cache TTL). [] honnête si impossible."""
    sym = (sym or '').upper()
    if not sym:
        return []
    cache = scan_state.setdefault('options_ondemand', {})
    ent = cache.get(sym)
    now = time.time()
    if ent and now - (ent.get('ts') or 0) < TTL_S:
        return ent.get('contracts') or []
    detail = (scan_state.get('detail') or {}).get(sym) or {}
    spot = detail.get('price')
    contracts = []
    if isinstance(spot, (int, float)) and spot > 0:
        plan = detail.get('plan') or {}
        tgt = plan.get('tp2') or round(spot * 1.12, 2)
        try:
            contracts = legacy_engine.best_for_symbol(
                sym, spot, tgt, 'call', max_n=4,
                buckets=('court', 'moyen', 'long'),
                earnings_dte=detail.get('earnings_dte'))
        except Exception:
            contracts = []
        # Verdict baissier → aussi des puts (protection / thèse courte).
        if (detail.get('verdict') or '').upper() in ('SELL', 'STRONG_SELL', 'AVOID'):
            stop = plan.get('stop') or round(spot * 0.90, 2)
            try:
                contracts = contracts + legacy_engine.best_for_symbol(
                    sym, spot, stop, 'put', max_n=2,
                    buckets=('moyen', 'long'),
                    earnings_dte=detail.get('earnings_dte'))
            except Exception as exc:              # noqa: BLE001
                #  Les calls sont deja la : on garde ce qu'on a, mais on NOTE
                #  que les puts manquent — sinon une these baissiere s'affiche
                #  sans protection, et rien ne dit pourquoi.
                _noter(sym, 'puts indisponibles', exc)
        # `best_for_symbol` ne pose pas le champ spot ; vol_charts (structure par
        # terme, cône, smile) et les scénarios en dépendent — on l'injecte ici.
        for c in contracts:
            c.setdefault('spot', spot)
    # vide → n'empoisonne le cache que EMPTY_TTL_S (réessai rapide après le scan)
    ts = now if contracts else (now - TTL_S + EMPTY_TTL_S)
    cache[sym] = {'ts': ts, 'contracts': contracts}
    return contracts


def warm_chain(sym, n_exp=3):
    """Force la lecture C ET P des `n_exp` échéances les plus proches → PERSISTE la
    chaîne LARGE (déclenche _df côté terminal) pour max pain / murs d'OI / PCR réels.
    Best-effort, cache TTL (pas de martelage), silencieux. ⛔ lecture seule."""
    sym = (sym or '').upper()
    if not sym:
        return
    cache = scan_state.setdefault('options_warm_cache', {})
    if time.time() - (cache.get(sym) or 0) < TTL_S:
        return                                    # voie rapide : déjà frais, aucun verrou
    with _warm_lock(sym):                          # un seul pull réel par symbole (anti-troupeau)
        if time.time() - (cache.get(sym) or 0) < TTL_S:
            return                                # re-check sous le verrou : les autres voient le frais
        try:
            tk = legacy_engine.yf.Ticker(sym)
            exps = list(tk.options or [])[:n_exp]
            if not exps:
                return                            # pipeline pas prêt → ne PAS poser le cache (retry)
            for exp in exps:
                ch = tk.option_chain(exp)
                for side in ('calls', 'puts'):    # accéder aux 2 côtés → _df('C') et _df('P')
                    try:
                        _ = getattr(ch, side)
                    except Exception as exc:      # noqa: BLE001
                        _noter(sym, 'cote %s illisible' % side, exc)
            cache[sym] = time.time()              # succès → throttle 15 min
        except Exception as exc:                  # noqa: BLE001
            #  Le prechauffage a echoue : le cache n'est PAS pose (retry au
            #  prochain passage) et la raison est conservee.
            _noter(sym, 'prechauffage de la chaine', exc)


def _lookup_greeks(ent, exp, right, strike):
    """Greeks RÉELS (modelGreeks IBKR persistés) d'un contrat PRÉCIS depuis la chaîne
    large. Match STRICT : échéance (8 chiffres) + côté + strike exact. None si absent —
    on ne substitue JAMAIS un autre strike/échéance (ce serait estimer). ⛔ lecture seule."""
    if not ent:
        return None
    want = ''.join(ch for ch in str(exp or '') if ch.isdigit())[:8]
    if not want:
        return None
    match_exp = None
    for e in ent:
        if e in ('spot', 'ts'):
            continue
        if ''.join(ch for ch in str(e) if ch.isdigit())[:8] == want:
            match_exp = e
            break
    if match_exp is None:
        return None
    side = (ent.get(match_exp) or {}).get(right) or {}
    row = side.get(strike) or side.get(round(strike, 2))
    if not row:
        return None
    if row.get('delta') is None and row.get('vega') is None:
        return None                                      # coté mais sans greeks broker
    return row


def desk_greeks(opt_positions):
    """Greeks AGRÉGÉS du desk depuis les greeks BROKER (modelGreeks IBKR) persistés dans
    scan_state['options_chain_full']. opt_positions : [{sym,exp,strike,right|type,qty}].
    Multiplicateur 100/contrat. Greeks du broker UNIQUEMENT — jamais estimés ; une jambe
    non cotée (hors fenêtre de strikes tirée, ou chaîne pas encore chargée) → greeks None
    (agrégat partiel honnête). Ne bloque pas (lit le persisté, ne tire rien). ⛔ lecture seule."""
    full = scan_state.get('options_chain_full') or {}
    legs = []
    for p in opt_positions or []:
        sym = str(p.get('sym') or p.get('symbol') or '').upper()
        r = str(p.get('right') or p.get('type') or 'C').upper()
        right = 'P' if r.startswith('P') else 'C'
        try:
            strike = round(float(p.get('strike')), 2)
            qty = float(p.get('qty') if p.get('qty') is not None else p.get('quantity') or 0)
        except (TypeError, ValueError):
            legs.append({'sym': sym, 'delta': None})
            continue
        g = _lookup_greeks(full.get(sym), p.get('exp'), right, strike)
        if not g or not qty:
            legs.append({'sym': sym, 'delta': None})
            continue
        mult = 100.0 * qty                               # 1 contrat = 100 actions
        legs.append({
            'sym': sym,
            'delta': (round(g['delta'] * mult, 3) if g.get('delta') is not None else None),
            'gamma': (round(g['gamma'] * mult, 4) if g.get('gamma') is not None else None),
            'theta': (round(g['theta'] * mult, 3) if g.get('theta') is not None else None),
            'vega': (round(g['vega'] * mult, 3) if g.get('vega') is not None else None)})

    def _sum(name):
        vals = [l[name] for l in legs if l.get(name) is not None]
        return round(sum(vals), 3) if vals else None
    priced = sum(1 for l in legs if l.get('delta') is not None)
    vega_tot = _sum('vega')
    return {'legs': legs, 'delta': _sum('delta'), 'gamma': _sum('gamma'),
            'theta': _sum('theta'), 'vega': vega_tot,
            'vega_usd': vega_tot,                        # $ P&L par point de vol (déjà ×100×qty)
            'open_options': len(legs), 'priced': priced,
            'greeks_partial': priced < len(legs)}


#  Marques de contrat en cours de lecture EN FOND (clé → époque) : une requête
#  utilisateur ne tire jamais la chaîne elle-même (`reseau=False`), elle lance
#  une lecture de fond au plus une fois par clé et par TTL.
_MARQUES_EN_COURS: dict = {}
_MARQUES_VERROU = threading.Lock()


def _lire_marque_en_fond(sym, exp_prefix, strike, right, key):
    now = time.time()
    with _MARQUES_VERROU:
        if now - _MARQUES_EN_COURS.get(key, 0) < EMPTY_TTL_S:
            return False
        _MARQUES_EN_COURS[key] = now

    def _run():
        try:
            contract_mark(sym, exp_prefix, strike, right, reseau=True)
        finally:
            with _MARQUES_VERROU:
                _MARQUES_EN_COURS.pop(key, None)
    threading.Thread(target=_run, daemon=True, name='marque-' + key).start()
    return True


def contract_mark(sym, exp_prefix, strike, right, reseau=True):
    """Mid RÉEL d'un contrat PRÉCIS via la chaîne (IBKR si TWS ouvert via le
    monkeypatch de legacy_engine.yf, sinon yfinance). Utilisé pour marquer les
    positions options du desk quand IBKR ne cote pas — le board ne contient que
    les « meilleurs » strikes, pas forcément celui détenu. None honnête si le
    contrat n'est pas coté ; cache TTL partagé (pas de martelage).

    `reseau=False` (requête utilisateur) : sert le cache tel quel — même
    périmé, car une marque datée vaut mieux qu'une attente — et, s'il manque
    ou est périmé, lance la lecture EN FOND ; rend None si rien n'est en cache."""
    sym = (sym or '').upper()
    right = (right or 'C').upper()
    try:
        strike = float(strike)
    except (TypeError, ValueError):
        return None
    key = '%s|%s|%s|%s' % (sym, exp_prefix or '', strike, right[:1])
    cache = scan_state.setdefault('options_mark_cache', {})
    ent = cache.get(key)
    now = time.time()
    if ent and now - (ent.get('ts') or 0) < TTL_S:
        return ent.get('mark')
    if not reseau:
        _lire_marque_en_fond(sym, exp_prefix, strike, right, key)
        return ent.get('mark') if ent else None
    mark = None
    try:
        tk = legacy_engine.yf.Ticker(sym)
        exps = list(tk.options or [])
        exp = next((e for e in exps if str(e).startswith(str(exp_prefix or ''))), None)
        if exp:
            ch = tk.option_chain(exp)
            df = ch.puts if right.startswith('P') else ch.calls
            rows = df[abs(df['strike'] - strike) < 0.01]
            if len(rows):
                r0 = rows.iloc[0]
                bid = float(r0['bid'] or 0)
                ask = float(r0['ask'] or 0)
                last = float(r0['lastPrice'] or 0)
                if bid > 0 and ask > 0:
                    mark = round((bid + ask) / 2.0, 2)
                elif last > 0:
                    mark = round(last, 2)
    except Exception:
        mark = None
    cache[key] = {'ts': now, 'mark': mark}
    return mark


def board_with(sym):
    """Board global ∪ contrats à la demande pour `sym` s'il en est absent.

    Ne mute PAS scan_state['options_board'] (la boucle _opt_loop le republie et
    écraserait l'ajout) — la fusion se fait à la lecture, le cache TTL absorbe
    le coût.
    """
    board = scan_state.get('options_board') or []
    sym = (sym or '').upper()
    if not sym or _has_sym(board, sym):
        return board
    extra = fetch(sym)
    return list(board) + extra if extra else board


__all__ = ['fetch', 'board_with', 'contract_mark', 'warm_chain', 'desk_greeks', 'TTL_S']
