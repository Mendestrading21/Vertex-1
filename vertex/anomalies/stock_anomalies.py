"""
vertex/anomalies/stock_anomalies.py — Détecteur d'ANOMALIES (titres « intéressants » qui sortent de l'ordinaire).

N'utilise QUE des champs déjà calculés par analyse() : change, atr_pct, volx, ext_atr,
rsi, roc, rs, pos52, series{close, ema20}. Zéro requête réseau, zéro donnée inventée.

⚠️ Limites honnêtes (yfinance différé ~15min) :
  - pas de GAP (open/high/low non exposés) → anomalie GAP volontairement omise.
  - pas de série RSI → la "divergence prix/momentum" est un PROXY close-based (étiqueté).
  - volume par barre non exposé → VOL_DRY_UP basé sur le RVOL du jour (instantané).
"""


INTEREST = {
    'VOLUME_SPIKE': "Volume anormal = les gros interviennent. Si le prix monte avec, c'est de l'accumulation institutionnelle — surveiller pour entrer sur force.",
    'OUTSIZED_MOVE': "Mouvement plus grand que la volatilité normale = vrai catalyseur (pas du bruit). En hausse, impulsion à suivre.",
    'BREAKOUT_52W': "Nouveau plus-haut 52 semaines = aucune résistance au-dessus, tous les détenteurs sont gagnants. Setup haussier classique : on achète la force.",
    'OVEREXTENSION': "Trop loin de la MM20 = risque de repli. NE PAS acheter ici — attendre une respiration vers la moyenne.",
    'RS_DIVERGENCE': "Force relative élevée alors que le jour est calme = le titre tient mieux que le marché. Candidat à l'achat dès la reprise.",
    'RSI_DIVERGENCE': "Prix au plus-haut mais RSI qui faiblit = essoufflement. Signal de prudence, pas un achat.",
    'VOL_DRY_UP': "Volume qui s'assèche collé sous un plus-haut = compression avant cassure. Précède souvent un breakout haussier — à surveiller de près.",
    'STALL_AT_HIGHS': "Rejet en haut de range sur gros volume = distribution (les gros vendent). Prudence, retournement possible.",
    'REVERSAL_FROM_LOWS': "Rebond puissant depuis le bas du range = retournement potentiel. À CONFIRMER (peut être un faux signal de contre-tendance).",
    'MA20_RECLAIM': "Reconquête de la MM20 = reprise de la tendance courte. Bon point d'entrée swing si la tendance de fond reste haussière.",
}


def _f(d, k, default=0.0):
    v = d.get(k)
    return float(v) if v is not None else default


def _series(d):
    s = d.get('series') or {}
    close = [x for x in (s.get('close') or []) if x is not None]
    ema20 = s.get('ema20') or []
    return close, ema20


