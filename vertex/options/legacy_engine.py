"""
vertex/options/legacy_engine.py — Moteur OPTIONS INTELLIGENCE (cahier §6).

Pour les meilleurs setups du scanner, tire la VRAIE chaîne d'options (yfinance),
calcule les greeks (Black-Scholes maison), score la "suitability" (vertex.quant.scoring),
filtre les contrats sales (spread large / OI faible / IV extrême) et CLASSE les
meilleures options à trader : CALLS sur les haussiers, PUTS sélectifs sur les
baissiers. Échéances ciblées 6 / 9 / 12 mois (profil utilisateur).

⛔ ANALYSE ONLY — aucune exécution. Recommandation pédagogique, pas un ordre.
"""
import math
from datetime import datetime
from zoneinfo import ZoneInfo


def _ny_now():
    """Heure de New York (naïve) — les échéances d'options sont des dates de
    séance US : un serveur en UTC/Europe surestimerait le DTE d'un jour en
    soirée avec datetime.now() naïf."""
    return datetime.now(ZoneInfo('America/New_York')).replace(tzinfo=None)

import yfinance as yf

from vertex.quant import scoring
from vertex.strategy import config
from vertex.data_sources.rates import rate_sensitivity

R = 0.045


def _i(x):
    try:
        return 0 if x is None or (isinstance(x, float) and math.isnan(x)) else int(x)
    except Exception:
        return 0


def _f(x):
    try:
        return 0.0 if x is None or (isinstance(x, float) and math.isnan(x)) else float(x)
    except Exception:
        return 0.0


def _reported_number(x):
    """Vrai si une donnée numérique est présente, y compris zéro reporté.

    Le zéro est une observation potentiellement illiquide ; `None`/NaN est une
    absence. La couverture ne les confond jamais.
    """
    try:
        return x is not None and math.isfinite(float(x))
    except (TypeError, ValueError):
        return False


def _reported_timestamp(x):
    if x is None:
        return False
    text = str(x).strip()
    return bool(text) and text.lower() not in ('none', 'nan', 'nat')


def _npdf(x):
    return math.exp(-0.5 * x * x) / math.sqrt(2 * math.pi)


def _ncdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2)))


def _greeks(S, K, T, sig, is_call):
    if T <= 0 or sig <= 0 or S <= 0 or K <= 0:
        return 0.0, 0.0, 0.0, 0.0
    srt = sig * math.sqrt(T)
    d1 = (math.log(S / K) + (R + 0.5 * sig * sig) * T) / srt
    d2 = d1 - srt
    pdf = _npdf(d1)
    delta = _ncdf(d1) if is_call else _ncdf(d1) - 1.0
    gamma = pdf / (S * srt)
    vega = S * pdf * math.sqrt(T) / 100.0
    term = -(S * pdf * sig) / (2.0 * math.sqrt(T))
    theta = ((term - R * K * math.exp(-R * T) * _ncdf(d2)) if is_call
             else (term + R * K * math.exp(-R * T) * _ncdf(-d2))) / 365.0
    return delta, gamma, theta, vega


def gamma(S, K, T, sig):
    """Gamma Black-Scholes (source unique — utilisé aussi par le GEX du terminal)."""
    if T <= 0 or sig <= 0 or S <= 0 or K <= 0:
        return 0.0
    d1 = (math.log(S / K) + (R + 0.5 * sig * sig) * T) / (sig * math.sqrt(T))
    return _npdf(d1) / (S * sig * math.sqrt(T))


def _bs_price(S, K, T, sig, is_call):
    if T <= 0 or sig <= 0:
        return max((S - K) if is_call else (K - S), 0.0)
    srt = sig * math.sqrt(T)
    d1 = (math.log(S / K) + (R + 0.5 * sig * sig) * T) / srt
    d2 = d1 - srt
    if is_call:
        return S * _ncdf(d1) - K * math.exp(-R * T) * _ncdf(d2)
    return K * math.exp(-R * T) * _ncdf(-d2) - S * _ncdf(-d1)


def _bs_price_at_rate(S, K, T, sig, is_call, rate):
    if T <= 0 or sig <= 0:
        return max((S - K) if is_call else (K - S), 0.0)
    srt = sig * math.sqrt(T)
    d1 = (math.log(S / K) + (rate + 0.5 * sig * sig) * T) / srt
    d2 = d1 - srt
    if is_call:
        return S * _ncdf(d1) - K * math.exp(-rate * T) * _ncdf(d2)
    return K * math.exp(-rate * T) * _ncdf(-d2) - S * _ncdf(-d1)


