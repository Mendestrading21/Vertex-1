"""
vertex/engines/options_lab.py — OPTIONS RESEARCH CENTER (moteur).

Construit le payload complet de la page Options Lab : un centre de recherche
sur les options en 12 chapitres — cockpit marché, fiche de recherche, analyse
complète, plan de trading, visualisations, centre de stratégies, tops,
comparateur, comité, matrice de risques, timeline, et les lectures IA.

Tout est calculé depuis l'état de scan (`scan_state`) : le board d'options,
le détail technique par titre, la stratégie par horizons, le contexte marché.
Aucun réseau. Dégradation propre : une donnée absente devient None/'—',
jamais une invention.

⛔ Analyse uniquement — ce moteur produit des lectures, jamais des ordres.
"""

import math
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

#  Liquidité d'une ligne de board : UN SEUL accesseur pour tout le dépôt.
#  Ce moteur lisait `.get('spread_pct')` et `.get('vol')` à la main — les clés
#  du board de DÉMONSTRATION et des fixtures. Le producteur canonique
#  (`legacy_engine.build_board`) publie `spread` et `vol`, et marque les
#  valeurs IMPUTÉES (`liquidity_coverage`). Conséquence mesurée le 2026-09-06
#  sur un board à la forme RÉELLE (spread 6,5 sur 2/2 contrats) : la carte
#  « Meilleure liquidité » du comité rendait winner « — », value null, status
#  COMMITTEE_LIQUIDITY_UNAVAILABLE, pendant que « Meilleur volume » servait
#  675 dans la MÊME charge. Dégradation honnête, mais structurellement
#  inatteignable sur données réelles.
from vertex.options import board_fields as _bf

# ─── petits outils numériques (Black-Scholes léger, sans dépendance) ───

def _ncdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _npdf(x):
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def _bs(spot, strike, T, iv, right='CALL', r=0.045):
    """Prix Black-Scholes (par action). T en années, iv en décimal."""
    if T <= 0 or iv <= 0 or spot <= 0 or strike <= 0:
        pay = (spot - strike) if right == 'CALL' else (strike - spot)
        return max(0.0, pay)
    d1 = (math.log(spot / strike) + (r + iv * iv / 2) * T) / (iv * math.sqrt(T))
    d2 = d1 - iv * math.sqrt(T)
    if right == 'CALL':
        return spot * _ncdf(d1) - strike * math.exp(-r * T) * _ncdf(d2)
    return strike * math.exp(-r * T) * _ncdf(-d2) - spot * _ncdf(-d1)


def _r2(x, nd=2):
    try:
        return round(float(x), nd)
    except Exception:
        return None


def _pct(part, total):
    return round(part / total * 100) if total else None


def _best_leg(pick, key='m6'):
    d = pick.get('primary', 'CALL')
    legs = (pick.get('put') if d == 'PUT' else pick.get('call')) or []
    return next((l for l in legs if l.get('key') == key), legs[0] if legs else None)


# ─── sélection du contrat vedette ───

def _star(board, detail):
    """Le meilleur contrat du board : qualité d'abord, départagé par POP puis liquidité."""
    ranked = sorted([c for c in board if c.get('quality') is not None],
                    key=lambda c: (c.get('quality', 0), c.get('pop', 0), c.get('oi') or 0),
                    reverse=True)
    return ranked[0] if ranked else None


def _rr(c):
    """Risk/Reward d'un contrat : potentiel (%) rapporté à la prime à risque (100 %)."""
    pot = c.get('pot')
    return _r2(pot / 100.0, 2) if pot is not None else None


# ─── ① COCKPIT MARCHÉ ───

def _overview(board, detail, market, demo):
    def dte_value(contract):
        try:
            value = float(contract.get('dte'))
        except (TypeError, ValueError):
            return None
        return value if value >= 0 else None

    calls = [c for c in board if c.get('type') == 'CALL']
    puts = [c for c in board if c.get('type') == 'PUT']
    leaps = [c for c in board if dte_value(c) is not None and dte_value(c) >= 300]
    syms = sorted({c.get('sym') for c in board if c.get('sym')})
    ivs = [c['iv'] for c in board if c.get('iv') is not None]
    pops = [c['pop'] for c in board if c.get('pop') is not None]
    quals = [c['quality'] for c in board if c.get('quality') is not None]
    rrs = [r for r in (_rr(c) for c in board) if r is not None]
    ois = [c['oi'] for c in board if c.get('oi') is not None]
    vols = [v for v in (_bf.volume(c) for c in board) if v is not None]
    pcr = _r2(len(puts) / len(calls), 2) if calls else None
    # flux : proxy honnête = anomalies de volume du sous-jacent (vol_z du scan)
    flow = sorted(((s, (detail.get(s) or {}).get('vol_z')) for s in syms),
                  key=lambda x: (x[1] or 0), reverse=True)
    hot = [{'sym': s, 'vol_z': _r2(z, 1)} for s, z in flow if z is not None and z >= 1.2][:6]
    iv_avg = _r2(sum(ivs) / len(ivs), 1) if ivs else None
    pop_avg = _r2(sum(pops) / len(pops)) if pops else None
    vix = (market or {}).get('vix')
    roro = (market or {}).get('roro')
    regime = (market or {}).get('spy_regime')
    # lecture IA du marché des options
    bits = []
    if iv_avg is not None:
        bits.append(('IV médiane %s%% — les primes sont %s' %
                     (iv_avg, 'chères : privilégier les spreads et la vente de prime'
                      if iv_avg >= 45 else 'raisonnables : l\'achat sec de CALL/PUT reste jouable'
                      if iv_avg >= 30 else 'bon marché : acheter de la convexité coûte peu')))
    if pcr is not None:
        bits.append('put/call %s — le board penche %s' %
                    (pcr, 'côté couverture (prudence dominante)' if pcr >= 0.8
                     else 'côté haussier (recherche de convexité à la hausse)' if pcr <= 0.45
                     else 'de façon équilibrée'))
    if roro == 'RISK-OFF':
        bits.append('climat RISK-OFF : réduire la taille, allonger les échéances, éviter le théta court')
    elif regime == 'CHOP':
        bits.append('marché sans tendance : les stratégies de range (condor, credit spread) dominent le directionnel')
    elif roro == 'RISK-ON':
        bits.append('climat RISK-ON : le directionnel long (CALL, débit spread) a le vent dans le dos')
    if vix is not None:
        bits.append('VIX %s (%s)' % (_r2(vix, 1), 'stress — options chères, vendeurs avantagés'
                                     if vix >= 22 else 'calme — hedge bon marché' if vix <= 14 else 'zone neutre'))
    return {
        'contracts': len(board), 'tickers': len(syms), 'calls': len(calls),
        'puts': len(puts), 'leaps': len(leaps), 'pcr': pcr,
        'oi_total': sum(ois) if ois else None, 'vol_total': sum(vols) if vols else None,
        'iv_avg': iv_avg, 'pop_avg': pop_avg,
        'rr_avg': _r2(sum(rrs) / len(rrs), 2) if rrs else None,
        'score_avg': _r2(sum(quals) / len(quals)) if quals else None,
        'hot_flow': hot,
        'buckets': {b: sum(1 for c in board if c.get('bucket') == b)
                    for b in ('court', 'moyen', 'long')},
        'ai': '. '.join(bits) + '.' if bits else None,
        'source': 'démo (synthétique)' if demo else 'chaînes réelles',
    }


# ─── ② FICHE DE RECHERCHE (le contrat vedette) ───