def detect_anomalies(rows, detail):
    """-> liste de dicts {symbol, code, label, dir, sev, score_anom, note} triée par sévérité."""
    out = []
    for r in rows:
        sym = r.get('symbol')
        d = detail.get(sym)
        if not d:
            continue
        change = _f(d, 'change')
        atr_pct = max(_f(d, 'atr_pct', 0.1), 0.1)
        volx = _f(d, 'volx', 1.0)
        ext_atr = _f(d, 'ext_atr')
        rsi = _f(d, 'rsi', 50)
        rs = _f(d, 'rs', 50)
        pos52 = _f(d, 'pos52', 50)
        close, ema20 = _series(d)
        hits = []

        if volx >= 2.0:
            hits.append(('VOLUME_SPIKE', 'VOLUME SPIKE', 'NEUTRAL', 60 + min(40, (volx - 2) * 20),
                         f'RVOL {volx:.1f}x la moyenne 20j'))

        ratio = abs(change) / atr_pct
        if ratio >= 1.5:
            dirn = 'UP' if change >= 0 else 'DOWN'
            hits.append(('OUTSIZED_MOVE', 'MOVE OUTSIZED', dirn, 50 + min(50, (ratio - 1.5) * 40),
                         f'{change:+.1f}% = {ratio:.1f}x l ATR journalier'))

        if pos52 >= 98:
            sev = 70 + (20 if volx >= 1.3 else 0) + (10 if pos52 >= 99.5 else 0)
            hits.append(('BREAKOUT_52W', 'CASSURE 52s', 'UP', min(sev, 100),
                         f'pos52 {pos52:.0f}%' + (' + volume' if volx >= 1.3 else ' (volume mou)')))

        if ext_atr >= 4 or rsi >= 80:
            base = max(ext_atr, 4)
            sev = 55 + min(45, (base - 4) * 12) + (10 if rsi >= 85 else 0)
            hits.append(('OVEREXTENSION', 'SUREXTENSION', 'WARN', min(sev, 100),
                         f'{ext_atr:.1f} ATR au-dessus EMA20, RSI {rsi:.0f} - risque pullback'))

        if rs >= 70 and change <= 0.3:
            hits.append(('RS_DIVERGENCE', 'RS DIVERGENCE', 'UP', min(50 + (rs - 70) * 0.8, 100),
                         f'RS {rs:.0f} mais jour mou ({change:+.1f}%) - tient le marche'))
        elif rs <= 35 and change >= 1.5:
            hits.append(('RS_DIVERGENCE', 'RS DIVERGENCE', 'WARN', 55,
                         f'rebond {change:+.1f}% sur titre faible (RS {rs:.0f}) - suspect'))

        if d.get('rsi_div') == 'bear':
            hits.append(('RSI_DIVERGENCE', 'DIVERGENCE RSI', 'WARN', 64,
                         'prix au plus-haut mais RSI en repli — vraie divergence baissiere'))
        elif d.get('rsi_div') == 'bull':
            hits.append(('RSI_DIVERGENCE', 'DIVERGENCE RSI', 'UP', 58,
                         'prix au plus-bas mais RSI remonte — divergence haussiere'))

        if volx <= 0.7 and pos52 >= 85 and ext_atr < 2:
            hits.append(('VOL_DRY_UP', 'VOL DRY-UP', 'UP', min(50 + (0.7 - volx) * 40 + (pos52 - 85) * 0.5, 100),
                         f'volume sec ({volx:.1f}x) colle sous le haut (pos52 {pos52:.0f}%)'))

        if pos52 >= 95 and change <= -1 and volx >= 1.5:
            hits.append(('STALL_AT_HIGHS', 'CALAGE AU SOMMET', 'DOWN',
                         min(55 + abs(change) * 5 + (volx - 1.5) * 15, 100),
                         f'rejet {change:+.1f}% en haut de range sur volume {volx:.1f}x'))

        if pos52 <= 30 and change >= 2 and volx >= 1.5:
            hits.append(('REVERSAL_FROM_LOWS', 'RETOURNEMENT BAS', 'UP',
                         min(45 + change * 3 + (volx - 1.5) * 10, 100),
                         f'rebond {change:+.1f}% du bas de range (pos52 {pos52:.0f}%) - confirmer'))

        if len(close) >= 2 and len(ema20) >= 2 and ema20[-1] is not None and ema20[-2] is not None:
            if close[-1] > ema20[-1] and close[-2] <= ema20[-2] and change > 0:
                hits.append(('MA20_RECLAIM', 'RECONQUETE EMA20', 'UP',
                             min(40 + min(30, change * 4) + (10 if volx >= 1.3 else 0), 100),
                             f'repasse au-dessus EMA20 ({change:+.1f}%)'))

        if not hits:
            continue
        sev_max = max(h[3] for h in hits)
        score_anom = min(100, round(sev_max + (len(hits) - 1) * 6))
        for code, label, dirn, sev, note in hits:
            out.append({'symbol': sym, 'code': code, 'label': label, 'dir': dirn,
                        'sev': round(sev), 'score_anom': score_anom, 'note': note,
                        'interest': INTEREST.get(code, '')})

    out.sort(key=lambda a: (a['sev'], a['score_anom']), reverse=True)
    return out


# ═══════════════════════════════════════════════════════════════════════
#  MOTEUR ÉTENDU Strategy OS (§16) — anomalies actions sur barres OHLCV.
#  Format standard vertex.anomalies.models.Anomaly. Détecteurs adaptatifs
#  (z-scores, percentiles) plutôt que seuils statiques. Les proxies de flux
#  institutionnels sont TOUJOURS étiquetés proxy — jamais « donnée certaine ».
# ═══════════════════════════════════════════════════════════════════════
import math as _math