def option_rate_sensitivity(S, K, T, sig, is_call, rate_quote=None):
    """Sensibilité descriptive au taux, seulement avec une courbe provenancée."""
    quote = rate_quote.to_dict() if hasattr(rate_quote, 'to_dict') else (rate_quote or {})
    rate = quote.get('rate') if isinstance(quote, dict) else None
    try:
        usable = math.isfinite(float(rate)) and not bool(quote.get('fallback_used'))
    except (TypeError, ValueError):
        usable = False
    if not usable:
        return {'available': False, 'read_only': True,
                'reason': 'courbe de taux provenancée non disponible ou servie par repli',
                'rate_provenance': (quote or None)}
    sensitivity = rate_sensitivity(
        lambda candidate_rate: _bs_price_at_rate(S, K, T, sig, is_call, candidate_rate),
        float(rate),
    )
    return {'available': sensitivity['sensitivity_per_bump'] is not None,
            'read_only': True, 'rate_provenance': quote,
            'model': 'Black-Scholes sans dividende', 'sensitivity': sensitivity}


def option_price_integrity(S, K, T, price, is_call):
    """Bornes européennes sans dividende : garde-fou, jamais estimation de prix."""
    if any(not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0
           for v in (S, K, T, price)):
        return {'available': False, 'status': 'OPTION_INPUT_INSUFFICIENT',
                'read_only': True, 'reason': 'spot, strike, durée ou prix non exploitable'}
    discounted_strike = K * math.exp(-R * T)
    lower = max(0.0, S - discounted_strike) if is_call else max(0.0, discounted_strike - S)
    upper = S if is_call else discounted_strike
    tolerance = max(0.01, upper * 0.0001)  # précision de cotation, pas une marge de marché
    valid = lower - tolerance <= price <= upper + tolerance
    return {'available': valid,
            'status': 'OPTION_PRICE_COHERENT' if valid else 'PRICE_OUTSIDE_NO_ARBITRAGE',
            'read_only': True, 'lower_bound': round(lower, 8), 'upper_bound': round(upper, 8),
            'observed_price': round(price, 8), 'tolerance': round(tolerance, 8),
            'reason': None if valid else 'prix observé hors bornes européennes sans dividende'}


def _iv_from_price(S, K, T, price, is_call):
    """IV implicite par bissection (fallback quand yfinance ne donne pas d'IV fiable)."""
    integrity = option_price_integrity(S, K, T, price, is_call)
    if not integrity['available']:
        return None
    lo, hi = 0.02, 3.0
    if _bs_price(S, K, T, hi, is_call) < price:   # prix hors bornes
        return None
    for _ in range(40):
        m = (lo + hi) / 2.0
        if _bs_price(S, K, T, m, is_call) < price:
            lo = m
        else:
            hi = m
    return round((lo + hi) / 2.0, 4)


def _prob_above(S, K, T, sig):
    """P(S_T > K) sous le modèle lognormal (risque-neutre) = N(d2). Sert au calcul des probabilités."""
    if S <= 0 or K <= 0 or T <= 0 or sig <= 0:
        return 0.0
    d2 = (math.log(S / K) + (R - 0.5 * sig * sig) * T) / (sig * math.sqrt(T))
    return _ncdf(d2)