def _research(star, board, detail, market, pick, company=None):
    if not star:
        return None
    sym = star['sym']
    d = detail.get(sym) or {}
    spot, be = star.get('spot'), star.get('be')
    move_needed = _r2((be / spot - 1) * 100, 1) if (spot and be) else None
    rr = _rr(star)
    pop, quality, iv = star.get('pop'), star.get('quality'), star.get('iv')
    leg = _best_leg(pick) if pick else None
    # décision : les seuils sont documentés dans la fiche elle-même
    roro = (market or {}).get('roro')
    if quality is not None and quality >= 62 and (pop or 0) >= 30 and roro != 'RISK-OFF':
        decision = {'verdict': 'ACHETER', 'tone': 'good',
                    'why': 'qualité %s/100, POP %s%% et climat porteur — le trade a un avantage mesurable.' % (quality, pop)}
    elif quality is not None and quality >= 45 and roro != 'RISK-OFF':
        decision = {'verdict': 'ATTENDRE', 'tone': 'warn',
                    'why': 'setup correct mais sans marge de sécurité — attendre un repli du titre ou de l\'IV avant d\'engager.'}
    else:
        decision = {'verdict': 'ÉVITER', 'tone': 'bad',
                    'why': ('climat risk-off : pas de nouveau risque directionnel.' if roro == 'RISK-OFF'
                            else 'le rapport qualité/coût ne justifie pas la prime — chercher ailleurs.')}
    alt = next((c for c in board if c.get('sym') != sym and c.get('quality') is not None), None)
    thesis = [t for t in [
        ('Pourquoi cette option — %s %s $%s (%sj) sort premier des %s contrats : qualité %s/100, '
         'la meilleure combinaison potentiel/liquidité/coût du board.'
         % (sym, star.get('type'), star.get('strike'), star.get('dte'), len(board), quality)),
        ('Pourquoi aujourd\'hui — le titre cote $%s ; le point mort est à $%s (%s%% à parcourir) '
         'pour un potentiel scénario cible de +%s%%.' % (spot, be, move_needed, star.get('pot'))
         if move_needed is not None else None),
        ('Pourquoi maintenant — IV %s%% (%s) et thêta %s%%/j : la fenêtre de coût est %s.'
         % (iv, 'chère' if (iv or 0) >= 50 else 'raisonnable',
            star.get('theta_burn'), 'défavorable — négocier le prix' if (iv or 0) >= 55 else 'correcte')
         if iv is not None else None),
        ('Pourquoi pas une autre — l\'alternative n°2 (%s %s $%s, qualité %s) affiche %s.'
         % (alt['sym'], alt.get('type'), alt.get('strike'), alt.get('quality'),
            'moins de potentiel ou plus de risque de thêta')
         if alt else None),
    ] if t]
    return {
        'sym': sym, 'name': (company or {}).get('name'),
        'type': star.get('type'), 'strike': star.get('strike'),
        'exp': star.get('exp'), 'dte': star.get('dte'),
        'premium': star.get('cost'), 'spot': spot, 'be': be,
        'move_needed_pct': move_needed, 'target': star.get('tgt'), 'pot': star.get('pot'),
        'score': quality, 'confidence': d.get('confidence'), 'pop': pop, 'rr': rr,
        'expected_return': leg.get('gain_exp') if leg else star.get('pot'),
        'capital': (leg.get('sizes') if leg else None),
        'hold': ('%s j' % leg['hold']) if leg and leg.get('hold') else None,
        'iv': iv, 'delta': star.get('delta'), 'theta_burn': star.get('theta_burn'),
        'oi': star.get('oi'), 'vol': _bf.volume(star), 'spread_pct': _bf.spread_pct(star),
        'sector': d.get('sector'), 'stock_score': d.get('score'), 'stock_verdict': d.get('verdict'),
        'thesis': thesis,
        'exec_summary': ('Vertex retient ce %s car son score composite (%s/100) domine le board : '
                         'momentum du sous-jacent, coût de la prime, probabilité de profit et liquidité '
                         'y sont simultanément parmi les meilleurs. Perte max = la prime ($%s).'
                         % (star.get('type'), quality, star.get('cost'))),
        'decision': decision,
        'by_horizon': _by_horizon(star, board),
        'runners': _runners(star, board),
    }


def _by_horizon(star, board):
    """La meilleure option par horizon (court / moyen / long) — priorité au titre vedette."""
    out = []
    for bk, lab in (('court', 'Court'), ('moyen', 'Moyen'), ('long', 'Long')):
        cs = [c for c in board if c.get('bucket') == bk and c.get('quality') is not None]
        if not cs:
            continue
        mine = [c for c in cs if c.get('sym') == star.get('sym')]
        c = max(mine or cs, key=lambda x: x.get('quality', 0))
        out.append({'bucket': lab, 'sym': c.get('sym'), 'type': c.get('type'),
                    'strike': c.get('strike'), 'dte': c.get('dte'), 'score': c.get('quality')})
    return out


def _runners(star, board, n=3):
    """Les dauphines : les meilleures options APRÈS celle du jour (titres distincts)."""
    key = (star.get('sym'), star.get('exp'), star.get('strike'), star.get('type'))
    seen = {star.get('sym')}
    out = []
    for c in sorted([c for c in board if c.get('quality') is not None],
                    key=lambda x: -(x.get('quality') or 0)):
        if (c.get('sym'), c.get('exp'), c.get('strike'), c.get('type')) == key or c.get('sym') in seen:
            continue
        seen.add(c.get('sym'))
        out.append({'sym': c.get('sym'), 'type': c.get('type'), 'strike': c.get('strike'),
                    'exp': (c.get('exp') or '')[:10], 'dte': c.get('dte'), 'score': c.get('quality'),
                    'pop': c.get('pop'), 'cost': c.get('cost'), 'pot': c.get('pot'),
                    'be': c.get('be')})
        if len(out) >= n:
            break
    return out


# ─── ③ ANALYSE COMPLÈTE (une seule grande section, 10 dimensions) ───

def _grade_row(key, label, icon, score, impact, importance, text, reco):
    return {'key': key, 'label': label, 'icon': icon,
            'score': None if score is None else max(0, min(100, round(score))),
            'impact': impact, 'importance': importance, 'text': text, 'reco': reco}


