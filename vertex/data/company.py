"""
vertex/data/company.py — COUCHE ENTREPRISE (profil « lent », rafraîchi ~1×/semaine).

VERTEX sépare deux natures de données :
  • les VALEURS DE MARCHÉ (cours, technique, Grecs options) — EN DIRECT (IBKR/yfinance) ;
  • le PROFIL D'ENTREPRISE (activité, CEO, employés, segments de revenus, fondamentaux) —
    qui ne bouge pas d'un jour à l'autre → mis en cache sur disque et rafraîchi au plus
    UNE FOIS PAR SEMAINE.

Ce module ne fournit QUE le profil lent. Il se rafraîchit tout seul : si l'entrée en
cache a plus de 7 jours, on retente un fetch yfinance (sur la machine de l'utilisateur) ;
sinon on sert le cache. Sans réseau (cloud/démo), on retombe sur une couche curée pour
les grands noms — jamais de page vide, et l'état « rassis » est signalé à l'UI.

Segments de revenus et année de fondation sont CURÉS (les feeds gratuits ne les donnent
pas de façon fiable). Les concurrents sont dérivés automatiquement des pairs de la même
industrie dans l'univers scanné → couverture de TOUTES les entreprises.
"""

import json
import os
import time

from vertex.data_sources import rendement_dividende as _rdt

try:
    from vertex.data.universe import _INDUSTRY, _GICS_SECTOR, _GICS, UNIVERSE
except Exception:  # pragma: no cover
    _INDUSTRY, _GICS_SECTOR, _GICS, UNIVERSE = {}, {}, {}, []

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_CACHE = os.path.join(_ROOT, 'company_cache.json')
_WEEK = 7 * 24 * 3600
_SCHEMA_V = 3   # version du schéma de cache — bump quand on AJOUTE des champs (analystes, etc.)
                # → les entrées d'une version antérieure sont re-récupérées automatiquement

# ─── Segments de revenus (curés — % approximatifs du CA, ordre décroissant) ───
REVENUE_SEGMENTS = {
    'NVDA': [('Data Center', 78), ('Gaming', 12), ('Prof. Visualization', 3), ('Automobile', 2), ('Autres', 5)],
    'AAPL': [('iPhone', 52), ('Services', 22), ('Mac', 10), ('Wearables', 9), ('iPad', 7)],
    'MSFT': [('Intelligent Cloud', 43), ('Productivity', 32), ('Personal Computing', 25)],
    'GOOGL': [('Search', 57), ('YouTube', 11), ('Google Cloud', 12), ('Réseau', 9), ('Autres', 11)],
    'AMZN': [('Online Stores', 40), ('Third-party', 24), ('AWS', 17), ('Publicité', 9), ('Abonnements', 7), ('Autres', 3)],
    'META': [('Publicité', 96), ('Reality Labs', 2), ('Autres', 2)],
    'TSLA': [('Automobile', 79), ('Énergie & Stockage', 9), ('Services', 8), ('Autres', 4)],
    'AVGO': [('Semi-conducteurs', 58), ('Logiciels d\'infra', 42)],
    'AMD': [('Data Center', 50), ('Client', 30), ('Gaming', 12), ('Embedded', 8)],
    'NFLX': [('Streaming', 99), ('Autres', 1)],
    'CRM': [('Subscription & Support', 94), ('Services pro', 6)],
    'META': [('Publicité', 96), ('Reality Labs', 2), ('Autres', 2)],
    'JPM': [('Consumer Banking', 42), ('Corporate & Invest.', 34), ('Asset Mgmt', 13), ('Commercial', 11)],
    'V': [('Services', 34), ('Data Processing', 33), ('International', 27), ('Autres', 6)],
    'MA': [('Payment Network', 62), ('Value-added Services', 38)],
    'LLY': [('Diabète & Obésité', 55), ('Oncologie', 18), ('Immunologie', 14), ('Neuroscience', 13)],
    'COST': [('Alimentaire', 54), ('Non-alimentaire', 30), ('Services', 12), ('Abonnements', 4)],
    'HD': [('Bricolage / Maison', 100)],
    'UNH': [('UnitedHealthcare', 63), ('Optum', 37)],
    'XOM': [('Upstream', 38), ('Raffinage', 42), ('Chimie', 20)],
    'WMT': [('Walmart US', 68), ('International', 18), ('Sam\'s Club', 14)],
}

# ─── Année de fondation (curée — yfinance ne la donne pas de façon fiable) ───
FOUNDED = {
    'NVDA': 1993, 'AAPL': 1976, 'MSFT': 1975, 'GOOGL': 1998, 'AMZN': 1994, 'META': 2004,
    'TSLA': 2003, 'AVGO': 1991, 'AMD': 1969, 'NFLX': 1997, 'CRM': 1999, 'JPM': 1799,
    'V': 1958, 'MA': 1966, 'LLY': 1876, 'COST': 1983, 'HD': 1978, 'UNH': 1977,
    'XOM': 1870, 'WMT': 1962,
}