def option_quality(c, spot):
    """💎 OPTION QUALITY SCORE /100 (delta /20, échéance /15, spread /15, OI /15,
    volume /10, IV /10, théta /10, breakeven /5). Pour juger la PROPRETÉ du contrat."""
    d = abs(_f(c.get('delta')))
    dte = _i(c.get('dte'))
    sp = c.get('spread')
    oi = _i(c.get('oi'))
    vol = _i(c.get('vol'))
    iv = _f(c.get('iv'))
    tb = _f(c.get('theta_burn'))
    be = _f(c.get('be'))
    bk = c.get('bucket')
    qd = 20 if 0.70 <= d <= 0.88 else 15 if (0.62 <= d < 0.70 or 0.88 < d <= 0.92) else 10 if 0.52 <= d < 0.62 else 5
    qe = {'long': 15, 'moyen': 11, 'court': 6}.get(bk, 8)
    s = sp if sp is not None else 12
    qs = 15 if s < 2 else 12 if s < 4 else 9 if s < 6 else 5 if s < 10 else 2
    qo = 15 if oi > 5000 else 12 if oi > 2000 else 9 if oi > 1000 else 6 if oi > 500 else 3 if oi > 100 else 0
    qv = 10 if vol > 500 else 7 if vol > 100 else 5 if vol > 50 else 3 if vol > 10 else 1
    qi = 10 if iv < 35 else 8 if iv < 50 else 5 if iv < 70 else 3 if iv < 90 else 1
    qt = 10 if tb < 0.3 else 8 if tb < 0.6 else 6 if tb < 1.0 else 4 if tb < 1.5 else 2
    bedist = abs(be - spot) / spot * 100 if spot else 99
    qb = 5 if bedist < 6 else 4 if bedist < 10 else 3 if bedist < 15 else 1
    total = qd + qe + qs + qo + qv + qi + qt + qb
    return {'score': total,
            'parts': {'Delta': [qd, 20], 'Échéance': [qe, 15], 'Spread': [qs, 15], 'OI': [qo, 15],
                      'Volume': [qv, 10], 'IV': [qi, 10], 'Théta': [qt, 10], 'Breakeven': [qb, 5]}}


def breakeven_check(c, spot):
    """Le breakeven est-il atteignable ? distance + hausse mensuelle nécessaire + verdict."""
    be = _f(c.get('be'))
    dte = max(_i(c.get('dte')), 1)
    is_call = c.get('type') == 'CALL'
    dist = (be - spot) / spot * 100 if spot else 0.0
    monthly = abs(dist) / max(dte / 30.0, 0.1)
    verdict = 'réaliste' if monthly < 2.5 else 'agressif' if monthly < 5 else 'danger théta'
    return {'be': round(be, 2), 'dist': round(dist, 1), 'monthly': round(monthly, 2),
            'verdict': verdict, 'dir': 'call' if is_call else 'put'}


def scenarios(c, spot, levels, horizon_days=40):
    """3 scénarios obligatoires : pessimiste (stop) / probable (TP1) / exceptionnel (TP3).
    Reprice l'option (Black-Scholes) au niveau cible, à un horizon de ~40j (théta inclus)."""
    iv = _f(c.get('iv')) / 100.0
    K = _f(c.get('strike'))
    dte = max(_i(c.get('dte')), 1)
    mid = _f(c.get('mid'))
    is_call = c.get('type') == 'CALL'
    T_fut = max((dte - horizon_days) / 365.0, 0.01)

    def pnl(px):
        if not px or mid <= 0:
            return None
        val = _bs_price(px, K, T_fut, iv, is_call)
        return round((val - mid) / mid * 100)
    pr = levels.get('tp1') or levels.get('tp2')
    ex = levels.get('tp3') or levels.get('tp2')
    return {'horizon': horizon_days,
            'pess': {'px': levels.get('stop'), 'pnl': pnl(levels.get('stop'))},
            'prob': {'px': pr, 'pnl': pnl(pr)},
            'exalt': {'px': ex, 'pnl': pnl(ex)}}


def _pick_expiries(exps, now, buckets=None):
    """Échéances ciblées PAR BUCKET (court/moyen/long). buckets=None -> ('long',) rétro-compat.
    Renvoie [(exp_str, dte, bucket_key)]."""
    buckets = buckets or config.DEFAULT_BUCKETS
    picks, seen = [], set()
    for bk in buckets:
        b = config.OPTION_BUCKETS[bk]
        best, bd = None, 1e9
        for e in exps:
            try:
                d = (datetime.strptime(e, '%Y-%m-%d') - now).days
            except Exception:
                continue
            if b['min'] <= d <= b['max'] and abs(d - b['target']) < bd:
                bd, best = abs(d - b['target']), e
        if best and best not in seen:
            seen.add(best)
            picks.append((best, (datetime.strptime(best, '%Y-%m-%d') - now).days, bk))
    return picks