def _analysis(star, detail, market, sectors, overview):
    if not star:
        return []
    sym = star['sym']
    d = detail.get(sym) or {}
    mc = market or {}
    rows = []
    put = star.get('type') == 'PUT'

    def _dir(score):
        """Score directionnel lu dans le SENS du trade : un PUT profite de la faiblesse."""
        return None if score is None else (100 - score if put else score)
    # marché
    roro, reg, vix = mc.get('roro'), mc.get('spy_regime'), mc.get('vix')
    msc = 75 if roro == 'RISK-ON' and reg != 'CHOP' else 30 if roro == 'RISK-OFF' else 50
    rows.append(_grade_row('market', 'Contexte marché', '🌍', msc,
        'haussier' if msc >= 65 else 'baissier' if msc <= 35 else 'neutre', 'haute',
        'Régime %s · %s · VIX %s. %s' % (reg or '—', roro or '—', _r2(vix, 1) if vix else '—',
            'Le vent est dans le dos du directionnel long.' if msc >= 65 else
            'Le marché refuse le risque : le timing joue contre les acheteurs d\'options.' if msc <= 35 else
            'Marché mitigé : l\'avantage vient du titre, pas de l\'indice.'),
        'taille normale' if msc >= 65 else 'taille réduite, échéances longues' if msc <= 35 else 'sélectivité maximale'))
    # secteur
    sec = d.get('sector')
    srow = next((s for s in (sectors or []) if s.get('sector') == sec or s.get('name') == sec), None)
    ssc = None if not srow else max(0, min(100, 50 + (srow.get('avg_rs', 50) - 50) * 1.2))
    rows.append(_grade_row('sector', 'Contexte secteur', '🏭', ssc,
        'favorable' if (ssc or 0) >= 60 else 'défavorable' if ssc is not None and ssc <= 40 else 'neutre', 'moyenne',
        ('Secteur %s : RS moyen %s, momentum %s.' % (sec, srow.get('avg_rs'), srow.get('avg_change'))
         if srow else 'Secteur %s non classé dans la rotation du jour — analyse titre par titre.' % (sec or '—')),
        'surpondérer les leaders du secteur' if (ssc or 0) >= 60 else 'ne prendre que le meilleur titre du secteur'))
    # entreprise
    st_sc = d.get('score')
    rows.append(_grade_row('company', 'Contexte entreprise', '🏢', _dir(st_sc),
        'positif' if (_dir(st_sc) or 0) >= 60 else 'négatif' if _dir(st_sc) is not None and _dir(st_sc) <= 40 else 'neutre', 'haute',
        'Score quant du titre %s/100 · verdict %s · tendance %s.'
        % (st_sc if st_sc is not None else '—', d.get('verdict') or '—', d.get('trend') or '—')
        + (' Lu au sens PUT : la faiblesse du titre sert la thèse.' if put else ''),
        'le sous-jacent porte la thèse' if (st_sc or 0) >= 60 else 'exiger une décote sur la prime'))
    # technique
    rsi, adx, rs, pos52 = d.get('rsi'), d.get('adx'), d.get('rs'), d.get('pos52')
    tsc = None
    if rsi is not None:
        tsc = 50 + (min(rs or 50, 100) - 50) * 0.5 + ((adx or 20) - 20) * 0.8 - max(0, (rsi - 70)) * 1.5
    rows.append(_grade_row('technical', 'Analyse technique', '📐', _dir(tsc),
        'soutient' if (_dir(tsc) or 0) >= 60 else 'fragilise' if _dir(tsc) is not None and _dir(tsc) <= 40 else 'neutre', 'haute',
        'RSI %s · ADX %s · force relative %s · position 52 sem. %s%%. %s'
        % (rsi if rsi is not None else '—', adx if adx is not None else '—',
           rs if rs is not None else '—', pos52 if pos52 is not None else '—',
           d.get('chart_read') or ''),
        'entrer sur repli vers la MM20' if (rsi or 50) > 68 else 'l\'entrée directe est défendable'))
    # options (coût de la prime)
    iv = star.get('iv')
    iv_available = isinstance(iv, (int, float)) and not isinstance(iv, bool) and iv > 0
    osc = max(5, min(95, 100 - (iv - 25) * 1.6)) if iv_available else None
    option_row = _grade_row('options', 'Analyse options', '🧾', osc,
        'prime chère' if iv_available and iv >= 50 else 'prime correcte' if iv_available else 'coût de prime indisponible', 'haute',
        'IV %s%% · thêta %s%%/j · point mort +%s%% · delta %s.'
        % (iv if iv_available else '—', star.get('theta_burn'), _r2((star.get('be', 0) / star.get('spot', 1) - 1) * 100, 1),
           star.get('delta')),
        'préférer un spread pour neutraliser l\'IV' if iv_available and iv >= 50 else
        'l\'achat sec reste efficient' if iv_available else 'vérifier l\'IV avant toute interprétation du coût de prime')
    option_row['coverage'] = {'iv_available': iv_available,
                              'status': 'PREMIUM_COST_IV_AVAILABLE' if iv_available else 'PREMIUM_COST_IV_UNAVAILABLE',
                              'read_only': True}
    rows.append(option_row)
    # institutionnels (proxy honnête : anomalie de volume + accumulation)
    volz, acc = d.get('vol_z'), d.get('accumulation')
    volz_available = isinstance(volz, (int, float)) and not isinstance(volz, bool)
    isc = max(0, min(100, 50 + volz * 18 + (10 if acc else 0))) if volz_available else None
    institutional_score = _dir(isc)
    institutional = _grade_row('institutional', 'Institutionnels', '🏦', institutional_score,
        'accumulation' if institutional_score is not None and institutional_score >= 60 else
        'distribution' if institutional_score is not None and institutional_score <= 40 else
        'neutre' if institutional_score is not None else 'flux institutionnel indisponible', 'moyenne',
        ('Volume anormal z=%s · profil %s. Proxy : le flux réel par contrat n\'est pas publié ici.'
         % (_r2(volz, 1), 'accumulation' if acc else 'distribution' if d.get('distribution') else 'mixte')
         if volz_available else 'Flux institutionnel non quantifié — anomalie de volume indisponible, aucune imputation appliquée.'),
        'suivre les cassures accompagnées de volume' if institutional_score is not None else
        'vérifier l’anomalie de volume avant toute lecture institutionnelle')
    institutional['coverage'] = {'volume_anomaly_available': volz_available,
                                 'status': 'INSTITUTIONAL_SIGNAL_AVAILABLE' if volz_available else 'INSTITUTIONAL_SIGNAL_UNAVAILABLE',
                                 'read_only': True}
    rows.append(institutional)
    # momentum
    mom = d.get('mom')
    mom_available = isinstance(mom, (int, float)) and not isinstance(mom, bool)
    mmsc = max(0, min(100, 50 + mom * 5)) if mom_available else None
    momentum_score = _dir(mmsc)
    momentum = _grade_row('momentum', 'Momentum', '🚀', momentum_score,
        'porteur' if momentum_score is not None and momentum_score >= 60 else
        'essoufflé' if momentum_score is not None and momentum_score <= 40 else
        'neutre' if momentum_score is not None else 'momentum indisponible', 'moyenne',
        ('Momentum %s · perf 1 mois %s%% · 3 mois %s%%.'
         % (_r2(mom, 1), d.get('perf_m'), d.get('perf_q'))
         if mom_available else 'Momentum non quantifié — donnée indisponible, aucune imputation appliquée.'),
        'laisser courir tant que la MM20 tient' if momentum_score is not None else
        'vérifier le momentum avant toute lecture directionnelle')
    momentum['coverage'] = {'momentum_available': mom_available,
                            'status': 'MOMENTUM_SIGNAL_AVAILABLE' if mom_available else 'MOMENTUM_SIGNAL_UNAVAILABLE',
                            'read_only': True}
    rows.append(momentum)
    # liquidité
    oi, spr = star.get('oi'), _bf.spread_pct(star)
    _vol_star = _bf.volume(star)
    oi_available = isinstance(oi, (int, float)) and not isinstance(oi, bool) and oi >= 0
    spread_available = isinstance(spr, (int, float)) and not isinstance(spr, bool) and spr >= 0
    lsc = (max(5, min(95, (min(oi, 20000) / 20000 * 60) + (35 - min(spr, 12) * 3)))
           if oi_available and spread_available else None)
    liq = _grade_row('liquidity', 'Liquidité', '💧', lsc,
        'exécutable' if lsc is not None and lsc >= 55 else 'coûteuse' if lsc is not None else 'indisponible', 'haute',
        ('OI %s · volume %s · spread %s%%. Un spread large est un péage payé deux fois (entrée + sortie).'
         % (f"{oi:,}".replace(',', ' ') if oi_available else '—',
            f"{_vol_star:,}".replace(',', ' ') if _vol_star is not None else '—',
            spr if spread_available else '—') if lsc is not None else
         'Liquidité non quantifiée — OI ou spread indisponible, aucune imputation appliquée.'),
        'ordres à cours limité uniquement' if lsc is None or lsc < 55 else 'limite au milieu de fourchette')
    liq['coverage'] = {'oi_available': oi_available, 'spread_available': spread_available,
                       'status': 'LIQUIDITY_INPUT_AVAILABLE' if lsc is not None else 'LIQUIDITY_INPUT_UNAVAILABLE',
                       'read_only': True}
    rows.append(liq)
    # greeks
    delta = star.get('delta')
    delta_available = isinstance(delta, (int, float)) and not isinstance(delta, bool)
    gsc = max(10, min(90, abs(delta) * 130)) if delta_available else None
    greeks = _grade_row('greeks', 'Greeks', '🧮', gsc,
        'équilibrés' if gsc is not None and gsc >= 45 else
        'convexité pure' if gsc is not None else 'sensibilité grecque indisponible', 'moyenne',
        ('Delta %s (sensibilité directionnelle) · thêta %s%%/j (loyer du temps) · IV %s%% (prix de l\'incertitude).'
         % (delta, star.get('theta_burn'), star.get('iv'))
         if delta_available else 'Greeks non qualifiés — delta indisponible, aucune convexité n’est inférée.'),
        'delta 0.45-0.70 = le meilleur rapport exposition/décote' if delta_available else
        'vérifier le delta avant toute lecture de convexité')
    greeks['coverage'] = {'delta_available': delta_available,
                          'status': 'GREEKS_DELTA_AVAILABLE' if delta_available else 'GREEKS_DELTA_UNAVAILABLE',
                          'read_only': True}
    rows.append(greeks)
    # catalyseurs
    raw_dte = star.get('dte')
    dte_available = isinstance(raw_dte, (int, float)) and not isinstance(raw_dte, bool) and raw_dte > 0 and float(raw_dte).is_integer()
    dte = int(raw_dte) if dte_available else None
    csc = 65 if dte is not None and dte >= 120 else 40 if dte is not None and dte >= 45 else 25 if dte is not None else None
    rows.append(_grade_row('catalysts', 'Catalyseurs', '📅', csc,
        'temps pour soi' if csc is not None and csc >= 60 else 'course contre la montre' if csc is not None else 'échéance indisponible', 'moyenne',
        ('%s jours avant expiration — %s fenêtres de résultats trimestriels sur la durée de vie.'
         % (dte, max(0, round(dte / 91))) if dte is not None else
         'DTE indisponible — horizon vers l’expiration et résultats non qualifié.'),
        'sortir ou réduire avant chaque publication (risque d\'IV crush)'))
    return rows


# ─── ④ PLAN DE TRADING (timeline) ───

def _plan(star, research, pick):
    if not star:
        return None
    leg = _best_leg(pick) if pick else None
    ex = (leg or {}).get('exit') or {}
    spot, be = star.get('spot'), star.get('be')
    raw_dte = star.get('dte')
    dte_available = isinstance(raw_dte, (int, float)) and not isinstance(raw_dte, bool) and raw_dte > 0 and float(raw_dte).is_integer()
    steps = [
        {'key': 'entry', 'label': 'Entrée', 'icon': '🎯', 'tone': 'info',
         'text': ('Prime $%s (limite au milieu de fourchette).'
                  % ('%d' % star['cost'] if star.get('cost') is not None else '—'))
                 + (' Titre à $%s.' % ('%g' % spot) if spot else '')},
        {'key': 'valid', 'label': 'Validation', 'icon': '✅', 'tone': 'good',
         'text': ('La thèse est validée si le titre progresse vers le point mort ($%s) '
                  'dans le premier tiers de la durée de vie.' % ('%g' % be)) if be else
                 'La thèse est validée si le titre progresse vers le point mort dans '
                 'le premier tiers de la durée de vie.'},
        {'key': 'stop', 'label': 'Stop', 'icon': '🛑', 'tone': 'bad',
         'text': 'Sortie à −50 %% de la prime' + (' ($%s)' % ex.get('stop50') if ex.get('stop50') else '') +
                 ' — on ne moyenne jamais à la baisse une option.'},
        {'key': 'tp1', 'label': 'TP1 · +50 %', 'icon': '🥇', 'tone': 'good',
         'text': 'Sécuriser la moitié de la position' + (' vers $%s' % ex.get('tp50') if ex.get('tp50') else '') + '.'},
        {'key': 'tp2', 'label': 'TP2 · +100 %', 'icon': '🥈', 'tone': 'good',
         'text': 'La position restante devient gratuite' + (' vers $%s' % ex.get('tp100') if ex.get('tp100') else '') +
                 ' — laisser courir vers la cible $%s.' % star.get('tgt')},
        {'key': 'earn', 'label': 'Avant résultats', 'icon': '📢', 'tone': 'warn',
         'text': 'Réduire ou solder avant chaque publication : l\'IV crush peut effacer un gain latent en une nuit.'},
        {'key': 'exit', 'label': 'Sortie idéale', 'icon': '⌛', 'tone': 'warn',
         'text': ('Solder 2-3 semaines avant l\'expiration — le thêta s\'accélère en fin de vie.' if dte_available else
                  'Horizon de sortie avant expiration indisponible — DTE non reporté.')},
        {'key': 'expiry', 'label': 'Expiration', 'icon': '🏁', 'tone': 'mut',
         'text': ('%s — ne rien tenir au-delà.' % (star.get('exp') or '')[:10] if dte_available and star.get('exp') else
                  'Date d’expiration indisponible — aucune échéance n’est inférée.')},
    ]
    return {
        'steps': steps,
        'capital': (leg or {}).get('sizes') or research.get('capital'),
        'duration': ('%s j de détention visés' % leg['hold']) if leg and leg.get('hold') else None,
        'timeline_coverage': {'dte_available': dte_available,
                              'status': 'TRADE_PLAN_DTE_AVAILABLE' if dte_available else 'TRADE_PLAN_DTE_UNAVAILABLE',
                              'read_only': True},
        'mgmt': 'Risque par trade ≤ 1-2 % du capital. Jamais plus de 3 positions options simultanées corrélées.',
        'ai': ('Discipline avant conviction : le plan est écrit AVANT l\'entrée, la sortie sur stop est '
               'mécanique, les profits se prennent par moitiés. Le pire ennemi de l\'acheteur d\'options '
               'est l\'espoir en fin de vie du contrat.'),
    }


