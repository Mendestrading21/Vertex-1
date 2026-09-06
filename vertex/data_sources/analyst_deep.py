"""vertex.data_sources.analyst_deep — données analystes PROFONDES yfinance, à la demande.

Ces méthodes yfinance sont 1 appel réseau/titre et throttlées → JAMAIS en scan de
masse : on les charge quand l'utilisateur ouvre une fiche, avec un cache disque
(TTL 12 h). Chaque bloc est isolé (try/except) : une source qui casse n'empêche
pas les autres. Données publiques Yahoo — peuvent dater (étiqueté côté UI).

Blocs exposés :
  - eps_revisions : nb de révisions BPA à la hausse/baisse (7 j / 30 j) — momentum
    de révision, l'un des facteurs d'alpha les plus robustes.
  - eps_trend     : estimation BPA actuelle vs 30/90 j → sens de révision (%).
  - surprises     : historique battu/manqué (estimation vs réel) sur N trimestres.
  - next_earnings : prochaine date de résultats.
  - ratings_actions : relèvements/abaissements de notes récents (catalyseurs datés).
  - holders       : top détenteurs institutionnels (13F) + variation.
  - insider       : solde achats/ventes d'initiés récents.

⛔ Lecture seule — aucune écriture, aucun ordre.
"""
from __future__ import annotations

import json
import os
import time

from vertex.data_sources import revisions as _revisions
from vertex.data_sources.models import utc_now_iso

CACHE_PATH = os.environ.get('ANALYST_CACHE', 'analyst_cache.json')
TTL_S = 12 * 3600


def _num(v):
    try:
        f = float(v)
        return f if f == f else None      # écarte les NaN
    except Exception:
        return None


def _row(df, period):
    """Renvoie la ligne d'un DataFrame indexé par période ('0y', '0q', …) en dict."""
    try:
        if df is None or getattr(df, 'empty', True) or period not in df.index:
            return {}
        return {k: df.loc[period, k] for k in df.columns}
    except Exception:
        return {}


def _eps_revisions(t):
    try:
        r = _row(t.eps_revisions, '0y') or _row(t.eps_revisions, '0q')
        if not r:
            return None
        up30, down30 = _num(r.get('upLast30days')), _num(r.get('downLast30days'))
        up7, down7 = _num(r.get('upLast7days')), _num(r.get('downLast7Days'))
        net30 = (up30 or 0) - (down30 or 0)
        return {'up30': int(up30) if up30 is not None else None,
                'down30': int(down30) if down30 is not None else None,
                'up7': int(up7) if up7 is not None else None,
                'down7': int(down7) if down7 is not None else None,
                'net30': int(net30),
                'trend': 'up' if net30 > 0 else ('down' if net30 < 0 else 'flat')}
    except Exception:
        return None


def _eps_trend(t):
    try:
        r = _row(t.eps_trend, '0y')
        cur, d90 = _num(r.get('current')), _num(r.get('90daysAgo'))
        if cur is None or not d90:
            return None
        return {'current': round(cur, 3), 'd90': round(d90, 3),
                'revision_pct_90d': round((cur / d90 - 1) * 100, 1)}
    except Exception:
        return None


def _growth_fwd(t):
    try:
        r = _row(t.earnings_estimate, '0y')
        g = _num(r.get('growth'))
        return round(g * 100, 1) if g is not None else None
    except Exception:
        return None


def _surprises(t, n=8):
    try:
        df = t.get_earnings_dates(limit=n + 4)
        if df is None or getattr(df, 'empty', True):
            return None
        out, next_date, beats, total, acc = [], None, 0, 0, 0.0
        for idx, row in df.iterrows():
            est = _num(row.get('EPS Estimate'))
            act = _num(row.get('Reported EPS'))
            surp = _num(row.get('Surprise(%)'))
            dt = str(idx)[:10]
            if act is None:                       # trimestre à venir (pas encore publié)
                if next_date is None:
                    next_date = dt
                continue
            if total >= n:                        # fenêtre = N derniers trimestres publiés
                break
            total += 1
            if surp is not None:
                acc += surp
                if surp > 0:
                    beats += 1
            out.append({'date': dt, 'est': est, 'act': act, 'surprise': surp})
        summary = ({'beats': beats, 'total': total,
                    'avg': round(acc / total, 1) if total else None} if total else None)
        return {'history': out, 'summary': summary, 'next': next_date}
    except Exception:
        return None