def _horodatage_depeche(t):
    """L'horodatage d'une dépêche TEL QUE LA SOURCE LE DÉCLARE — jamais tronqué.

    RACINE DU CONSTAT 9, mesurée le 2026-09-06. Cette fonction remplace
    `str(t)[:16].replace('T', ' ')`, qui détruisait DEUX choses :

      1. le fuseau. yfinance sert `pubDate = '2026-09-04T23:42:00Z'` ; la
         troncature à 16 caractères rendait `'2026-09-04 23:42'`, sans le `Z`.
         En aval `news_plus.horodatage_source` sait lire `Z` et les décalages
         `±HH:MM` et les convertit en UTC — mais il n'avait plus rien à lire,
         donc `published_at` sortait SANS fuseau et l'écran devait afficher
         « 04/09/2026 23:42 (fuseau n/d) » là où il pouvait dire « Il y a
         12 min ». Mesure du fil servi : 45 items sur 45 arrivaient sans
         fuseau alors que la source en portait un.
      2. l'époque. L'ancien format plat de yfinance sert
         `providerPublishTime`, un ENTIER de secondes UNIX ; `str(...)[:16]`
         en faisait la chaîne `'1757000000'`, illisible pour tout le monde en
         aval, d'où `published_at = None` — une absence là où la source avait
         donné une date.

    On ne fabrique rien : une époque est convertie (c'est une lecture d'unité,
    pas une estimation), une chaîne est rendue telle quelle, et tout ce qui
    n'est ni l'un ni l'autre rend `''` — l'absence, distincte d'une valeur.
    """
    if t is None or isinstance(t, bool):
        return ''
    if isinstance(t, (int, float)):
        #  Époque UNIX en secondes, UTC — le `Z` est porté par la conversion,
        #  pas supposé. Une valeur hors domaine reste une absence.
        try:
            from datetime import timezone
            return datetime.fromtimestamp(float(t), tz=timezone.utc).strftime(
                '%Y-%m-%dT%H:%M:%SZ')
        except (OverflowError, OSError, ValueError):
            return ''
    return str(t).strip()


def news_for(tk, n=5):
    """Dernières news d'un titre (yfinance) — gère l'ancien format plat et le nouveau imbriqué."""
    out = []
    try:
        for it in (tk.news or [])[:n]:
            if not isinstance(it, dict):
                continue
            c = it.get('content', it)
            title = c.get('title') or it.get('title')
            prov = c.get('provider')
            pub = prov.get('displayName') if isinstance(prov, dict) else (it.get('publisher') or '')
            t = c.get('pubDate') or it.get('providerPublishTime') or ''
            cu = c.get('canonicalUrl')
            link = cu.get('url') if isinstance(cu, dict) else (it.get('link') or '')
            if title:
                out.append({'title': title, 'pub': pub or '',
                            'time': _horodatage_depeche(t), 'link': link or ''})
    except Exception:
        pass
    return out