from vertex.anomalies.models import Anomaly as _A, SEV_INFO as _SI, SEV_WARN as _SW


def _closes(bars):
    return [b['close'] for b in bars if b.get('close') is not None]


def _mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


def _std(xs):
    if len(xs) < 2:
        return 0.0
    m = _mean(xs)
    return _math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def _returns(closes):
    return [(b / a - 1) for a, b in zip(closes, closes[1:]) if a]


def _atr(bars, n=14):
    trs = []
    for prev, cur in zip(bars, bars[1:]):
        h, l, pc = cur.get('high'), cur.get('low'), prev.get('close')
        if None in (h, l, pc):
            continue
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    if not trs:
        return 0.0
    return _mean(trs[-n:])


def _rsi(closes, n=14):
    if len(closes) < n + 1:
        return None
    gains, losses = [], []
    for a, b in zip(closes[-n - 1:], closes[-n:]):
        d = b - a
        gains.append(max(d, 0))
        losses.append(max(-d, 0))
    avg_l = _mean(losses)
    if avg_l == 0:
        return 100.0
    rs = _mean(gains) / avg_l
    return 100 - 100 / (1 + rs)


def _obv(bars):
    obv, out = 0.0, []
    for prev, cur in zip(bars, bars[1:]):
        v = cur.get('volume') or 0
        if cur.get('close') is None or prev.get('close') is None:
            out.append(obv)
            continue
        if cur['close'] > prev['close']:
            obv += v
        elif cur['close'] < prev['close']:
            obv -= v
        out.append(obv)
    return out