# ─── Profil curé (secours hors-ligne / démo — grands noms). Le fetch live yfinance
#     enrichit/rafraîchit ces valeurs sur la machine de l'utilisateur. ───
PROFILE_CURATED = {
    'NVDA': dict(activity='GPU & puces d\'accélération IA', model='Fabless · design de puces',
                 position='Dominante (~90% du marché IA)', ceo='Jensen Huang', employees=29600,
                 country='États-Unis', clients='Hyperscalers, cloud, OEM, gaming', moat='~90% du marché IA'),
    'AAPL': dict(activity='Électronique grand public & services', model='Matériel + écosystème de services',
                 position='Leader premium', ceo='Tim Cook', employees=161000, country='États-Unis',
                 clients='Grand public mondial', moat='Écosystème verrouillé, marque'),
    'MSFT': dict(activity='Logiciels, cloud (Azure) & IA', model='Licences + cloud par abonnement',
                 position='Leader cloud & productivité', ceo='Satya Nadella', employees=228000,
                 country='États-Unis', clients='Entreprises & grand public', moat='Coûts de migration élevés'),
    'GOOGL': dict(activity='Recherche, publicité, cloud, IA', model='Publicité ciblée + cloud',
                  position='Quasi-monopole de la recherche', ceo='Sundar Pichai', employees=182000,
                  country='États-Unis', clients='Annonceurs, entreprises', moat='Données & échelle'),
    'AMZN': dict(activity='E-commerce & cloud (AWS)', model='Marketplace + cloud + pub',
                 position='Leader e-commerce & cloud', ceo='Andy Jassy', employees=1500000,
                 country='États-Unis', clients='Grand public & entreprises', moat='Logistique & AWS'),
    'META': dict(activity='Réseaux sociaux & publicité', model='Publicité ciblée',
                 position='Leader social mondial', ceo='Mark Zuckerberg', employees=67000,
                 country='États-Unis', clients='Annonceurs', moat='Effets de réseau (milliards d\'utilisateurs)'),
    'TSLA': dict(activity='Véhicules électriques & énergie', model='Intégration verticale',
                 position='Leader VE premium', ceo='Elon Musk', employees=125000, country='États-Unis',
                 clients='Grand public', moat='Marque, batteries, logiciel'),
    'AVGO': dict(activity='Semi-conducteurs & logiciels d\'infra', model='Puces + logiciels par acquisitions',
                 position='Leader connectivité', ceo='Hock Tan', employees=37000, country='États-Unis',
                 clients='Data centers, télécoms, OEM', moat='Portefeuille de brevets'),
}

_LABELS = {'États-Unis': '🇺🇸 États-Unis'}