def best_for_symbol(sym, spot, target, direction, iv_rank=50, max_n=2, buckets=None,
                    earnings_dte=None, include_diagnostics=False, rate_quote=None):
    """Meilleurs contrats par bucket (court/moyen/long), classés. buckets=None -> long (rétro-compat)."""
    buckets = buckets or config.DEFAULT_BUCKETS
    out = []
    price_rejections = []
    try:
        tk = yf.Ticker(sym)
        now = _ny_now()
        for exp, dte, bk in _pick_expiries(list(tk.options), now, buckets):
            T = max(dte / 365.0, 0.02)
            ch = tk.option_chain(exp)
            df = ch.calls if direction == 'call' else ch.puts
            for _, row in df.iterrows():
                K = _f(row['strike'])
                if direction == 'call':
                    lo, hi = (0.99, 1.10) if bk == 'court' else (0.98, 1.18)
                else:
                    lo, hi = (0.90, 1.01) if bk == 'court' else (0.82, 1.02)
                if not (spot * lo <= K <= spot * hi):
                    continue
                iv = _f(row.get('impliedVolatility'))
                raw_oi, raw_vol = row.get('openInterest'), row.get('volume')
                raw_bid, raw_ask = row.get('bid'), row.get('ask')
                raw_trade_time = row.get('lastTradeDate')
                oi = _i(raw_oi)
                vol = _i(raw_vol)
                bid = _f(raw_bid)
                ask = _f(raw_ask)
                quoted = bid > 0 and ask > 0
                mid = (bid + ask) / 2.0 if quoted else _f(row.get('lastPrice'))
                if mid <= 0:
                    continue
                price_integrity = option_price_integrity(spot, K, T, mid, direction == 'call')
                if not price_integrity['available']:
                    if len(price_rejections) < 12:
                        price_rejections.append({'sym': sym, 'type': direction.upper(), 'bucket': bk,
                                                 'exp': exp, 'dte': dte, 'strike': K,
                                                 'price_integrity': price_integrity,
                                                 'derived_metrics_withheld': True})
                    continue
                # IV : si yfinance ne donne rien d'exploitable, on la RECALCULE depuis le prix
                stale = False
                if not (0.03 < iv < 3.0):
                    solved = _iv_from_price(spot, K, T, mid, direction == 'call')
                    if solved is None or solved < 0.03:
                        continue
                    iv, stale = solved, True
                if not quoted or oi <= 0:
                    stale = True               # hors séance / illiquide → indicatif
                spread = (ask - bid) / mid * 100.0 if (quoted and ask > bid) else (None if stale else 99.0)
                sc_spread = spread if spread is not None else 12.0
                delta, gamma, theta, vega = _greeks(spot, K, T, iv, direction == 'call')
                theta_burn = abs(theta) / mid * 100.0 if mid else 0.0   # érosion %/jour
                be = K + mid if direction == 'call' else K - mid
                intr = (max(target - K, 0) if direction == 'call' else max(K - target, 0))
                pot = (intr - mid) / mid * 100.0 if mid else 0.0
                suit = scoring.options_score({'oi': oi, 'spread_pct': sc_spread, 'delta': delta,
                                              'dte': dte, 'iv_rank': iv_rank, 'tech_ok': True,
                                              'bucket': bk, 'theta_burn': theta_burn, 'earnings_dte': earnings_dte})
                flags = []
                if bk == 'court':
                    flags.append('decay rapide')
                if earnings_dte is not None and 0 <= earnings_dte <= dte:
                    flags.append('earnings')
                if iv_rank > 70:
                    flags.append('IV chere')
                if spread is not None and spread > 8:
                    flags.append('spread large')
                if stale:
                    flags.append('hors séance')
                # PROBABILITÉS (lognormal, IV de l'option) + score de DANGER
                if direction == 'call':
                    pop = _prob_above(spot, be, T, iv) * 100        # proba profit à l'échéance
                    p_itm = _prob_above(spot, K, T, iv) * 100        # proba finir dans la monnaie
                    p_tgt = _prob_above(spot, target, T, iv) * 100   # proba d'atteindre la cible
                else:
                    pop = (1 - _prob_above(spot, be, T, iv)) * 100
                    p_itm = (1 - _prob_above(spot, K, T, iv)) * 100
                    p_tgt = (1 - _prob_above(spot, target, T, iv)) * 100
                dg = ((2 if theta_burn > 1.5 else 1 if theta_burn > 0.8 else 0)
                      + (2 if pop < 35 else 1 if pop < 50 else 0)
                      + (1 if 'earnings' in flags else 0)
                      + (1 if iv * 100 > 60 else 0)
                      + (1 if bk == 'court' else 0))
                danger = 'Extrême' if dg >= 6 else 'Élevé' if dg >= 4 else 'Modéré' if dg >= 2 else 'Faible'
                _c = {
                    'sym': sym, 'type': direction.upper(), 'bucket': bk, 'exp': exp, 'dte': dte, 'strike': K,
                    'tgt': round(target, 2),
                    'pop': round(pop), 'p_itm': round(p_itm), 'p_tgt': round(p_tgt),
                    'danger': danger, 'danger_n': dg,
                    'bid': round(bid, 2), 'ask': round(ask, 2),
                    'mid': round(mid, 2), 'cost': round(mid * 100), 'be': round(be, 2),
                    'iv': round(iv * 100, 1), 'delta': round(delta, 2), 'gamma': round(gamma, 4),
                    'theta': round(theta, 3), 'theta_burn': round(theta_burn, 2), 'vega': round(vega, 3),
                    'oi': oi, 'vol': vol, 'spread': round(spread, 1) if spread is not None else None,
                    'pot': round(pot), 'suit': round(suit), 'grade': config.grade(suit),
                    'em_pct': round(iv * math.sqrt(T) * 100, 1),
                    'flags': flags, 'stale': stale,
                    'price_integrity': price_integrity,
                    'rate_sensitivity': option_rate_sensitivity(
                        spot, K, T, iv, direction == 'call', rate_quote=rate_quote),
                    'liquidity_coverage': {
                        'bid_present': _reported_number(raw_bid),
                        'ask_present': _reported_number(raw_ask),
                        'volume_present': _reported_number(raw_vol),
                        'open_interest_present': _reported_number(raw_oi),
                        'quoted_bid_ask': quoted,
                        'reported_fields': sum((_reported_number(raw_bid), _reported_number(raw_ask),
                                                _reported_number(raw_vol), _reported_number(raw_oi))),
                        'total_fields': 4,
                        'read_only': True,
                        'note': 'champ absent ≠ zéro observé ; aucune liquidité n’est imputée',
                    },
                    'quote_timestamp_coverage': {
                        'reported': _reported_timestamp(raw_trade_time),
                        'timestamp': str(raw_trade_time) if _reported_timestamp(raw_trade_time) else None,
                        'status': ('REPORTED_TIMESTAMP_ONLY' if _reported_timestamp(raw_trade_time)
                                   else 'TIMESTAMP_UNAVAILABLE'),
                        'read_only': True,
                        'note': 'horodatage reporté sans déduction d’âge ou de fraîcheur',
                    },
                }
                _q = option_quality(_c, spot)
                _c['quality'] = _q['score']
                _c['quality_parts'] = _q['parts']
                out.append(_c)
    except Exception:
        return {'contracts': [], 'price_rejections': [], 'price_rejection_count': 0} if include_diagnostics else []
    # Niveau 1 (séance) : contrats liquides, données réelles. Préféré.
    live = [c for c in out if not c['stale'] and c['spread'] is not None
            and c['spread'] <= config.PROFILE['max_bidask_spread_pct']
            and c['oi'] >= 100 and c['suit'] >= 45]
    # Niveau 2 (hors séance) : si rien de liquide, on montre l'analyse INDICATIVE (IV recalculée).
    good = live if live else [c for c in out if c['suit'] >= 40]
    order = {'court': 0, 'moyen': 1, 'long': 2}
    good.sort(key=lambda c: (order.get(c['bucket'], 9), -c['suit']))
    # max_n PAR BUCKET (sinon le long écrase le court)
    res, cnt = [], {}
    for c in good:
        if cnt.get(c['bucket'], 0) < max_n:
            res.append(c)
            cnt[c['bucket']] = cnt.get(c['bucket'], 0) + 1
    if include_diagnostics:
        return {'contracts': res, 'price_rejections': price_rejections,
                'price_rejection_count': len(price_rejections)}
    return res