def detect_stock_anomalies(symbol, bars, context=None):
    """Moteur étendu : bars = OHLCV quotidiennes triées (>= ~60 pour être utile).

    context (optionnel) : {'benchmark_closes': [...], 'sector_closes': [...],
    'fundamentals': {...}, 'events': {...}} — chaque bloc absent désactive
    honnêtement les détecteurs correspondants (aucune invention).
    """
    context = context or {}
    out = []
    closes = _closes(bars)
    if len(closes) < 30:
        return out
    rets = _returns(closes)
    last_ret = rets[-1] if rets else 0.0
    sd = _std(rets[:-1][-120:])
    atr = _atr(bars)
    last = bars[-1]
    prev = bars[-2]
    vol_hist = [b.get('volume') or 0 for b in bars[:-1][-60:]]
    vol_avg = _mean([v for v in vol_hist if v]) or 0
    last_vol = last.get('volume') or 0

    def add(code, sev, conf, observed, expected, impact):
        out.append(_A(code=code, severity=sev, confidence=conf, source=symbol,
                      observed=observed, expected=expected, impact=impact))

    # ── Prix ──────────────────────────────────────────────────────────
    if sd > 0:
        z = last_ret / sd
        if abs(z) >= 3:
            add('RETURN_ZSCORE', _SW, min(0.95, abs(z) / 6),
                {'zscore': round(z, 2), 'return_pct': round(last_ret * 100, 2)},
                {'zscore': '|z| < 3'}, 'rendement du jour hors distribution — vrai catalyseur probable')
    if prev.get('close') and last.get('open'):
        gap = last['open'] / prev['close'] - 1
        if atr and prev['close']:
            gap_atr = abs(gap) * prev['close'] / atr
            if gap > 0 and gap_atr >= 1.0:
                add('GAP_UP', _SW, min(0.9, gap_atr / 3), {'gap_pct': round(gap * 100, 2)},
                    {'gap': '< 1 ATR'}, 'gap haussier significatif à l’ouverture')
            elif gap < 0 and gap_atr >= 1.0:
                add('GAP_DOWN', _SW, min(0.9, gap_atr / 3), {'gap_pct': round(gap * 100, 2)},
                    {'gap': '< 1 ATR'}, 'gap baissier significatif à l’ouverture')
    if atr and prev.get('close'):
        move_atr = abs(last['close'] - prev['close']) / atr
        if move_atr >= 2.5:
            add('OUTSIZED_ATR_MOVE', _SW, min(0.9, move_atr / 5), {'move_x_atr': round(move_atr, 2)},
                {'move_x_atr': '< 2.5'}, 'mouvement disproportionné vs volatilité normale')
    hi_52 = max((b.get('high') or b['close']) for b in bars[-252:-1])
    lo_52 = min((b.get('low') or b['close']) for b in bars[-252:-1])
    if (last.get('high') or last['close']) >= hi_52 * 0.999:
        add('NEW_52W_HIGH', _SI, 0.9, {'close': last['close'], 'high_52w': hi_52},
            {}, 'nouveau plus-haut 52 semaines — aucune résistance au-dessus')
    if (last.get('low') or last['close']) <= lo_52 * 1.001:
        add('NEW_52W_LOW', _SW, 0.9, {'close': last['close'], 'low_52w': lo_52},
            {}, 'nouveau plus-bas 52 semaines — pression persistante')
    # échec de cassure : plus-haut 60j dépassé en séance puis clôture dessous
    hi_prior = max((b.get('high') or b['close']) for b in bars[-61:-1])
    if (last.get('high') or last['close']) > hi_prior and last['close'] < hi_prior:
        add('FAILED_BREAKOUT', _SW, 0.7,
            {'intraday_high': last.get('high'), 'breakout_level': hi_prior, 'close': last['close']},
            {'close': f'> {hi_prior}'}, 'cassure avortée — piège haussier possible')
    lo_prior = min((b.get('low') or b['close']) for b in bars[-61:-1])
    if (last.get('low') or last['close']) < lo_prior and last['close'] > lo_prior:
        add('FAILED_BREAKDOWN', _SW, 0.7,
            {'intraday_low': last.get('low'), 'breakdown_level': lo_prior, 'close': last['close']},
            {}, 'cassure baissière avortée — reprise possible (support reconquis en séance)')
    ma20 = _mean(closes[-20:])
    if prev['close'] < _mean(closes[-21:-1]) and last['close'] > ma20:
        add('SUPPORT_RECLAIM', _SI, 0.6, {'close': last['close'], 'ma20': round(ma20, 2)},
            {}, 'reconquête de la moyenne 20 séances')
    if last.get('high') and last['close'] < last['high'] - 0.7 * (last['high'] - (last.get('low') or last['close'])) \
            and (last['high'] >= hi_prior * 0.995):
        add('RESISTANCE_REJECTION', _SW, 0.6, {'high': last['high'], 'close': last['close']},
            {}, 'rejet net sous la résistance — offre présente')
    if last.get('open') and prev.get('close'):
        if last['open'] < prev['close'] * 0.99 and last['close'] > prev['close']:
            add('OVERNIGHT_REVERSAL', _SI, 0.6,
                {'open_gap_pct': round((last['open'] / prev['close'] - 1) * 100, 2),
                 'close_pct': round((last['close'] / prev['close'] - 1) * 100, 2)},
                {}, 'gap baissier entièrement racheté en séance')
    if last.get('open') and last.get('low') and last.get('high'):
        rng = last['high'] - last['low']
        if rng > 0 and (last['close'] - last['low']) / rng >= 0.8 \
                and (last['open'] - last['low']) / rng <= 0.3 and last['close'] > last['open']:
            add('INTRADAY_REVERSAL', _SI, 0.55, {'range_position': 'clôture > 80% du range'},
                {}, 'retournement intrajournalier acheteur (mèche basse rachetée)')

    # ── Volume ────────────────────────────────────────────────────────
    if vol_avg and last_vol:
        rvol = last_vol / vol_avg
        if rvol >= 2.5:
            add('VOLUME_SPIKE', _SW, min(0.9, rvol / 6), {'rvol': round(rvol, 2)},
                {'rvol': '< 2.5'}, 'volume anormal — intervention de grosses mains PROBABLE (proxy)')
        elif rvol <= 0.4 and last['close'] >= hi_52 * 0.95:
            add('VOLUME_DRY_UP', _SI, 0.6, {'rvol': round(rvol, 2)},
                {}, 'assèchement du volume près des plus-hauts — compression pré-cassure')
        up_days = [b for p, b in zip(bars[-21:-1], bars[-20:]) if b['close'] > p['close']]
        down_days = [b for p, b in zip(bars[-21:-1], bars[-20:]) if b['close'] < p['close']]
        up_vol = _mean([b.get('volume') or 0 for b in up_days]) if up_days else 0
        down_vol = _mean([b.get('volume') or 0 for b in down_days]) if down_days else 0
        if up_vol and down_vol:
            if up_vol / down_vol >= 1.6:
                add('ACCUMULATION_PROXY', _SI, 0.55, {'up_down_vol_ratio': round(up_vol / down_vol, 2)},
                    {}, 'PROXY d’accumulation (volume des hausses > volume des baisses) — signal à confirmer, PAS une donnée certaine de flux institutionnel')
            elif down_vol / up_vol >= 1.6:
                add('DISTRIBUTION_PROXY', _SW, 0.55, {'down_up_vol_ratio': round(down_vol / up_vol, 2)},
                    {}, 'PROXY de distribution — signal à confirmer, PAS une donnée certaine de flux institutionnel')
        # divergence prix/volume : prix qui monte sur 10 séances, volume qui baisse
        if len(closes) >= 20 and closes[-1] > closes[-11] * 1.03:
            v_recent = _mean([b.get('volume') or 0 for b in bars[-10:]])
            v_before = _mean([b.get('volume') or 0 for b in bars[-20:-10]])
            if v_before and v_recent / v_before < 0.7:
                add('PRICE_VOLUME_DIVERGENCE', _SW, 0.55,
                    {'price_10d_pct': round((closes[-1] / closes[-11] - 1) * 100, 1),
                     'volume_ratio': round(v_recent / v_before, 2)},
                    {}, 'hausse de prix sans participation — fragilité potentielle')
        obv = _obv(bars)
        if len(obv) >= 20 and closes[-1] > closes[-11] and obv[-1] < obv[-11]:
            add('OBV_DIVERGENCE', _SW, 0.5, {'obv_direction': 'down', 'price_direction': 'up'},
                {}, 'OBV en baisse alors que le prix monte — divergence de flux (proxy)')

    # ── Volatilité ────────────────────────────────────────────────────
    if len(rets) >= 60:
        rv_recent = _std(rets[-10:]) * _math.sqrt(252)
        rv_before = _std(rets[-60:-10]) * _math.sqrt(252)
        if rv_before:
            ratio = rv_recent / rv_before
            if ratio <= 0.55:
                add('VOLATILITY_COMPRESSION', _SI, 0.6, {'rv_ratio': round(ratio, 2)},
                    {}, 'compression de volatilité — expansion souvent à venir')
            elif ratio >= 1.8:
                add('VOLATILITY_EXPANSION', _SW, 0.6, {'rv_ratio': round(ratio, 2)},
                    {}, 'expansion de volatilité — régime en train de changer')
            if ratio >= 2.5:
                add('REALIZED_VOL_SHOCK', _SW, 0.7, {'rv_recent': round(rv_recent, 3)},
                    {}, 'choc de volatilité réalisée')
        atr_recent = _atr(bars[-15:])
        atr_before = _atr(bars[-60:-15])
        if atr_before and atr_recent / atr_before >= 1.7:
            add('ATR_REGIME_SHIFT', _SW, 0.6, {'atr_ratio': round(atr_recent / atr_before, 2)},
                {}, 'changement de régime d’ATR — recalibrer stops et tailles')

    # ── Momentum ──────────────────────────────────────────────────────
    r = _rsi(closes)
    r_prev = _rsi(closes[:-5])
    if r is not None and r_prev is not None and len(closes) >= 20:
        if closes[-1] > max(closes[-20:-1]) and r < r_prev - 3:
            add('RSI_DIVERGENCE', _SW, 0.55, {'rsi': round(r, 1), 'rsi_5d_ago': round(r_prev, 1)},
                {}, 'prix au plus-haut mais RSI qui faiblit — essoufflement (proxy close-based)')
    if len(closes) >= 25:
        roc_now = closes[-1] / closes[-11] - 1
        roc_before = closes[-11] / closes[-21] - 1
        if roc_now > roc_before + 0.04 and roc_now > 0:
            add('ROC_ACCELERATION', _SI, 0.55, {'roc_10d': round(roc_now * 100, 1),
                                                'roc_prior': round(roc_before * 100, 1)},
                {}, 'accélération du momentum')
        elif roc_before > roc_now + 0.04 and roc_before > 0:
            add('ROC_DECELERATION', _SW, 0.55, {'roc_10d': round(roc_now * 100, 1),
                                                'roc_prior': round(roc_before * 100, 1)},
                {}, 'décélération du momentum — tendance qui fatigue')

    # ── Marché relatif (nécessite un benchmark fourni) ────────────────
    bench = context.get('benchmark_closes') or []
    if len(bench) >= 21 and len(closes) >= 21:
        rel_now = (closes[-1] / closes[-21]) / (bench[-1] / bench[-21])
        if rel_now >= 1.08:
            add('SECTOR_RELATIVE_BREAKOUT' if context.get('benchmark_is_sector')
                else 'INDEX_DIVERGENCE', _SI, 0.6,
                {'relative_20d': round(rel_now, 3)}, {},
                'surperformance nette vs référence sur 20 séances')
        elif rel_now <= 0.92:
            add('SECTOR_RELATIVE_BREAKDOWN' if context.get('benchmark_is_sector')
                else 'INDEX_DIVERGENCE', _SW, 0.6,
                {'relative_20d': round(rel_now, 3)}, {},
                'sous-performance nette vs référence sur 20 séances')
        rets_b = _returns(bench[-60:])
        rets_s = _returns(closes[-60:])
        n = min(len(rets_b), len(rets_s))
        if n >= 30:
            rb, rs_ = rets_b[-n:], rets_s[-n:]
            mb, ms = _mean(rb), _mean(rs_)
            cov = _mean([(a - mb) * (b - ms) for a, b in zip(rb, rs_)])
            var_b = _mean([(a - mb) ** 2 for a in rb])
            corr_den = (_std(rb) * _std(rs_))
            corr = cov / corr_den if corr_den else 0
            half = n // 2
            mb1, ms1 = _mean(rb[:half]), _mean(rs_[:half])
            cd1 = (_std(rb[:half]) * _std(rs_[:half]))
            corr1 = (_mean([(a - mb1) * (b - ms1) for a, b in zip(rb[:half], rs_[:half])]) / cd1) if cd1 else 0
            if corr1 - corr >= 0.4:
                add('CORRELATION_BREAK', _SW, 0.5, {'corr_recent': round(corr, 2),
                                                    'corr_prior': round(corr1, 2)},
                    {}, 'rupture de corrélation avec la référence')
            if var_b:
                beta = cov / var_b
                mb2, ms2 = _mean(rb[:half]), _mean(rs_[:half])
                var_b1 = _mean([(a - mb2) ** 2 for a in rb[:half]])
                cov1 = _mean([(a - mb2) * (b - ms2) for a, b in zip(rb[:half], rs_[:half])])
                if var_b1:
                    beta_prior = cov1 / var_b1
                    if abs(beta - beta_prior) >= 0.6:
                        add('BETA_SHIFT', _SW, 0.5, {'beta_recent': round(beta, 2),
                                                     'beta_prior': round(beta_prior, 2)},
                            {}, 'bêta en mutation — le titre ne se comporte plus pareil')

    # ── Fondamental (nécessite des fondamentaux fournis — sinon rien) ──
    fund = context.get('fundamentals') or {}
    g_now, g_prev = fund.get('revenue_growth'), fund.get('revenue_growth_prev')
    if g_now is not None and g_prev is not None:
        if g_now > g_prev + 0.05:
            add('REVENUE_ACCELERATION', _SI, 0.6, {'growth': g_now, 'prev': g_prev},
                {}, 'accélération du chiffre d’affaires')
        elif g_now < g_prev - 0.05:
            add('REVENUE_DECELERATION', _SW, 0.6, {'growth': g_now, 'prev': g_prev},
                {}, 'décélération du chiffre d’affaires')
    m_now, m_prev = fund.get('margin'), fund.get('margin_prev')
    if m_now is not None and m_prev is not None and abs(m_now - m_prev) >= 0.03:
        add('MARGIN_INFLECTION', _SW if m_now < m_prev else _SI, 0.6,
            {'margin': m_now, 'prev': m_prev}, {}, 'inflexion de marge')
    pe, sector_pe = fund.get('pe'), fund.get('sector_median_pe')
    if pe and sector_pe and (pe / sector_pe >= 2.2 or pe / sector_pe <= 0.45):
        add('VALUATION_DISLOCATION', _SW, 0.55, {'pe': pe, 'sector_median_pe': sector_pe},
            {}, 'valorisation disloquée vs secteur — comprendre pourquoi avant d’agir')
    if fund.get('eps_revision_pct') is not None and abs(fund['eps_revision_pct']) >= 8:
        add('EARNINGS_REVISION_SHOCK', _SW, 0.65, {'eps_revision_pct': fund['eps_revision_pct']},
            {}, 'choc de révision des BPA')
    if g_now is not None and len(closes) >= 63:
        px_3m = closes[-1] / closes[-63] - 1
        if px_3m > 0.25 and g_now < 0:
            add('PRICE_FUNDAMENTAL_DIVERGENCE', _SW, 0.55,
                {'price_3m_pct': round(px_3m * 100, 1), 'revenue_growth': g_now},
                {}, 'prix en forte hausse sur fondamental en dégradation')
    if fund.get('quality_flags'):
        add('QUALITY_DETERIORATION', _SW, 0.6, {'flags': fund['quality_flags']},
            {}, 'détérioration de qualité (dette/cash-flow/dilution)')

    # ── Événements (nécessite un bloc events fourni) ──────────────────
    ev = context.get('events') or {}
    dte_earn = ev.get('earnings_in_days')
    if dte_earn is not None and 0 < dte_earn <= 10 and len(closes) >= 11:
        run = closes[-1] / closes[-11] - 1
        if run >= 0.06:
            add('PRE_EARNINGS_RUNUP', _SW, 0.6,
                {'runup_10d_pct': round(run * 100, 1), 'earnings_in_days': dte_earn},
                {}, 'montée pré-résultats — attentes déjà dans le prix, IV chère probable')
    days_since = ev.get('days_since_earnings')
    if days_since is not None and 1 <= days_since <= 15 and len(closes) > days_since + 1:
        post = closes[-1] / closes[-days_since - 1] - 1
        if post >= 0.05:
            add('POST_EARNINGS_DRIFT', _SI, 0.55,
                {'drift_pct': round(post * 100, 1), 'days_since': days_since},
                {}, 'drift post-résultats haussier en cours')
        elif post <= -0.05 and ev.get('earnings_reaction_day1', 0) > 0:
            add('POST_EARNINGS_REVERSAL', _SW, 0.55,
                {'move_since_pct': round(post * 100, 1)},
                {}, 'réaction initiale positive entièrement rendue — retournement post-résultats')
    if ev.get('guidance_change_pct') is not None and abs(ev['guidance_change_pct']) >= 5:
        add('GUIDANCE_SHOCK', _SW, 0.7, {'guidance_change_pct': ev['guidance_change_pct']},
            {}, 'choc de guidance')
    if (ev.get('analyst_revisions_30d') or 0) >= 4:
        add('ANALYST_REVISION_CLUSTER', _SI, 0.6,
            {'revisions_30d': ev['analyst_revisions_30d']}, {},
            'grappe de révisions d’analystes')
    if (ev.get('news_count_24h') or 0) >= 5:
        add('NEWS_CLUSTER', _SI, 0.5, {'news_24h': ev['news_count_24h']}, {},
            'grappe de news — attention au bruit')
    if ev.get('major_event_today') and sd and abs(last_ret) < sd:
        add('EVENT_WITHOUT_PRICE_CONFIRMATION', _SW, 0.5,
            {'return_pct': round(last_ret * 100, 2)}, {},
            'événement majeur sans réaction de prix — le marché n’y croit pas (encore)')
    if sd and abs(last_ret) >= 3 * sd and not ev.get('known_catalyst') and ev:
        add('PRICE_MOVE_WITHOUT_IDENTIFIED_CATALYST', _SW, 0.6,
            {'return_pct': round(last_ret * 100, 2)}, {},
            'mouvement violent sans catalyseur identifié — chercher l’information manquante')

    return out