# ─── ⑤ VISUALISATIONS (données prêtes à tracer) ───

def _viz(star, board, detail, pick):
    if not star:
        return None

    def positive_number(value):
        return isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0

    spot = star.get('spot')
    strike = star.get('strike')
    iv_pct = star.get('iv')
    dte = star.get('dte')
    premium = star.get('cost')
    dte_valid = isinstance(dte, (int, float)) and not isinstance(dte, bool) and dte > 0 and float(dte).is_integer()
    coverage = {
        'spot_available': positive_number(spot),
        'strike_available': positive_number(strike),
        'iv_available': positive_number(iv_pct),
        'dte_available': dte_valid,
        'premium_available': positive_number(premium),
        'read_only': True,
    }
    if not all(coverage[key] for key in ('spot_available', 'strike_available', 'iv_available',
                                         'dte_available', 'premium_available')):
        coverage['status'] = 'OPTION_VIZ_INPUT_UNAVAILABLE'
        return {'unavailable': True,
                'reason': 'visualisations options indisponibles — intrants spot, strike, IV, DTE ou prime manquants',
                'coverage': coverage,
                'payoff': {'points': [], 'be': None, 'spot': None, 'target': None, 'prem': None},
                'cone': [], 'dist': {'points': [], 'be': None, 'spot': None, 'p_be': None},
                'theta': [], 'term': [], 'radar': {},
                'em': {'pct': None, 'lo': None, 'hi': None}, 'kelly': None,
                'gauges': {'pop': None, 'conviction': star.get('quality')}, 'heat': []}
    coverage['status'] = 'OPTION_VIZ_INPUT_AVAILABLE'
    dte = int(dte)
    right = star.get('type') if star.get('type') in ('CALL', 'PUT') else None
    if right is None:
        coverage.update({'right_available': False, 'status': 'OPTION_VIZ_INPUT_UNAVAILABLE'})
        return {'unavailable': True,
                'reason': 'visualisations options indisponibles — type de contrat absent ou invalide',
                'coverage': coverage,
                'payoff': {'points': [], 'be': None, 'spot': None, 'target': None, 'prem': None},
                'cone': [], 'dist': {'points': [], 'be': None, 'spot': None, 'p_be': None},
                'theta': [], 'term': [], 'radar': {},
                'em': {'pct': None, 'lo': None, 'hi': None}, 'kelly': None,
                'gauges': {'pop': None, 'conviction': star.get('quality')}, 'heat': []}
    coverage['right_available'] = True
    iv = iv_pct / 100.0
    T = dte / 365.0
    prem = premium / 100.0
    sgn = 1 if right == 'CALL' else -1
    # payoff à l'échéance (par contrat)
    lo, hi = spot * (1 - 2.2 * iv * math.sqrt(T)), spot * (1 + 2.2 * iv * math.sqrt(T))
    xs = [lo + (hi - lo) * i / 60 for i in range(61)]
    payoff = [{'x': _r2(x), 'y': _r2((max(0.0, sgn * (x - strike)) - prem) * 100)} for x in xs]
    # cône analytique (percentiles log-normaux) — le "Monte Carlo" exact, sans bruit
    steps = 24
    cone = []
    for i in range(steps + 1):
        t = T * i / steps
        s = iv * math.sqrt(t)
        mu = -0.5 * iv * iv * t
        row = {'d': round(dte * i / steps)}
        for name, z in (('p5', -1.645), ('p25', -0.674), ('p50', 0.0), ('p75', 0.674), ('p95', 1.645)):
            row[name] = _r2(spot * math.exp(mu + z * s))
        cone.append(row)
    # distribution de probabilité du prix à l'échéance + P(>BE)
    be = star.get('be')
    be_available = positive_number(be)
    sT = iv * math.sqrt(T)
    dist = [{'x': _r2(x), 'y': _r2(_npdf((math.log(x / spot) + 0.5 * sT * sT) / sT) / (x * sT), 6)}
            for x in xs if x > 0]
    p_be = _ncdf(sgn * (math.log(spot / be) - 0.5 * sT * sT) / sT) if be_available else None
    # décroissance thêta : valeur BS du contrat en fonction des jours restants
    theta_curve = [{'d': dd, 'v': _r2(_bs(spot, strike, dd / 365.0, iv, right) * 100)}
                   for dd in range(dte, -1, -max(1, dte // 30))]
    # structure IV par échéance (titre vedette vs médiane du board)
    def _med(vals):
        v = sorted(vals)
        return _r2(v[len(v) // 2], 1) if v else None
    term = []
    for bk, lab in (('court', '≤2 mois'), ('moyen', '~6 mois'), ('long', '12 mois+')):
        mine = [c['iv'] for c in board if c.get('sym') == star['sym'] and c.get('bucket') == bk and c.get('iv')]
        alls = [c['iv'] for c in board if c.get('bucket') == bk and c.get('iv')]
        term.append({'bucket': lab, 'sym_iv': _med(mine), 'board_iv': _med(alls)})
    # radar greeks (normalisé 0-100)
    leg = _best_leg(pick) if pick else None
    def reported_number(value, positive=False):
        return (isinstance(value, (int, float)) and not isinstance(value, bool)
                and (value > 0 if positive else True))
    delta = star.get('delta')
    gamma = (leg or {}).get('gamma')
    theta = star.get('theta_burn')
    vega = (leg or {}).get('vega')
    radar_coverage = {
        'delta': reported_number(delta),
        'gamma': reported_number(gamma),
        'theta': reported_number(theta),
        'vega': reported_number(vega),
        'iv': reported_number(star.get('iv'), positive=True),
    }
    radar = {
        'Delta': min(100, abs(delta) * 125) if radar_coverage['delta'] else None,
        'Gamma': min(100, gamma * 2500) if radar_coverage['gamma'] else None,
        'Theta': min(100, theta * 90) if radar_coverage['theta'] else None,
        'Vega': min(100, vega * 250) if radar_coverage['vega'] else None,
        'IV': min(100, star.get('iv') * 1.4) if radar_coverage['iv'] else None,
    }
    # Kelly (fraction optimale bornée) — seulement avec POP et potentiel reportés.
    pop_pct = star.get('pop')
    pot_pct = star.get('pot')
    pop_available = isinstance(pop_pct, (int, float)) and not isinstance(pop_pct, bool) and 0 <= pop_pct <= 100
    pot_available = isinstance(pot_pct, (int, float)) and not isinstance(pot_pct, bool) and pot_pct > 0
    kelly = None
    if pop_available and pot_available:
        pop = pop_pct / 100.0
        b = max(0.1, pot_pct / 100.0)
        kelly = max(0.0, min(0.15, pop - (1 - pop) / b))
    # heatmaps : meilleure ligne par titre × métriques
    best_by = {}
    for c in board:
        s = c.get('sym')
        if s and (s not in best_by or (c.get('quality') or 0) > (best_by[s].get('quality') or 0)):
            best_by[s] = c
    heat = [{'sym': s, 'score': c.get('quality'), 'pop': c.get('pop'), 'rr': _rr(c),
             'iv': c.get('iv'), 'flow': _r2((detail.get(s) or {}).get('vol_z'), 1)}
            for s, c in sorted(best_by.items(), key=lambda kv: -(kv[1].get('quality') or 0))]
    em_pct = star.get('em_pct')
    # Une amplitude nulle ne provient pas d'un calcul IV×racine(DTE) exploitable.
    # Ne pas présenter spot±0 comme une fourchette de marché observée.
    em_available = isinstance(em_pct, (int, float)) and not isinstance(em_pct, bool) and em_pct > 0
    return {
        'unavailable': False,
        'coverage': coverage,
        'payoff': {'points': payoff, 'be': be, 'spot': spot, 'target': star.get('tgt'), 'prem': star.get('cost')},
        'cone': cone,
        'dist': {'points': dist, 'be': be if be_available else None, 'spot': spot,
                 'p_be': _r2(p_be * 100, 1) if p_be is not None else None,
                 'coverage': {'break_even_available': be_available,
                              'status': 'BREAK_EVEN_AVAILABLE' if be_available else 'BREAK_EVEN_UNAVAILABLE',
                              'read_only': True}},
        'theta': theta_curve,
        'term': term,
        'radar': radar,
        'radar_coverage': {'available': radar_coverage,
                           'status': ('RADAR_GREEKS_AVAILABLE' if all(radar_coverage.values())
                                      else 'RADAR_GREEKS_PARTIAL'),
                           'read_only': True},
        'em': {'pct': em_pct if em_available else None,
               'lo': _r2(spot * (1 - em_pct / 100)) if em_available else None,
               'hi': _r2(spot * (1 + em_pct / 100)) if em_available else None,
               'coverage': {'available': em_available,
                            'status': 'EXPECTED_MOVE_AVAILABLE' if em_available else 'EXPECTED_MOVE_UNAVAILABLE',
                            'read_only': True}},
        'kelly': {'pct': _r2(kelly * 100, 1) if kelly is not None else None,
                  'note': ('fraction de Kelly bornée à 15 % — au-delà, la variance détruit le capital'
                           if kelly is not None else 'fraction Kelly indisponible — POP ou potentiel de gain non reporté'),
                  'coverage': {'pop_available': pop_available, 'potential_available': pot_available,
                               'status': 'KELLY_INPUT_AVAILABLE' if kelly is not None else 'KELLY_INPUT_UNAVAILABLE',
                               'read_only': True}},
        'gauges': {'pop': star.get('pop'), 'conviction': star.get('quality')},
        'heat': heat,
    }


# ─── ⑥ STRATEGY CENTER (16 stratégies notées en contexte) ───

_STRATS = [
    ('Covered Call', 'revenu', 'faible', 'modéré',
     'vous détenez 100 actions et l\'IV est élevée', 'forte conviction haussière (le gain est plafonné)',
     'range haussier calme, IV chère'),
    ('Cash Secured Put', 'revenu', 'modéré', 'modéré',
     'vous voulez acheter le titre moins cher en étant payé pour attendre', 'tendance baissière installée',
     'support solide, IV chère'),
    ('Bull Call Spread', 'directionnel', 'défini', 'modéré',
     'haussier avec IV chère — le spread neutralise le coût de la volatilité', 'mouvement explosif attendu (gain plafonné)',
     'tendance haussière, IV ≥ 45 %'),
    ('Bear Put Spread', 'directionnel', 'défini', 'modéré',
     'baissier avec un risque strictement défini', 'marché risk-on porteur',
     'cassure de support, secteur faible'),
    ('Calendar Spread', 'volatilité', 'défini', 'modéré',
     'IV courte chère vs longue — vendre le proche, garder le lointain', 'gros mouvement directionnel imminent',
     'range + événement lointain'),
    ('Diagonal Spread', 'hybride', 'défini', 'bon',
     'tendance douce + revenu de thêta sur le strike vendu', 'volatilité erratique',
     'tendance modérée, IV pentue'),
    ('Iron Condor', 'range', 'défini', 'limité',
     'marché en range avec IV élevée — vendre les deux ailes', 'tendance forte ou catalyseur proche',
     'CHOP + VIX élevé'),
    ('Iron Butterfly', 'range', 'défini', 'limité',
     'pari sur l\'immobilité autour d\'un strike pivot', 'titre volatil',
     'consolidation serrée post-mouvement'),
    ('Butterfly', 'ciblé', 'faible', 'élevé',
     'vous avez une cible de prix précise à l\'échéance', 'incertitude sur la destination',
     'aimant de prix identifiable (max pain, gros OI)'),
    ('Straddle', 'volatilité', 'élevé', 'élevé',
     'gros mouvement attendu, direction inconnue, IV encore basse', 'IV déjà gonflée (vous payez le crush)',
     'avant catalyseur binaire, IV < 35 %'),
    ('Strangle', 'volatilité', 'élevé', 'élevé',
     'même pari que le straddle, prime réduite, seuils plus lointains', 'IV chère',
     'compression de volatilité (squeeze)'),
    ('Poor Man\'s Covered Call', 'revenu', 'modéré', 'bon',
     'covered call avec 4× moins de capital (LEAPS deep ITM + vente courte)', 'titre sans tendance ni liquidité LEAPS',
     'tendance haussière longue, LEAPS liquides'),
    ('Protective Put', 'couverture', 'coût connu', 'assurance',
     'protéger un portefeuille actions sans le vendre', 'marché calme (l\'assurance coûte pour rien)',
     'risque macro identifié, VIX bas'),
    ('Collar', 'couverture', 'faible', 'borné',
     'protéger un gain latent à coût quasi nul (put financé par call vendu)', 'vous voulez garder tout le potentiel',
     'après un fort rallye, avant une zone de turbulence'),
    ('Debit Spread', 'directionnel', 'défini', 'modéré',
     'convexité directionnelle au coût maîtrisé — le geste par défaut quand l\'IV est chère', 'IV très basse (l\'achat sec paie plus)',
     'directionnel, IV moyenne à chère'),
    ('Credit Spread', 'revenu', 'défini', 'limité',
     'encaisser du thêta avec un risque borné, POP structurellement élevée', 'tendance contraire forte',
     'range ou tendance amie, IV chère'),
]


def _strategies(star, market):
    roro = (market or {}).get('roro')
    reg = (market or {}).get('spy_regime')
    iv = (star or {}).get('iv')
    iv_available = isinstance(iv, (int, float)) and not isinstance(iv, bool) and iv > 0
    iv_rich = iv >= 45 if iv_available else None
    trending = reg in ('TREND', 'UP') and roro != 'RISK-OFF'
    chop = reg == 'CHOP'
    out = []
    for name, kind, risk, potential, when, avoid, ctx in _STRATS:
        s = 50
        if kind == 'directionnel':
            s += (18 if trending else -12 if chop else 0) + (8 if 'Spread' in name and iv_rich is True else 0)
            if 'Bear' in name:
                s += (15 if roro == 'RISK-OFF' else -12 if trending else 0)
        if kind == 'range':
            s += (20 if chop else -15 if trending else 0) + (10 if iv_rich is True else -8 if iv_rich is False else 0)
        if kind == 'revenu':
            s += (14 if iv_rich is True else -10 if iv_rich is False else 0) + (6 if not chop else 0)
        if kind == 'volatilité':
            s += (-14 if iv_rich is True else 12 if iv_rich is False else 0)
        if kind == 'couverture':
            s += (18 if roro == 'RISK-OFF' else -4) + (8 if iv_rich is False else -4 if iv_rich is True else 0)
        if kind in ('hybride', 'ciblé'):
            s += 6 if trending else 0
        s = max(10, min(95, round(s)))
        out.append({'name': name, 'kind': kind, 'score': s, 'risk': risk, 'potential': potential,
                    'when': when, 'avoid': avoid, 'context': ctx,
                    'fit': 'recommandée' if s >= 68 else 'jouable' if s >= 50 else 'hors contexte',
                    'coverage': {'iv_available': iv_available,
                                 'status': 'IV_AVAILABLE' if iv_available else 'IV_UNAVAILABLE',
                                 'read_only': True}})
    out.sort(key=lambda x: -x['score'])
    best = out[0]
    iv_text = 'IV médiane %s%%' % iv if iv_available else 'IV indisponible'
    ai = ('Contexte du jour : %s, %s, %s. La structure la mieux payée est « %s » (%s/100) — %s'
          % (reg or 'régime inconnu', roro or 'risk indéterminé', iv_text, best['name'], best['score'], best['when']))
    return {'items': out, 'ai': ai,
            'coverage': {'iv_available': iv_available,
                         'status': 'IV_AVAILABLE' if iv_available else 'IV_UNAVAILABLE',
                         'read_only': True}}


# ─── ⑦ TOP OPPORTUNITÉS (listes premium) ───

def _row(c, note):
    return {'sym': c.get('sym'), 'type': c.get('type'), 'strike': c.get('strike'),
            'exp': (c.get('exp') or '')[:10], 'dte': c.get('dte'), 'score': c.get('quality'),
            'pop': c.get('pop'), 'rr': _rr(c), 'iv': c.get('iv'), 'note': note}


def _tops(board, detail):
    if not board:
        return []
    det = detail or {}

    def dte_value(contract):
        """DTE numérique non négatif réellement reporté, sinon None sans repli."""
        try:
            value = float(contract.get('dte'))
        except (TypeError, ValueError):
            return None
        return value if value >= 0 else None

    def take(pred, key, note_fn, n=5, rev=True):
        rows = [c for c in board if pred(c)]
        rows.sort(key=key, reverse=rev)
        return [_row(c, note_fn(c)) for c in rows[:n]]

    dz = lambda c: (det.get(c.get('sym')) or {})

    def valid_iv(contract):
        value = contract.get('iv')
        return isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0

    def valid_score(value):
        return isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= value <= 100

    def valid_number(value):
        return isinstance(value, (int, float)) and not isinstance(value, bool)

    valid_iv_contracts = sum(1 for contract in board if valid_iv(contract))
    top_lowiv_rows = take(valid_iv, lambda c: -c.get('iv'),
                          lambda c: 'IV %s%% — la convexité la moins chère' % c.get('iv'))

    def eligible_top_long(contract):
        return (dte_value(contract) is not None and dte_value(contract) >= 150
                and valid_score(contract.get('quality')) and valid_score(contract.get('pop')))

    top_long_eligible_contracts = sum(1 for contract in board if eligible_top_long(contract))
    top_long_rows = take(eligible_top_long,
                         lambda c: c.get('quality') + c.get('pop') * 0.3,
                         lambda c: 'qualité %s + POP %s%% sur %s j' %
                         (c.get('quality'), c.get('pop'), c.get('dte')))
    lists = [
        ('top_call', '📈 TOP CALL', take(lambda c: c.get('type') == 'CALL', lambda c: c.get('quality') or 0,
         lambda c: 'qualité %s — le meilleur profil haussier du board' % c.get('quality'))),
        ('top_put', '📉 TOP PUT', take(lambda c: c.get('type') == 'PUT', lambda c: c.get('quality') or 0,
         lambda c: 'protection/pari baissier le mieux noté' )),
        ('top_leaps', '🏛️ TOP LEAPS', take(lambda c: dte_value(c) is not None and dte_value(c) >= 300, lambda c: c.get('quality') or 0,
         lambda c: '%s j — le temps travaille pour la thèse' % c.get('dte'))),
        ('top_momentum', '🚀 TOP Momentum', take(
         lambda c: valid_number(dz(c).get('mom')) and dz(c).get('mom') > 0,
         lambda c: dz(c).get('mom'), lambda c: 'momentum titre %s' % _r2(dz(c).get('mom'), 1))),
        ('top_breakout', '💥 TOP Breakout', take(lambda c: dz(c).get('breakout'),
         lambda c: c.get('quality') or 0, lambda c: 'cassure détectée sur le sous-jacent')),
        ('top_swing', '🌊 TOP Swing', take(lambda c: c.get('swing_ok'),
         lambda c: c.get('swing_ret') or 0, lambda c: 'projection swing +%s%%' % c.get('swing_ret'))),
        ('top_lowiv', '❄️ TOP Low IV', top_lowiv_rows),
        ('top_pop', '🎯 TOP High POP', take(lambda c: valid_score(c.get('pop')),
         lambda c: c.get('pop'), lambda c: 'POP %s%% — probabilité de profit maximale' % c.get('pop'))),
        ('top_rr', '⚖️ TOP Risk/Reward', take(lambda c: _rr(c) is not None,
         lambda c: _rr(c) or 0, lambda c: 'R:R %s — asymétrie maximale' % _rr(c))),
        ('top_flow', '🐋 TOP Flux (volume anormal)', take(
         lambda c: valid_number(dz(c).get('vol_z')) and dz(c).get('vol_z') >= 1.0,
         lambda c: dz(c).get('vol_z'), lambda c: 'volume titre z=%s' % _r2(dz(c).get('vol_z'), 1))),
        ('top_long', '🧭 TOP Long terme', top_long_rows),
        ('top_short', '⚡ TOP Court terme', take(lambda c: dte_value(c) is not None and dte_value(c) <= 60,
         lambda c: c.get('quality') or 0, lambda c: 'tactique %s j — thêta agressif, taille réduite' % c.get('dte'))),
        ('top_defensive', '🛡️ TOP Défensif', take(
            lambda c: c.get('type') == 'PUT' or (dz(c).get('sector') or '') in
            ('Santé', 'Consommation de base', 'Services publics', 'Healthcare', 'Utilities', 'Consumer Staples'),
            lambda c: c.get('quality') or 0, lambda c: 'profil défensif (secteur/PUT de couverture)')),
    ]
    result = []
    for key, label, rows in lists:
        # La liste IV reste servie même vide : son indisponibilité ne doit pas
        # être confondue avec l’absence d’opportunité de convexité bon marché.
        if not rows and key not in ('top_lowiv', 'top_long'):
            continue
        entry = {'key': key, 'label': label, 'rows': rows}
        if key == 'top_lowiv':
            entry['coverage'] = {
                'iv_valid_contracts': valid_iv_contracts,
                'iv_invalid_or_missing_contracts': len(board) - valid_iv_contracts,
                'status': 'TOP_LOW_IV_AVAILABLE' if valid_iv_contracts else 'TOP_LOW_IV_UNAVAILABLE',
                'read_only': True,
            }
        if key == 'top_long':
            entry['coverage'] = {
                'quality_and_pop_eligible_contracts': top_long_eligible_contracts,
                'quality_or_pop_unavailable_contracts': sum(
                    1 for contract in board
                    if dte_value(contract) is not None and dte_value(contract) >= 150
                    and not (valid_score(contract.get('quality')) and valid_score(contract.get('pop')))
                ),
                'status': 'TOP_LONG_COMPOSITE_AVAILABLE' if top_long_eligible_contracts else 'TOP_LONG_COMPOSITE_UNAVAILABLE',
                'read_only': True,
            }
        result.append(entry)
    return result


# ─── ⑧ COMPARATEUR (véhicules sur le titre vedette) ───

def _comparator(star, pick, detail):
    if not star:
        return None
    sym = star['sym']
    spot = star.get('spot')
    iv_pct = star.get('iv')
    spot_available = isinstance(spot, (int, float)) and not isinstance(spot, bool) and spot > 0
    iv_available = isinstance(iv_pct, (int, float)) and not isinstance(iv_pct, bool) and iv_pct > 0
    if not spot_available or not iv_available:
        return {'symbol': sym, 'unavailable': True, 'rows': [],
                'reason': 'matrice de véhicules indisponible — spot ou IV non reporté',
                'coverage': {'spot_available': spot_available, 'iv_available': iv_available,
                             'status': 'VEHICLE_MATRIX_INPUT_UNAVAILABLE', 'read_only': True}}
    iv = iv_pct / 100.0
    d = detail.get(sym) or {}
    leg6 = _best_leg(pick, 'm6') if pick else None
    leg12 = _best_leg(pick, 'm12') if pick else None
    T6 = 0.5
    rows = []

    def metric(value, lower=0.0, upper=None):
        valid = isinstance(value, (int, float)) and not isinstance(value, bool) and value >= lower
        if upper is not None:
            valid = valid and value <= upper
        return value if valid else None

    def add(name, cost, maxloss, maxgain, pop, be, note, pop_observed=False, break_even_observed=False):
        rows.append({'name': name, 'cost': _r2(cost), 'maxloss': _r2(maxloss),
                     'maxgain': maxgain if isinstance(maxgain, str) else _r2(maxgain),
                     'pop': _r2(pop), 'be': _r2(be), 'note': note,
                     'coverage': {'pop_available': pop is not None,
                                  'pop_observed': pop_observed and pop is not None,
                                  'break_even_available': be is not None,
                                  'break_even_observed': break_even_observed and be is not None,
                                  'read_only': True}})

    add('Action (100 titres)', spot * 100, spot * 100, 'illimité', None,
        spot, 'delta 1, pas de thêta, pas d\'échéance — la référence',
        break_even_observed=True)
    c_atm = _bs(spot, spot, T6, iv, 'CALL') * 100
    call_pop = metric(star.get('pop'), upper=100)
    call_be = metric((leg6 or {}).get('breakeven'))
    add('CALL 6 mois (ATM)', (leg6 or {}).get('premium', 0) * 100 or c_atm, c_atm if not leg6 else leg6['premium'] * 100,
        'illimité', call_pop, call_be, 'convexité maximale — perte bornée à la prime',
        pop_observed=True, break_even_observed=True)
    p_atm = _bs(spot, spot, T6, iv, 'PUT') * 100
    add('PUT 6 mois (ATM)', p_atm, p_atm, spot * 100 - p_atm, None,
        None, 'pari baissier ou assurance du portefeuille')
    c_leaps = _bs(spot, spot * 0.85, 1.2, iv * 0.9, 'CALL') * 100
    leaps_be = metric((leg12 or {}).get('breakeven'))
    add('LEAPS 12 mois+ (delta 0.8)', (leg12 or {}).get('premium', 0) * 100 or c_leaps, c_leaps if not leg12 else leg12['premium'] * 100,
        'illimité', None, leaps_be, 'quasi-action à 40 % du prix — le temps pèse peu',
        break_even_observed=True)
    cc_prem = _bs(spot, spot * 1.05, 0.12, iv, 'CALL') * 100
    add('Covered Call (45 j)', spot * 100 - cc_prem, spot * 100 - cc_prem, cc_prem + spot * 5,
        None, None, 'revenu %s$/mois env. — gain plafonné à +5 %%' % _r2(cc_prem * 0.66))
    csp_prem = _bs(spot, spot * 0.95, 0.12, iv, 'PUT') * 100
    add('Cash Secured Put (45 j)', spot * 95, spot * 95 - csp_prem, csp_prem, None,
        None, 'être payé %s$ pour acheter 5 %% moins cher' % _r2(csp_prem))
    bcs = (_bs(spot, spot, T6, iv, 'CALL') - _bs(spot, spot * 1.10, T6, iv, 'CALL')) * 100
    add('Bull Call Spread (6 mois)', bcs, bcs, spot * 10 - bcs, None,
        None, 'coût réduit de ~40 %, gain plafonné à +10 %')
    bps = (_bs(spot, spot, T6, iv, 'PUT') - _bs(spot, spot * 0.90, T6, iv, 'PUT')) * 100
    add('Bear Put Spread (6 mois)', bps, bps, spot * 10 - bps, None,
        None, 'baissier à risque défini')
    # verdict
    trending = str(d.get('trend') or '').upper() in ('UP', 'HAUSSE', 'TREND') or (d.get('score') or 0) >= 60
    iv_rich = iv * 100 >= 45
    if trending and not iv_rich:
        v = 'CALL 6 mois : tendance amie + prime raisonnable, la convexité sèche est le meilleur rapport gain/complexité.'
    elif trending and iv_rich:
        v = 'Bull Call Spread : la tendance est amie mais l\'IV est chère — le spread rend la prime au marché.'
    elif not trending and iv_rich:
        v = 'Cash Secured Put / Credit Spread : sans tendance nette, mieux vaut encaisser la prime chère que la payer.'
    else:
        v = 'Action ou LEAPS : sans avantage optionnel clair, rester simple — le sous-jacent d\'abord.'
    return {'sym': sym, 'rows': rows, 'verdict': v,
            'note': 'primes théoriques Black-Scholes (estimation) quand la chaîne réelle n\'est pas chargée'}


# ─── ⑨ COMITÉ VERTEX (le grand tableau des « meilleurs ») ───

def _committee(board, detail, tops, star):
    if not board:
        return []
    det = detail or {}
    dz = lambda c: (det.get(c.get('sym')) or {})

    def dte_value(contract):
        try:
            value = float(contract.get('dte'))
        except (TypeError, ValueError):
            return None
        return value if value >= 0 else None

    def best(pred, key):
        cs = [c for c in board if pred(c)]
        return max(cs, key=key) if cs else None

    def fmt(c):
        return '%s %s $%s · %sj' % (c['sym'], c.get('type'), c.get('strike'), c.get('dte')) if c else '—'

    stocks = sorted(det.items(), key=lambda kv: -(kv[1].get('score') or 0))
    rows = []

    def add(title, c, why, val=None, coverage=None):
        rows.append({'title': title, 'winner': fmt(c) if not isinstance(c, str) else c,
                     'value': val, 'why': why, 'coverage': coverage})

    if stocks:
        s0 = stocks[0]
        add('Meilleure action', s0[0], 'score quant %s/100 — %s' % (s0[1].get('score'), s0[1].get('verdict') or ''),
            '%s/100' % s0[1].get('score'))
    add('Meilleure option', star, 'qualité composite maximale du board', '%s/100' % (star or {}).get('quality'))
    c = best(lambda x: x.get('type') == 'CALL', lambda x: x.get('quality') or 0)
    add('Meilleur CALL', c, 'le profil haussier le mieux noté', '%s/100' % (c or {}).get('quality'))
    c = best(lambda x: x.get('type') == 'PUT', lambda x: x.get('quality') or 0)
    add('Meilleur PUT', c, 'la meilleure protection / pari baissier', '%s/100' % (c or {}).get('quality') if c else None)
    c = best(lambda x: dte_value(x) is not None and dte_value(x) >= 300, lambda x: x.get('quality') or 0)
    add('Meilleur LEAPS', c, 'la conviction longue la moins dépendante du timing', '%s j' % (c or {}).get('dte') if c else None)
    c = best(lambda x: _rr(x) is not None, lambda x: _rr(x) or 0)
    add('Meilleur Risk/Reward', c, 'asymétrie gain/perte maximale', 'R:R %s' % _rr(c) if c else None)
    c = best(lambda x: x.get('pop') is not None, lambda x: x.get('pop') or 0)
    add('Meilleure POP', c, 'probabilité de profit la plus haute', '%s%%' % (c or {}).get('pop') if c else None)
    c = best(lambda x: True, lambda x: dz(x).get('mom') or -99)
    add('Meilleur momentum', c, 'le sous-jacent le plus dynamique', _r2(dz(c).get('mom'), 1) if c else None)
    def liquidity_ready(contract):
        oi, spread = contract.get('oi'), _bf.spread_pct(contract)
        return (isinstance(oi, (int, float)) and not isinstance(oi, bool) and oi >= 0
                and isinstance(spread, (int, float)) and not isinstance(spread, bool) and spread >= 0)

    c = best(liquidity_ready, lambda x: x.get('oi') - _bf.spread_pct(x) * 1000)
    add('Meilleure liquidité', c,
        'OI massif + spread serré = exécution propre' if c else 'Liquidité non classable — OI ou spread indisponible.',
        (f"OI {c.get('oi'):,}".replace(',', ' ') if c and c.get('oi') is not None else None),
        {'available': c is not None,
         'status': 'COMMITTEE_LIQUIDITY_AVAILABLE' if c else 'COMMITTEE_LIQUIDITY_UNAVAILABLE',
         'read_only': True})
    c = best(lambda x: _bf.volume(x) is not None, lambda x: _bf.volume(x) or 0)
    _vol_c = _bf.volume(c)
    add('Meilleur volume', c, 'l\'activité du jour la plus dense', (f"{_vol_c:,}".replace(',', ' ') if _vol_c is not None else None))
    c = best(lambda x: True, lambda x: dz(x).get('vol_z') or -9)
    add('Meilleur flux', c, 'volume anormal sur le sous-jacent (z-score)', 'z=%s' % _r2(dz(c).get('vol_z'), 1) if c else None)
    # secteur
    sec_sc = {}
    for s, dd in det.items():
        if dd.get('sector') and dd.get('score') is not None:
            sec_sc.setdefault(dd['sector'], []).append(dd['score'])
    if sec_sc:
        bs_ = max(sec_sc.items(), key=lambda kv: sum(kv[1]) / len(kv[1]))
        add('Meilleur secteur', bs_[0], 'score moyen %s sur %s titres' % (_r2(sum(bs_[1]) / len(bs_[1])), len(bs_[1])))
    c = best(lambda x: x.get('swing_ok'), lambda x: x.get('swing_ret') or 0)
    add('Meilleur trade swing', c, 'projection swing la plus payée', '+%s%%' % (c or {}).get('swing_ret') if c else None)
    c = best(lambda x: dte_value(x) is not None and dte_value(x) >= 150, lambda x: (x.get('quality') or 0) + (x.get('pop') or 0) * 0.3)
    add('Meilleur long terme', c, 'qualité + POP sur échéance longue', None)
    c = best(lambda x: dte_value(x) is not None and dte_value(x) <= 60, lambda x: x.get('quality') or 0)
    add('Meilleur court terme', c, 'le tactique le mieux noté — taille réduite obligatoire', None)
    c = best(lambda x: True, lambda x: (x.get('quality') or 0) + (dz(x).get('confidence') or 0) * 0.3)
    add('Plus forte conviction', c, 'qualité du contrat × confiance du scan sur le titre', None)
    c = best(lambda x: True, lambda x: x.get('pot') or 0)
    add('Plus gros potentiel', c, 'scénario cible maximal', '+%s%%' % (c or {}).get('pot') if c else None)
    c = best(lambda x: True, lambda x: (x.get('danger_n') or 0) * 100 + (x.get('theta_burn') or 0) * 10)
    add('Plus gros risque', c, '%s drapeaux de danger + thêta %s%%/j — à ne toucher qu\'en taille minuscule'
        % ((c or {}).get('danger_n'), (c or {}).get('theta_burn')), None)
    add('Opportunité de la semaine', star, 'la synthèse du comité : le meilleur rapport signal/prix du moment',
        '%s/100' % (star or {}).get('quality'))
    return rows


# ─── ⑩ MATRICE DE RISQUES ───

def _risks(star, market):
    def available_number(value, strictly_positive=False):
        return (isinstance(value, (int, float)) and not isinstance(value, bool)
                and (value > 0 if strictly_positive else value >= 0))

    iv = (star or {}).get('iv')
    dte = (star or {}).get('dte')
    spr = _bf.spread_pct(star)
    iv_available = available_number(iv, strictly_positive=True)
    dte_available = available_number(dte, strictly_positive=True)
    spread_available = available_number(spr)
    vix = (market or {}).get('vix')
    vix_available = available_number(vix, strictly_positive=True)
    roro = (market or {}).get('roro')

    def lvl(x, lo, hi):
        return 'ÉLEVÉ' if x >= hi else 'MOYEN' if x >= lo else 'FAIBLE'

    theta_burn = (star or {}).get('theta_burn')
    theta_available = isinstance(theta_burn, (int, float)) and not isinstance(theta_burn, bool) and theta_burn >= 0
    theta_l = lvl(theta_burn * 100, 30, 70) if theta_available else 'INCONNU'
    return [
        {'name': 'Thêta (érosion du temps)', 'level': theta_l,
         'impact': ('perte quotidienne certaine' if theta_available else 'érosion non quantifiée — donnée thêta indisponible'),
         'proba': ('100 % — c\'est un loyer, pas un aléa' if theta_available else 'INCONNUE — aucune valeur de thêta reportée'),
         'fix': 'échéances ≥ 4-6 mois, sortie 2-3 semaines avant expiration',
         'coverage': {'available': theta_available,
                      'status': 'THETA_BURN_AVAILABLE' if theta_available else 'THETA_BURN_UNAVAILABLE',
                      'read_only': True}},
        {'name': 'IV crush', 'level': lvl(iv, 40, 55) if iv_available else 'INCONNU',
         'impact': 'la prime peut fondre de 20-40 % en une nuit' if iv_available else 'sensibilité IV non quantifiée — IV indisponible',
         'proba': 'quasi certaine après chaque publication de résultats' if iv_available else 'INCONNUE — IV non reportée',
         'fix': 'réduire/solder avant les résultats, ou jouer des spreads (vega neutralisé)',
         'coverage': {'available': iv_available, 'status': 'IV_AVAILABLE' if iv_available else 'IV_UNAVAILABLE', 'read_only': True}},
        {'name': 'Liquidité', 'level': lvl(spr, 4, 8) if spread_available else 'INCONNU', 'impact': 'impossible de sortir au juste prix',
         'proba': 'permanente sur les strikes exotiques',
         'fix': 'OI > 500, spread < 5 %, ordres limités uniquement',
         'coverage': {'available': spread_available, 'status': 'SPREAD_AVAILABLE' if spread_available else 'SPREAD_UNAVAILABLE', 'read_only': True}},
        {'name': 'Spread (fourchette)', 'level': lvl(spr, 3, 7) if spread_available else 'INCONNU',
         'impact': 'péage payé à l\'entrée ET à la sortie' if spread_available else 'coût de fourchette non quantifié — spread indisponible',
         'proba': 'systématique' if spread_available else 'INCONNUE — spread non reporté',
         'fix': 'négocier au milieu de fourchette, jamais « au marché »',
         'coverage': {'available': spread_available, 'status': 'SPREAD_AVAILABLE' if spread_available else 'SPREAD_UNAVAILABLE', 'read_only': True}},
        {'name': 'Macro (taux, dollar)', 'level': 'ÉLEVÉ' if roro == 'RISK-OFF' else 'MOYEN',
         'impact': 'compression des multiples → gap baissier des sous-jacents',
         'proba': 'élevée en période de resserrement', 'fix': 'taille réduite + PUT de couverture indiciel'},
        {'name': 'Gap overnight', 'level': 'MOYEN', 'impact': 'le stop ne protège pas pendant la nuit',
         'proba': 'quelques fois par trimestre', 'fix': 'la taille EST le stop : risque max = prime, dimensionner en conséquence'},
        {'name': 'Fed / CPI / NFP',
         'level': 'ÉLEVÉ' if vix_available and vix >= 20 else 'MOYEN' if vix_available else 'INCONNU',
         'impact': 'volatilité brutale ±2-3 % sur indices' if vix_available else
                   'risque macro non quantifié — VIX indisponible',
         'proba': 'calendrier connu — chaque mois' if vix_available else 'INCONNUE — VIX non reporté',
         'fix': 'ne pas ouvrir de position la veille, laisser l\'IV se dégonfler après',
         'coverage': {'available': vix_available,
                      'status': 'MACRO_VIX_AVAILABLE' if vix_available else 'MACRO_VIX_UNAVAILABLE',
                      'read_only': True}},
        {'name': 'Résultats trimestriels', 'level': lvl(90 - min(dte, 90), 30, 60) if dte_available else 'INCONNU',
         'impact': 'gap + IV crush combinés' if dte_available else 'horizon vers les résultats non qualifié — DTE indisponible',
         'proba': '4× par an, dates connues' if dte_available else 'INCONNUE — DTE non reporté',
         'fix': 'règle du desk : réduire ou sortir AVANT la publication',
         'coverage': {'available': dte_available, 'status': 'DTE_AVAILABLE' if dte_available else 'DTE_UNAVAILABLE', 'read_only': True}},
        {'name': 'Expiration', 'level': lvl(60 - min(dte, 60), 20, 45) if dte_available else 'INCONNU',
         'impact': 'le thêta s\'emballe, le gamma devient loterie' if dte_available else 'horizon d’expiration non qualifié — DTE indisponible',
         'proba': 'mécanique en fin de vie' if dte_available else 'INCONNUE — DTE non reporté',
         'fix': 'ne jamais tenir les 2-3 dernières semaines d\'un contrat acheté',
         'coverage': {'available': dte_available, 'status': 'DTE_AVAILABLE' if dte_available else 'DTE_UNAVAILABLE', 'read_only': True}},
        {'name': 'Volatilité du sous-jacent',
         'level': (lvl((star or {}).get('em_pct'), 25, 40)
                   if isinstance((star or {}).get('em_pct'), (int, float))
                   and not isinstance((star or {}).get('em_pct'), bool)
                   and (star or {}).get('em_pct') > 0 else 'INCONNU'),
         'impact': ('move attendu ±%s%% — le chemin peut secouer avant la cible' % (star or {}).get('em_pct')
                    if isinstance((star or {}).get('em_pct'), (int, float))
                    and not isinstance((star or {}).get('em_pct'), bool)
                    and (star or {}).get('em_pct') > 0 else
                    'mouvement attendu non quantifié — donnée indisponible'),
         'proba': ('structurelle' if isinstance((star or {}).get('em_pct'), (int, float))
                   and not isinstance((star or {}).get('em_pct'), bool)
                   and (star or {}).get('em_pct') > 0 else 'INCONNUE — mouvement attendu non reporté'),
         'fix': 'delta modéré (0.45-0.60) + taille qui laisse dormir',
         'coverage': {'available': isinstance((star or {}).get('em_pct'), (int, float))
                                  and not isinstance((star or {}).get('em_pct'), bool)
                                  and (star or {}).get('em_pct') > 0,
                      'status': ('EXPECTED_MOVE_AVAILABLE' if isinstance((star or {}).get('em_pct'), (int, float))
                                 and not isinstance((star or {}).get('em_pct'), bool)
                                 and (star or {}).get('em_pct') > 0 else 'EXPECTED_MOVE_UNAVAILABLE'),
                      'read_only': True}},
    ]


# ─── ⑪ TIMELINE (échéancier concret) ───

def _timeline(star, plan, cal_items=None):
    if not star:
        return []
    raw_dte = star.get('dte')
    dte_available = isinstance(raw_dte, (int, float)) and not isinstance(raw_dte, bool) and raw_dte > 0 and float(raw_dte).is_integer()
    dte = int(raw_dte) if dte_available else None
    # Dates de séance US : horloge de New York, pas celle du serveur.
    today = datetime.now(ZoneInfo('America/New_York')).replace(tzinfo=None)

    def at(days):
        return (today + timedelta(days=days)).strftime('%d %b')

    tl = [
        {'when': 'Aujourd\'hui', 'date': at(0), 'icon': '📍', 'tone': 'info',
         'label': 'Point de départ', 'text': (('titre à $%s · ' % ('%g' % star['spot'])) if star.get('spot') else '')
         + 'prime $%s · plan écrit avant l\'entrée' % ('%d' % star['cost'] if star.get('cost') is not None else '—')},
    ]
    if dte is None:
        tl.append({'when': '—', 'date': '—', 'icon': '⚠', 'tone': 'warn',
                   'label': 'Timeline indisponible',
                   'text': 'DTE absent ou invalide — aucun checkpoint, résultat ou expiration n’est daté par défaut.',
                   'coverage': {'dte_available': False, 'status': 'TIMELINE_DTE_UNAVAILABLE', 'read_only': True}})
    else:
        tl.extend([
        {'when': 'J+%s' % max(5, dte // 6), 'date': at(max(5, dte // 6)), 'icon': '✅', 'tone': 'good',
         'label': 'Checkpoint de validation', 'text': 'la thèse doit commencer à payer — sinon réévaluer sans état d\'âme'},
        {'when': 'J+%s' % (dte // 3), 'date': at(dte // 3), 'icon': '🥇', 'tone': 'good',
         'label': 'Fenêtre TP1', 'text': 'zone statistique de prise de profit partielle (+50 %)'},
        {'when': '~J+%s' % round(dte * 0.55), 'date': at(round(dte * 0.55)), 'icon': '📢', 'tone': 'warn',
         'label': 'Fenêtre de résultats', 'text': 'réduire ou solder avant la publication — IV crush'},
        {'when': 'J+%s' % max(1, dte - 18), 'date': at(max(1, dte - 18)), 'icon': '⌛', 'tone': 'warn',
         'label': 'Sortie conseillée', 'text': 'dernière fenêtre propre avant l\'accélération du thêta'},
        {'when': 'J+%s' % dte, 'date': (star.get('exp') or '')[:10], 'icon': '🏁', 'tone': 'bad',
         'label': 'Expiration', 'text': 'ne rien tenir jusqu\'ici — un contrat acheté se solde avant'},
        ])
    # événements macro réels si le calendrier est chargé
    for it in (cal_items or [])[:4]:
        lab = it.get('title') or it.get('label') or it.get('event')
        if lab:
            tl.append({'when': it.get('when') or it.get('date') or '', 'date': it.get('date') or '',
                       'icon': '🗓️', 'tone': 'mut', 'label': 'Macro', 'text': lab})
    return tl


# ─── BUILD (point d'entrée) ───

def build(state, demo=False, cal_items=None):
    """Payload complet Options Lab. `state` = scan_state (dict partagé)."""
    board = state.get('options_board') or []
    detail = state.get('detail') or {}
    market = state.get('market_ctx') or {}
    sectors = state.get('sectors') or []
    strategy = state.get('strategy') or {}
    star = _star(board, detail)
    pick = next((p for p in (strategy.get('picks') or []) if p.get('symbol') == (star or {}).get('sym')),
                (strategy.get('picks') or [None])[0])
    overview = _overview(board, detail, market, demo)
    research = _research(star, board, detail, market, pick)
    tops = _tops(board, detail)
    return {
        'as_of': state.get('scan_ts_h') or state.get('updated'),
        'demo': bool(demo),
        'empty': not board,
        'overview': overview,
        'research': research,
        'analysis': _analysis(star, detail, market, sectors, overview),
        'plan': _plan(star, research or {}, pick),
        'viz': _viz(star, board, detail, pick),
        'strategies': _strategies(star, market),
        'tops': tops,
        'comparator': _comparator(star, pick, detail),
        'committee': _committee(board, detail, tops, star),
        'risks': _risks(star, market),
        'timeline': _timeline(star, None, cal_items),
    }


__all__ = ['build']