def build_board(detail, rows, max_calls=6, max_puts=3):
    """Board options du jour : calls (court/moyen/long) sur top haussiers, puts sur baissiers."""
    board = []
    buys = [r for r in rows if r['verdict'] in ('BUY', 'WATCH')][:max_calls]
    sells = [r for r in rows if r['verdict'] == 'AVOID'][-max_puts:]
    for r in buys:
        d = detail.get(r['symbol'])
        if d:
            board += best_for_symbol(r['symbol'], d['price'], d['plan']['tp2'], 'call',
                                     max_n=1, buckets=('court', 'moyen', 'long'))
    for r in sells:
        d = detail.get(r['symbol'])
        if d:
            board += best_for_symbol(r['symbol'], d['price'], d['price'] - 2 * d['plan']['atr'], 'put',
                                     max_n=1, buckets=('moyen', 'long'))
    order = {'court': 0, 'moyen': 1, 'long': 2}
    board.sort(key=lambda c: (order.get(c['bucket'], 9), -c['suit']))
    return board


def board_coverage(contracts):
    """Synthèse de couverture des contrats déjà produits, sans reclassement."""
    contracts = list(contracts or [])
    total = len(contracts)
    liquidity_reported = sum(
        1 for contract in contracts
        if (contract.get('liquidity_coverage') or {}).get('reported_fields', 0) == 4
    )
    quoted = sum(
        1 for contract in contracts
        if (contract.get('liquidity_coverage') or {}).get('quoted_bid_ask') is True
    )
    timestamp_reported = sum(
        1 for contract in contracts
        if (contract.get('quote_timestamp_coverage') or {}).get('reported') is True
    )
    return {
        'available': bool(contracts), 'contract_count': total,
        'liquidity_fields_complete': liquidity_reported,
        'quoted_bid_ask': quoted, 'timestamps_reported': timestamp_reported,
        'liquidity_fields_complete_pct': round(100 * liquidity_reported / total, 1) if total else 0.0,
        'quoted_bid_ask_pct': round(100 * quoted / total, 1) if total else 0.0,
        'timestamps_reported_pct': round(100 * timestamp_reported / total, 1) if total else 0.0,
        'read_only': True,
        'note': 'synthèse descriptive ; aucun contrat n’est reclassé ou exclu',
    }