def _load():
    try:
        with open(_CACHE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def _save(cache):
    try:
        with open(_CACHE, 'w', encoding='utf-8') as f:
            json.dump(cache, f)
    except Exception:
        pass


_SECMED = {'ts': 0.0, 'data': {}}


def sector_medians(max_age=1800):
    """Médianes de valorisation par SECTEUR, calculées sur le cache entreprise RÉEL
    (pe / forward_pe / margin / rev_growth / roe). Mémoïsé 30 min. Alimente la
    comparaison « vs secteur » de la fiche avec de vraies données (plus de n/d)."""
    import statistics
    now = time.time()
    # memo sur le TIMESTAMP (pas la truthiness) : un résultat vide est aussi mémoïsé,
    # sinon chaque appel reparserait le cache entreprise (~1.4 Mo) → perf dégradée.
    if _SECMED['ts'] > 0 and now - _SECMED['ts'] < max_age:
        return _SECMED['data']
    groups = {}
    for v in _load().values():
        sec = v.get('sector')
        if sec:
            groups.setdefault(sec, []).append(v)

    def med(vals, mult=1.0, nd=3):
        vals = [x for x in vals if x is not None]
        return round(statistics.median(vals) * mult, 2) if len(vals) >= nd else None

    out = {}
    for sec, rows in groups.items():
        pes = [v['pe'] for v in rows if v.get('pe') and 0 < v['pe'] < 250]
        fwd = [v['forward_pe'] for v in rows if v.get('forward_pe') and 0 < v['forward_pe'] < 250]
        mg = [v['margin'] for v in rows if v.get('margin') is not None]
        gr = [v['rev_growth'] for v in rows if v.get('rev_growth') is not None]
        roe = [v['roe'] for v in rows if v.get('roe') is not None]
        if len(pes) >= 3 or len(mg) >= 3:
            out[sec] = {'median_pe': med(pes), 'median_fwd_pe': med(fwd),
                        'median_margin': med(mg, 100.0), 'median_growth': med(gr, 100.0),
                        'median_roe': med(roe, 100.0), 'n': len(rows)}
    _SECMED['ts'] = now
    _SECMED['data'] = out
    return out


def peers(sym, n=4):
    """Concurrents = pairs de la MÊME INDUSTRIE dans l'univers (sinon même secteur GICS)."""
    ind = _INDUSTRY_OF().get(sym)
    pool = []
    if ind:
        pool = [s for s, i in _INDUSTRY_OF().items() if i == ind and s != sym]
    if len(pool) < 2:
        sec = _GICS_SECTOR.get(sym)
        pool = [s for s in _GICS.get(sec, []) if s != sym]
    return pool[:n]


_IND_CACHE = {}


def _INDUSTRY_OF():
    """ticker → industrie (aplati depuis _INDUSTRY = {industrie: [tickers]})."""
    if not _IND_CACHE:
        for indus, syms in (_INDUSTRY or {}).items():
            for s in syms:
                _IND_CACHE[s] = indus
    return _IND_CACHE


def _quarters(tk, n=8):
    """Historique trimestriel (CA, résultat net) — [] si indisponible."""
    try:
        df = tk.quarterly_income_stmt
        if df is None or df.empty:
            return []
        out = []
        for col in list(df.columns)[:n]:
            rev = df.at['Total Revenue', col] if 'Total Revenue' in df.index else None
            ni = df.at['Net Income', col] if 'Net Income' in df.index else None
            if rev is None and ni is None:
                continue
            out.append({'q': str(col)[:10],
                        'rev': None if rev != rev or rev is None else round(float(rev)),
                        'ni': None if ni != ni or ni is None else round(float(ni))})
        out.reverse()                                  # chronologique
        return out
    except Exception:
        return []


def _fetch_profile(sym):
    """Profil via yfinance .info (lent/flaky — tourne sur la machine de l'utilisateur)."""
    import yfinance as yf
    tk = yf.Ticker(sym)
    info = tk.info or {}
    officers = info.get('companyOfficers') or []
    ceo = None
    for o in officers:
        t = (o.get('title') or '').lower()
        if 'ceo' in t or 'chief executive' in t:
            ceo = o.get('name')
            break
    if not ceo and officers:
        ceo = officers[0].get('name')
    return {
        'name': info.get('shortName') or info.get('longName'),
        'activity': info.get('industry'),
        'sector': info.get('sector'),
        'ceo': ceo,
        'employees': info.get('fullTimeEmployees'),
        'country': info.get('country'),
        'summary': info.get('longBusinessSummary'),
        'website': info.get('website'),
        # fondamentaux « lents » (cadence hebdo suffit)
        'pe': info.get('trailingPE'), 'forward_pe': info.get('forwardPE'),
        'peg': info.get('pegRatio'), 'margin': info.get('profitMargins'),
        'roe': info.get('returnOnEquity'), 'rev_growth': info.get('revenueGrowth'),
        'eps_growth': info.get('earningsGrowth'), 'fcf': info.get('freeCashflow'),
        'debt_to_ebitda': (round(info['totalDebt'] / info['ebitda'], 2)
                           if info.get('totalDebt') and info.get('ebitda') else None),
        'ebitda': info.get('ebitda'), 'beta': info.get('beta'),
        'earnings_date': (__import__('datetime').datetime.fromtimestamp(info['earningsTimestamp'])
                          .strftime('%Y-%m-%d') if info.get('earningsTimestamp') else None),
        'cash': info.get('totalCash'), 'debt': info.get('totalDebt'),
        'dividend': _rdt.valeur(info), 'mcap': info.get('marketCap'),
        # ── consensus analystes (type TipRanks — fourni par yfinance / IBKR) ──
        'rating': info.get('recommendationKey'), 'rating_mean': info.get('recommendationMean'),
        'n_analysts': info.get('numberOfAnalystOpinions'),
        'target_mean': info.get('targetMeanPrice'), 'target_high': info.get('targetHighPrice'),
        'target_low': info.get('targetLowPrice'), 'target_median': info.get('targetMedianPrice'),
        # ── historique trimestriel (8 trimestres : CA + résultat net) ──
        'quarters': _quarters(tk),
    }


def fraicheur(sym):
    """(présent dans le cache, frais) — AUCUN réseau. Sert à répondre à une
    requête utilisateur sans la faire attendre yfinance ni une traduction."""
    e = _load().get((sym or '').upper())
    frais = bool(e) and (time.time() - (e.get('ts') or 0) < _WEEK) and e.get('_v') == _SCHEMA_V
    return bool(e), frais


def get(sym, demo=False, allow_fetch=True, brief=False):
    """Profil d'entreprise (cache hebdo). Retourne un dict enrichi + méta de fraîcheur.

    - `demo=True`  : jamais de réseau, on sert la couche curée (cloud/démo).
    - rafraîchit en tâche de fond si l'entrée a > 7 jours et `allow_fetch`.
    - `brief=True` : enrichit l'explication métier via l'IA SI une clé est
      présente — résumé FR + « ce qu'elle vend / comment elle gagne / clients / moat »,
      persistés dans le cache. Sans clé : no-op (on garde la description d'origine).
    """
    sym = (sym or '').upper()
    cache = _load()
    e = cache.get(sym)
    # « frais » = récent ET du schéma courant (une version antérieure force le re-fetch)
    fresh = bool(e) and (time.time() - (e.get('ts') or 0) < _WEEK) and e.get('_v') == _SCHEMA_V

    if not fresh and allow_fetch and not demo:
        try:
            prof = _fetch_profile(sym)
            if prof.get('name') or prof.get('employees'):
                e = {'ts': time.time(), '_v': _SCHEMA_V,
                     **{k: v for k, v in prof.items() if v is not None}}
                cache[sym] = e
                _save(cache)
                fresh = True
        except Exception:
            pass

    # secours curé (jamais de vide)
    cur = PROFILE_CURATED.get(sym, {})
    base = dict(cur)
    if e:
        base.update({k: v for k, v in e.items() if v is not None})

    # ── explication métier : résumé FR (traduit 1×) + vend/gagne/clients/moat (IA si clé) ──
    if brief and base.get('summary') and not demo:
        try:
            from vertex.ai import briefs as _ai
            if not base.get('summary_fr'):               # traduit une seule fois (IA→Google→EN)
                fr = _ai.fr_desc(sym, base['summary'])
                if fr:
                    base['summary'] = fr
                base['summary_fr'] = True
            # libellé d'industrie (yfinance = anglais) → FR ; les titres curés sont déjà FR
            if base.get('activity') and not base.get('activity_fr') and not cur.get('activity'):
                base['activity'] = _ai.fr_label(base['activity'])
                base['activity_fr'] = True
            if not base.get('sells'):                    # vend/gagne/clients/moat : IA seulement
                bd = _ai.company_brief(sym, base['summary']) or {}
                for k_src, k_dst in (('sells', 'sells'), ('earns', 'model'),
                                     ('clients', 'clients'), ('moat', 'moat')):
                    if bd.get(k_src) and not base.get(k_dst):
                        base[k_dst] = bd[k_src]
            if e is not None:                            # persiste l'enrichissement sur disque
                for kk in ('summary', 'summary_fr', 'activity', 'activity_fr',
                           'sells', 'model', 'clients', 'moat'):
                    if base.get(kk) is not None:
                        e[kk] = base[kk]
                cache[sym] = e
                _save(cache)
        except Exception:
            pass

    country = base.get('country') or (cur.get('country'))
    out = {
        'symbol': sym,
        'name': base.get('name'),
        'activity': base.get('activity') or cur.get('activity') or _INDUSTRY_OF().get(sym),
        'model': base.get('model') or cur.get('model'),
        'sells': base.get('sells'),
        'position': base.get('position') or cur.get('position'),
        'ceo': base.get('ceo') or cur.get('ceo'),
        'employees': base.get('employees') or cur.get('employees'),
        'country': _LABELS.get(country, country),
        'clients': base.get('clients') or cur.get('clients'),
        'moat': base.get('moat') or cur.get('moat') or base.get('position'),
        'summary': base.get('summary'),
        'sector': base.get('sector') or _GICS_SECTOR.get(sym),
        'industry': _INDUSTRY_OF().get(sym),
        'founded': FOUNDED.get(sym),
        'segments': REVENUE_SEGMENTS.get(sym),
        'peers': peers(sym),
        # fondamentaux lents (None si non fetché — l'UI affiche « — »)
        'fundamentals': {k: base.get(k) for k in
                         ('pe', 'forward_pe', 'peg', 'margin', 'roe', 'rev_growth',
                          'eps_growth', 'fcf', 'cash', 'debt', 'dividend', 'mcap',
                          'beta', 'ebitda', 'debt_to_ebitda', 'earnings_date', 'quarters')},
        'analysts': {k: base.get(k) for k in
                     ('rating', 'rating_mean', 'n_analysts', 'target_mean',
                      'target_high', 'target_low', 'target_median')},
        'stale': not fresh,          # True → couche curée / cache > 7j (UI le signale)
        'updated': (e or {}).get('ts'),
    }
    return out


__all__ = ['get', 'peers', 'sector_medians', 'REVENUE_SEGMENTS', 'FOUNDED', 'PROFILE_CURATED']