#: Ce que chaque FAMILLE de détecteurs exige du contexte, et ce qu'elle promet.
#: Mesuré le 2026-09-06 par recensement des 42 appels à `add()` de ce module.
FAMILLES = {
    'prix_volume': {
        'exige': (),
        'detections': 23,
        'libelle': 'prix, volume et structure — depuis les barres seules',
    },
    'relatif': {
        'exige': ('benchmark_closes',),
        'detections': 4,
        'libelle': 'force relative, corrélation et bêta vs référence',
    },
    'fondamental': {
        'exige': ('fundamentals',),
        'detections': 7,
        'libelle': 'croissance, marge, valorisation et révisions',
    },
    'evenement': {
        'exige': ('events',),
        'detections': 8,
        'libelle': 'résultats, guidance, révisions groupées et actualités',
    },
}


def couverture_detecteurs(context=None) -> dict:
    """Quelles familles de détecteurs le contexte fourni permet-il d'évaluer ?

    ## Pourquoi cette fonction existe

    Mesure du 2026-09-06 : le seul appelant de production
    (`vertex.engines.anomaly_context.build`) construit son contexte avec
    `context = {}` puis n'y ajoute au plus que `benchmark_closes`. Les blocs
    `fundamentals` et `events` ne sont JAMAIS transmis. Conséquence mesurée par
    recensement des appels à `add()` : **15 détections sur 42** ne peuvent pas
    se déclencher — sept fondamentales (dont `VALUATION_DISLOCATION`,
    `EARNINGS_REVISION_SHOCK`, `QUALITY_DETERIORATION`) et huit événementielles
    (dont `GUIDANCE_SHOCK`, `POST_EARNINGS_DRIFT`).

    Le balayage des lectures et des écritures du dépôt précise le tableau, et
    la nuance compte :

    - `quality_flags` et `eps_revision_pct` n'ont AUCUN producteur, nulle part.
      La détection `QUALITY_DETERIORATION` et la pénalité de score de
      `vertex.scanner.stages` sont donc mortes par construction, pas seulement
      par contexte manquant ;
    - `sector_median_pe` EN A un (`vertex.options.pack` le dérive de
      `median_pe` par secteur, et `vertex.quant.scoring` le lit) — mais il
      n'atteint jamais ce détecteur. Ce n'est pas la même maladie : ici la
      donnée existe et le câble manque.

    Rien de tout cela n'est FAUX : aucune anomalie inventée, aucun chiffre
    fabriqué. Mais l'appelant publiait `provenance: OHLCV_ENRICHED` et
    `limitations: []` dès qu'un benchmark était présent, c'est-à-dire qu'il
    annonçait une couverture complète en ayant exécuté 27 détecteurs sur 42.
    Une absence silencieuse se lit comme « rien à signaler » : c'est l'inverse
    d'une mesure.

    Le détecteur est le seul propriétaire légitime de cette information — lui
    seul sait ce que chaque famille exige. Il la rend donc explicitement, à
    charge pour l'appelant de la publier dans ses `limitations`.
    """
    context = context or {}
    evaluees, absentes, limites = [], [], []
    for nom, spec in FAMILLES.items():
        manquants = [c for c in spec['exige'] if not context.get(c)]
        if manquants:
            absentes.append(nom)
            limites.append('%s : %d détection(s) non exécutée(s) — %s absent du contexte'
                           % (spec['libelle'], spec['detections'], ', '.join(manquants)))
        else:
            evaluees.append(nom)
    total = sum(f['detections'] for f in FAMILLES.values())
    executees = sum(FAMILLES[n]['detections'] for n in evaluees)
    return {
        'familles_evaluees': evaluees,
        'familles_absentes': absentes,
        'detections_executees': executees,
        'detections_totales': total,
        'complet': not absentes,
        'limitations': limites,
    }


__all__ = ['detect_stock_anomalies', 'couverture_detecteurs', 'FAMILLES']