def recommend(contracts):
    """Choisit LA meilleure option entre court / moyen / long (profil swing : moyen/long
    privilégiés, court seulement si excellent). Renvoie le contrat + une justification FR."""
    if not contracts:
        return None

    def sc(c):
        s = c['suit']
        s += {'moyen': 6, 'long': 4, 'court': -2}.get(c.get('bucket'), 0)   # sweet-spot swing
        s += (c.get('pop', 50) - 50) * 0.4                                  # favorise une bonne proba de profit
        s -= c.get('danger_n', 0) * 4                                       # pénalise fort le danger
        if 'earnings' in (c.get('flags') or []):
            s -= 5
        if c.get('theta_burn', 0) > 1.5:
            s -= 4
        return s

    best = max(contracts, key=sc)
    lab = {'court': 'échéance COURTE (~1-2 mois) — tactique, théta violent',
           'moyen': 'échéance MOYENNE (~3 mois) — le compromis idéal du swing',
           'long': 'échéance LONGUE (6-12M) — robuste, théta lent'}
    why = [lab.get(best.get('bucket'), '')]
    why.append(f"proba de profit {best.get('pop')}% · danger {best.get('danger')}")
    if 'earnings' in (best.get('flags') or []):
        why.append('couvre des résultats (risque IV-crush)')
    why.append(f"delta {best['delta']} · suitability {best['suit']}/100 · coût ${best['cost']:,}".replace(',', ' '))
    return {**best, 'why': ' · '.join(w for w in why if w)}


def _reco_score(c):
    """Score de recommandation (sweet-spot swing) — partagé par recommend/recommend_top."""
    s = c['suit']
    s += {'moyen': 6, 'long': 4, 'court': -2}.get(c.get('bucket'), 0)   # privilégie moyen/long
    s += (c.get('pop', 50) - 50) * 0.4                                  # bonne proba de profit
    s -= c.get('danger_n', 0) * 4                                       # pénalise le danger
    if 'earnings' in (c.get('flags') or []):
        s -= 5
    if c.get('theta_burn', 0) > 1.5:
        s -= 4
    return s


def recommend_top(contracts, n=2):
    """Renvoie les n MEILLEURES échéances classées (#1, #2…), chacune avec justification
    et un libellé de rang. Privilégie la DIVERSITÉ d'horizon (pas 2× le même bucket si évitable).
    C'est ce qui répond à « trop d'échéances, dis-moi laquelle est la meilleure » (la/les 2 meilleures)."""
    if not contracts:
        return []
    lab = {'court': 'échéance COURTE (~1-2 mois) — tactique, théta violent',
           'moyen': 'échéance MOYENNE (~3 mois) — le compromis idéal du swing',
           'long': 'échéance LONGUE (6-12M) — robuste, théta lent'}
    tier = {1: 'MEILLEUR CHOIX', 2: 'ALTERNATIVE', 3: '3e option'}
    ranked = sorted(contracts, key=_reco_score, reverse=True)
    picked, seen_buckets = [], set()
    for c in ranked:                                   # 1re passe : un seul par bucket (diversité)
        if c.get('bucket') in seen_buckets:
            continue
        seen_buckets.add(c.get('bucket'))
        picked.append(c)
        if len(picked) >= n:
            break
    if len(picked) < n:                                # 2e passe : compléter si pas assez de buckets
        for c in ranked:
            if c not in picked:
                picked.append(c)
            if len(picked) >= n:
                break
    out = []
    for i, best in enumerate(picked[:n], 1):
        why = [lab.get(best.get('bucket'), '')]
        why.append(f"proba de profit {best.get('pop')}% · danger {best.get('danger')}")
        if 'earnings' in (best.get('flags') or []):
            why.append('couvre des résultats (risque IV-crush)')
        why.append(f"delta {best['delta']} · suitability {best['suit']}/100 · coût ${best['cost']:,}".replace(',', ' '))
        out.append({**best, 'rank': i, 'tier': tier.get(i, f'#{i}'),
                    'why': ' · '.join(w for w in why if w)})
    return out