def _ratings_actions(t, n=6):
    try:
        df = t.upgrades_downgrades
        if df is None or getattr(df, 'empty', True):
            return None
        df = df.sort_index(ascending=False).head(n)
        out = []
        for idx, row in df.iterrows():
            out.append({
                'date': str(idx)[:10],
                'firm': str(row.get('Firm') or '')[:40],
                'to': str(row.get('ToGrade') or ''),
                'from': str(row.get('FromGrade') or ''),
                'action': str(row.get('Action') or ''),
                'pt_action': str(row.get('priceTargetAction') or ''),
                'target': _num(row.get('currentPriceTarget')),
                'prior': _num(row.get('priorPriceTarget'))})
        return out or None
    except Exception:
        return None


def _holders(t, n=5):
    try:
        df = t.institutional_holders
        if df is None or getattr(df, 'empty', True):
            return None
        out = []
        for _, row in df.head(n).iterrows():
            out.append({'holder': str(row.get('Holder') or '')[:36],
                        'pct': _num(row.get('pctHeld')),
                        'change': _num(row.get('pctChange'))})
        return out or None
    except Exception:
        return None


def _insider(t):
    try:
        df = t.insider_transactions
        if df is None or getattr(df, 'empty', True):
            return None
        buys = sells = 0
        buy_sh = sell_sh = 0.0
        for _, row in df.head(30).iterrows():
            txt = (str(row.get('Transaction') or '') + ' ' + str(row.get('Text') or '')).lower()
            sh = _num(row.get('Shares')) or 0
            if 'buy' in txt or 'purchase' in txt or 'acqui' in txt:
                buys += 1; buy_sh += sh
            elif 'sale' in txt or 'sell' in txt or 'dispos' in txt:
                sells += 1; sell_sh += sh
        if not (buys or sells):
            return None
        return {'buys': buys, 'sells': sells,
                'net_shares': int(buy_sh - sell_sh),
                'bias': 'buy' if buy_sh > sell_sh else ('sell' if sell_sh > buy_sh else 'flat')}
    except Exception:
        return None


def _load_cache():
    try:
        with open(CACHE_PATH, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def _save_cache(cache):
    try:
        with open(CACHE_PATH, 'w', encoding='utf-8') as f:
            json.dump(cache, f)
    except Exception:
        pass


def depuis_cache(sym, ttl=TTL_S):
    """(entrée du cache ou None, fraîche ?) — AUCUN réseau. Sert à répondre à
    une requête utilisateur sans la faire attendre une collecte yfinance."""
    sym = (sym or '').upper()
    ent = _load_cache().get(sym) if sym else None
    frais = bool(ent) and (time.time() - ent.get('_ts', 0)) < ttl
    return ent, frais


def get(sym, ttl=TTL_S, force=False):
    """Renvoie le paquet analyste profond pour `sym` (caché TTL h). None si tout échoue."""
    sym = (sym or '').upper()
    if not sym:
        return None
    cache = _load_cache()
    ent = cache.get(sym)
    now = time.time()
    if ent and not force and (now - ent.get('_ts', 0)) < ttl:
        return ent
    try:
        import yfinance as yf
        t = yf.Ticker(sym)
    except Exception:
        return ent          # renvoie le cache périmé plutôt que rien
    pack = {
        '_ts': now,
        'eps_revisions': _eps_revisions(t),
        'eps_trend': _eps_trend(t),
        'growth_fwd': _growth_fwd(t),
        'surprises': _surprises(t),
        'ratings_actions': _ratings_actions(t),
        'holders': _holders(t),
        'insider': _insider(t),
    }
    # ne persiste que si au moins un bloc a des données (évite de cacher un échec total)
    if any(pack[k] for k in pack if k != '_ts'):
        #  CE QUI A CHANGE depuis la derniere observation. Sans cela,
        #  `cache[sym] = pack` ecrasait l'instantane precedent et Vertex n'avait
        #  aucun historique de revision — seulement celui que Yahoo veut bien
        #  fournir. Voir `data_sources/revisions`.
        vus = _revisions.diff(ent, pack, vu_a=utc_now_iso())
        pack['revisions_observees'] = _revisions.accumuler(
            (ent or {}).get('revisions_observees'), vus)
        pack['revisions_couverture'] = _revisions.couverture(
            pack['revisions_observees'])
        cache[sym] = pack
        _save_cache(cache)
        return pack
    return ent


__all__ = ['get']
